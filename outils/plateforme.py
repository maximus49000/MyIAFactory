"""Plateforme (serveur dédié OVH) : machine à états en 7 étapes et point d'entrée `lancer.py plateforme`.

Étapes : lecture, os, ssh, durcissement, docker, images, licence. Aucune ne s'exécute avant que la précédente soit « fait ».
« Prêt » = étapes 1 à 6 ; la licence Unity est facultative. L'état est écrit dans `plateforme.json` à chaque étape, sans
aucun secret (clés OVH, licence) : tout texte écrit ou affiché passe par `masquer`. Le client OVH et les fonctions SSH sont
injectables : les tests ne font aucun appel réel. Un OS non Ubuntu LTS n'est jamais effacé sans `--accord-reinstallation`.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import ovh_api
from campagne import pid_vivant
import plateforme_acces
import plateforme_ovh
import plateforme_ssh
from ovh_api import ErreurOvh
from plateforme_acces import ErreurAcces
from plateforme_ovh import ErreurAccord, ErreurCleSsh
from plateforme_ssh import ErreurSsh

ETAPES = ("lecture", "os", "ssh", "durcissement", "docker", "images", "licence")
LIBELLES = {
    "lecture": "Lecture du serveur chez OVH", "os": "Système Ubuntu LTS installé", "ssh": "Accès SSH par clé dédiée",
    "durcissement": "Durcissement (clé seule, pare-feu)", "docker": "Docker installé", "images": "Images Unity, Android et agent",
    "licence": "Licence Unity (facultative)",
}
CACHE = "plateforme.json"
VERROU = "plateforme.lock"
UTILISATEUR = "ubuntu"
NOM_CLE_OVH = "myiafactory-plateforme"
BUDGET_REINSTALLATION_S = 40 * 60
PAS_TACHE_S = 30
RACINE_SERVEUR = Path(__file__).resolve().parent.parent / "serveur_ovh"
SCRIPT_DISTANT = "/tmp/myiafactory_mise_en_place.sh"
DOSSIER_DISTANT = "$HOME/myiafactory/serveur_ovh"
DELAIS_ETAPE_S = {"durcissement": 900, "docker": 1200, "images": 3600, "etat": 120, "licence": 600}
CHANGEMENT_CLE = "HOST IDENTIFICATION HAS CHANGED"
ERREURS = (ErreurOvh, ErreurSsh, ErreurAcces, ErreurCleSsh, ErreurAccord, ValueError, RuntimeError, OSError,
           subprocess.SubprocessError)


def calculer_etat(rapports):
    """Mise en forme des rapports par étape ; `pret` = étapes 1 à 6 faites (la licence ne compte pas)."""
    etapes = []
    for id_ in ETAPES:
        r = rapports.get(id_) or {}
        etapes.append({"id": id_, "libelle": LIBELLES[id_], "statut": r.get("statut", "a_faire"),
                       "detail": r.get("detail", ""), "geste": r.get("geste", "")})
    pret = all(e["statut"] == "fait" for e in etapes[:6])
    return {"etapes": etapes, "pret": pret, "pret_sans_unity": pret}


def _rapport(statut, detail="", geste=""):
    return {"statut": statut, "detail": detail, "geste": geste}


def _lire_cache(dossier):
    try:
        d = json.loads((Path(dossier) / CACHE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


class _Contexte:
    def __init__(self, dossier, accord, client, ssh, dormir):
        self.dossier, self.accord, self.client, self.ssh, self.dormir = Path(dossier), accord is True, client, ssh, dormir
        self.cache = _lire_cache(dossier)
        self.rapports = {k: v for k, v in (self.cache.get("rapports") or {}).items() if k in ETAPES and isinstance(v, dict)}
        self.acces, self.secrets, self.srv = None, [], {}
        self.ip, self.cle, self.pub = None, None, None
        self.restant_s, self.script_envoye, self.persister, self.reinstalle = 0, False, True, False

    @property
    def hote(self):
        return f"{UTILISATEUR}@{self.ip}"

    def preparer_secrets(self):
        """Charge ovh.json et réunit les secrets à masquer ; renvoie l'ErreurAcces éventuelle."""
        erreur = None
        try:
            self.acces = plateforme_acces.charger_ovh(self.dossier)
            self.secrets = [self.acces["cle_app"], self.acces["secret"], self.acces["consommateur"]]
        except ErreurAcces as e:
            self.acces, erreur = None, e
        licence = plateforme_acces.chemin_licence(self.dossier)
        if licence:
            try:
                self.secrets += plateforme_acces.secrets_licence(licence.read_bytes().decode("utf-8", errors="replace"))
            except OSError:
                pass
        return erreur

    def masquer(self, texte):
        return plateforme_acces.masquer(str(texte), self.secrets)

    def masquer_arbre(self, v):
        """Masque chaque texte AVANT la sérialisation JSON (la licence multi-ligne y serait échappée)."""
        if isinstance(v, str):
            return self.masquer(v)
        if isinstance(v, list):
            return [self.masquer_arbre(x) for x in v]
        return {k: self.masquer_arbre(x) for k, x in v.items()} if isinstance(v, dict) else v

    def ecrire(self, extra=None, strict=False):
        """Écrit le cache (jamais de secret) ; renvoie l'état calculé.

        `strict` : une écriture impossible lève OSError (utilisé quand perdre l'écriture exposerait à une double
        réinstallation) ; sinon l'échec est ignoré. `persister` à False (vérification) : rien n'est écrit.
        """
        etat = self.masquer_arbre(calculer_etat(self.rapports))
        etat.update(self.masquer_arbre(extra or {}))
        if self.persister:
            donnees = self.masquer_arbre({"rapports": self.rapports, "etat": etat, "ip": self.ip,
                                          "tache": self.cache.get("tache"), "demande": self.cache.get("demande")})
            texte = self.masquer(json.dumps(donnees, ensure_ascii=False, indent=2))
            try:
                self.dossier.mkdir(parents=True, exist_ok=True)
                (self.dossier / CACHE).write_text(texte, encoding="utf-8")
            except OSError:
                if strict:
                    raise
        return json.loads(self.masquer(json.dumps(etat, ensure_ascii=False)))

    def client_ovh(self):
        if self.client is None:
            a = self.acces
            self.client = ovh_api.ClientOvh(a["point"], a["cle_app"], a["secret"], a["consommateur"])
        return self.client


