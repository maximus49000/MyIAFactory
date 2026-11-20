"""Installation à la demande des capacités d'un serveur distant : aperçu en lecture seule, puis installation sur accord.

Le moteur travaille sur un serveur dont le système est déjà installé et joignable ; il ne touche jamais au système
d'exploitation. Chaque capacité manquante est installée par l'étape distante que le catalogue lui associe (script
`mise_en_place.sh`, déposé dans le dossier privé du serveur). Les capacités non installables ne sont jamais lancées.

Garanties : aucune écriture sans `accord is True` ; une seule installation à la fois (verrou pid) ; l'état réel est
relu par sonde au début et à la fin (jamais l'état en cache) ; une panne de réseau donne « inconnue », jamais
« absente » ; l'état `serveurs-etat.json` ne contient aucun secret. Tout passe par `ssh` (injectable).
"""
import hashlib
import io
import json
import math
import os
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import plateforme_acces
import plateforme_ssh
import serveur_etat
import plateforme
from plateforme import COMMANDE_DEPOT, DOSSIER_DISTANT, RACINE_SERVEUR, VARIABLE_DOSSIER, SCRIPT_DISTANT, pid_vivant
from serveur_capacites import CATALOGUE, bloquees, manquantes_pour
from serveur_modele import ecrire_atomique

ETAT = "serveurs-etat.json"
VERROU = "serveurs-installation.lock"
VERROU_JEUNE_S = 30
DELAI_DEFAUT_S = 600
DELAIS_ETAPE_S = {"docker": 1200, "durcissement": 900, "android_build": 1800, "android_emulateur": 1800, "emulateur_image": 900, "agent_image": 900, "unity_cli": 300}
LONGUEUR_MAX = 200
STATUTS_ETAPE = ("fait", "a_faire", "bloque")


class ErreurInstallation(Exception):
    """Refus d'installer (accès, accord, verrou) : message français et `geste` (ce que l'utilisateur peut faire)."""

    def __init__(self, message, geste=""):
        super().__init__(message)
        self.geste = geste


def _maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texte(valeur, serveur):
    """Texte sans secret (chemin de clé masqué), sur une ligne, tronqué."""
    brut = " ".join(str(valeur or "").split())
    return plateforme_acces.masquer(brut, [str(getattr(serveur, "cle", "") or "")])[:LONGUEUR_MAX]


# ---------------------------------------------------------------- état

def lire_etat(dossier=plateforme_acces.DOSSIER):
    """Contenu de `serveurs-etat.json` ; dictionnaire vide si absent, abîmé ou de forme inattendue. Jamais d'exception."""
    try:
        donnees = json.loads((Path(dossier) / ETAT).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in donnees.items() if isinstance(v, dict)} if isinstance(donnees, dict) else {}


INTERROMPUE = "Installation interrompue : relancez ou vérifiez."
_VERROU_PROCESSUS = threading.Lock()        # une seule installation à la fois dans CE processus (le fichier ne suffit pas)


def installation_en_cours(dossier=plateforme_acces.DOSSIER, vivant=pid_vivant):
    """Une installation tourne-t-elle ? Verrou tenu par un processus vivant (ou par ce processus, tant que son verrou
    interne est pris), ou fichier verrou vide récent."""
    chemin = Path(dossier) / VERROU
    return chemin.exists() and _verrou_tenu(chemin, vivant, _VERROU_PROCESSUS.locked())


def _degrader(caps):
    """Copie de `caps` où chaque capacité restée « en_cours » est devenue « inconnue » (installation interrompue)."""
    return {i: (_entree("inconnue", INTERROMPUE, "Relancez l'installation ou lancez un aperçu pour constater l'état.")
                if isinstance(c, dict) and c.get("statut") == "en_cours" else c) for i, c in caps.items()}


def lire_etat_vivant(dossier=plateforme_acces.DOSSIER, vivant=pid_vivant):
    """Comme `lire_etat`, mais sans installation vivante les « en_cours » périmés (fenêtre fermée en cours de route)
    sont présentés « inconnue ». Ne modifie aucun fichier. Jamais d'exception."""
    etat = lire_etat(dossier)
    try:
        if installation_en_cours(dossier, vivant):
            return etat
    except Exception:
        pass
    sortie = {}
    for sid, e in etat.items():
        caps = e.get("capacites")
        inst = e.get("installation")
        sortie[sid] = {**e,
                       "capacites": _degrader(caps) if isinstance(caps, dict) else caps,
                       "installation": {**inst, "en_cours": False} if isinstance(inst, dict) else inst}
    return sortie


