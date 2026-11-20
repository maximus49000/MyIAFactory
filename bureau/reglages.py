"""Réglages d'un projet : lecture et écriture."""
import contextlib
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

from .deport import LIEUX_PAR_DEFAUT, valider_lieux
from .deport_types import catalogue_union
from .releve import MOTIF_GENRE  # un id de projet suit le même motif qu'un genre

DEFAUTS = {"port": 8770, "charge_max": 75, "fraicheur_min": 30, "releve": {}, "prix_automatiques": True,
           "moteur": {"couche": "claude"}, "agents_cloud_max": 3,
           # Vrai quand le Directeur a accordé le dossier du projet pour les sessions cloud : le moteur répond alors
           # lui-même « Yes, I trust this folder » à Claude Code (jamais sans cet accord).
           "cloud_dossier_approuve": False,
           # Vrai quand le Directeur laisse le moteur valider lui-même les leçons proposées, au niveau qu'elles proposent.
           "lecons_auto": False,
           # Vrai (par défaut) : le Chef analyse chaque blocage d'une tâche avant le Directeur (« Analyse intelligente
           # des blocages ») ; faux, le moteur fait comme avant, sans aucun appel de ce jugement.
           "analyse_blocages": True,
           # Vrai : la livraison (la construction de l'apk, 8 à 14 min) ne part pas toute seule quand les éléments sont
           # conformes ; elle attend « Livrer maintenant » (essai de coûts du 2026-11-19). Faux : comme avant.
           "livraison_sur_demande": False,
           # Vrai : une évolution moyenne (cahier validé ensuite) n'a plus de session de tests et de revue à part ; la
           # programmation relit et teste elle-même (essai de coûts du 2026-11-19 : 0,12 à 0,17 € et 3 à 7 min de moins,
           # mais plus de regard neuf). Faux : comme avant.
           "une_session_moyenne": False,
           # Exécution déportée : lieu de chaque action (poste, github, serveur), commande de remplacement éventuelle
           # par action, heure de la campagne de charge. Les clés absentes valent ces défauts.
           "deport": {"lieux": dict(LIEUX_PAR_DEFAUT), "commandes": {}, "charge_heure": "03:00"}}
_HEURE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
COUCHES_MOTEUR = ("claude", "api")   # `claude -p` (l'abonnement) ou l'API Messages (clé facturée à part)
AGENTS_CLOUD_MAX = (1, 16)
AGENTS_ABONNEMENT_MAX = (1, 32)   # le plafond des tâches d'agent actives sur l'abonnement, tous projets et tous lieux


class ReglagesInvalides(Exception):
    pass


def charger(chemin):
    chemin = Path(chemin)
    r = json.loads(json.dumps(DEFAUTS))
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
        if not isinstance(donnees, dict):
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : un objet JSON est attendu")
        r.update(donnees)
    _verifier_moteur(r)
    r["dossier"] = str(chemin.parent)
    return r


def _verifier_moteur(r):
    """Les réglages du moteur : `moteur.couche` vaut claude ou api ; `agents_cloud_max` va de 1 à 16."""
    m = r.get("moteur")
    if not isinstance(m, dict) or m.get("couche", "claude") not in COUCHES_MOTEUR:
        raise ReglagesInvalides("Réglages : « moteur.couche » doit valoir « claude » ou « api ».")
    n = r.get("agents_cloud_max")
    if type(n) is not int or not AGENTS_CLOUD_MAX[0] <= n <= AGENTS_CLOUD_MAX[1]:
        raise ReglagesInvalides("Réglages : « agents_cloud_max » doit être un entier de 1 à 16.")
    if type(r.get("cloud_dossier_approuve")) is not bool:
        raise ReglagesInvalides("Réglages : « cloud_dossier_approuve » doit valoir true ou false.")
    if type(r.get("lecons_auto")) is not bool:
        raise ReglagesInvalides("Réglages : « lecons_auto » doit valoir true ou false.")
    if type(r.get("analyse_blocages")) is not bool:
        raise ReglagesInvalides("Réglages : « analyse_blocages » doit valoir true ou false.")
    if type(r.get("livraison_sur_demande")) is not bool:
        raise ReglagesInvalides("Réglages : « livraison_sur_demande » doit valoir true ou false.")
    if type(r.get("une_session_moyenne")) is not bool:
        raise ReglagesInvalides("Réglages : « une_session_moyenne » doit valoir true ou false.")
    r["deport"] = normaliser_deport(r.get("deport"), "Réglages")


