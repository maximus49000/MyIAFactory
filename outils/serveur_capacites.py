"""Catalogue des capacités installables sur un serveur distant générique : données et logique pures (ni SSH ni E/S).

Chaque capacité nomme l'étape distante du script `mise_en_place.sh` qui l'installe (`etape`), ses dépendances et une
sonde SHELL strictement en lecture seule (code 0 = présente). Les étapes `android_build`, `android_emulateur` et
`unity_cli` sont créées par un autre morceau du plan : le catalogue ne fait que les nommer.

`taille_go` et `duree_min` sont des ESTIMATIONS tirées de nos installations réelles (espace disque en Go, durée en minutes),
pas des garanties : elles servent à chiffrer une proposition avant validation.

La couche de sonde est la source de vérité : elle sonde TOUTES les capacités indépendamment et fournit l'ensemble
`installees` explicite ; `ordre_installation` ne déduit rien d'une capacité installée (aucune dépendance implicite).

Limites connues des sondes (lecture seule, sans sudo) : celle du durcissement ne voit pas le pare-feu (ufw), configuré après
le fichier sshd ; celle de la base vérifie la présence du binaire docker, pas que son démon tourne.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable


@dataclass(frozen=True)
class Capacite:
    id: str
    libelle: str
    depend: tuple
    etape: str
    sonde: str
    taille_go: float
    duree_min: int
    installable: bool = True
    raison_non_installable: str = ""

    def __post_init__(self):
        if not self.installable and not self.raison_non_installable.strip():
            raise ValueError(f"La capacité « {self.id} » non installable doit dire pourquoi (raison_non_installable).")


_CATALOGUE = {
    "base": Capacite(
        "base", "Base du serveur (Docker, outils)", (), "docker",
        "command -v docker >/dev/null", 0.5, 5),
    "durcissement": Capacite(
        "durcissement", "Durcissement SSH (connexion par clé seulement)", ("base",), "durcissement",
        "grep -qi '^PasswordAuthentication no' /etc/ssh/sshd_config.d/00-myiafactory.conf", 0.0, 2),
    "android-build": Capacite(
        "android-build", "Construction Android (SDK, plateforme 36, Java)", ("base",), "android_build",
        "test -x ~/android-sdk/platform-tools/adb && test -d ~/android-sdk/platforms/android-36 "
        "&& test -d ~/android-sdk/build-tools/36.0.0 && { command -v java >/dev/null "
        # un Java quelconque : sur le PATH, JDK 17 d'Ubuntu, ou JDK livré avec le module Android d'Unity (boucle : un motif sans
        # correspondance reste un texte brut que `test -x` refuse, et `break` rend 0 dès qu'un exécutable existe)
        "|| for j in /usr/lib/jvm/java-17-openjdk-*/bin/java "
        "~/Unity/Hub/Editor/*/Editor/Data/PlaybackEngines/AndroidPlayer/OpenJDK/bin/java; do test -x \"$j\" && break; done; }", 5.4, 10),
    "android-emulateur": Capacite(
        "android-emulateur", "Émulateur Android (KVM)", ("android-build",), "android_emulateur",
        # le dossier de l'image système ÉPINGLÉE (android_sdk.emulator_image de versions.json, « ; » -> « / » ; test de
        # concordance), pas seulement system-images : une autre image ne suffit pas à l'émulateur des tâches
        "test -x ~/android-sdk/emulator/emulator && test -d ~/android-sdk/system-images/android-34/google_apis/x86_64 "
        "&& id -nG | grep -qw kvm && test -e /dev/kvm", 2.0, 8),
    "emulateur-image": Capacite(
        "emulateur-image", "Image de l'émulateur (conteneur d'outil sans identifiants)", ("android-emulateur",), "emulateur_image",
        "test -s ~/.myiafactory/emulateur-image.version", 1.5, 10),
    "unity-cli": Capacite(
        "unity-cli", "Unity CLI (outil officiel en ligne de commande)", ("base",), "unity_cli",
        "test -x ~/.local/bin/unity && ~/.local/bin/unity --version >/dev/null 2>&1", 0.1, 2),
    "unity-editeur": Capacite(
        "unity-editeur", "Éditeur Unity", ("unity-cli",), "unity_cli",
        "ls ~/Unity/Hub/Editor/*/Editor/Unity >/dev/null 2>&1", 24.0, 25,
        installable=False,
        raison_non_installable="installer l'éditeur par la session graphique (Unity Hub) ou `unity install <version>` une fois connecté"),
    "session-graphique": Capacite(
        "session-graphique", "Session graphique distante (bureau + Unity Hub)", ("base",), "bureau_distant",
        "ss -ltn 2>/dev/null | grep -qE '127\\.0\\.0\\.1:3389( |$)' && command -v unityhub >/dev/null", 3.0, 12,
        installable=False,
        raison_non_installable="installer par `lancer.py plateforme installer --bureau-distant`"),
    "agent": Capacite(
        "agent", "Agent de développement sur le serveur (image myiafactory/agent, réseau des agents)", ("base",), "agent_image",
        "test -s ~/.myiafactory/agent-image.version", 1.0, 8),
    # Image des campagnes de tests routées au serveur (conteneur sans réseau, sans jeton ni clé ; voir images/tests/).
    "tests-image": Capacite(
        "tests-image", "Image des campagnes de tests (conteneur sans réseau ni secret)", ("base",), "tests_image",
        "test -s ~/.myiafactory/tests-image.version", 1.0, 6),
    # Image des campagnes Gradle/Android : myiafactory/tests + JDK 17 et 21 ; le SDK de l'hôte (android-build) est monté en lecture seule.
    "tests-android": Capacite(
        "tests-android", "Image des tests Gradle/Android (SDK de l'hôte en lecture seule)", ("tests-image", "android-build"),
        "tests_android_image", "test -s ~/.myiafactory/tests-android-image.version", 0.5, 4),
    # Licence Unity de Hub pour les tests (§ 5.16, tâche 14i) : une capacité À ÉTATS. Le marqueur ~/.myiafactory/unity-licence.etat
    # (« conteneur B1|B2|B3 », « hote » ou « absente ») est écrit par la seule étape unity_licence_etat (outil de l'expérience J13,
    # campagne qui rend 81, bouton « Vérifier la licence ») ; la sonde le lit, vérifie par `test -s` que les fichiers de licence
    # existent toujours (JAMAIS leur contenu) et imprime conteneur|hote|absente ; présente = conteneur ou hote. L'état et la
    # variante retenus sont gardés dans l'état local du serveur (`serveurs-etat.json` > `etats`, serveur_installation).
    "unity-licence": Capacite(
        "unity-licence", "Licence Unity de Hub pour les tests", ("base",), "unity_licence_etat",
        "e=$(head -c 64 ~/.myiafactory/unity-licence.etat 2>/dev/null); e=${e%%[[:space:]]*}; "
        "case \"$e\" in conteneur|hote) ;; *) e=absente ;; esac; "
        "if [ \"$e\" != absente ]; then test -s ~/.local/share/unity3d/Unity/Unity_lic.ulf "
        "|| for f in ~/.config/unity3d/Unity/licenses/*; do test -s \"$f\" && break; done || e=absente; fi; "
        "echo \"$e\"; test \"$e\" != absente", 0.0, 5,
        installable=False,
        raison_non_installable="licence de Unity Hub : reconnecter Hub par la session graphique"),
    # Bac à sable de l'hôte (option A, § 5.16, tâches 14h et 14i) : utilisateur unity-tests, script racine, marqueur de l'audit
    # J14 (écrit SEULEMENT si toutes les vérifications de la sonde passent ; il prouve aussi la règle sudoers, que la sonde ne
    # peut pas lire : /etc/sudoers.d n'est lisible que par root) et un éditeur de /opt/unity/editors lisible par tous.
    "unity-bac-a-sable": Capacite(
        "unity-bac-a-sable", "Bac à sable de l'hôte pour les tests Unity (option A)", ("unity-licence", "session-graphique"),
        "unity_bac_a_sable",
        "id -u unity-tests >/dev/null 2>&1 && test -x /usr/local/lib/myiafactory/unity-bac-a-sable.sh "
        "&& test -x /usr/local/lib/myiafactory/sonde-bac-a-sable.sh && test -s ~/.myiafactory/unity-bac-a-sable.version "
        # un éditeur lisible et exécutable par les autres (« r-x » en fin des droits : unity-tests n'est ni propriétaire ni du groupe)
        "&& stat -c %A /opt/unity/editors/*/Editor/Unity 2>/dev/null | grep -q 'r.x$'",
        0.0, 5),
    # SDK Flutter de l'HÔTE (~/flutter-sdk, version épinglée de versions.json), monté en lecture seule dans le conteneur des
    # agents d'un projet Flutter ; Flutter pour Android s'appuie sur le SDK Android de l'hôte (android-build). Le marqueur
    # porte la version : une autre version épinglée le rend périmé (MARQUEURS de serveur_installation).
    "flutter-sdk": Capacite(
        "flutter-sdk", "Flutter (SDK de l'hôte, en lecture seule chez les agents)", ("android-build",), "flutter_sdk",
        "test -s ~/.myiafactory/flutter-sdk.version && test -x ~/flutter-sdk/bin/flutter", 3.0, 12),
    # Étape humaine : le jeton de l'abonnement est enregistré UNE fois par le Directeur ; la sonde ne lit jamais son contenu
    # (droits du dossier et du fichier, fichier non vide).
    "agent-abonnement": Capacite(
        "agent-abonnement", "Connexion de l'agent à l'abonnement (jeton enregistré par le Directeur)", ("agent",), "agent_abonnement",
        '[ "$(stat -c %a ~/agent-identifiants)" = 700 ] && [ "$(stat -c %a ~/agent-identifiants/jeton)" = 600 ] '
        '&& test -s ~/agent-identifiants/jeton', 0.0, 3,
        installable=False,
        # courte, lien en tête : le détail affiché au Directeur est tronqué à 200 caractères
        raison_non_installable="voir docs/serveur-agents.md#connexion-a-l-abonnement : le Directeur lance `bash enregistrer_jeton.sh` "
                               "sur le serveur et y colle le jeton de son abonnement"),
}

_BESOINS = {
    "apk": ("android-build",),
    "tests": ("android-build",),
    "lint": ("android-build",),
    "release": ("android-build",),
    "emulateur": ("android-emulateur",),
    # la recette sur émulateur (tâches serveur) tourne dans l'image de l'émulateur : c'est par cette action que le bureau
    # et `lancer.py plateforme serveurs apercu|installer <id> recette-emulateur` installent emulateur-image (et sa chaîne)
    "recette-emulateur": ("emulateur-image",),
    "charge": (),
    # le service permanent d'un projet (docs/serveur-services.md) : Docker et ufw de la base suffisent
    "service": ("base",),
    # un agent du projet tourne sur le serveur : seul (branche et rapport) ou pilote (il conduit l'émulateur par le pont fermé)
    "agent-serveur": ("agent", "agent-abonnement"),
    "agent-pilote": ("agent", "agent-abonnement", "emulateur-image"),
    # un agent d'un projet Flutter (pubspec.yaml qui dépend de flutter, vu sur le poste) : en plus, le SDK Flutter de l'hôte
    "agent-flutter": ("agent", "agent-abonnement", "flutter-sdk"),
    # les campagnes de tests d'un projet routées au serveur (`lancer.py tests …`) tournent dans l'image de tests
    "tests-serveur": ("tests-image",),
    "tests-serveur-android": ("tests-android",),
    # option A des tests Unity (§ 5.16, J14) : le bac à sable de l'hôte, sur accord du Directeur ; la licence (non installable)
    # reste une étape humaine, et la capacité n'est présente qu'après l'audit J14 (marqueur)
    "tests-serveur-unity-hote": ("unity-bac-a-sable",),
}

CATALOGUE = MappingProxyType(_CATALOGUE)
BESOINS = MappingProxyType(_BESOINS)


def verifier_catalogue(catalogue=None) -> None:
    """Lève `ValueError` pour une dépendance inconnue ou un cycle."""
    catalogue = CATALOGUE if catalogue is None else catalogue
    for cap in catalogue.values():
        for d in cap.depend:
            if d not in catalogue:
                raise ValueError(f"La capacité « {cap.id} » dépend de « {d} », qui n'existe pas au catalogue.")
    etat = {}                                   # 1 = en cours, 2 = terminée

    def visiter(i, chemin):
        if etat.get(i) == 2:
            return
        if etat.get(i) == 1:
            raise ValueError("Cycle de dépendances entre capacités : " + " -> ".join(chemin + [i]))
        etat[i] = 1
        for d in catalogue[i].depend:
            visiter(d, chemin + [i])
        etat[i] = 2

    for i in catalogue:
        visiter(i, [])


def _fermeture(demandees, catalogue):
    """Capacités demandées et leurs dépendances, dépendances d'abord, sans doublon (ordre stable)."""
    verifier_catalogue(catalogue)
    ordre = []

    def visiter(i):
        if i not in catalogue:
            raise ValueError(f"Capacité inconnue : « {i} ». Connues : {', '.join(sorted(catalogue))}.")
        if i in ordre:
            return
        for d in catalogue[i].depend:
            visiter(d)
        ordre.append(i)

    for i in demandees:
        visiter(i)
    return ordre