_GARDER = object()


def _charge_valide(charge):
    """La charge lue par la sonde si elle a la forme attendue (nombres finis), sinon None."""
    if not isinstance(charge, dict):
        return None
    sortie = {}
    for cle in ("charge_par_coeur", "memoire_libre_ratio", "conteneurs_outils"):
        v = charge.get(cle)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        try:
            if not math.isfinite(v):
                return None
        except OverflowError:       # entier démesuré
            return None
        sortie[cle] = v
    return sortie


def _ecrire_etat(dossier, serveur_id, capacites, en_cours, debut, charge=_GARDER, fusionner=True):
    """Réécrit l'entrée d'un serveur ; sa `charge` (lue par la sonde) est conservée sauf si `charge` est donnée.

    `capacites` ne dit que ce qui vient d'être constaté ou fait : par défaut elles sont fusionnées dans celles déjà connues
    (les autres capacités, et les raisons de blocage, ne sont jamais perdues). `fusionner=False` : une sonde complète."""
    tout = lire_etat(dossier)
    avant = tout.get(serveur_id, {}).get("capacites")
    if fusionner and isinstance(avant, dict):
        capacites = {**avant, **capacites}
    entree = {"capacites": capacites, "installation": {"en_cours": en_cours, "debut": debut}}
    ancienne = tout.get(serveur_id, {}).get("charge") if charge is _GARDER else charge
    if ancienne is not None:
        entree["charge"] = ancienne
    tout[serveur_id] = entree
    Path(dossier).mkdir(parents=True, exist_ok=True)
    ecrire_atomique(Path(dossier) / ETAT, json.dumps(tout, ensure_ascii=False, indent=2) + "\n")


def _entree(statut, detail="", geste=""):
    return {"statut": statut, "detail": detail, "geste": geste, "maj": _maintenant()}


_DETAIL_SONDE = {"presente": "Constatée par la sonde.", "absente": "Absente (constatée par la sonde).",
                 "inconnue": "Serveur injoignable ou état illisible."}


def enregistrer_sonde(dossier, serveur, etat, vivant=pid_vivant, charge=None, horloge=time.time, sous_verrou=None,
                      sur_echec=None):
    """Écrit le résultat d'une sonde (`{capacité: statut}`) dans l'état, sous les mêmes verrous qu'une installation.

    `ErreurInstallation` (« déjà en cours ») si une installation tient le verrou. Une capacité non installable restée
    « bloque » garde son entrée (et sa raison) tant que la sonde ne la constate pas présente.
    `charge` (lecture de `serveur_etat.charge`, faite par l'appelant hors verrou) est rangée dans l'état ; absente ou
    illisible, aucune charge n'est conservée (une charge périmée induirait en erreur).
    `sur_echec()` est appelée, verrou toujours tenu, si `sous_verrou` ou l'écriture échoue (retour arrière de l'appelant)."""
    deja = ErreurInstallation("Une installation est déjà en cours sur ce poste.", "Attendez sa fin puis relancez.")
    if not _VERROU_PROCESSUS.acquire(blocking=False):
        raise deja
    try:
        try:
            verrou = _prendre_verrou(dossier, vivant)
        except OSError as e:
            raise ErreurInstallation(f"Dossier de l'installation inutilisable : {_texte(e, serveur)}",
                                     "Vérifiez les droits d'écriture du dossier de configuration.") from e
        if verrou is None:
            raise deja
        try:
            try:
                if sous_verrou is not None:
                    sous_verrou()       # exécuté verrou pris : aucune installation ne peut démarrer entre cette action et l'écriture
                _enregistrer(dossier, serveur, etat, charge, horloge)
            except BaseException:
                if sur_echec is not None:
                    sur_echec()         # encore sous le verrou : personne ne peut écrire entre l'échec et le retour arrière
                raise
        finally:
            try:
                verrou.unlink()
            except OSError:
                pass
    finally:
        _VERROU_PROCESSUS.release()


