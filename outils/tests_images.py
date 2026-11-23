"""Catalogue des images des campagnes de tests au serveur et choix d'après le profil (conception § 5.12) : données et logique
pures (ni SSH ni docker). Les images dérivées (Node 18, JDK 11, .NET, Go…) sont construites ailleurs (tâche 14c) : ici,
`choisir_image` dit seulement qu'aucune image du catalogue ne convient (`derivee`).

`myiafactory/android` (Gradle 8.7, plateforme 34, root, curl) et `unityci/editor` ne sont PAS au catalogue des tests : le
premier ne convient à aucun projet réel (compileSdk 36, wrapper Gradle 9), le second ne sert que de base à une image
`myiafactory/tests-unity-<version>` (tâche 14g)."""
import re
from typing import Optional

IMAGE_DEFAUT = "myiafactory/tests"
# Sans réseau, une campagne Gradle ne réussit qu'avec un cache de dépendances préchauffé (§ 5.13). TÂCHE 14d : passer à vrai quand
# l'échauffement existe, ET traiter deux prérequis relevés à la relecture de 14b : (1) une sonde réelle du SDK de l'hôte, passée
# en `sdk_android` à `choisir_image` (plateformes, build-tools et licences présentes dans ~/android-sdk) ; (2) AGP écrit dans le
# SDK, monté en :ro par l'enveloppe (licences, composants manquants, cache de build) : à prévoir (copie, couche haute ou sonde).
CACHE_GRADLE_PRET = False
# Motifs fermés (les mêmes que ceux de l'enveloppe hôte `taches/lancer_tests.sh`, qui ne croit jamais le poste).
MOTIF_IMAGE = re.compile(r"myiafactory/tests(-[a-z0-9]{1,24})?", re.ASCII)

CATALOGUE_IMAGES = {
    "myiafactory/tests": {"capacite": "tests-image", "familles": ("python", "node", "make"),
                          "outils": {"python": "3.12", "node": "22"}},
    "myiafactory/tests-android": {"capacite": "tests-android", "familles": ("gradle-android", "gradle-jvm"),
                                  "outils": {"jdk": ("17", "21")}},
}
# Outils du profil que l'image n'a pas à porter : Gradle vient du wrapper du projet ; le SDK Android est celui de l'hôte (sonde).
_FOURNIS_AILLEURS = ("gradle", "android")
_VERSION = re.compile(r"v?(\d{1,4})(?:\.(\d{1,4}))?")


def _majeure(outil: str, texte) -> Optional[tuple]:
    """(majeur,) ou (majeur, mineur) pour python : la précision qui décide de la compatibilité."""
    m = _VERSION.match(str(texte))
    if not m:
        return None
    return (m.group(1), m.group(2) or "0") if outil == "python" else (m.group(1),)


def _convient(profil, image: dict) -> bool:
    if not all(f in image["familles"] for f in profil.familles):
        return False
    for outil, version in profil.outils.items():
        if outil in _FOURNIS_AILLEURS:
            continue
        offerte = image["outils"].get(outil)
        if offerte is None:
            return False
        voulue = _majeure(outil, version)
        offertes = offerte if isinstance(offerte, tuple) else (offerte,)
        if voulue is None or voulue not in [_majeure(outil, o) for o in offertes]:
            return False
    return True


def _plateforme(x) -> str:
    return str(x) if str(x).startswith("android-") else f"android-{x}"


def _sdk_manquant(profil, sdk_android: Optional[dict]) -> list:
    """Ce que le profil exige du SDK de l'hôte et qu'il n'a pas ; `sdk_android` (relevé de la sonde `android-build` :
    `{"platforms": [...], "build_tools": [...], "ndk": [...]}`) None = non relevé, rien n'est dit."""
    info = profil.outils.get("android")
    if sdk_android is None or not isinstance(info, dict):
        return []
    manque = []
    plateformes = {_plateforme(p) for p in sdk_android.get("platforms") or ()}
    if info.get("compileSdk") and _plateforme(info["compileSdk"]) not in plateformes:
        manque.append(f"platforms;{_plateforme(info['compileSdk'])}")
    if info.get("build_tools") and str(info["build_tools"]) not in {str(b) for b in sdk_android.get("build_tools") or ()}:
        manque.append(f"build-tools;{info['build_tools']}")
    if info.get("ndk") and str(info["ndk"]) not in {str(n) for n in sdk_android.get("ndk") or ()}:
        manque.append(f"ndk;{info['ndk']}")
    return manque


def choisir_image(profil, sdk_android: Optional[dict] = None) -> dict:
    """`{"image", "capacites", "derivee", "manque"}` : la première image du catalogue où chaque famille est connue et chaque
    outil du profil est à la même version majeure (Python : majeur.mineur). Une pile inconnue (aucune famille) reçoit l'image
    par défaut. Aucune image ne convient : `derivee` vrai, `image` None, `capacites` celle de l'image de base. Pour
    `gradle-android`, `manque` liste ce que le SDK de l'hôte n'a pas (`platforms;android-N`, `build-tools;V`, `ndk;V`)."""
    if not profil.familles:
        return {"image": IMAGE_DEFAUT, "capacites": [CATALOGUE_IMAGES[IMAGE_DEFAUT]["capacite"]], "derivee": False, "manque": []}
    for nom, image in CATALOGUE_IMAGES.items():
        if _convient(profil, image):
            manque = _sdk_manquant(profil, sdk_android) if "gradle-android" in profil.familles else []
            return {"image": nom, "capacites": [image["capacite"]], "derivee": False, "manque": manque}
    return {"image": None, "capacites": [CATALOGUE_IMAGES[IMAGE_DEFAUT]["capacite"]], "derivee": True, "manque": []}
