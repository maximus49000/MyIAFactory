"""Un APK n'est construit que si l'évolution en a besoin (règle du Directeur, 2026-11-27 : « s'il n'y avait pas besoin d'un
apk, il ne devrait pas être généré ») : d'après les fichiers que les tâches d'un élément ont réellement modifiés (diff de leur
branche `agent/<tâche>`), l'application change-t-elle ? Lecture seule : git et des motifs, jamais une exécution.

Pour un projet Flutter (`outils/projet_flutter.py`) l'application est le dossier du `pubspec.yaml`. Un fichier compte si :
- il est dans ce dossier (si le pubspec est à la RACINE du dépôt : n'importe où SAUF `serveur/`, `server/`, `docs/`, `.factory/`,
  `scripts/`, `tests/`, `Livrables/`, `.github/`) ;
- et il n'est ni un test (`test/`, `integration_test/`), ni de la documentation (`.md`, `.txt`, `.rst`), ni dans un motif de
  `apk_ignore` (liste de motifs de chemins du projet, réglable dans `factory.json` ; défaut `IGNORE_PAR_DEFAUT` : les copies de
  documents embarquées dans l'application, `**/assets/docs/**` — cas FM_Stats, `copier_docs_t4.py` : une modification qui ne touche
  que ces copies ne déclenche pas un APK à elle seule).
Un projet qui n'est pas Flutter, ou des fichiers inconnus (`None`) : l'APK est construit comme avant.
"""
import fnmatch
import re

IGNORE_PAR_DEFAUT = ("**/assets/docs/**",)
HORS_APPLICATION_A_LA_RACINE = ("serveur/", "server/", "docs/", ".factory/", "scripts/", "tests/", "Livrables/", ".github/")
SANS_EFFET_SUR_L_APK = ("test/", "integration_test/", "build/", ".dart_tool/")      # tests et sorties de construction
EXTENSIONS_DOCUMENTATION = (".md", ".mdx", ".txt", ".rst")


def _motif(glob):
    """Un motif de chemin (`**` traverse les dossiers, `*` reste dans un dossier) en expression régulière."""
    sortie, i = "", 0
    while i < len(glob):
        if glob[i:i + 3] == "**/":
            sortie += "(?:.*/)?"
            i += 3
        elif glob[i:i + 2] == "**":
            sortie += ".*"
            i += 2
        elif glob[i] == "*":
            sortie += "[^/]*"
            i += 1
        else:
            sortie += re.escape(glob[i])
            i += 1
    return re.compile(sortie + r"\Z")


def ignore(chemin, motifs):
    return any(_motif(m).match(chemin) for m in motifs)


def touche_l_application(dossier_app, fichiers, motifs=IGNORE_PAR_DEFAUT):
    """Vrai si un des `fichiers` (chemins relatifs au dépôt, « / ») change l'application Flutter dont le dossier est
    `dossier_app` (« . » pour la racine)."""
    base = "" if dossier_app in (".", "", None) else str(dossier_app).strip("/") + "/"
    for f in fichiers:
        f = str(f).replace("\\", "/")
        f = f[2:] if f.startswith("./") else f
        if base:
            if not f.startswith(base):
                continue
            dedans = f[len(base):]
        else:
            if f.startswith(HORS_APPLICATION_A_LA_RACINE):
                continue
            dedans = f
        if dedans.startswith(SANS_EFFET_SUR_L_APK) or dedans.lower().endswith(EXTENSIONS_DOCUMENTATION):
            continue
        if ignore(f, motifs):
            continue
        return True
    return False