def ordre_installation(demandees: Iterable[str], installees: set, catalogue=None) -> list:
    """Capacités manquantes, dépendances d'abord. Une capacité non installable reste dans la liste : voir `bloquees`."""
    catalogue = CATALOGUE if catalogue is None else catalogue
    return [i for i in _fermeture(list(demandees), catalogue) if i not in installees]


def bloquees(ids: Iterable[str], catalogue=None) -> list:
    """Capacités non installables dans la fermeture des `ids` DONNÉS, même déjà installées : `[{"id", "raison"}]`.
    L'appelant doit donc passer la liste des MANQUANTES : `bloquees(ordre_installation(...))`."""
    catalogue = CATALOGUE if catalogue is None else catalogue
    return [{"id": i, "raison": catalogue[i].raison_non_installable}
            for i in _fermeture(list(ids), catalogue) if not catalogue[i].installable]


def manquantes_pour(actions: Iterable[str], installees: set, catalogue=None) -> list:
    """Capacités à installer pour permettre `actions` (via `BESOINS`), dans l'ordre d'installation."""
    requises = []
    for a in actions:
        if a not in BESOINS:
            raise ValueError(f"Action inconnue : « {a} ». Connues : {', '.join(sorted(BESOINS))}.")
        requises.extend(BESOINS[a])
    return ordre_installation(requises, installees, catalogue)