def _est_ubuntu_lts(os_):
    m = re.match(r"ubuntu(\d{2})(\d{2})", (os_ or "").lower())
    return bool(m and int(m.group(1)) % 2 == 0 and m.group(2) == "04")


def _etape_lecture(c):
    c.srv = plateforme_ovh.lire_serveur(c.client_ovh(), c.acces["serveur"])
    c.ip = c.srv.get("ip") or c.cache.get("ip")
    if not c.ip:
        return _rapport("bloque", "OVH ne donne pas d'adresse pour ce serveur.",
                        "Vérifiez le nom du serveur dans ovh.json et l'espace client OVH.")
    return _rapport("fait", f"Serveur {c.acces['serveur']} lu (système : {c.srv.get('os') or 'aucun'}).")


def _transitoire(e):
    return e.code == 0 or e.code == 429 or e.code >= 500


def _attendre_tache(c, id_tache):
    """Attend la fin de la tâche OVH (40 min au plus) ; renvoie un rapport bloquant, ou None si elle est finie.

    Une erreur OVH passagère (5xx, délai) est réessayée dans le budget. L'état « en_cours » est écrit avant l'attente.
    """
    c.rapports["os"] = _rapport("en_cours", f"Réinstallation OVH en cours, tâche {id_tache}.")
    c.ecrire()
    ecoule = 0
    while True:
        try:
            etat = plateforme_ovh.etat_tache(c.client, c.acces["serveur"], id_tache)
        except ErreurOvh as e:
            if not _transitoire(e):
                raise
            etat = "en_cours"
        if etat == "fini":
            c.cache["tache"], c.cache["demande"], c.restant_s = None, None, BUDGET_REINSTALLATION_S - ecoule
            return None
        if etat == "echec":                        # définitif : rien ne tourne plus, une nouvelle demande reste possible
            c.cache["tache"], c.cache["demande"] = None, None
            return _rapport("bloque", "La tâche de réinstallation OVH a échoué.",
                            "Ouvrez l'espace client OVH (Bare Metal Cloud > serveur > Tâches), lisez l'erreur, puis relancez.")
        if ecoule >= BUDGET_REINSTALLATION_S:      # la tâche reste notée : une relance l'attend sans réinstaller
            return _rapport("bloque", f"La réinstallation (tâche {id_tache}) n'est pas terminée après 40 minutes.",
                            "Surveillez la tâche dans l'espace client OVH, puis relancez quand elle est terminée.")
        c.dormir(PAS_TACHE_S)
        ecoule += PAS_TACHE_S


