"""Exécution déportée : lieux d'exécution des actions et dépendances entre elles (logique pure, sans accès disque).

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""

# Chaque type d'action : ce qu'elle produit (un artefact) et ce qu'elle consomme (les actions dont elle dépend).
ACTIONS = {
    "apk": {"produit": "apk", "consomme": []},
    "tests": {"produit": None, "consomme": ["apk"]},
    "emulateur": {"produit": None, "consomme": ["apk"]},
    "charge": {"produit": None, "consomme": ["apk"]},
}
LIEUX = ("poste", "github", "serveur")
LIEUX_ETAPE_1 = ("poste", "github")
LIEUX_PAR_DEFAUT = {action: "poste" for action in ACTIONS}

_NOMS_LIEUX = {"poste": "poste", "github": "GitHub", "serveur": "serveur"}
_PRODUITS = {nom: a["produit"] for nom, a in ACTIONS.items() if a["produit"]}


def valider_lieux(lieux, etape_serveur=False):
    """Vérifie un dictionnaire {action: lieu} et le renvoie copié ; lève ValueError (message en français)."""
    if not isinstance(lieux, dict):
        raise ValueError("Les lieux doivent être un dictionnaire {action: lieu}.")
    permis = LIEUX if etape_serveur else LIEUX_ETAPE_1
    for action, lieu in lieux.items():
        if action not in ACTIONS:
            raise ValueError("Action inconnue : « %s » (attendu : %s)." % (action, ", ".join(ACTIONS)))
        if lieu not in LIEUX:
            raise ValueError("Lieu inconnu pour « %s » : « %s » (attendu : %s)." % (action, lieu, ", ".join(LIEUX)))
        if action == "emulateur" and lieu == "github":
            raise ValueError("L'émulateur est peu fiable sur GitHub : utilisez le poste ou le serveur.")
        if lieu not in permis:
            raise ValueError("Le lieu « %s » n'est pas encore disponible pour « %s »." % (lieu, action))
    return dict(lieux)


def lieu_effectif(global_, projet, action):
    """Lieu d'une action : la surcharge du projet l'emporte, sinon le réglage global, sinon le poste."""
    for source in (projet, global_):
        if source and source.get(action):
            return source[action]
    return "poste"


def a_attendre(lieux, action):
    """Les productions (noms d'action) d'un autre lieu que celui de `action` dont elle dépend."""
    lieu = lieux.get(action, "poste")
    return [dep for dep in ACTIONS[action]["consomme"] if lieux.get(dep, "poste") != lieu]


def avertissements(lieux):
    """Un texte par action qui devra attendre une production venue d'un autre lieu."""
    textes = []
    for action in ACTIONS:
        for dep in a_attendre(lieux, action):
            produit = _PRODUITS.get(dep, dep).upper()
            ici = _NOMS_LIEUX[lieux.get(action, "poste")]
            ailleurs = _NOMS_LIEUX[lieux.get(dep, "poste")]
            textes.append("« %s » tourne au lieu « %s » mais attendra l'%s produit par %s : "
                          "mettez la chaîne entière au même lieu pour éviter cette attente."
                          % (action, ici, produit, ailleurs))
    return textes