def normaliser_deport(v, contexte="Réglages", catalogue=None):
    """Valide la clé `deport` et la rend complète : lieux manquants au défaut (poste), commandes vides, charge 03:00.
    Lieux et commandes sont validés contre le catalogue d'actions du projet ; sans catalogue (réglage du bureau, qui
    n'a pas de projet), toute action connue d'un type quelconque est admise et seuls les noms inconnus sont refusés.
    Lève ReglagesInvalides (message en français) si une valeur est mauvaise."""
    if catalogue is None:
        catalogue = catalogue_union()
    if not isinstance(v, dict):
        raise ReglagesInvalides(f"{contexte} : « deport » doit être un objet {{lieux, commandes, charge_heure}}.")
    lieux = v.get("lieux", {})
    try:
        lieux = valider_lieux(lieux, catalogue=catalogue)
    except ValueError as e:
        raise ReglagesInvalides(f"{contexte} : « deport.lieux » : {e}")
    commandes = v.get("commandes", {})
    if not isinstance(commandes, dict) or not all(isinstance(c, str) for c in commandes.values()):
        raise ReglagesInvalides(f"{contexte} : « deport.commandes » doit associer une action connue à une "
                                "commande (texte).")
    for k in commandes:
        if k not in catalogue:
            raise ReglagesInvalides(f"{contexte} : « deport.commandes » : l'action « {k} » n'existe pas pour ce "
                                    "type de projet." if k in catalogue_union() else
                                    f"{contexte} : « deport.commandes » doit associer une action connue à une "
                                    "commande (texte).")
    heure = v.get("charge_heure", DEFAUTS["deport"]["charge_heure"])
    if not isinstance(heure, str) or not _HEURE.match(heure):
        raise ReglagesInvalides(f"{contexte} : « deport.charge_heure » doit être une heure HH:MM (00:00 à 23:59).")
    return {"lieux": {**LIEUX_PAR_DEFAUT, **lieux}, "commandes": dict(commandes), "charge_heure": heure}


MAX_PROJETS = 12


def _id_par_defaut(chemin):
    """Le nom du dossier des réglages (son parent pour `.factory`), ramené à `[a-z0-9-]`."""
    dossier = chemin.parent
    if dossier.name == ".factory":
        dossier = dossier.parent
    texte = unicodedata.normalize("NFKD", dossier.name).encode("ascii", "ignore").decode("ascii").lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    return texte[:40].rstrip("-") or "projet"


