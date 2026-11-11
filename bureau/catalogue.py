"""Le catalogue d'une fonctionnalité : où le trouver, le lire (fichier ou commande), le valider.

Le bureau le lit à la demande, jamais à chaque relevé. Les champs facultatifs au mauvais type sont retirés
et signalés ; seuls `elements`, et l'`id` et le `nom` de chaque élément, sont exigés."""
import json
import math
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from . import releve

MAX_ELEMENTS = 20000
MAX_OCTETS = 50 * 1024 * 1024
CACHE_COMMANDE_S = 30
MAX_AVERTISSEMENTS = 100
GENERIQUE = "*"                 # la déclaration qui vaut pour toute fonctionnalité
PLACE = "{fonctionnalite}"      # y est remplacé par l'identifiant de la fonctionnalité
MOTIF_GENERIQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

_verrou = threading.Lock()
_cache_fichiers = {}   # chemin résolu -> ((date, taille), (code, objet))
_cache_commandes = {}  # (commande, dossier) -> (heure monotone, (code, objet))


class CatalogueInvalide(ValueError):
    pass


def vider_cache():
    with _verrou:
        _cache_fichiers.clear()
        _cache_commandes.clear()


# -- où le trouver ---------------------------------------------------------
def _declaration_valide(d):
    if not isinstance(d, dict) or ("fichier" in d) == ("commande" in d):
        return False
    if "fichier" in d:
        return isinstance(d["fichier"], str) and bool(d["fichier"]) and "\x00" not in d["fichier"]
    cmd = d["commande"]
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) and c for c in cmd):
        return False
    return "dossier" not in d or isinstance(d["dossier"], str)


def declaration(regl, fonctionnalite):
    """`{fichier}` ou `{commande, dossier?}`, plus `base` (le dossier auquel ses chemins se rapportent) ;
    `None` si la fonctionnalité n'a pas de catalogue déclaré. Les réglages (`catalogues`) passent avant le
    fichier de factory (`orchestrateur`, chemin relatif aux réglages ; ses chemins sont relatifs à lui)."""
    dossier = Path(regl.get("dossier") or ".")
    sources = [(regl.get("catalogues"), dossier)]
    orch = regl.get("orchestrateur")
    if isinstance(orch, str) and orch and "\x00" not in orch:
        chemin = dossier / orch
        try:
            factory = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            factory = None
        if isinstance(factory, dict):
            sources.append((factory.get("catalogues"), chemin.parent))
    if not isinstance(fonctionnalite, str):
        return None
    for catalogues, base in sources:   # une déclaration exacte d'abord, réglages puis fichier de factory
        if isinstance(catalogues, dict) and fonctionnalite in catalogues and fonctionnalite != GENERIQUE:
            d = catalogues[fonctionnalite]
            if _declaration_valide(d):
                return {**d, "base": str(base)}
    if not MOTIF_GENERIQUE.match(fonctionnalite):   # rien qui puisse sortir du dossier ou passer pour une option
        return None
    for catalogues, base in sources:   # puis « * », où {fonctionnalite} devient l'identifiant
        d = catalogues.get(GENERIQUE) if isinstance(catalogues, dict) else None
        if _declaration_valide(d):
            remplacer = lambda v: v.replace(PLACE, fonctionnalite)  # noqa: E731
            d = dict(d)
            if "fichier" in d:
                d["fichier"] = remplacer(d["fichier"])
            else:
                d["commande"] = [remplacer(a) for a in d["commande"]]
            return {**d, "base": str(base)}
    return None


# -- le lire ---------------------------------------------------------------
def _analyser(octets):
    """(code, objet) à partir du JSON brut."""
    try:
        brut = json.loads(octets.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, RecursionError) as e:
        return 422, {"erreur": f"Catalogue illisible (JSON invalide) : {e}"[:300]}
    try:
        propre, avertissements = valider(brut)
    except CatalogueInvalide as e:
        return 422, {"erreur": f"Catalogue invalide : {e}"}
    return 200, {"catalogue": propre, "avertissements": avertissements}