def _demande_incertaine(detail):
    return _rapport("bloque", detail, "Vérifiez les tâches du serveur dans l'espace client OVH (Bare Metal Cloud > serveur > "
                    "Tâches) : ne relancez pas la réinstallation tant qu'une tâche d'installation y apparaît.")


def _reinstaller(c):
    modele = plateforme_ovh.choisir_ubuntu_lts(plateforme_ovh.modeles_os(c.client, c.acces["serveur"]))
    c.cle, c.pub = c.ssh.generer_cle(c.dossier)     # la clé doit être chez OVH avant l'installation qui l'injecte
    plateforme_ovh.enregistrer_cle_ssh(c.client, NOM_CLE_OVH, c.pub)
    c.reinstalle = True
    c.cache["demande"] = True                       # noté AVANT la requête : si la suite se perd, pas de seconde réinstallation
    try:
        c.ecrire(strict=True)
    except OSError:
        c.cache["demande"] = None
        return _rapport("bloque", "Écriture de plateforme.json impossible : réinstallation non lancée.",
                        f"Vérifiez les droits d'écriture sur {c.dossier}, puis relancez.")
    try:
        c.cache["tache"] = plateforme_ovh.reinstaller(c.client, c.acces["serveur"], modele, NOM_CLE_OVH, c.accord)
    except (ErreurAccord, ValueError):              # échec net avant la requête
        c.cache["demande"] = None
        c.ecrire()
        raise
    except ErreurOvh as e:
        if 400 <= e.code < 500:                     # refus net d'OVH : rien n'a démarré
            c.cache["demande"] = None
            c.ecrire()
            raise
        return _demande_incertaine(f"La réinstallation a été demandée mais sa confirmation a échoué ({c.masquer(e)}).")
    try:
        c.ecrire(strict=True)
    except OSError:
        return _demande_incertaine(f"Réinstallation lancée (tâche {c.cache['tache']}) mais plateforme.json n'a pas pu "
                                   "l'enregistrer : relancer risquerait une seconde réinstallation.")
    return _attendre_tache(c, c.cache["tache"]) or _rapport("fait", f"{modele} installé par OVH.")


def _etape_os(c):
    os_ = c.srv.get("os") or ""
    if c.cache.get("tache") is not None:     # une réinstallation est déjà lancée : on l'attend, on n'en relance pas
        return _attendre_tache(c, c.cache["tache"]) or _rapport("fait", "Ubuntu LTS installé par OVH.")
    if _est_ubuntu_lts(os_):
        c.cache["demande"] = None
        return _rapport("fait", f"Ubuntu LTS déjà présent ({os_}) : rien à installer.")
    if c.cache.get("demande"):
        return _demande_incertaine("Une réinstallation a été demandée à OVH mais son identifiant de tâche est inconnu.")
    if not c.accord:
        etat = "vierge" if not os_ or os_.lower().startswith("none") else f"occupé par « {os_} », qui n'est pas Ubuntu LTS"
        return _rapport("bloque", f"Le serveur est {etat} ; l'installation d'Ubuntu LTS efface le disque. Rien n'a été effacé.",
                        "Si vous êtes d'accord pour effacer ce serveur, relancez avec --accord-reinstallation.")
    return _reinstaller(c)