def lire_bureau(chemin):
    """Le fichier du bureau : `{"port"?: 8770, "projets": [chemin | {"chemin", "id"?}]}` (1 à 12 projets,
    chemins relatifs à ce fichier). Rend `{"port": int, "projets": [{"id", "chemin": Path}]}`."""
    chemin = Path(chemin)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as e:
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : {e}")
    if not isinstance(donnees, dict):
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : un objet JSON est attendu")
    port = donnees.get("port", DEFAUTS["port"])
    if type(port) is not int or not 0 <= port <= 65535:
        raise ReglagesInvalides("Fichier du bureau : « port » doit être un entier entre 0 et 65535.")
    projets = donnees.get("projets")
    if not isinstance(projets, list) or not 1 <= len(projets) <= MAX_PROJETS:
        raise ReglagesInvalides(f"Fichier du bureau : « projets » doit lister de 1 à {MAX_PROJETS} "
                                "fichiers de réglages.")
    entrees = []
    for i, p in enumerate(projets):
        id_ = None
        if isinstance(p, dict):
            id_ = p.get("id")
            p = p.get("chemin")
            if id_ is not None and (not isinstance(id_, str) or not MOTIF_GENRE.match(id_)):
                raise ReglagesInvalides(f"Fichier du bureau : projets[{i}].id invalide (lettres minuscules, "
                                        "chiffres et tirets, 40 caractères au plus).")
        if not isinstance(p, str) or not p.strip() or "\x00" in p:
            raise ReglagesInvalides(f"Fichier du bureau : projets[{i}] doit donner le chemin d'un fichier "
                                    "de réglages.")
        c = chemin.parent / p
        if not c.is_file():  # une faute de frappe ne doit pas créer un projet fantôme
            raise ReglagesInvalides(f"Fichier du bureau : projets[{i}] : fichier de réglages introuvable ({c}).")
        entrees.append((id_, c))
    dossiers = [c.resolve().parent for _, c in entrees]
    if len(dossiers) != len(set(dossiers)):  # le bureau écrit ses historiques à côté des réglages
        raise ReglagesInvalides("Fichier du bureau : deux projets ont leurs réglages dans le même dossier.")
    donnes = [i for i, _ in entrees if i is not None]
    if len(donnes) != len(set(donnes)):
        raise ReglagesInvalides("Fichier du bureau : deux projets portent le même id.")
    pris = set(donnes)
    sortie = []
    for id_, c in entrees:
        if id_ is None:
            base = _id_par_defaut(c)
            id_, n = base, 1
            while id_ in pris:
                n += 1
                suffixe = f"-{n}"
                id_ = base[:40 - len(suffixe)].rstrip("-") + suffixe
            pris.add(id_)
        sortie.append({"id": id_, "chemin": c})
    plafond = donnees.get("agents_abonnement_max")
    if "agents_abonnement_max" in donnees and (type(plafond) is not int or not
                                                AGENTS_ABONNEMENT_MAX[0] <= plafond <= AGENTS_ABONNEMENT_MAX[1]):
        raise ReglagesInvalides("Fichier du bureau : « agents_abonnement_max » doit être un entier de 1 à 32 (ou absent).")
    return {"port": port, "projets": sortie, "acces": lire_acces(donnees.get("acces", {})),
            "agents_abonnement_max": plafond,
            "moteur": lire_moteur_du_bureau(donnees.get("moteur", {})),
            "deport": normaliser_deport(donnees.get("deport", {}), "Fichier du bureau")}


def lire_moteur_du_bureau(v):
    """La couche des appels faits avant qu'un projet n'existe (l'échange de la création) : `{"couche": claude | api}`,
    `claude` par défaut ; une clé absente vaut le défaut."""
    if not isinstance(v, dict) or v.get("couche", "claude") not in COUCHES_MOTEUR:
        raise ReglagesInvalides("Fichier du bureau : « moteur.couche » doit valoir « claude » ou « api ».")
    return {"couche": v.get("couche", "claude")}


ACCES = ("tailscale", "reseau_local")


def lire_acces(v):
    """Les accès distants du bureau : `{"tailscale": bool, "reseau_local": bool}` (une clé absente vaut faux)."""
    if not isinstance(v, dict) or not all(k in ACCES and isinstance(x, bool) for k, x in v.items()):
        raise ReglagesInvalides("Fichier du bureau : « acces » doit valoir {\"tailscale\": vrai ou faux, "
                                "\"reseau_local\": vrai ou faux}.")
    return {k: v.get(k, False) for k in ACCES}


def fixer_charge_max(chemin, valeur):
    if type(valeur) is not int or not 30 <= valeur <= 95:
        raise ValueError("La charge maximum doit être un entier entre 30 et 95.")
    return _ecrire_cle(chemin, "charge_max", valeur)