def _enregistrer(dossier, serveur, etat, charge, horloge):
    """Écrit l'état constaté par une sonde (appelé verrou pris)."""
    avant = lire_etat(dossier).get(serveur.id, {})
    anciennes = avant.get("capacites") if isinstance(avant.get("capacites"), dict) else {}
    caps = {}
    for i, s in etat.items():
        ancienne = anciennes.get(i)
        if (i in CATALOGUE and not CATALOGUE[i].installable and s != "presente"
                and isinstance(ancienne, dict) and ancienne.get("statut") == "bloque"):
            caps[i] = ancienne
        else:
            caps[i] = _entree(s, _DETAIL_SONDE.get(s, ""))
    inst = avant.get("installation")
    debut = inst.get("debut", "") if isinstance(inst, dict) and isinstance(inst.get("debut"), str) else ""
    valide = _charge_valide(charge)
    if valide is not None:
        valide["maj"] = horloge()           # secondes epoch : une charge trop vieille est ignorée à la lecture
    _ecrire_etat(dossier, serveur.id, caps, False, debut, charge=valide, fusionner=False)


# ---------------------------------------------------------------- aperçu

def apercu(serveur, actions, ssh=plateforme_ssh, dossier=plateforme_acces.DOSSIER):
    """Ce qu'il faudrait installer pour `actions`, sans rien modifier (lecture SSH seulement, aucun fichier écrit).

    `taille_go` et `duree_min` ne comptent que les capacités installables. Serveur injoignable ou état illisible :
    `{"erreur", "etat"}` avec toutes les capacités « inconnue », et rien n'est calculé comme manquant."""
    inconnu = {i: serveur_etat.INCONNUE for i in CATALOGUE}
    try:
        requises = manquantes_pour(actions, set())      # fermeture des actions
    except ValueError as e:
        raise ErreurInstallation(str(e), "Choisissez des actions connues.") from e
    refus = serveur_etat.refus_acces(serveur, ssh=ssh)
    if refus:
        return {"erreur": _texte(refus, serveur), "etat": inconnu}
    etat = serveur_etat.sonder(serveur, ssh=ssh)
    illisibles = [i for i in requises if etat.get(i) != serveur_etat.PRESENTE and etat.get(i) != serveur_etat.ABSENTE]
    if illisibles:
        return {"erreur": "État du serveur illisible ou serveur injoignable : " + ", ".join(illisibles) + ".",
                "etat": {**inconnu, **etat}}
    installees = {i for i, s in etat.items() if s == serveur_etat.PRESENTE}
    perimees = _perimees(serveur, ssh, installees, set(requises))
    installees -= perimees
    etat = {**etat, **{i: serveur_etat.ABSENTE for i in perimees}}      # une capacité périmée n'est pas « présente » (raison : « À mettre à jour »)
    manquantes = manquantes_pour(actions, installees)
    installables = [CATALOGUE[i] for i in manquantes if CATALOGUE[i].installable]
    return {"manquantes": manquantes,
            "taille_go": float(sum(c.taille_go for c in installables)),
            "duree_min": int(sum(c.duree_min for c in installables)),
            "bloquees": bloquees(manquantes),
            "perimees": sorted(perimees),
            "etat": etat}


# ---------------------------------------------------------------- verrou

def _verrou_tenu(chemin, vivant, soi_tenu=False):
    """Pid d'un autre processus vivant, ou fichier vide/illisible trop récent pour être périmé (il est créé puis rempli).
    Notre propre pid : tenu seulement si `soi_tenu` (une installation de ce processus est en cours)."""
    try:
        autre = json.loads(chemin.read_text(encoding="utf-8")).get("pid")
    except (OSError, ValueError, AttributeError):
        autre = None
    if isinstance(autre, int):
        return soi_tenu if autre == os.getpid() else bool(vivant(autre))
    try:
        return time.time() - chemin.stat().st_mtime < VERROU_JEUNE_S
    except OSError:
        return False


def _prendre_verrou(dossier, vivant):
    chemin = Path(dossier) / VERROU
    Path(dossier).mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            with open(chemin, "x", encoding="utf-8") as f:
                f.write(json.dumps({"pid": os.getpid()}))
            return chemin
        except FileExistsError:
            if _verrou_tenu(chemin, vivant):
                return None
            try:
                chemin.unlink()
            except OSError:
                return None
    return None


def plateforme_en_cours(dossier=plateforme_acces.DOSSIER, vivant=pid_vivant):
    """L'installation de la plateforme (autre flux, verrou `plateforme.lock`) tourne-t-elle ? Un verrou à notre propre
    pid compte : le bureau lance cette installation dans un fil de ce même processus."""
    chemin = Path(dossier) / plateforme.VERROU
    return chemin.exists() and _verrou_tenu(chemin, vivant, True)


