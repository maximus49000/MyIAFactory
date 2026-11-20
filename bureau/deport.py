"""Exécution déportée : lieux d'exécution des actions et dépendances entre elles (logique pure, sans accès disque).

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""

from .deport_types import GENERIQUE, SERVIES_AU_SERVEUR, catalogue_union, sans_poste

# Vue d'ensemble du catalogue générique (compatibilité) : ce que chaque action produit et consomme.
ACTIONS = {nom: {"produit": e["produit"], "consomme": list(e["consomme"])} for nom, e in GENERIQUE.items()}
LIEUX = ("poste", "github", "serveur")
LIEUX_ETAPE_1 = ("poste", "github")
# une action qui ne tourne pas au poste (la recette sur émulateur) n'a pas de défaut : non réglée, elle est refusée
LIEUX_PAR_DEFAUT = {action: "poste" for action, e in GENERIQUE.items() if not sans_poste(e)}

_NOMS_LIEUX = {"poste": "poste", "github": "GitHub", "serveur": "serveur"}


def valider_lieux(lieux, etape_serveur=False, catalogue=GENERIQUE):
    """Vérifie un dictionnaire {action: lieu} et le renvoie copié ; lève ValueError (message en français).
    Seules les actions du catalogue existent ; un lieu que l'action n'offre pas est refusé avec son explication. Le
    serveur n'est permis (hors `etape_serveur`) qu'aux actions que `deporter` y sert (`SERVIES_AU_SERVEUR`)."""
    if not isinstance(lieux, dict):
        raise ValueError("Les lieux doivent être un dictionnaire {action: lieu}.")
    permis = LIEUX if etape_serveur else LIEUX_ETAPE_1
    for action, lieu in lieux.items():
        if action not in catalogue:
            if action in catalogue_union():
                raise ValueError("L'action « %s » n'existe pas pour ce type de projet (attendu : %s)."
                                 % (action, ", ".join(catalogue)))
            raise ValueError("Action inconnue : « %s » (attendu : %s)." % (action, ", ".join(catalogue)))
        if lieu not in LIEUX:
            raise ValueError("Lieu inconnu pour « %s » : « %s » (attendu : %s)." % (action, lieu, ", ".join(LIEUX)))
        entree = catalogue[action]
        if lieu not in entree["lieux"]:
            raison = entree["bientot"] or "ce lieu n'est pas prévu pour ce type de projet"
            raise ValueError("« %s » ne tourne pas au lieu « %s » : %s." % (action, _NOMS_LIEUX[lieu], raison))
        if lieu not in permis and not (lieu == "serveur" and action in SERVIES_AU_SERVEUR):
            raise ValueError("Le lieu « %s » n'est pas encore disponible pour « %s »." % (lieu, action))
    return dict(lieux)


def lieu_effectif(global_, projet, action, catalogue=None):
    """Lieu d'une action : la surcharge du projet l'emporte, sinon le réglage global, sinon le poste.

    Avec `catalogue`, une action qui ne tourne pas au poste (la recette sur émulateur, au seul serveur) ne prend que le
    réglage du projet (accord permanent donné projet par projet, jamais hérité du bureau) ; sans lui, ou s'il n'est
    pas un lieu de l'action (écrit à la main), None (non réglée : refusée)."""
    if catalogue is not None and action in catalogue and sans_poste(catalogue[action]):
        lieu = (projet or {}).get(action)
        return lieu if isinstance(lieu, str) and lieu in catalogue[action]["lieux"] else None
    for source in (projet, global_):
        if source and source.get(action):
            return source[action]
    return "poste"


def a_attendre(lieux, action, catalogue=GENERIQUE):
    """Les productions (noms d'action) d'un autre lieu que celui de `action` dont elle dépend."""
    lieu = lieux.get(action, "poste")
    return [dep for dep in catalogue[action]["consomme"] if lieux.get(dep, "poste") != lieu]


def _nom_lieu(lieu):
    """Le nom affiché d'un lieu ; une valeur inconnue (réglage abîmé) est dite telle quelle, sans lever."""
    return _NOMS_LIEUX.get(lieu, str(lieu)) if isinstance(lieu, str) else str(lieu)


def avertissements(lieux, catalogue=GENERIQUE):
    """Un texte par action qui devra attendre une production venue d'un autre lieu. Une action qui ne tourne pas au
    poste (la recette sur émulateur) n'en a pas : elle prend l'APK là où il est produit, la chaîne n'a pas à suivre."""
    textes = []
    for action in catalogue:
        if sans_poste(catalogue[action]):
            continue
        for dep in a_attendre(lieux, action, catalogue):
            produit = (catalogue[dep]["produit"] or dep).upper()
            ici = _nom_lieu(lieux.get(action, "poste"))
            ailleurs = _nom_lieu(lieux.get(dep, "poste"))
            textes.append("« %s » tourne au lieu « %s » mais attendra l'%s produit par %s : "
                          "mettez la chaîne entière au même lieu pour éviter cette attente."
                          % (action, ici, produit, ailleurs))
    return textes
