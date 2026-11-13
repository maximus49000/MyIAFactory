"""Les règles du projet : une liste courte de règles que le Directeur a retenues pour CE projet.

Un fichier JSON du projet, à côté du fichier de factory (`.factory/regles-projet.json`) :
`[{id, texte (1 à 500 caractères), cree_le, modifie_le?, origine?: {decision, agent}}]`. Il n'est écrit que par
`lancer regles` (ajouter, modifier, supprimer) ; la skill n'en garde rien (une règle appartient au projet, jamais à la
mémoire de la skill : aucun contrôle de mots interdits, rien n'en sort du dépôt du projet).

Les règles sont transmises en tête de chaque départ d'agent et de chaque jugement qui propose un workflow, et rappelées
au Directeur quand une demande d'accord d'un agent les touche (`touchees`). Rien n'est jamais refusé d'office.
"""
import json
import os
import re
import unicodedata
from pathlib import Path

from orchestrateur import suivi as su

FICHIER = "regles-projet.json"
MAX_TEXTE = 500                # une règle tient sur quelques lignes
MAX_REGLES = 40                # au-delà, la liste ne se lit plus (et coûterait à chaque départ d'agent)
MAX_EN_TETE = 2400             # la place que les règles prennent au plus dans un message de départ
MAX_TOUCHEES = 3               # les règles rappelées au plus pour une demande d'accord
ENTETE = "Règles du projet, à respecter"
OPERATIONS = ("ajouter", "modifier", "supprimer")


def chemin(f):
    """Le fichier des règles du projet : à côté du fichier de factory."""
    return Path(f["chemin"]).parent / FICHIER


def _valide(x):
    return (isinstance(x, dict) and isinstance(x.get("id"), str) and re.fullmatch(r"r[0-9]+", x["id"])
            and isinstance(x.get("texte"), str) and x["texte"].strip() and len(x["texte"]) <= MAX_TEXTE)


