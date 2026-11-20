"""Exécution déportée : ce que Git peut faire dépend du type de projet (catalogue d'actions par genre).

Une entrée de catalogue : `libelle` (texte affiché), `commande` (commande par défaut, vide si on ne la connaît pas),
`produit` (artefact produit, ou None), `consomme` (actions dont elle dépend), `artefact` (chemin publié, ou None),
`lieux` (lieux où elle peut tourner) et `bientot` (texte qui explique un lieu indisponible, ou None).

Logique pure, sans accès disque hors `catalogue_du_projet` et l'accord au serveur (`refus_accord`, qui lit le fichier
du bureau et les réglages enregistrés). Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""
import json
import os
import stat

_CHEMIN_APK = "**/build/outputs/apk/**/*.apk"
_PEU_FIABLE = "peu fiable sur GitHub, utilisez le poste ou le serveur"
_SERVEUR_SEUL = "ne tourne que sur le serveur (accord permanent pour ce projet)"

# Les actions que `deporter` sait servir sur le serveur (tâches d'émulation, `outils/serveur_tache_cli.py`). Une telle
# action ne tourne nulle part ailleurs : pas de défaut au poste, le Directeur la règle sur serveur projet par projet.
SERVIES_AU_SERVEUR = ("recette-emulateur",)

# Le fichier du bureau du Directeur : ses `projets[].chemin` (fichiers de réglages) disent quels projets existent.
BUREAU = os.path.join(os.path.expanduser("~"), "MyIAFactory", "bureau.json")
TAILLE_MAX_REGLAGES = 1024 * 1024
MSG_REGLEZ_SERVEUR = "Réglez le lieu de l'action sur serveur dans le bureau (accord permanent pour ce projet)."
MSG_NON_ENREGISTRE = ("Ce projet n'est pas enregistré dans le bureau (%s ; fichier du bureau : %s) : l'accord permanent "
                      "pour « %s » ne vaut que pour un projet du bureau du Directeur. Ajoutez-le au bureau, puis " +
                      MSG_REGLEZ_SERVEUR[0].lower() + MSG_REGLEZ_SERVEUR[1:])


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


def _lire_json_sur(chemin):
    """Le JSON d'un fichier ordinaire (ni lien, ni dossier, ni périphérique) d'au plus `TAILLE_MAX_REGLAGES` octets ;
    None au moindre ennui (absent, trop gros, illisible, JSON invalide ou trop profond)."""
    try:
        s = os.lstat(chemin)
        if not stat.S_ISREG(s.st_mode) or s.st_size > TAILLE_MAX_REGLAGES:
            return None
        with open(chemin, "rb") as f:
            brut = f.read(TAILLE_MAX_REGLAGES + 1)      # la taille est bornée à la lecture, quoi qu'ait dit lstat
        if len(brut) > TAILLE_MAX_REGLAGES:
            return None
        return json.loads(brut.decode("utf-8-sig"))
    except (OSError, ValueError, MemoryError, RecursionError):
        return None


def _norme(chemin):
    """Un chemin comparable : absolu, liens et alias résolus, casse ignorée sous Windows."""
    return os.path.normcase(os.path.realpath(os.path.abspath(str(chemin))))


def _racine_des_reglages(fichier):
    """Le projet d'un fichier de réglages : son dossier, ou le parent de `.factory`."""
    dossier = os.path.dirname(fichier)
    return os.path.dirname(dossier) if os.path.normcase(os.path.basename(dossier)) == ".factory" else dossier


def reglages_enregistres(racine, bureau=None):
    """Les fichiers de réglages (chemins réels) que le bureau enregistre pour le projet `racine`, dans son ordre ;
    [] si aucun ou si le fichier du bureau est absent, illisible ou abîmé. Les chemins relatifs le sont au bureau."""
    bureau = BUREAU if bureau is None else str(bureau)
    donnees = _lire_json_sur(bureau)
    projets = donnees.get("projets") if isinstance(donnees, dict) else None
    if not isinstance(projets, list):
        return []
    base, cible, trouves = os.path.dirname(os.path.abspath(bureau)), _norme(racine), []
    for entree in projets:
        chemin = entree.get("chemin") if isinstance(entree, dict) else entree
        if not isinstance(chemin, str) or not chemin.strip() or "\x00" in chemin:
            continue
        try:
            reel = os.path.realpath(os.path.join(base, chemin))
            if _norme(_racine_des_reglages(reel)) == cible:
                trouves.append(reel)
        except (OSError, ValueError):
            continue
    return trouves


def refus_accord(racine, action, bureau=None, reglages=None):
    """None si le Directeur a donné son accord permanent pour lancer `action` (servie au serveur) sur le projet
    `racine` ; sinon le message du refus (en français). L'accord ne vaut que pour un projet ENREGISTRÉ dans le bureau
    (`bureau`, par défaut `BUREAU`) et se lit dans le fichier de réglages qu'il enregistre pour ce projet (jamais un
    dossier quelconque, un `.factory` imbriqué ni un autre fichier) ; `reglages` (l'option `--reglages`) n'est admis que
    s'il est ce fichier enregistré. Fichier du bureau absent ou abîmé : refus."""
    if not servie_au_serveur(action, catalogue_du_projet(racine)[1]):
        return "« %s » n'est pas une action servie au serveur pour ce type de projet." % action
    enregistres = reglages_enregistres(racine, bureau)
    if not enregistres:
        return MSG_NON_ENREGISTRE % (racine, BUREAU if bureau is None else bureau, action)
    if reglages is not None:
        enregistres = [r for r in enregistres if _norme(r) == _norme(reglages)]
        if not enregistres:
            return ("--reglages (%s) n'est pas le fichier de réglages que le bureau enregistre pour ce projet : il ne "
                    "vaut pas accord. %s" % (reglages, MSG_REGLEZ_SERVEUR))
    for fichier in enregistres:
        donnees = _lire_json_sur(fichier)
        deport = donnees.get("deport") if isinstance(donnees, dict) else None
        lieux = deport.get("lieux") if isinstance(deport, dict) else None
        if isinstance(lieux, dict) and lieux.get(action) == "serveur":
            return None
    return "« %s » n'est pas réglée sur serveur pour ce projet. %s" % (action, MSG_REGLEZ_SERVEUR)


def accord_serveur(racine, action, bureau=None, reglages=None):
    """Vrai si `refus_accord` ne refuse pas."""
    return refus_accord(racine, action, bureau, reglages) is None


def sans_poste(entree):
    """Vrai pour une action qui ne tourne pas au poste (ex. `recette-emulateur`) : jamais de défaut « poste »."""
    return "poste" not in entree["lieux"]


def actions_exposees(catalogue):
    """La liste `[{id, libelle, lieux, bientot, servie_au_serveur}]` que le bureau affiche pour ce catalogue."""
    return [{"id": nom, "libelle": e["libelle"], "lieux": list(e["lieux"]), "bientot": e["bientot"],
             "servie_au_serveur": servie_au_serveur(nom, catalogue)}
            for nom, e in catalogue.items()]