def _etape_ssh(c):
    if c.cle is None:
        c.cle, c.pub = c.ssh.generer_cle(c.dossier)
    for _ in range(2):
        code, _sortie, erreur = c.ssh.executer(c.hote, "true", c.cle, delai=20)
        if code == 0:
            return _rapport("fait", f"Connexion SSH par clé dédiée à {c.hote} établie.")
        if CHANGEMENT_CLE not in erreur:
            break
        if not c.accord:
            return _rapport("bloque", "L'empreinte SSH du serveur a changé (réinstallation ?).",
                            "Si vous savez que le serveur a été réinstallé, relancez avec --accord-reinstallation "
                            "pour oublier l'ancienne empreinte.")
        c.ssh.oublier_hote(c.ip, True)
    c.rapports["ssh"] = _rapport("en_cours", "Attente du redémarrage du serveur (SSH pas encore disponible).")
    c.ecrire()
    if c.ssh.attendre_ssh(c.hote, c.cle, c.restant_s or 60):
        return _rapport("fait", f"Connexion SSH par clé dédiée à {c.hote} établie.")
    return _rapport("bloque", f"Le serveur {c.hote} ne répond pas en SSH avec la clé dédiée.",
                    f"Ajoutez la clé publique {c.cle}.pub à ~/.ssh/authorized_keys de {c.hote} "
                    "(ou réinstallez avec --accord-reinstallation), puis relancez.")


def _analyser(sortie):
    for ligne in reversed((sortie or "").strip().splitlines()):
        if ligne.lstrip().startswith("{"):
            try:
                d = json.loads(ligne)
                return d if isinstance(d, dict) else None
            except ValueError:
                return None
    return None


def _deposer(c, commande, texte):
    code, _o, erreur = c.ssh.executer(c.hote, commande, c.cle, stdin=texte, delai=60)
    return None if code == 0 else _rapport("bloque", f"Dépôt sur le serveur impossible : {c.masquer(erreur.strip()[:200])}",
                                           "Vérifiez la connexion SSH puis relancez.")


def _envoyer_script(c):
    if c.script_envoye:
        return None
    texte = (RACINE_SERVEUR / "mise_en_place.sh").read_text(encoding="utf-8")
    r = _deposer(c, f"cat > {SCRIPT_DISTANT} && chmod +x {SCRIPT_DISTANT}", texte)
    c.script_envoye = r is None
    return r


def _envoyer_images(c):
    """Dépose `serveur_ovh/images/**` là où le script les lit ($SERVEUR_OVH_DIR/images)."""
    for fichier in sorted(p for p in (RACINE_SERVEUR / "images").rglob("*") if p.is_file()):
        dest = f"{DOSSIER_DISTANT}/{shlex.quote(fichier.relative_to(RACINE_SERVEUR).as_posix())}"
        r = _deposer(c, f'mkdir -p "$(dirname "{dest}")" && cat > "{dest}"', fichier.read_text(encoding="utf-8"))
        if r:
            return r
    return None


def _lancer_etape(c, etape, stdin=None):
    """Lance une étape distante ; renvoie le rapport tiré de l'unique objet JSON du script."""
    r = _envoyer_script(c)
    if r:
        return r
    commande = f'SERVEUR_OVH_DIR="{DOSSIER_DISTANT}" bash {SCRIPT_DISTANT} --etape {etape}'
    code, sortie, erreur = c.ssh.executer(c.hote, commande, c.cle, stdin=stdin, delai=DELAIS_ETAPE_S.get(etape, 600))
    d = _analyser(sortie)
    if not d or d.get("statut") not in ("fait", "a_faire", "bloque"):
        return _rapport("bloque", f"Réponse illisible du serveur (code {code}) : {c.masquer(erreur.strip()[:200])}",
                        "Relancez ; si cela persiste, regardez la sortie du script sur le serveur.")
    geste = "" if d["statut"] == "fait" else "Lisez le détail, corrigez le point indiqué puis relancez."
    return _rapport(d["statut"], c.masquer(d.get("detail", "")), geste)


