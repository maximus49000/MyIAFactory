"""Réglages d'un projet : lecture et écriture."""
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

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
           "analyse_blocages": True}
COUCHES_MOTEUR = ("claude", "api")   # `claude -p` (l'abonnement) ou l'API Messages (clé facturée à part)
AGENTS_CLOUD_MAX = (1, 16)


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
    return {"port": port, "projets": sortie, "acces": lire_acces(donnees.get("acces", {})),
            "moteur": lire_moteur_du_bureau(donnees.get("moteur", {}))}


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


def fixer_analyse_blocages(chemin, valeur):
    """Note si le Chef analyse les blocages avant le Directeur (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« analyse_blocages » doit valoir true ou false.")
    return _ecrire_cle(chemin, "analyse_blocages", valeur)


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
