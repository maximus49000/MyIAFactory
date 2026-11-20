"""Exécution déportée : ce que Git peut faire dépend du type de projet (catalogue d'actions par genre).

Une entrée de catalogue : `libelle` (texte affiché), `commande` (commande par défaut, vide si on ne la connaît pas),
`produit` (artefact produit, ou None), `consomme` (actions dont elle dépend), `artefact` (chemin publié, ou None),
`lieux` (lieux où elle peut tourner) et `bientot` (texte qui explique un lieu indisponible, ou None).

Logique pure, sans accès disque hors `catalogue_du_projet` et `accord_serveur`. Reste compatible Python 3.9 : le code déporté est aussi
lancé par les agents.
"""
import json
import os

_CHEMIN_APK = "**/build/outputs/apk/**/*.apk"
_PEU_FIABLE = "peu fiable sur GitHub, utilisez le poste ou le serveur"
_SERVEUR_SEUL = "ne tourne que sur le serveur (accord permanent pour ce projet)"

# Les actions que `deporter` sait servir sur le serveur (tâches d'émulation, `outils/serveur_tache_cli.py`). Une telle
# action ne tourne nulle part ailleurs : pas de défaut au poste, le Directeur la règle sur serveur projet par projet.
SERVIES_AU_SERVEUR = ("recette-emulateur",)


def _entree(libelle, commande="", produit=None, consomme=(), artefact=None, lieux=("poste", "github", "serveur"),
            bientot=None):
    return {"libelle": libelle, "commande": commande, "produit": produit, "consomme": list(consomme),
            "artefact": artefact, "lieux": list(lieux), "bientot": bientot}


# Le catalogue d'un projet dont on ne connaît pas le type : les quatre actions d'origine, sans commande par défaut.
GENERIQUE = {
    "apk": _entree("APK", produit="apk", artefact=_CHEMIN_APK),
    "tests": _entree("Tests", consomme=["apk"]),
    "emulateur": _entree("Émulateur", consomme=["apk"], lieux=("poste", "serveur"), bientot=_PEU_FIABLE),
    "charge": _entree("Charge", consomme=["apk"]),
    "recette-emulateur": _entree("Recette sur émulateur", consomme=["apk"], lieux=("serveur",), bientot=_SERVEUR_SEUL),
}

# Application Android native (Gradle) : les tests se compilent depuis les sources et n'ont pas besoin de l'APK ;
# pas de test de charge (aucun serveur).
ANDROID = {
    "apk": _entree("Générer l'APK", "./gradlew assembleDebug", produit="apk",
                   artefact="app/build/outputs/apk/debug/*.apk", lieux=("poste", "github")),
    "tests": _entree("Tests unitaires", "./gradlew testDebugUnitTest", lieux=("poste", "github")),
    "lint": _entree("Analyse lint", "./gradlew lintDebug", lieux=("poste", "github")),
    "emulateur": _entree("Tests sur émulateur", "./gradlew connectedDebugAndroidTest", lieux=("poste",),
                         bientot=_PEU_FIABLE),
    "release": _entree("APK signé (release)", "./gradlew assembleRelease", produit="apk-release", lieux=("poste",),
                       bientot="demande vos clés de signature dans les secrets GitHub, que vous devez saisir "
                               "vous-même"),
    # l'APK installé sur un émulateur du serveur, piloté par un scénario (recette) ou par l'agent ; `emulateur` (les
    # tests instrumentés Gradle) reste au poste
    "recette-emulateur": _entree("Recette sur émulateur", consomme=["apk"], lieux=("serveur",), bientot=_SERVEUR_SEUL),
}

CATALOGUES = {"application-mobile-android": ANDROID}


def catalogue_union():
    """Toutes les actions de tous les catalogues (lieux réunis) : la validation permissive d'un réglage sans projet,
    comme le défaut global du bureau, qui ne refuse que les noms inconnus partout."""
    union = {}
    for catalogue in (GENERIQUE, *CATALOGUES.values()):
        for nom, entree in catalogue.items():
            if nom not in union:
                union[nom] = dict(entree, consomme=list(entree["consomme"]), lieux=list(entree["lieux"]))
            else:
                union[nom]["lieux"] += [x for x in entree["lieux"] if x not in union[nom]["lieux"]]
    return union