def _etape_durcissement(c):
    """Garde-fou anti-enfermement : seconde session par la clé dédiée, clé présente dans authorized_keys."""
    if c.ssh.executer(c.hote, "true", c.cle, delai=20)[0] != 0:
        return _rapport("bloque", "Seconde session SSH par la clé dédiée impossible : durcissement non lancé.",
                        "Rétablissez l'accès par la clé dédiée, puis relancez.")
    blob = " ".join((c.pub or "").split()[:2])
    if not blob or c.ssh.executer(c.hote, f"grep -qF -- {shlex.quote(blob)} ~/.ssh/authorized_keys", c.cle, delai=20)[0] != 0:
        return _rapport("bloque", "La clé dédiée n'est pas dans authorized_keys du serveur : durcissement non lancé.",
                        f"Ajoutez {c.cle}.pub à ~/.ssh/authorized_keys de {c.hote}, puis relancez.")
    return _lancer_etape(c, "durcissement")


def _etape_images(c):
    return _envoyer_script(c) or _envoyer_images(c) or _lancer_etape(c, "images")


def _etape_licence(c):
    """Sans unity.ulf : geste humain guidé (le serveur reste prêt sans Unity). Avec : envoyée en stdin à l'étape distante."""
    chemin = plateforme_acces.chemin_licence(c.dossier)
    if not chemin:
        return _rapport("a_faire", "Aucune licence Unity fournie : le serveur reste prêt, sans Unity.",
                        f"Activez Unity Personal dans Unity Hub sur votre PC, puis copiez le fichier de licence (en général "
                        f"C:\\ProgramData\\Unity\\Unity_lic.ulf) vers {c.dossier / 'unity.ulf'} et relancez. Avec le nouveau client "
                        "de licences Unity, ce fichier peut ne pas exister : il faut alors une licence Unity Pro/Plus à numéro de "
                        "série. L'activation manuelle (.alf) n'est pas prise en charge pour Unity Personal : "
                        "https://docs.unity3d.com/6000.6/Documentation/Manual/ManualActivationGuide.html (Unity 6000.6.7f1).")
    licence = chemin.read_bytes().decode("utf-8", errors="replace")   # octets : fins de ligne conservées, jamais en argument
    c.secrets += [x for x in plateforme_acces.secrets_licence(licence) if x not in c.secrets]   # octets exacts envoyés
    if len(licence.strip()) < 12:
        return _rapport("bloque", "Le fichier unity.ulf est vide ou trop court pour être une licence.", f"Recopiez la licence Unity dans {chemin}, puis relancez.")
    r = _lancer_etape(c, "licence", stdin=licence)
    if r["statut"] == "bloque":
        r["geste"] = "Vérifiez que unity.ulf est une licence valide pour Unity 6000.6.7f1 (détail ci-dessus), puis relancez."
    return r


ACTIONS = {"lecture": _etape_lecture, "os": _etape_os, "ssh": _etape_ssh, "durcissement": _etape_durcissement,
           "docker": lambda c: _lancer_etape(c, "docker"), "images": _etape_images, "licence": _etape_licence}


def _executer_etape(c, id_):
    try:
        return ACTIONS[id_](c)
    except ERREURS as e:
        geste = "Vérifiez ovh.json et l'accès à l'API OVH." if id_ == "lecture" else "Corrigez le point indiqué puis relancez."
        return _rapport("bloque", c.masquer(e) or type(e).__name__, geste)


def _preparer(dossier, accord, client, ssh, dormir, persister=True):
    c = _Contexte(dossier, accord, client, ssh or plateforme_ssh, dormir)
    c.persister = persister
    erreur = c.preparer_secrets()
    if erreur:
        c.rapports["lecture"] = _rapport("bloque", c.masquer(erreur), "Créez ou corrigez ovh.json comme indiqué.")
        return c, c.ecrire()
    return c, None


def _prendre_verrou(dossier, vivant):
    """Verrou pid dans le dossier : une seule installation à la fois ; celui d'un processus mort est repris."""
    chemin = Path(dossier) / VERROU
    Path(dossier).mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            with open(chemin, "x", encoding="utf-8") as f:
                f.write(json.dumps({"pid": os.getpid()}))
            return chemin
        except FileExistsError:
            try:
                autre = json.loads(chemin.read_text(encoding="utf-8")).get("pid")
            except (OSError, ValueError, AttributeError):
                autre = None
            if isinstance(autre, int) and autre != os.getpid() and vivant(autre):
                return None
            try:
                chemin.unlink()
            except OSError:
                return None
    return None


