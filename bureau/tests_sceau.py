"""Le sceau du budget des tests : `~/MyIAFactory/tests-sceau.json`, hors des projets, par identifiant de projet.

`{"<id projet>": {"budget_s": 300, "commande_complete": "npx vitest run", "reference_s": 241, "campagnes": 57,
"cumul_s": 9120.4, "derniers_nb_tests": 318, "tache_auto": false, "commande_refusee": null, "alertes": {},
"maj": "<date>"}}`

Le budget y fait foi (`reglages.json` n'en garde qu'une copie d'affichage) ; `campagnes` et `cumul_s` sont des
compteurs qui ne font que monter. La lecture ne lève jamais ; l'écriture se fait sous verrou, par fichier temporaire
puis remplacement, et un sceau illisible n'est JAMAIS réécrit à l'aveugle (il porte les autres projets).

Reste compatible Python 3.9 : le lanceur des agents (`outils/campagne.py`, `outils/deporter.py`) l'importe."""
import copy
import json
import math
import os
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .verrou_fichier import remplacer, verrou_fichier

SCEAU = Path("~/MyIAFactory/tests-sceau.json").expanduser()
BUDGET_DEFAUT_S = 300
BUDGET_MIN_S, BUDGET_MAX_S = 60, 3600
ENTREE_VIDE = {"budget_s": 300, "commande_complete": None, "reference_s": None, "campagnes": 0, "cumul_s": 0.0,
               "derniers_nb_tests": None, "tache_auto": False, "commande_refusee": None, "alertes": {}, "maj": None}
TAILLE_MAX = 1024 * 1024          # douze projets tiennent en quelques Ko : au-delà, le fichier n'est pas un sceau
PROFONDEUR_MAX = 32               # un sceau a 3 ou 4 niveaux ; au-delà, il est illisible (jamais de RecursionError)
ATTENTE_LANCEUR_S = 2             # l'attente du verrou côté lanceur : une campagne ne patiente pas 10 s pour mesurer


class SceauIllisible(Exception):
    """Le sceau existe mais ne se lit pas (JSON invalide, pas un objet, trop gros, pas un fichier ordinaire)."""


def _maintenant():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _refuser_constante(nom):
    raise ValueError("valeur non JSON : %s" % nom)


