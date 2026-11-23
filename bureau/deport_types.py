"""Exécution déportée : ce que Git peut faire dépend du type de projet (catalogue d'actions par genre).

Une entrée de catalogue : `libelle` (texte affiché), `commande` (commande par défaut, vide si on ne la connaît pas),
`produit` (artefact produit, ou None), `consomme` (actions dont elle dépend), `artefact` (chemin publié, ou None),
`lieux` (lieux où elle peut tourner) et `bientot` (texte qui explique un lieu indisponible, ou None).

Logique pure, sans accès disque hors `catalogue_du_projet` et l'accord au serveur (`refus_accord` et `refus_route`, qui
lisent le fichier du bureau et les réglages enregistrés). Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
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
# Les actions que `lancer.py tests` sait ROUTER au serveur (conception § 5.7, `outils/tests_serveur.py`) : elles gardent
# leurs autres lieux (le repli au poste existe) ; l'accord se lit dans les réglages enregistrés du projet, sinon dans
# le défaut du bureau (`refus_route`).
ROUTEES_AU_SERVEUR = ("tests",)

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
        # Course acceptée : entre `lstat` et `open`, le fichier pourrait être remplacé par un lien. Seul qui peut écrire
        # dans le dossier des réglages enregistrés le peut, et il peut de toute façon y écrire le réglage lui-même ;
        # la taille reste bornée à la lecture.
        with open(chemin, "rb") as f:
            brut = f.read(TAILLE_MAX_REGLAGES + 1)
        if len(brut) > TAILLE_MAX_REGLAGES:
            return None
        return json.loads(brut.decode("utf-8-sig"))
    except (OSError, ValueError, MemoryError, RecursionError):
        return None


def _sans_prefixe(chemin):
    """`\\\\?\\C:\\…` ramené à `C:\\…` (même fichier, autre écriture) ; la forme UNC `\\\\?\\UNC\\…` est refusée
    (ValueError) : un partage réseau n'est jamais un projet du poste."""
    c = str(chemin)
    if c[:4] in ("\\\\?\\", "//?/"):
        if c[4:8].upper() in ("UNC\\", "UNC/"):
            raise ValueError("chemin UNC refusé")
        return c[4:]
    return c


def _norme(chemin):
    """Un chemin comparable : préfixe `\\\\?\\` ôté, absolu, liens et alias résolus, casse ignorée sous Windows."""
    return os.path.normcase(_sans_prefixe(os.path.realpath(os.path.abspath(_sans_prefixe(chemin)))))


def _racine_des_reglages(fichier):
    """Le projet d'un fichier de réglages : son dossier, ou le parent de `.factory`."""
    dossier = os.path.dirname(fichier)
    return os.path.dirname(dossier) if os.path.normcase(os.path.basename(dossier)) == ".factory" else dossier


def reglages_enregistres(racine, bureau=None):
    """Les fichiers de réglages que le bureau enregistre pour le projet `racine`, TELS QU'ENREGISTRÉS (chemins absolus
    non résolus, pour que la lecture refuse un fichier en lien), dans son ordre ; [] si aucun ou si le fichier du
    bureau est absent, illisible ou abîmé. Les chemins relatifs le sont au bureau. Le projet d'une entrée est pris sur
    le chemin enregistré, PAS sur sa cible : une entrée dont le fichier mène ailleurs (`.factory` en jonction ou lien,
    `reglages.json` en lien vers un autre projet) est écartée, et le projet visé par le lien n'en devient pas enregistré."""
    bureau = BUREAU if bureau is None else str(bureau)
    donnees = _lire_json_sur(bureau)
    projets = donnees.get("projets") if isinstance(donnees, dict) else None
    if not isinstance(projets, list):
        return []
    try:
        cible = _norme(racine)
    except (OSError, ValueError):
        return []
    base, trouves = os.path.dirname(os.path.abspath(bureau)), []
    for entree in projets:
        chemin = entree.get("chemin") if isinstance(entree, dict) else entree
        if not isinstance(chemin, str) or not chemin.strip() or "\x00" in chemin:
            continue
        try:
            fichier = os.path.abspath(os.path.join(base, _sans_prefixe(chemin)))
            projet = _norme(_racine_des_reglages(fichier))
            if projet != cible:
                continue
            if _norme(_racine_des_reglages(os.path.realpath(fichier))) != projet:
                continue          # le fichier enregistré mène dans un autre projet : jamais d'accord par un lien
            trouves.append(fichier)
        except (OSError, ValueError):
            continue
    return trouves