def lire(f):
    """Les règles du projet (une liste vide si le fichier manque ou est illisible ; une entrée invalide est ignorée)."""
    try:
        d = json.loads(chemin(f).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    return [x for x in d if _valide(x)] if isinstance(d, list) else []


def _ecrire(f, regles):
    c = chemin(f)
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_name(c.name + ".tmp")
    tmp.write_text(json.dumps(regles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, c)


def _texte(v):
    if not isinstance(v, str) or not v.strip():
        raise ValueError("« texte » est obligatoire (la règle, en clair).")
    v = " ".join(v.split())
    if len(v) > MAX_TEXTE:
        raise ValueError(f"Une règle tient en {MAX_TEXTE} caractères au plus.")
    return v


def _origine(o):
    if o is None:
        return None
    if (not isinstance(o, dict) or not all(isinstance(o.get(c), str) and o[c].strip() and len(o[c]) <= 80
                                          for c in ("decision", "agent"))):
        raise ValueError("« origine » est {decision, agent} (textes courts).")
    return {"decision": o["decision"], "agent": o["agent"]}


def appliquer(f, operation, id_=None, texte=None, origine=None, quand=None):
    """Ajoute, modifie ou supprime une règle ; rend la règle touchée. Lève `ValueError` sur un refus. Ajouter deux fois
    le même texte n'en crée qu'une (`deja`)."""
    if operation not in OPERATIONS:
        raise ValueError("« operation » doit valoir ajouter, modifier ou supprimer.")
    regles = lire(f)
    if operation == "ajouter":
        texte, origine = _texte(texte), _origine(origine)
        deja = next((x for x in regles if x["texte"].casefold() == texte.casefold()), None)
        if deja:
            return deja, True
        if len(regles) >= MAX_REGLES:
            raise ValueError(f"Le projet a déjà {MAX_REGLES} règles : supprimez-en une avant d'en ajouter.")
        n = max([int(x["id"][1:]) for x in regles] or [0]) + 1
        r = {"id": f"r{n}", "texte": texte, "cree_le": quand or su.maintenant()}
        if origine:
            r["origine"] = origine
        regles.append(r)
        _ecrire(f, regles)
        return r, False
    r = next((x for x in regles if x["id"] == id_), None)
    if r is None:
        raise ValueError(f"Règle inconnue « {id_} ».")
    if operation == "modifier":
        r["texte"], r["modifie_le"] = _texte(texte), quand or su.maintenant()
    else:
        regles.remove(r)
    _ecrire(f, regles)
    return r, False


def en_tete(regles):
    """« Règles du projet, à respecter : » puis une ligne par règle, au plus `MAX_EN_TETE` caractères ; vide sans règle.
    `regles` : des règles `{texte}` ou des textes."""
    textes = [x["texte"] if isinstance(x, dict) else x for x in regles or []]
    if not textes:
        return ""
    lignes, taille = [], 0
    for t in textes:
        if taille + len(t) + 3 > MAX_EN_TETE:
            break
        lignes.append(f"- {t}")
        taille += len(t) + 3
    return f"## {ENTETE} :\n" + "\n".join(lignes)


# --- Le rappel : une règle est « touchée » par une demande d'accord quand elles partagent assez de mots.
# Correspondance simple, documentée (docs/installation.md) : on compare les racines (les 4 premières lettres, sans
# accents ni casse) des mots de 4 lettres ou plus, hors mots vides, avec quelques synonymes ; la règle est touchée quand la demande partage au
# moins 2 de ces racines avec elle (1 si la règle n'en a qu'une). Un rappel, jamais un refus.
MOTS_VIDES = frozenset("""
pour dans avec sans cette cela celui celle ceux elle elles ils leur leurs vous nous votre notre tout tous toute toutes
plus moins tres aussi comme mais donc alors ainsi entre sous vers chez dont quand lors apres avant depuis pendant
etre avoir faire fait faut peut doit sont sera ete etes ont avait pas jamais aucun aucune ni une des les aux par sur
que qui quoi quel quelle ce ces son ses mon mes ton tes notamment seulement meme chaque autre autres
""".split())


def _plat(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte.casefold()) if unicodedata.category(c) != "Mn")


# Quelques mots qui parlent de la même chose se ramènent à une seule racine : un téléphone branché, `adb`, le débogage USB
# ou un « appareil physique » sont le même sujet.
SYNONYMES = {m: "appa" for m in ("telephone", "smartphone", "phone", "mobile", "device", "devices", "appareil", "appareils",
                                 "adb", "usb")}


def racines(texte):
    """Les racines (4 lettres) des mots significatifs d'un texte (les synonymes de `SYNONYMES` ont la même)."""
    mots = re.findall(r"[a-z0-9]+", _plat(texte or ""))
    return {SYNONYMES.get(m) or m[:4] for m in mots if (len(m) >= 4 or m in SYNONYMES) and m not in MOTS_VIDES}


def touchees(regles, *textes):
    """Les règles (au plus `MAX_TOUCHEES`) que la demande (les `textes` donnés) touche."""
    demande = set()
    for t in textes:
        if isinstance(t, str):
            demande |= racines(t)
    sortie = []
    for r in regles or []:
        cles = racines(r["texte"])
        if cles and len(cles & demande) >= min(2, len(cles)):
            sortie.append(r)
    return sortie[:MAX_TOUCHEES]


# Le sens d'une règle : « Autorisé : … » (ou une réponse « … : Oui, … » retenue) autorise ; « Pas de … », « Interdit »,
# « Jamais », « Ne pas » interdisent. Une règle sans sens clair n'est qu'un rappel.
_AUTORISE = re.compile(r"^\s*autoris[ée]+s?\s*:")
_OUI_FINAL = re.compile(r":\s*(oui|j'accepte|d'accord|accepte)\b[^:]*$")
_INTERDIT = re.compile(r"^\s*(pas de|pas d'|interdit|jamais|ne pas|ne jamais|refus)")


def sens(texte):
    """`"autorise"`, `"interdit"` ou `None` (un simple rappel)."""
    t = (texte or "").casefold()
    if _INTERDIT.search(t):
        return "interdit"
    if _AUTORISE.search(t) or _OUI_FINAL.search(t):
        return "autorise"
    return None


def couvre(regle, *textes):
    """La règle couvre la demande, plus fortement que `touchees` : au moins 3 de ses racines, et 60 % d'entre elles, sont
    dans la demande. Sert à donner un accord d'office ; un simple rappel se contente de `touchees`."""
    demande = set()
    for t in textes:
        if isinstance(t, str):
            demande |= racines(t)
    cles = racines(re.sub(r"^\s*autoris[ée]+s?\s*:", "", regle["texte"], flags=re.I))
    commun = len(cles & demande)
    return bool(cles) and commun >= 3 and commun * 10 >= 6 * len(cles)