# ---------------------------------------------------------------- étapes distantes

def _analyser(sortie):
    for ligne in reversed((sortie or "").strip().splitlines()):
        if ligne.lstrip().startswith("{"):
            try:
                d = json.loads(ligne)
                return d if isinstance(d, dict) else None
            except ValueError:
                return None
    return None


# Fichiers du dossier des scripts du dépôt dont une étape a besoin sur le serveur (chemins relatifs à ce dossier, noms fixes). Le lanceur de
# tâches ajoutera lancer_emulation.sh à son propre dépôt.
FICHIERS_ETAPE = {"emulateur_image": ("images/emulateur/Dockerfile", "images/emulateur/entree-tache.sh", "taches/pont.sh"),
                  # enregistrer_jeton.sh est lancé à la main par le Directeur : déposé avec l'étape, hors de l'empreinte de l'image
                  "agent_image": ("images/agent/Dockerfile", "images/agent/entree-agent.py", "images/agent/pont",
                                  "taches/enregistrer_jeton.sh")}
# Fichiers du contexte de construction de l'image, dans l'ordre de l'empreinte (par défaut : tous ceux de l'étape).
EMPREINTE_FICHIERS = {**FICHIERS_ETAPE,
                      "agent_image": ("images/agent/Dockerfile", "images/agent/entree-agent.py", "images/agent/pont")}


# Dépôt par une archive tar lue sur l'entrée standard : extraite dans un dossier temporaire privé (umask 077, mktemp -d) ;
# RIEN n'est déplacé tant que tar n'a pas réussi ET que chacun des fichiers attendus n'est pas là et non vide (un flux coupé
# à une frontière de membre ne laisse donc rien de mis à jour) ; chaque fichier est ensuite déplacé (mv -f) à sa place ; le
# dossier temporaire est supprimé quoi qu'il arrive.
def commande_depot(etape):
    fichiers = " ".join(f'"{rel}"' for rel in FICHIERS_ETAPE[etape])         # noms fixes du dépôt, jamais une entrée externe
    return (
        'install -d -m 700 "$HOME/myiafactory" && umask 077 && d=$(mktemp -d "$HOME/myiafactory/.depot.XXXXXX") || exit 1; '
        f'dest="{DOSSIER_DISTANT}"; r=1; '
        'if tar -x --no-same-owner -C "$d" -f -; then r=0; '
        f'for f in {fichiers}; do [ -f "$d/$f" ] && [ -s "$d/$f" ] || r=1; done; '
        'if [ "$r" = 0 ]; then '
        f'for f in {fichiers}; do '
        'install -d -m 700 "$dest/$(dirname "$f")" && mv -f "$d/$f" "$dest/$f" || r=1; done; fi; fi; '
        'rm -rf "$d"; exit $r')


COMMANDE_DEPOT_FICHIERS = commande_depot("emulateur_image")


def empreinte_etape(etape):
    """Empreinte de l'image de l'étape, identique à celle que l'étape écrit dans son marqueur sur le serveur : versions
    épinglées + 16 premiers hexa du SHA-256 des fichiers déposés, concaténés dans l'ordre de FICHIERS_ETAPE, mêmes octets."""
    versions = json.loads((RACINE_SERVEUR / "versions.json").read_text(encoding="utf-8"))
    h = hashlib.sha256()
    for rel in EMPREINTE_FICHIERS[etape]:
        h.update((RACINE_SERVEUR / rel).read_bytes())
    if etape == "agent_image":                       # mêmes champs, même ordre que EMPREINTE_AGENT du script
        versions_image = f"ubuntu={versions['base_ubuntu']};node={versions['node']};claude_code={versions['claude_code']}"
    else:
        versions_image = f"ubuntu={versions['base_ubuntu']};jdk=17"
    return f"{versions_image};fichiers={h.hexdigest()[:16]}"


# Capacités dont la sonde (lecture seule, existence du marqueur) ne dit pas si ce qui est installé est à jour : le marqueur
# contient l'empreinte, que le moteur compare à l'empreinte locale par une lecture SSH de ce seul fichier (`cat`). Choix : la
# sonde du catalogue reste une pure existence de fichier (le validateur interdit d'y passer une valeur du poste) ; la
# péremption est une lecture de plus, faite par le moteur seulement pour les capacités demandées.
MARQUEURS = {"emulateur-image": ("emulateur_image", '$HOME/.myiafactory/emulateur-image.version'),
             "agent": ("agent_image", '$HOME/.myiafactory/agent-image.version')}