def catalogue_du_projet(dossier):
    """`(genre, catalogue)` du projet : le genre est lu dans `<dossier>/.factory/factory.json` ou
    `<dossier>/factory.json` ; absent, illisible ou inconnu, `("generique", GENERIQUE)`."""
    for chemin in (os.path.join(str(dossier), ".factory", "factory.json"), os.path.join(str(dossier), "factory.json")):
        try:
            with open(chemin, encoding="utf-8-sig") as f:
                donnees = json.load(f)
        except (OSError, ValueError, RecursionError):      # illisible ou trop profond : le générique
            continue
        genre = donnees.get("genre") if isinstance(donnees, dict) else None
        if isinstance(genre, str) and genre in CATALOGUES:
            return genre, CATALOGUES[genre]
    return "generique", GENERIQUE


def racine_du_projet(dossier):
    """Le dossier du projet pour `dossier` (souvent un sous-dossier où travaille un agent, ex. `app/`) : le plus
    proche (lui-même, puis ses parents) qui contient `.factory/`, sans dépasser la racine du dépôt git ni monter au
    dossier personnel ; à défaut, `dossier` lui-même (résolu)."""
    try:
        depart = os.path.abspath(str(dossier))
        if os.path.basename(depart) == ".factory":
            return os.path.dirname(depart)
        maison = os.path.normcase(os.path.abspath(os.path.expanduser("~")))
        d = depart
        while True:
            if os.path.isdir(os.path.join(d, ".factory")):
                return d
            if os.path.exists(os.path.join(d, ".git")):
                break                      # la racine du dépôt : le projet n'est pas au-dessus
            parent = os.path.dirname(d)
            if parent == d or os.path.normcase(parent) == maison:
                break
            d = parent
        return depart
    except (OSError, ValueError):
        return str(dossier)


def servie_au_serveur(nom, catalogue):
    """Vrai si `deporter` sait servir l'action `nom` sur le serveur et que ce catalogue l'y permet."""
    return nom in SERVIES_AU_SERVEUR and nom in catalogue and "serveur" in catalogue[nom]["lieux"]


def reglages_du_projet(racine):
    """Le seul fichier où vit l'accord permanent d'un projet : `<racine>/.factory/reglages.json`."""
    return os.path.join(str(racine), ".factory", "reglages.json")


def accord_serveur(racine, action):
    """Vrai si le projet `racine` a réglé `action` (servie au serveur) sur `serveur` dans SES réglages
    (`reglages_du_projet`) : l'accord permanent du Directeur pour ce projet et cette action. Jamais hérité du bureau,
    jamais lu dans un autre fichier ; faux au moindre ennui (fichier absent, illisible, valeur autre)."""
    if not servie_au_serveur(action, catalogue_du_projet(racine)[1]):
        return False
    try:
        with open(reglages_du_projet(racine), encoding="utf-8-sig") as f:
            donnees = json.load(f)
    except (OSError, ValueError, RecursionError):
        return False
    deport = donnees.get("deport") if isinstance(donnees, dict) else None
    lieux = deport.get("lieux") if isinstance(deport, dict) else None
    return isinstance(lieux, dict) and lieux.get(action) == "serveur"


def sans_poste(entree):
    """Vrai pour une action qui ne tourne pas au poste (ex. `recette-emulateur`) : jamais de défaut « poste »."""
    return "poste" not in entree["lieux"]


def actions_exposees(catalogue):
    """La liste `[{id, libelle, lieux, bientot, servie_au_serveur}]` que le bureau affiche pour ce catalogue."""
    return [{"id": nom, "libelle": e["libelle"], "lieux": list(e["lieux"]), "bientot": e["bientot"],
             "servie_au_serveur": servie_au_serveur(nom, catalogue)}
            for nom, e in catalogue.items()]