def fixer_lecons_auto(chemin, valeur):
    """Note si le moteur valide lui-même les leçons proposées (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« lecons_auto » doit valoir true ou false.")
    return _ecrire_cle(chemin, "lecons_auto", valeur)


def fixer_deport(chemin, deport, catalogue=None):
    """Note le déport du projet (lieux, commandes, heure de charge) : validé avant d'écrire, ReglagesInvalides sinon.
    Seuls les lieux explicitement donnés sont écrits (jamais ceux complétés par défaut : le projet hérite du bureau
    pour les autres). `catalogue` : les actions du type du projet. Rend les réglages rechargés."""
    complet = normaliser_deport(deport, "Réglages", catalogue)
    explicites = {a: complet["lieux"][a] for a in deport.get("lieux", {})}
    return _ecrire_cle(chemin, "deport", {**complet, "lieux": explicites})


_VERROU_ECRITURE = threading.Lock()     # lecture-modification-écriture d'un fichier de réglages : une à la fois ici
VERROU_ATTENTE_S = 10                   # attente au plus d'un autre processus qui écrit le même fichier
VERROU_PERIME_S = 60                    # un verrou plus vieux (processus mort) est repris


@contextlib.contextmanager
def _verrou_fichier(chemin):
    """Une écriture à la fois sur `chemin` : verrou du processus, plus un fichier `<nom>.verrou` créé en exclusif pour
    les autres processus (le bureau et l'installation écrivent le même fichier du bureau). Attente bornée ; un verrou
    périmé est repris. `TimeoutError` si l'autre écriture ne finit pas."""
    marque = Path(str(chemin) + ".verrou")
    with _VERROU_ECRITURE:
        fin = time.monotonic() + VERROU_ATTENTE_S
        while True:
            try:
                os.close(os.open(str(marque), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except FileExistsError:
                try:
                    if time.time() - marque.stat().st_mtime > VERROU_PERIME_S:
                        marque.unlink()
                        continue
                except OSError:
                    continue
                if time.monotonic() >= fin:
                    raise TimeoutError(f"Fichier en cours d'écriture par un autre programme : {chemin}")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                marque.unlink()
            except OSError:
                pass


def fixer_agents_abonnement_max(chemin, valeur):
    """Note, dans le fichier du bureau, le plafond des agents actifs sur l'abonnement (entier de 1 à 32 ; `None` : plus de
    plafond, la clé disparaît). Le reste du fichier est gardé (relu SOUS VERROU : une autre écriture du fichier du bureau
    n'est jamais perdue). Rend la valeur écrite."""
    if valeur is not None and (type(valeur) is not int or not AGENTS_ABONNEMENT_MAX[0] <= valeur <= AGENTS_ABONNEMENT_MAX[1]):
        raise ValueError("« agents_abonnement_max » doit être un entier de 1 à 32 (ou nul : aucun plafond).")
    chemin = Path(chemin)
    try:
        with _verrou_fichier(chemin):
            return _fixer_plafond(chemin, valeur)
    except TimeoutError as e:
        raise ReglagesInvalides(str(e)) from None


def _fixer_plafond(chemin, valeur):
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as e:
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : {e}")
    if not isinstance(donnees, dict):
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : un objet JSON est attendu")
    if valeur is None:
        donnees.pop("agents_abonnement_max", None)
    else:
        donnees["agents_abonnement_max"] = valeur
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return valeur


def fixer_analyse_blocages(chemin, valeur):
    """Note si le Chef analyse les blocages avant le Directeur (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« analyse_blocages » doit valoir true ou false.")
    return _ecrire_cle(chemin, "analyse_blocages", valeur)


def fixer_livraison_sur_demande(chemin, valeur):
    """Note si la livraison attend le clic « Livrer maintenant » (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« livraison_sur_demande » doit valoir true ou false.")
    return _ecrire_cle(chemin, "livraison_sur_demande", valeur)


def fixer_une_session_moyenne(chemin, valeur):
    """Note si une évolution moyenne se fait en une seule session, sans tests ni revue à part (vrai ou faux)."""
    if type(valeur) is not bool:
        raise ValueError("« une_session_moyenne » doit valoir true ou false.")
    return _ecrire_cle(chemin, "une_session_moyenne", valeur)


def fixer_cloud_dossier_approuve(chemin, valeur):
    """Note si le Directeur accorde le dossier du projet pour les sessions cloud (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« cloud_dossier_approuve » doit valoir true ou false.")
    return _ecrire_cle(chemin, "cloud_dossier_approuve", valeur)


def _ecrire_cle(chemin, cle, valeur):
    chemin = Path(chemin)
    donnees = {}
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
    donnees[cle] = valeur
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return charger(chemin)
