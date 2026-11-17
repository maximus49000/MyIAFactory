"""Exécution déportée : ce que Git peut faire dépend du type de projet (catalogue d'actions par genre).

Une entrée de catalogue : `libelle` (texte affiché), `commande` (commande par défaut, vide si on ne la connaît pas),
`produit` (artefact produit, ou None), `consomme` (actions dont elle dépend), `artefact` (chemin publié, ou None),
`lieux` (lieux où elle peut tourner) et `bientot` (texte qui explique un lieu indisponible, ou None).

Logique pure, sans accès disque hors `catalogue_du_projet`. Reste compatible Python 3.9 : le code déporté est aussi
lancé par les agents.
"""
import json
import os

_CHEMIN_APK = "**/build/outputs/apk/**/*.apk"
_PEU_FIABLE = "peu fiable sur GitHub, utilisez le poste ou le serveur"


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
        except (OSError, ValueError):
            continue
        genre = donnees.get("genre") if isinstance(donnees, dict) else None
        if isinstance(genre, str) and genre in CATALOGUES:
            return genre, CATALOGUES[genre]
    return "generique", GENERIQUE


def actions_exposees(catalogue):
    """La liste `[{id, libelle, lieux, bientot}]` que le bureau affiche pour ce catalogue."""
    return [{"id": nom, "libelle": e["libelle"], "lieux": list(e["lieux"]), "bientot": e["bientot"]}
            for nom, e in catalogue.items()]