def refus_accord(racine, action, bureau=None, reglages=None):
    """None si le Directeur a donné son accord permanent pour lancer `action` (servie au serveur) sur le projet
    `racine` ; sinon le message du refus (en français). L'accord ne vaut que pour un projet ENREGISTRÉ dans le bureau
    (`bureau`, par défaut `BUREAU`) et se lit dans le fichier de réglages qu'il enregistre pour ce projet (jamais un
    dossier quelconque, un `.factory` imbriqué ni un autre fichier) ; `reglages` (l'option `--reglages`) n'est admis que
    s'il est ce fichier enregistré. Fichier du bureau absent ou abîmé : refus."""
    enregistres = reglages_enregistres(racine, bureau)      # d'abord : rien n'est lu dans un dossier non enregistré
    if not enregistres:
        return MSG_NON_ENREGISTRE % (racine, BUREAU if bureau is None else bureau, action)
    if not servie_au_serveur(action, catalogue_du_projet(racine)[1]):
        return "« %s » n'est pas une action servie au serveur pour ce type de projet." % action
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


def routee_au_serveur(nom, catalogue):
    """Vrai si `lancer.py tests` sait router l'action `nom` au serveur et que ce catalogue l'y permet."""
    return nom in ROUTEES_AU_SERVEUR and nom in catalogue and "serveur" in catalogue[nom]["lieux"]


def _lieu_ecrit(donnees, action):
    """`(réglé, lieu)` de `action` dans la clé `deport.lieux` d'un JSON déjà lu : une valeur vide ou absente ne règle
    rien (la règle de `deport.lieu_effectif`)."""
    deport = donnees.get("deport") if isinstance(donnees, dict) else None
    lieux = deport.get("lieux") if isinstance(deport, dict) else None
    if not isinstance(lieux, dict) or not lieux.get(action):
        return False, None
    return True, lieux[action]


def _contient(racine, cible):
    return cible == racine or cible.startswith(racine if racine.endswith(os.sep) else racine + os.sep)


def _plus_longue_entree(cible, bureau):
    """`(racine normée, entrée valide)` de l'entrée du bureau à la racine la plus longue qui contient `cible` (normée),
    TOUTES entrées comptées, même celles dont le fichier mène ailleurs (lien, jonction) ; None si aucune. Une entrée
    illisible (chemin vide, erreur de résolution) qui pourrait contenir `cible` rend `("?", False)`."""
    donnees = _lire_json_sur(bureau)
    projets = donnees.get("projets") if isinstance(donnees, dict) else None
    if not isinstance(projets, list):
        return None
    base, meilleur = os.path.dirname(os.path.abspath(bureau)), None
    for entree in projets:
        chemin = entree.get("chemin") if isinstance(entree, dict) else entree
        if not isinstance(chemin, str) or not chemin.strip() or "\x00" in chemin:
            continue
        try:
            fichier = os.path.abspath(os.path.join(base, _sans_prefixe(chemin)))
            racine = _norme(_racine_des_reglages(fichier))
            valide = _norme(_racine_des_reglages(os.path.realpath(fichier))) == racine
        except (OSError, ValueError):
            return "?", False      # on ne sait pas si elle contient `cible` : jamais d'accord par défaut d'un parent
        if _contient(racine, cible) and (meilleur is None or len(racine) > len(meilleur[0])):
            meilleur = (racine, valide)
    return meilleur


def _racine_trop_large(racine):
    """Vrai pour une racine de lecteur, le dossier personnel ou un de ses parents : jamais l'accord pour tout dessous."""
    if os.path.dirname(racine) == racine:
        return True
    try:
        maison = _norme(os.path.expanduser("~"))
    except (OSError, ValueError):
        return True
    return _contient(racine, maison)


