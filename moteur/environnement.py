"""L'environnement du poste : ce que le workflow d'une fonctionnalité demande comme outils, et ce qui est déjà là.

La proposition d'un workflow (`proposer_organisation`) liste les outils dont ses étapes ont besoin :
`{"outil", "pour", "executables": [noms], "installation": texte}`. `verifier` regarde, **en code**, lesquels sont déjà
sur le poste : jamais une commande écrite par l'IA. Un exécutable est un **nom** (`java`, `gradle`), cherché dans le
`PATH` puis aux emplacements usuels (`JAVA_HOME`, `ANDROID_HOME`, `ANDROID_SDK_ROOT`) ; un nom qui n'a pas la forme d'un
nom de programme (espace, `;`, `&`, chemin, option) est refusé sans être cherché ni lancé. Ce qui est trouvé n'est lancé
que pour lire sa version, avec une option d'une liste fixe (`--version`, `-version`, `version`), délai de 10 s.

Chaque outil rendu porte son `etat` : `en_place` (avec `chemin` et, si lisible, `version`) ou `a_installer`.

Un outil peut porter une **version minimale** (champ `version_min`, ou le nombre qui suit son nom : « JDK 17 »). La
version lue est alors comparée : trop ancienne (Java 8 pour un JDK 17), l'outil est `a_installer` et `raison` dit ce
qui a été trouvé ; illisible, il reste `en_place` mais `raison` dit que la version n'a pas pu être vérifiée.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

from moteur.jugement import MOTIF_EXECUTABLE

OPTIONS_DE_VERSION = ("--version", "-version", "version")   # la liste fixe : jamais une option venue de l'IA
DELAI_VERSION_S = 10
LONGUEUR_VERSION = 120
# Où chercher après le PATH : (variable d'environnement, sous-dossiers du SDK ou du JDK). `*` : tous les dossiers du niveau.
EMPLACEMENTS = (("JAVA_HOME", ("bin",)),
                ("ANDROID_HOME", ("cmdline-tools/latest/bin", "cmdline-tools/bin", "platform-tools", "tools/bin",
                                  "emulator", "build-tools/*")),
                ("ANDROID_SDK_ROOT", ("cmdline-tools/latest/bin", "cmdline-tools/bin", "platform-tools", "tools/bin",
                                      "emulator", "build-tools/*")))


def executer_version(argv, delai_s=DELAI_VERSION_S):
    """(code, sortie) d'un programme lancé pour lire sa version : sans fenêtre, sans entrée, sortie et erreurs réunies."""
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=delai_s,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return p.returncode, (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")


def _dossiers_usuels(env):
    for variable, sous_dossiers in EMPLACEMENTS:
        racine = (env.get(variable) or "").strip()
        if not racine or not Path(racine).is_dir():
            continue
        for sous in sous_dossiers:
            if sous.endswith("/*"):
                parent = Path(racine) / sous[:-2]
                if parent.is_dir():
                    yield from sorted((d for d in parent.iterdir() if d.is_dir()), reverse=True)
            else:
                yield Path(racine) / sous


def trouver(nom, *, which=shutil.which, env=None):
    """Le chemin du programme `nom` (un nom seul), ou `None` : le `PATH`, puis les emplacements usuels."""
    env = os.environ if env is None else env
    chemin = which(nom)
    if chemin:
        return str(chemin)
    for dossier in _dossiers_usuels(env):
        chemin = which(nom, path=str(dossier))
        if chemin:
            return str(chemin)
    return None


def lire_version(chemin, executer=executer_version):
    """La première ligne de la sortie de la première option de la liste fixe qui répond (code 0), sinon `None`."""
    for option in OPTIONS_DE_VERSION:
        code, sortie = executer([chemin, option], DELAI_VERSION_S)
        lignes = [x.strip() for x in str(sortie or "").splitlines() if x.strip()]
        if code == 0 and lignes:
            return lignes[0][:LONGUEUR_VERSION]
    return None


def _numeros(texte):
    m = re.search(r"\d+(?:\.\d+)*", str(texte or ""))
    return tuple(int(x) for x in m.group(0).split(".")) if m else None


def version_minimale(outil):
    """La version minimale demandée par un outil, en nombres (`(17,)`), ou `None` : le champ `version_min`, sinon le
    nombre qui suit un nom d'un seul mot (« JDK 17 », « Gradle 8.5 ») ; « Android SDK 34 complet » n'en porte pas."""
    explicite = outil.get("version_min")
    if explicite not in (None, ""):
        return _numeros(explicite)
    m = re.fullmatch(r"\S+ v?(\d+(?:\.\d+)*)\+?", str(outil.get("outil") or "").strip())
    return _numeros(m.group(1)) if m else None


def numeros_de_version(ligne):
    """Les nombres de la version lue dans une ligne (`(8,)` pour « java version "1.8.0_351" », `(21, 0, 4)` pour
    « openjdk version "21.0.4" »), ou `None` si rien de lisible. Java 1.x est la version x."""
    texte = str(ligne or "")
    m = re.search(r'"(\d+(?:\.\d+)*)', texte) or re.search(r"\d+(?:\.\d+)+", texte) or re.search(r"\d+", texte)
    if not m:
        return None
    n = tuple(int(x) for x in re.findall(r"\d+", m.group(0) if m.lastindex is None else m.group(1)))
    if re.search(r"java|jdk|jre", texte, re.I) and len(n) > 1 and n[0] == 1:
        n = n[1:]
    return n


def verifier(outils, *, which=shutil.which, executer=executer_version, env=None):
    """Chaque outil de la proposition avec son état : `en_place` (`chemin`, `version`?) ou `a_installer`. Un outil est en
    place quand **tous** ses exécutables sont trouvés. Un exécutable est cherché une seule fois, même s'il sert à
    plusieurs outils. Un nom refusé (pas un nom de programme) n'est ni cherché ni lancé : l'outil reste à installer et
    le dit dans `refuses`."""
    trouves = {}      # nom -> chemin | None, pour ne chercher (et ne lancer) qu'une fois chaque exécutable
    versions = {}
    sortie = []
    for outil in outils:
        o = dict(outil)
        noms = [n for n in outil.get("executables") or [] if isinstance(n, str)]
        valides = [n for n in noms if MOTIF_EXECUTABLE.match(n)]
        refuses = [n for n in noms if not MOTIF_EXECUTABLE.match(n)]
        for n in valides:
            if n not in trouves:
                trouves[n] = trouver(n, which=which, env=env)
        chemins = [trouves[n] for n in valides]
        if valides and not refuses and all(chemins):
            o["etat"], o["chemin"] = "en_place", chemins[0]
            if valides[0] not in versions:
                versions[valides[0]] = lire_version(chemins[0], executer)
            if versions[valides[0]]:
                o["version"] = versions[valides[0]]
            minimale = version_minimale(outil)
            if minimale:
                trouvee = numeros_de_version(versions[valides[0]])
                texte_min = ".".join(str(x) for x in minimale)
                if trouvee is None:
                    o["raison"] = f"version {texte_min} minimum demandée, version non vérifiée (illisible)"
                elif trouvee + (0,) * (len(minimale) - len(trouvee)) < minimale:
                    o["etat"] = "a_installer"
                    o["raison"] = f"version trouvée : {versions[valides[0]]} ; {texte_min} minimum demandée"
        else:
            o["etat"] = "a_installer"
            o.pop("chemin", None)
            o.pop("version", None)
            o.pop("raison", None)
            if refuses:
                o["refuses"] = refuses
        sortie.append(o)
    return sortie


def a_installer(outils):
    return [o for o in outils if o.get("etat") != "en_place"]