def installer(dossier=plateforme_acces.DOSSIER, accord_reinstallation=False, client=None, ssh=None, dormir=time.sleep,
              vivant=pid_vivant):
    """Enchaîne les étapes en reprenant là où la dernière exécution s'est arrêtée (une seule exécution à la fois)."""
    try:
        verrou = _prendre_verrou(dossier, vivant)
    except OSError:
        verrou = None
    if verrou is None:
        return calculer_etat({"lecture": _rapport("bloque", "Une installation est déjà en cours (ou le dossier est inaccessible).",
                                                  "Attendez la fin de l'autre exécution, puis relancez.")})
    try:
        return _installer(dossier, accord_reinstallation, client, ssh, dormir)
    finally:
        try:
            verrou.unlink()
        except OSError:
            pass


def _installer(dossier, accord_reinstallation, client, ssh, dormir):
    c, etat = _preparer(dossier, accord_reinstallation, client, ssh, dormir)
    if etat:
        return etat
    for i, id_ in enumerate(ETAPES):
        if c.rapports.get(id_, {}).get("statut") == "fait" and id_ not in ("lecture", "os"):
            if id_ == "ssh":
                c.cle, c.pub = c.ssh.generer_cle(c.dossier)
            continue
        pendant = c.cache.get("tache") is not None or bool(c.cache.get("demande"))
        r = _executer_etape(c, id_)
        c.rapports[id_] = r
        if id_ == "os" and (r["statut"] != "fait" or pendant or c.reinstalle):
            # Un changement de système est en cours ou vient d'avoir lieu : tout ce qui suit est à refaire.
            for suivant in ETAPES[2:]:
                c.rapports[suivant] = _rapport("a_faire", "À refaire : le système du serveur change.")
        c.ecrire()
        if r["statut"] == "bloque" or (r["statut"] == "a_faire" and id_ != "licence"):
            for suivant in ETAPES[i + 1:]:
                if c.rapports.get(suivant, {}).get("statut") != "fait":
                    c.rapports[suivant] = _rapport("a_faire", "En attente de l'étape précédente.")
            break
    return c.ecrire()


def verifier(dossier=plateforme_acces.DOSSIER, client=None, ssh=None, dormir=time.sleep):
    """Contrôle l'état réel sans rien modifier ni écrire (jamais de réinstallation) : lecture, système, SSH, étape `etat`."""
    c, etat = _preparer(dossier, False, client, ssh, dormir, persister=False)
    if etat:
        return etat
    c.cache, c.rapports, extra = {}, {}, {}
    for id_ in ("lecture", "os", "ssh"):
        c.rapports[id_] = _executer_etape(c, id_)
        if c.rapports[id_]["statut"] != "fait":
            break
    else:
        extra["serveur"] = _verifier_distant(c)
    return c.ecrire(extra)


def _verifier_distant(c):
    try:
        return _lancer_etape(c, "etat")
    except ERREURS as e:
        return _rapport("bloque", c.masquer(e), "Relancez.")


def main(argv):
    args = list(argv)
    if not args or args[0] not in ("etat", "installer", "verifier"):
        print("Usage : lancer.py plateforme <etat|installer|verifier> [--accord-reinstallation] [--dossier <d>]", file=sys.stderr)
        return 2
    commande, accord, dossier = args[0], False, plateforme_acces.DOSSIER
    reste = args[1:]
    while reste:
        a = reste.pop(0)
        if a == "--accord-reinstallation":
            accord = True
        elif a == "--dossier" and reste:
            dossier = Path(reste.pop(0))
        else:
            print(f"Argument inconnu : {a}", file=sys.stderr)
            return 2
    if commande == "etat":
        etat = _lire_cache(dossier).get("etat") or calculer_etat({})
    elif commande == "installer":
        etat = installer(dossier, accord)
    else:
        etat = verifier(dossier)
    c = _Contexte(dossier, False, None, None, time.sleep)
    c.preparer_secrets()
    print(c.masquer(json.dumps(c.masquer_arbre(etat), ensure_ascii=False, indent=2)))
    bloque = any(e["statut"] == "bloque" for e in etat["etapes"])
    return 1 if bloque or not etat["pret"] else 0
