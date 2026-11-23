"""Un projet Flutter, vu du poste : lecture seule, bornée, sans rien exécuter (ni `flutter`, ni `dart`, ni YAML complet).

Un projet est Flutter quand un `pubspec.yaml` — à la racine du dépôt ou dans un sous-dossier direct (FM_Stats :
`android_app/pubspec.yaml`) — déclare dans sa section `dependencies:` la dépendance `flutter:` suivie de `sdk: flutter`.
Le résultat ne sort du poste que sous une forme FERMÉE : le booléen `"flutter"` de la demande d'un agent serveur
(`serveur_agent`), relu sur le serveur par un motif strict (`lancer_agent.sh`). Aucune valeur lue ici n'est transmise
telle quelle.

`version_demandee` lit, bornée et par motif strict, la version que le projet épingle (`.fvmrc`, puis la contrainte
`environment: flutter:` de `pubspec.yaml`) : une information pour le Directeur et pour la future famille de tests
`flutter` (route des tests au serveur), jamais une commande.
"""
import json
import re
from pathlib import Path

NOM = "pubspec.yaml"
LECTURE_MAX = 262144                 # 256 Ko lus au plus par fichier
SOUS_DOSSIERS_MAX = 200              # sous-dossiers directs examinés au plus
IGNORES = frozenset({"build", "node_modules", "Pods", "vendor", "venv", "__pycache__"})
_CLE_FLUTTER = re.compile(r"flutter:[ \t]*(#.*)?")
_SDK_FLUTTER = re.compile(r"sdk:[ \t]*['\"]?flutter['\"]?[ \t]*(#.*)?")
_SECTION = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):[ \t]*(#.*)?")
MOTIF_VERSION = re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[-+][0-9A-Za-z.]{1,30})?", re.ASCII)
MOTIF_CONTRAINTE = re.compile(r"[0-9<>=^ .+-]{1,40}", re.ASCII)


def _lire(chemin):
    """Texte d'un fichier ORDINAIRE (jamais un lien), 256 Ko au plus ; None s'il est absent ou illisible."""
    try:
        p = Path(chemin)
        if p.is_symlink() or not p.is_file():
            return None
        with open(p, "rb") as f:
            return f.read(LECTURE_MAX).decode("utf-8", "replace")
    except OSError:
        return None


def _section(texte, nom):
    """Les lignes (non vides, hors commentaires) de la section de premier niveau `nom:`, avec leur indentation."""
    dedans, lignes = False, []
    for brute in texte.splitlines():
        if not brute.strip() or brute.lstrip().startswith("#"):
            continue
        if not brute[0].isspace():
            m = _SECTION.fullmatch(brute.rstrip())
            dedans = bool(m) and m.group(1) == nom
            continue
        if dedans:
            lignes.append((len(brute) - len(brute.lstrip()), brute.strip()))
    return lignes


def depend_de_flutter(texte):
    """Vrai si la section `dependencies:` de ce pubspec déclare `flutter:` (premier niveau) puis `sdk: flutter`."""
    if not isinstance(texte, str):
        return False
    lignes = _section(texte, "dependencies")
    if not lignes:
        return False
    niveau = lignes[0][0]
    for i, (n, ligne) in enumerate(lignes):
        if n == niveau and _CLE_FLUTTER.fullmatch(ligne):
            suite = lignes[i + 1] if i + 1 < len(lignes) else None
            return suite is not None and suite[0] > niveau and bool(_SDK_FLUTTER.fullmatch(suite[1]))
    return False


def dossier_flutter(projet):
    """Le dossier (relatif au projet, « . » pour la racine) du premier pubspec.yaml Flutter : la racine d'abord, puis
    les sous-dossiers directs par ordre alphabétique (cachés et dossiers de construction exclus, liens jamais suivis) ;
    None si le projet n'est pas Flutter ou illisible."""
    racine = Path(projet)
    if depend_de_flutter(_lire(racine / NOM)):
        return "."
    try:
        enfants = sorted((e for e in racine.iterdir() if not e.name.startswith(".") and e.name not in IGNORES),
                         key=lambda e: e.name)[:SOUS_DOSSIERS_MAX]
    except OSError:
        return None
    for e in enfants:
        try:
            if e.is_symlink() or not e.is_dir():
                continue
        except OSError:
            continue
        if depend_de_flutter(_lire(e / NOM)):
            return e.name
    return None


def est_flutter(projet):
    return dossier_flutter(projet) is not None


def version_demandee(dossier):
    """`(version, origine)` : la version exacte de `.fvmrc` (clé `flutter`), sinon la contrainte `environment: flutter:`
    de pubspec.yaml ; `(None, None)` si rien de lisible. Chaque valeur passe un motif strict (sinon ignorée)."""
    d = Path(dossier)
    brut = _lire(d / ".fvmrc")
    if brut:
        try:
            v = json.loads(brut).get("flutter")
        except (ValueError, AttributeError):
            v = None
        if isinstance(v, str) and MOTIF_VERSION.fullmatch(v):
            return v, ".fvmrc"
    texte = _lire(d / NOM)
    if texte:
        for n, ligne in _section(texte, "environment"):
            m = re.fullmatch(r"flutter:[ \t]*['\"]?([^'\"#]*?)['\"]?[ \t]*(#.*)?", ligne)
            if m and MOTIF_CONTRAINTE.fullmatch(m.group(1)):
                return m.group(1), NOM
    return None, None