def _lire_fichier(chemin):
    try:
        st = chemin.stat()
    except OSError:
        return 422, {"erreur": f"Catalogue introuvable : {chemin.name}"}
    if st.st_size > MAX_OCTETS:
        return 422, {"erreur": f"Catalogue trop gros (plus de {MAX_OCTETS // (1024 * 1024)} Mo)."}
    cle = str(chemin.resolve())
    signature = (st.st_mtime_ns, st.st_size)
    with _verrou:
        en_cache = _cache_fichiers.get(cle)
    if en_cache and en_cache[0] == signature:
        return en_cache[1]
    try:
        octets = chemin.read_bytes()
    except OSError as e:
        return 422, {"erreur": f"Catalogue illisible : {e}"[:300]}
    resultat = _analyser(octets)
    with _verrou:
        _cache_fichiers[cle] = (signature, resultat)
    return resultat


def _lancer_commande(cmd, cwd):
    try:
        code, sortie, erreurs = releve._executer(cmd, str(cwd))
    except subprocess.TimeoutExpired:
        return 502, {"erreur": f"La commande du catalogue a dépassé {releve.DELAI_COMMANDE_S} s."}
    except OSError as e:
        return 502, {"erreur": f"La commande du catalogue n'a pas pu être lancée : {e}"[:300]}
    if code != 0:
        detail = erreurs.decode("utf-8", "replace").strip()[:200]
        return 502, {"erreur": f"La commande du catalogue a échoué (code {code}). {detail}".strip()}
    if len(sortie) > MAX_OCTETS:
        return 422, {"erreur": f"Catalogue trop gros (plus de {MAX_OCTETS // (1024 * 1024)} Mo)."}
    return _analyser(sortie)


def _ramener(objet, base, dossier):
    """Une copie du résultat dont les chemins (relatifs à `base`, le dossier du fichier de factory) sont rendus
    relatifs au dossier des réglages, d'où le bureau sert les images. Le même objet si les deux dossiers sont un."""
    base, dossier = Path(base).resolve(), Path(dossier).resolve()
    if base == dossier or "catalogue" not in objet:
        return objet

    def r(chemin):
        return Path(os.path.relpath(base / chemin, dossier)).as_posix()

    cat = dict(objet["catalogue"])
    elements = []
    for e in cat.get("elements", []):
        e = dict(e)
        if "captures" in e:
            e["captures"] = [{**c, "chemin": r(c["chemin"])} for c in e["captures"]]
        if "comparaisons" in e:
            e["comparaisons"] = [{**c, **{k: r(c[k]) for k in ("reel", "produit") if k in c}} for c in e["comparaisons"]]
        elements.append(e)
    cat["elements"] = elements
    return {**objet, "catalogue": cat}


def lire(regl, fonctionnalite):
    """(code HTTP, objet) : 200 `{catalogue, avertissements}`, 404 (pas de catalogue déclaré), 502 (la
    commande a échoué), 422 (fichier illisible ou `elements` invalide). Ne lève jamais."""
    try:
        d = declaration(regl, fonctionnalite)
        if d is None:
            return 404, {"erreur": "Aucun catalogue pour cette fonctionnalité."}
        base = Path(d["base"])
        dossier = Path(regl.get("dossier") or ".")
        if "fichier" in d:
            code, objet = _lire_fichier(base / d["fichier"])
            return code, (_ramener(objet, base, dossier) if code == 200 else objet)
        cwd = (base / d.get("dossier", ".")).resolve()
        cle = (tuple(d["commande"]), str(cwd))
        with _verrou:
            en_cache = _cache_commandes.get(cle)
        if en_cache and time.monotonic() - en_cache[0] < CACHE_COMMANDE_S:
            return en_cache[1]
        resultat = _lancer_commande(d["commande"], cwd)
        if resultat[0] == 200:
            resultat = (200, _ramener(resultat[1], base, dossier))
        with _verrou:
            _cache_commandes[cle] = (time.monotonic(), resultat)
        return resultat
    except Exception as e:  # jamais une exception vers le serveur
        return 422, {"erreur": f"Catalogue inutilisable : {e}"[:300]}


