"""Registre des réglages et résolution à trois niveaux : projet > type > global > défaut (logique pure).

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents. N'importe que `bureau.deport`.
Origine d'une valeur : `defaut`, `global`, `type:<genre>` ou `projet`.
"""

from dataclasses import dataclass

from . import deport

NIVEAUX = ("global", "type", "projet")


@dataclass(frozen=True)
class Reglage:
    id: str
    section: str
    libelle: str
    aide: str
    forme: str          # "booleen" | "lieu"
    niveaux: tuple      # sous-ensemble de NIVEAUX où ce réglage peut être posé
    defaut: object
    cle: str            # clé à plat dans le JSON du projet (« lecons_auto »)


# les réglages booléens sont déclarés ici (phase suivante) ; les lieux sont dérivés du catalogue
REGISTRE = ()

_ABSENT = object()


def _dict(valeur):
    return valeur if isinstance(valeur, dict) else {}


def _niveau_type(bureau, genre):
    return _dict(_dict(_dict(bureau).get("types")).get(genre)) if genre else {}


def valeur_effective(r, projet, bureau, genre):
    """`(valeur, origine)` d'un réglage : projet, puis type (si le genre est connu), puis global, puis défaut.
    Un niveau que le réglage ne permet pas est ignoré."""
    projet, bureau = _dict(projet), _dict(bureau)
    if "projet" in r.niveaux and r.cle in projet:
        return projet[r.cle], "projet"
    if genre and "type" in r.niveaux:
        valeurs = _dict(_niveau_type(bureau, genre).get("reglages"))
        if r.id in valeurs:
            return valeurs[r.id], "type:" + genre
    if "global" in r.niveaux:
        valeurs = _dict(bureau.get("reglages"))
        if r.id in valeurs:
            return valeurs[r.id], "global"
    return r.defaut, "defaut"


def _lieux_valides(lieux):
    return {a: v for a, v in _dict(lieux).items() if isinstance(v, str) and v in deport.LIEUX}


def lieux_du_type(bureau, genre):
    """Les lieux posés au niveau type dans le fichier du bureau tel qu'il est écrit (`types.<genre>.deport.lieux`),
    `{action: lieu}` ; tout ce qui est abîmé (objet manquant, valeur qui n'est pas un lieu) est ignoré. `{}` sans genre
    ou pour le genre « generique » (pas de niveau type). Pour les outils qui lancent les actions (`deporter`, la
    consigne de départ) : la même lecture que la page Réglages."""
    if not genre or genre == "generique":
        return {}
    gardes = {}
    for action, lieu in _lieux_valides(_dict(_dict(_niveau_type(bureau, genre).get("deport"))).get("lieux")).items():
        try:      # comme `reglages.lire_bureau` : un lieu que le bureau n'accepte pas est écarté
            deport.valider_lieux({action: lieu}, catalogue=deport.catalogue_union())
        except ValueError:
            continue
        gardes[action] = lieu
    return gardes


def lieux_effectifs(catalogue, projet, bureau, genre):
    """Pour chaque action du catalogue, `(lieu, origine)`. L'action au seul serveur (recette sur émulateur) ne prend
    que le niveau projet (sinon `(None, "defaut")`). `bureau["deport"]["lieux"]` est le niveau global tel qu'écrit
    (lieux explicites seulement) ; une action absente n'y est pas réglée."""
    projet, bureau = _dict(projet), _dict(bureau)
    du_projet = _lieux_valides(_dict(projet.get("deport")).get("lieux"))
    du_type = lieux_du_type(bureau, genre)
    global_ = _lieux_valides(_dict(bureau.get("deport")).get("lieux"))
    resultat = {}
    for action, entree in catalogue.items():
        lieu = deport.lieu_effectif(global_, du_projet, action, catalogue, du_type)
        if deport.sans_poste(entree):
            origine = "projet" if lieu is not None else "defaut"
        elif du_projet.get(action) == lieu:
            origine = "projet"
        elif du_type.get(action) == lieu:
            origine = "type:" + genre
        elif global_.get(action) == lieu:
            origine = "global"
        else:
            origine = "defaut"
        resultat[action] = (lieu, origine)
    return resultat