def _nombre(v, mini=0.0, maxi=None):
    """Vrai pour un nombre fini (ni booléen ni texte) entre `mini` et `maxi`."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < mini:
        return False
    return maxi is None or v <= maxi


def _entier(v):
    return type(v) is int and v >= 0


def _texte_ou_rien(v):
    return v is None or isinstance(v, str)


# Le type attendu de chaque champ connu : une valeur d'un autre type (sceau abîmé ou modifié à la main) vaut le défaut.
_VALIDES = {
    "budget_s": lambda v: _nombre(v, BUDGET_MIN_S, BUDGET_MAX_S),
    "commande_complete": _texte_ou_rien,
    "reference_s": lambda v: v is None or _nombre(v),
    "campagnes": _entier,
    "cumul_s": _nombre,
    "derniers_nb_tests": lambda v: v is None or _entier(v),
    "tache_auto": lambda v: isinstance(v, bool),
    "commande_refusee": _texte_ou_rien,
    "alertes": lambda v: isinstance(v, dict),
    "maj": _texte_ou_rien,
}


def _completer(brute):
    """L'entrée d'un projet complétée par `ENTREE_VIDE` : un champ connu de mauvais type prend le défaut, les champs
    inconnus sont gardés (versions futures). Toujours une copie indépendante."""
    entree = copy.deepcopy(ENTREE_VIDE)
    if isinstance(brute, dict):
        for cle, valeur in brute.items():
            if cle not in _VALIDES:
                entree[cle] = copy.deepcopy(valeur)
            elif _VALIDES[cle](valeur):
                entree[cle] = float(valeur) if cle == "cumul_s" else copy.deepcopy(valeur)
    return entree


def _charger(sceau):
    """Le contenu du sceau (un objet), `None` s'il n'existe pas ; `SceauIllisible` s'il existe sans se lire. Un lien,
    un dossier ou un fichier spécial à la place du sceau est illisible : jamais suivi, jamais remplacé."""
    chemin = str(sceau)
    try:
        s = os.lstat(chemin)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise SceauIllisible("sceau inaccessible : %s" % e)
    if not stat.S_ISREG(s.st_mode):
        raise SceauIllisible("le sceau n'est pas un fichier ordinaire : %s" % chemin)
    if s.st_size > TAILLE_MAX:
        raise SceauIllisible("sceau trop gros : %s" % chemin)
    try:
        # Course acceptée entre `lstat` et `open` (comme `deport_types._lire_json_sur`) : la taille reste bornée ici.
        with open(chemin, "rb") as f:
            brut = f.read(TAILLE_MAX + 1)
        if len(brut) > TAILLE_MAX:
            raise SceauIllisible("sceau trop gros : %s" % chemin)
        donnees = json.loads(brut.decode("utf-8-sig"), parse_constant=_refuser_constante)
    except SceauIllisible:
        raise
    except (OSError, ValueError, RecursionError, MemoryError) as e:
        raise SceauIllisible("sceau illisible : %s" % e)
    if not isinstance(donnees, dict):
        raise SceauIllisible("sceau illisible : un objet JSON est attendu")
    if _profondeur(donnees) > PROFONDEUR_MAX:
        # `json` lit jusqu'à ~1 000 niveaux, mais la copie (`deepcopy`) et l'écriture s'arrêtent bien avant : un sceau
        # aussi imbriqué n'en est pas un (et ne doit jamais faire lever RecursionError aux appelants)
        raise SceauIllisible("sceau illisible : imbrication trop profonde")
    return donnees


def _profondeur(valeur):
    """La profondeur d'imbrication d'une valeur JSON, sans récursion (une liste ou un objet compte un niveau)."""
    pire, pile = 0, [(valeur, 1)]
    while pile:
        v, p = pile.pop()
        if isinstance(v, dict):
            enfants = v.values()
        elif isinstance(v, list):
            enfants = v
        else:
            continue
        pire = max(pire, p)
        if pire > PROFONDEUR_MAX:
            return pire
        pile.extend((e, p + 1) for e in enfants)
    return pire


def lire_etat(id_projet: str, sceau=SCEAU):
    """`(entrée, état)` : l'entrée du projet complétée par `ENTREE_VIDE`, et `"ok"` (sceau lisible, projet présent),
    `"absent"` (pas de sceau, ou pas d'entrée pour ce projet) ou `"illisible"` (sceau abîmé, ou id inutilisable) ; dans
    ces deux derniers cas, une copie de `ENTREE_VIDE`. Les règles d'alerte s'en servent pour ne pas confondre un sceau
    abîmé avec un projet neuf. Ne lève jamais."""
    try:
        donnees = _charger(sceau)
        if donnees is None:
            return _completer(None), "absent"
        brute = donnees.get(id_projet)          # un id non hachable lève TypeError : illisible
        if brute is None and id_projet not in donnees:
            return _completer(None), "absent"
        return _completer(brute), "ok"
    except Exception:  # noqa: BLE001 — illisible ou inattendu : une lecture ne casse jamais l'appelant
        return copy.deepcopy(ENTREE_VIDE), "illisible"


def lire(id_projet: str, sceau=SCEAU) -> dict:
    """L'entrée du projet complétée par `ENTREE_VIDE` ; absente ou illisible : une copie de `ENTREE_VIDE`. Ne lève
    jamais."""
    try:
        return lire_etat(id_projet, sceau)[0]
    except Exception:  # noqa: BLE001 — par construction `lire_etat` ne lève pas ; garde-fou
        return copy.deepcopy(ENTREE_VIDE)


def _ecrire(sceau, donnees):
    """Écrit `donnees` par un fichier temporaire du même dossier, vidé sur le disque, puis `os.replace` (atomique) :
    un lecteur voit l'ancien sceau ou le nouveau, jamais un sceau à moitié écrit."""
    texte = json.dumps(donnees, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
    dossier = os.path.dirname(os.path.abspath(str(sceau)))
    fd, temporaire = tempfile.mkstemp(prefix=".tests-sceau-", suffix=".tmp", dir=dossier)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(texte.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        remplacer(temporaire, sceau)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


def modifier(id_projet: str, changer: Callable[[dict], None], sceau=SCEAU,
             maintenant: Callable[[], str] = _maintenant, attente_s=None) -> dict:
    """Sous `verrou_fichier(sceau)` : relit le sceau, applique `changer` à l'entrée du projet (complétée), pose `maj`,
    écrit par fichier temporaire puis `os.replace`, et rend l'entrée écrite. Les autres projets sont gardés tels quels.
    Sceau présent mais illisible : `SceauIllisible`, rien n'est écrit. `changer` qui lève, ou une valeur non JSON :
    l'exception remonte, rien n'est écrit. `attente_s` : l'attente du verrou (défaut : celle des réglages, 10 s ; le
    lanceur passe `ATTENTE_LANCEUR_S`). Peut lever `TimeoutError` (verrou) ou `OSError` (disque)."""
    if not isinstance(id_projet, str) or not id_projet:
        raise ValueError("identifiant de projet invalide")
    dossier = Path(os.path.abspath(str(sceau))).parent
    if not os.path.lexists(str(sceau)):
        dossier.mkdir(parents=True, exist_ok=True)
    with verrou_fichier(sceau, attente_s=attente_s):
        donnees = _charger(sceau)
        if donnees is None:
            donnees = {}
        entree = _completer(donnees.get(id_projet))
        changer(entree)
        entree["maj"] = maintenant()
        donnees[id_projet] = entree
        _ecrire(sceau, donnees)
    return copy.deepcopy(entree)