def ids(regl, fonctionnalite):
    """L'ensemble des ids d'éléments du catalogue, ou `None` s'il n'est pas lisible."""
    code, objet = lire(regl, fonctionnalite)
    if code != 200:
        return None
    return {e["id"] for e in objet["catalogue"]["elements"]}


# -- le valider ------------------------------------------------------------
def _texte(v):
    return isinstance(v, str)


def _nombre(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _entier(v):
    return type(v) is int


def _texte_ou_nombre(v):
    return _texte(v) or _nombre(v)


def _chemin(v):
    """Un chemin relatif du projet ; une adresse (`https:`, `data:`, `C:`…) ou un chemin absolu n'en est pas un."""
    return (isinstance(v, str) and bool(v) and "\x00" not in v and ":" not in v
            and v[0] not in "/\\" and not Path(v).is_absolute())


def _point(v):
    return isinstance(v, list) and len(v) == 2 and all(_nombre(x) for x in v)


def _liste_de(controle):
    return lambda v: isinstance(v, list) and all(controle(x) for x in v)


# Un objet : clé -> (contrôle, obligatoire). Les contrôles `_chemin` et `releve.lien_valide` sont « doux » :
# une valeur refusée est retirée de l'objet (et l'objet entier s'il l'exigeait), avec un avertissement.
OBJ_GROUPE = {"id": (_texte, True), "nom": (_texte, True)}
OBJ_PASSE = {"numero": (_entier, True), "date": (_texte, False), "titre": (_texte, False)}
OBJ_LECON = {"id": (_texte, True), "titre": (_texte, False), "texte": (_texte, False), "portee": (_texte, False),
             "passe": (_entier, False)}
OBJ_KIT = {"id": (_texte, True), "nom": (_texte, False), "description": (_texte, False)}
OBJ_TRACE = {"nom": (_texte, False), "points": (_liste_de(_point), True), "groupe": (_texte, False)}
OBJ_CARAC = {"libelle": (_texte, True), "valeur": (_texte_ou_nombre, True)}
OBJ_CAPTURE = {"chemin": (_chemin, True), "passe": (_entier, False)}
OBJ_COMPARAISON = {"angle": (_texte, False), "reel": (_chemin, False), "produit": (_chemin, False),
                   "credit": (_texte, False), "lien": (releve.lien_valide, False)}
OBJ_LIEN = {"libelle": (_texte, False), "url": (releve.lien_valide, True)}
OBJ_DOUTE = {"date": (_texte, False), "raison": (_texte, False), "leve_par": (_texte, False)}
OBJ_RETOUR = {"t": (_texte, False), "texte": (_texte, True), "etat": (_texte, False), "reponse": (_texte, False)}
OBJ_POSITION = {"x": (_nombre, True), "y": (_nombre, True)}
# Une emprise du fond de la vue de haut : un polygone (3 points au moins), à l'élément qu'elle figure s'il y en a un
# (elle prend alors sa teinte), sinon un contexte neutre ; `groupe` la range avec son groupe.
OBJ_FOND = {"points": (lambda v: _liste_de(_point)(v) and len(v) >= 3, True), "element": (_texte, False),
            "groupe": (_texte, False)}
DOUX = (_chemin, releve.lien_valide)

RACINE = {"groupes": ("liste", OBJ_GROUPE), "passes": ("liste", OBJ_PASSE), "lecons": ("liste", OBJ_LECON),
          "kit": ("liste", OBJ_KIT), "trace": ("liste", OBJ_TRACE), "fond": ("liste", OBJ_FOND)}
ELEMENT = {"groupe": ("valeur", _texte), "etat": ("valeur", _texte), "note": ("valeur", _texte),
           "evenement": ("valeur", _texte),
           "caracteristiques": ("liste", OBJ_CARAC), "captures": ("liste", OBJ_CAPTURE),
           "comparaisons": ("liste", OBJ_COMPARAISON), "liens": ("liste", OBJ_LIEN),
           "retours": ("liste", OBJ_RETOUR),
           "kit": ("valeur", _liste_de(_texte)), "lecons_appliquees": ("valeur", _liste_de(_texte)),
           "a_reevaluer": ("valeur", _liste_de(_texte)), "passes": ("valeur", _liste_de(_entier)),
           "doute": ("objet", OBJ_DOUTE), "position": ("objet", OBJ_POSITION)}


def _objet(v, schema, nom, avert):
    """L'objet nettoyé, ou `None` s'il ne convient pas (avertissement déjà noté pour les refus doux)."""
    if not isinstance(v, dict):
        return None
    propre = {}
    for cle, (controle, obligatoire) in schema.items():
        x = v.get(cle)
        if x is None:
            if obligatoire:
                return None
            continue
        if controle(x):
            propre[cle] = x
        elif controle in DOUX and isinstance(x, str):
            avert(f"{nom}.{cle} retiré (adresse ou chemin refusé).")
            if obligatoire:
                return False  # retiré par un refus doux : le reste du champ est gardé
        else:
            return None
    return propre


def _champ(valeur, forme, schema, nom, avert):
    """(garder, valeur nettoyée)."""
    if forme == "valeur":
        return schema(valeur), valeur
    if forme == "objet":
        o = _objet(valeur, schema, nom, avert)
        return bool(o), o
    if not isinstance(valeur, list):
        return False, None
    propres = []
    for i, x in enumerate(valeur):
        o = _objet(x, schema, f"{nom}[{i}]", avert)
        if o is None:
            return False, None
        if o is not False:
            propres.append(o)
    return True, propres


def _nettoyer(objet, champs, prefixe, avert):
    propre = {}
    for cle, (forme, schema) in champs.items():
        if objet.get(cle) is None:
            continue
        nom = f"{prefixe}{cle}"
        garder, valeur = _champ(objet[cle], forme, schema, nom, avert)
        if garder:
            propre[cle] = valeur
        else:
            avert(f"{nom} retiré (forme inattendue).")
    return propre


def valider(c):
    """(catalogue propre, avertissements). Lève `CatalogueInvalide` si `elements` ne convient pas."""
    if not isinstance(c, dict):
        raise CatalogueInvalide("un objet JSON est attendu.")
    elements = c.get("elements")
    if not isinstance(elements, list):
        raise CatalogueInvalide("« elements » doit être une liste.")
    if len(elements) > MAX_ELEMENTS:
        raise CatalogueInvalide(f"plus de {MAX_ELEMENTS} éléments.")
    avertissements = []
    en_trop = [0]

    def avert(texte):
        if len(avertissements) < MAX_AVERTISSEMENTS:
            avertissements.append(texte)
        else:
            en_trop[0] += 1

    vus = set()
    propres = []
    for i, e in enumerate(elements):
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"] \
                or not isinstance(e.get("nom"), str):
            raise CatalogueInvalide(f"elements[{i}] doit avoir un « id » et un « nom » textes.")
        if e["id"] in vus:
            raise CatalogueInvalide(f"elements[{i}] : id « {e['id'][:60]} » en double.")
        vus.add(e["id"])
        propres.append({"id": e["id"], "nom": e["nom"], **_nettoyer(e, ELEMENT, f"elements[{i}].", avert)})
    propre = {**_nettoyer(c, RACINE, "", avert), "elements": propres}
    if en_trop[0]:
        avertissements.append(f"… et {en_trop[0]} autres avertissements.")
    return propre, avertissements