def refus_route(dossier, action, bureau=None):
    """None si `action` (routée, ex. `tests`) lancée depuis `dossier` a l'accord du Directeur pour partir au serveur ;
    sinon le message du refus (en français). Le projet est celui du bureau qui CONTIENT `dossier`
    (`tests_mesures.projet_enregistre`, le plus long : une copie de travail `.claude/worktrees/x` rangée sous le projet
    compte comme lui ; chemins résolus, liens et jonctions compris : un lien vers un dossier non enregistré n'est pas
    le projet). Refus aussi quand l'entrée la plus longue qui contient `dossier` est écartée (son fichier de réglages
    ou son `.factory` mène ailleurs) : jamais l'accord d'un projet parent plus court à sa place ; et quand la racine du
    projet est une racine de lecteur, le dossier personnel ou un de ses parents (un tel « projet » couvrirait tout).
    L'accord se lit dans les SEULS fichiers de réglages que le bureau enregistre pour ce projet (jamais `--reglages`,
    un `.factory` imbriqué ni un fichier du dossier de travail) ; s'ils ne règlent pas l'action, dans le défaut du
    bureau (`deport.lieux`, écrit par le seul Directeur). Plusieurs fichiers enregistrés qui la règlent doivent tous
    dire serveur. Un fichier enregistré illisible (absent, en lien, abîmé) refuse : son réglage propre n'est jamais
    remplacé par le défaut. Fichier du bureau absent ou abîmé : refus."""
    bureau = BUREAU if bureau is None else str(bureau)
    if action not in ROUTEES_AU_SERVEUR:
        return "« %s » n'est pas une action routée au serveur." % action
    from . import tests_mesures      # ici : `tests_mesures` importe ce module
    try:
        cible = _norme(dossier)
        plus_longue = _plus_longue_entree(cible, bureau)
    except (OSError, ValueError):
        return MSG_NON_ENREGISTRE % (dossier, bureau, action)
    if plus_longue is None:
        return MSG_NON_ENREGISTRE % (dossier, bureau, action)
    if not plus_longue[1]:
        return ("L'entrée du bureau qui contient %s a des réglages qui mènent ailleurs (lien ou jonction) : pas de tests "
                "au serveur, ni par un projet parent. %s" % (dossier, MSG_REGLEZ_SERVEUR))
    trouve = tests_mesures.projet_enregistre(dossier, bureau)
    if trouve is None or _norme(trouve[1]) != plus_longue[0]:
        return MSG_NON_ENREGISTRE % (dossier, bureau, action)
    racine = str(trouve[1])
    if _racine_trop_large(plus_longue[0]):
        return ("Le projet enregistré %s est une racine de lecteur ou contient le dossier personnel : il ne vaut pas "
                "accord pour tout ce qu'il contient. Enregistrez le dossier du projet lui-même." % racine)
    if not routee_au_serveur(action, catalogue_du_projet(racine)[1]):
        return "« %s » ne tourne pas au serveur pour ce type de projet." % action
    enregistres = reglages_enregistres(racine, bureau)
    if not enregistres:
        return MSG_NON_ENREGISTRE % (dossier, bureau, action)
    regles = []
    for fichier in enregistres:
        donnees = _lire_json_sur(fichier)
        if not isinstance(donnees, dict):
            return ("Les réglages enregistrés de ce projet (%s) sont illisibles : pas de tests au serveur. %s"
                    % (fichier, MSG_REGLEZ_SERVEUR))
        regle, lieu = _lieu_ecrit(donnees, action)
        if regle:
            regles.append(lieu)
    if regles:
        autres = [l for l in regles if l != "serveur"]
        if not autres:
            return None
        return ("« %s » est réglée sur « %s » pour ce projet, pas sur serveur. %s"
                % (action, autres[0], MSG_REGLEZ_SERVEUR))
    regle, lieu = _lieu_ecrit(_lire_json_sur(bureau), action)
    if regle and lieu == "serveur":
        return None
    return ("« %s » n'est réglée sur serveur ni pour ce projet ni par défaut au bureau. %s"
            % (action, MSG_REGLEZ_SERVEUR))


def sans_poste(entree):
    """Vrai pour une action qui ne tourne pas au poste (ex. `recette-emulateur`) : jamais de défaut « poste »."""
    return "poste" not in entree["lieux"]


def actions_exposees(catalogue):
    """La liste `[{id, libelle, lieux, bientot, servie_au_serveur}]` que le bureau affiche pour ce catalogue."""
    return [{"id": nom, "libelle": e["libelle"], "lieux": list(e["lieux"]), "bientot": e["bientot"],
             "servie_au_serveur": servie_au_serveur(nom, catalogue)}
            for nom, e in catalogue.items()]