def _perimees(serveur, ssh, presentes, requises):
    """Capacités présentes (sonde) dont le marqueur ne porte pas l'empreinte locale : à refaire. Un serveur injoignable pendant la
    lecture (255/124) laisse la capacité telle que la sonde l'a vue ; un fichier local illisible la rend périmée (l'étape dira pourquoi)."""
    perimees = set()
    for i, (etape, marqueur) in MARQUEURS.items():
        if i not in presentes or i not in requises:
            continue
        try:
            attendue = empreinte_etape(etape)
        except (OSError, ValueError, KeyError):
            perimees.add(i)
            continue
        code, sortie, _e = ssh.executer(serveur_etat.cible(serveur), f'head -c 256 "{marqueur}" 2>/dev/null', serveur.cle, delai=20)
        if code in (255, 124):
            continue
        if code != 0 or (sortie or "").strip() != attendue:
            perimees.add(i)
    return perimees


def _archive_fichiers(etape):
    """Archive tar (en mémoire) des fichiers de l'étape : fichiers ordinaires seulement, noms fixes, propriétaire root,
    droits 0644 (0755 pour un .sh), octets lus tels quels (fins de ligne LF du dépôt)."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for rel in FICHIERS_ETAPE[etape]:
            chemin = RACINE_SERVEUR / rel
            if chemin.is_symlink() or not chemin.is_file():
                raise FileNotFoundError(f"Fichier du dépôt introuvable ou non ordinaire : {rel}")
            donnees = chemin.read_bytes()
            info = tarfile.TarInfo(rel)
            info.size, info.mode, info.mtime = len(donnees), (0o755 if rel.endswith(".sh") else 0o644), 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


def _deposer_fichiers(serveur, ssh, etape):
    """Dépose les fichiers dont l'étape a besoin. (statut, détail) ; None si réussi. Un fichier local manquant est un blocage
    (rien à voir avec la connexion)."""
    try:
        archive = _archive_fichiers(etape)
    except OSError as e:
        return "bloque", f"Fichier du dépôt introuvable ou illisible, l'étape ne peut pas être préparée : {_texte(e, serveur)}"
    code, _o, erreur = ssh.executer_octets(serveur_etat.cible(serveur), commande_depot(etape), serveur.cle,
                                           entree=archive, delai=120)
    if code == 0:
        return None
    return ("inconnue" if code in (255, 124) else "bloque",
            f"Dépôt des fichiers de l'étape {etape} sur le serveur impossible : {_texte(erreur, serveur)}")


def _deposer_script(serveur, ssh):
    """Dépose le script dans le dossier privé du serveur (0700, jamais /tmp). (statut, détail) ; None si réussi."""
    texte = (RACINE_SERVEUR / "mise_en_place.sh").read_bytes().decode("utf-8")   # octets du dépôt, fins de ligne intactes
    code, _o, erreur = ssh.executer(serveur_etat.cible(serveur), COMMANDE_DEPOT, serveur.cle, stdin=texte, delai=60)
    if code == 0:
        return None
    return ("inconnue" if code in (255, 124) else "bloque",
            f"Dépôt du script sur le serveur impossible : {_texte(erreur, serveur)}")


def _lancer_etape(serveur, ssh, etape):
    """(statut, détail) d'une étape distante : l'unique objet JSON de sa sortie ; « inconnue » si la connexion tombe."""
    delai = DELAIS_ETAPE_S.get(etape, DELAI_DEFAUT_S)
    prefixe = f'{VARIABLE_DOSSIER}="{DOSSIER_DISTANT}" ' if etape in FICHIERS_ETAPE else ""
    code, sortie, erreur = ssh.executer(serveur_etat.cible(serveur), f'{prefixe}bash "{SCRIPT_DISTANT}" --etape {etape}',
                                        serveur.cle, delai=delai)
    d = _analyser(sortie)
    if not d or d.get("statut") not in STATUTS_ETAPE:
        if code == 124:
            return "inconnue", ("Délai dépassé : l'étape peut encore tourner sur le serveur, attendez avant de relancer "
                                f"({etape}).")
        if code == 255:
            return "inconnue", f"Serveur injoignable pendant l'étape {etape} : {_texte(erreur, serveur)}"
        return "bloque", f"Réponse illisible du serveur (code {code}) : {_texte(erreur, serveur)}"
    return d["statut"], _texte(d.get("detail", ""), serveur)


# ---------------------------------------------------------------- installation

GESTE_ETAPE = "Lisez le détail, corrigez le point indiqué puis relancez l'installation."


def installer(serveur, actions, accord, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, dormir=time.sleep,
              vivant=pid_vivant):
    """Installe les capacités manquantes pour `actions`, dans l'ordre, après accord explicite (`accord is True`).

    Renvoie `{"capacites": {id: {statut, detail, geste, maj}}, "ok": bool, "erreur": str | None}`.
    `ErreurInstallation` pour un refus (accord, accès, installation déjà en cours), sans rien avoir modifié.
    `dormir` n'est pas utilisé : paramètre réservé aux tests et conservé pour la parité avec les autres moteurs."""
    if accord is not True:
        raise ErreurInstallation("Installation refusée : l'accord n'a pas été donné.",
                                 "Validez l'aperçu (taille, durée) pour donner votre accord.")
    try:
        requises = manquantes_pour(actions, set())
    except ValueError as e:
        raise ErreurInstallation(str(e), "Choisissez des actions connues.") from e
    deja = ErreurInstallation("Une installation est déjà en cours sur ce poste.",
                              "Attendez sa fin (ou son abandon) puis relancez.")
    if not _VERROU_PROCESSUS.acquire(blocking=False):       # même processus : double clic, deuxième fil
        raise deja
    try:
        refus = serveur_etat.refus_acces(serveur, ssh=ssh)
        if refus:
            raise ErreurInstallation(_texte(refus, serveur), "Corrigez l'accès au serveur puis relancez.")
        try:
            verrou = _prendre_verrou(dossier, vivant)
        except OSError as e:
            raise ErreurInstallation(f"Dossier de l'installation inutilisable : {_texte(e, serveur)}",
                                     "Vérifiez les droits d'écriture du dossier de configuration.") from e
        if verrou is None:
            raise deja
        if plateforme_en_cours(dossier, vivant):               # vérifié verrou pris : les deux flux se refusent mutuellement
            try:
                verrou.unlink()
            except OSError:
                pass
            raise ErreurInstallation("L'installation de la plateforme est en cours : le script du serveur ne peut pas servir "
                                     "aux deux à la fois.", "Attendez la fin de l'installation de la plateforme puis relancez.")
        debut = _maintenant()
        caps = {}
        try:
            try:
                return _derouler(serveur, requises, actions, ssh, dossier, caps, debut)
            finally:
                caps.update(_degrader(caps))                # aucune capacité ne reste « en_cours » (interruption comprise)
                _ecrire_etat(dossier, serveur.id, caps, False, debut)
        finally:
            try:
                verrou.unlink()
            except OSError:
                pass
    finally:
        _VERROU_PROCESSUS.release()


def _rafraichies(anciennes, sondes, exclues):
    """Entrées déjà connues, hors `exclues`, remises à jour d'après la sonde qui vient d'être lue (mêmes règles que
    `_enregistrer`) : « bloque » gardé avec sa raison sauf si la sonde dit présente ; sonde illisible : état connu gardé ;
    jamais « presente » sans confirmation de la sonde."""
    sortie = {}
    for i, ancienne in anciennes.items():
        s = sondes.get(i)
        if i in exclues or s not in (serveur_etat.PRESENTE, serveur_etat.ABSENTE):
            continue
        statut = ancienne.get("statut") if isinstance(ancienne, dict) else None
        if s == serveur_etat.PRESENTE:
            sortie[i] = ancienne if statut in ("presente", "fait") else _entree("presente", _DETAIL_SONDE["presente"])
        elif statut != "bloque":
            sortie[i] = _entree("absente", _DETAIL_SONDE["absente"])
    return sortie


def _derouler(serveur, requises, actions, ssh, dossier, caps, debut):
    frais = {}

    def ecrire(en_cours=True):
        _ecrire_etat(dossier, serveur.id, {**frais, **caps}, en_cours, debut)

    def resultat(erreur=None):
        return {"capacites": caps, "ok": erreur is None and all(
            caps[i]["statut"] in ("fait", "presente") for i in requises), "erreur": erreur}

    sondes = serveur_etat.sonder(serveur, ssh=ssh)             # état réel, jamais le cache
    if any(sondes.get(i) not in (serveur_etat.PRESENTE, serveur_etat.ABSENTE) for i in requises):
        for i in requises:
            caps[i] = _entree("inconnue", "Serveur injoignable ou état illisible : rien n'a été installé.",
                              "Vérifiez la connexion au serveur puis relancez.")
        return resultat("Serveur injoignable : rien n'a été installé.")
    presentes = {i for i, s in sondes.items() if s == serveur_etat.PRESENTE}
    perimees = _perimees(serveur, ssh, presentes, set(requises))
    presentes -= perimees
    avant = lire_etat(dossier).get(serveur.id, {}).get("capacites")
    frais.update(_rafraichies(avant if isinstance(avant, dict) else {}, sondes, set(requises)))
    a_faire = manquantes_pour(actions, presentes)
    for i in requises:
        caps[i] = (_entree("presente", "Déjà présente.") if i in presentes else
                   _entree("a_faire", "À mettre à jour : les fichiers déposés sur le serveur sont périmés.") if i in perimees else
                   _entree("a_faire", "À installer."))
    ecrire()

    fait, erreur, arret = set(presentes), None, None            # arret : capacité qui interrompt toute la suite
    script_depose, fichiers_deposes = False, set()
    for i in a_faire:
        cap = CATALOGUE[i]
        if arret:
            caps[i] = _entree("a_faire", f"En attente de {arret}.", GESTE_ETAPE)
            continue
        attente = [d for d in cap.depend if d not in fait]
        if attente:
            caps[i] = _entree("a_faire", "En attente de " + ", ".join(attente) + ".", GESTE_ETAPE)
            continue
        if not cap.installable:
            caps[i] = _entree("bloque", _texte(f"Non installable automatiquement : {cap.raison_non_installable}", serveur),
                              _texte(cap.raison_non_installable, serveur))
            ecrire()
            continue
        caps[i] = _entree("en_cours", f"Installation de « {cap.libelle} » en cours.")
        ecrire()
        try:
            r = None if script_depose else _deposer_script(serveur, ssh)
            script_depose = script_depose or r is None
            if r is None and cap.etape in FICHIERS_ETAPE and cap.etape not in fichiers_deposes:
                r = _deposer_fichiers(serveur, ssh, cap.etape)
                if r is None:
                    fichiers_deposes.add(cap.etape)
            statut, detail = r or _lancer_etape(serveur, ssh, cap.etape)
        except Exception as e:                                   # réseau, hôte invalide, fichier du script absent
            statut, detail = "inconnue", f"Étape interrompue : {_texte(e, serveur) or type(e).__name__}"
        if statut == "fait":
            fait.add(i)
            caps[i] = _entree("fait", detail)
        elif statut == "inconnue":
            caps[i] = _entree("inconnue", detail, "Vérifiez la connexion au serveur (et que l'étape ne tourne plus) puis relancez.")
            arret, erreur = i, f"Installation interrompue, serveur injoignable ou délai dépassé : {detail}"
        else:
            caps[i] = _entree(statut, detail, GESTE_ETAPE)
            arret = i
        ecrire()

    if erreur is None:                                           # relecture finale : la présence réelle fait foi
        finales = serveur_etat.sonder(serveur, ssh=ssh)
        finales_presentes = {i for i, v in finales.items() if v == serveur_etat.PRESENTE}
        perimees_finales = _perimees(serveur, ssh, finales_presentes, set(requises))      # l'empreinte aussi, pas seulement l'existence
        for i in requises:
            if caps[i]["statut"] != "fait":
                continue
            if finales.get(i) == serveur_etat.ABSENTE:
                caps[i] = _entree("bloque", "L'étape s'est terminée mais la capacité n'est pas détectée sur le serveur.",
                                  GESTE_ETAPE)
            elif finales.get(i) != serveur_etat.PRESENTE:
                caps[i] = _entree("inconnue", "Présence non vérifiable après l'étape (serveur injoignable).",
                                  "Relancez un aperçu pour constater l'état.")
            elif i in perimees_finales:
                caps[i] = _entree("bloque", "L'étape s'est terminée mais le marqueur du serveur porte une empreinte périmée.",
                                  GESTE_ETAPE)
    return resultat(erreur)
