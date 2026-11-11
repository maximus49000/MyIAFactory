"""L'examen du dossier d'un projet : vide, existant, déjà installé. Borné, sans réseau, n'écrit rien.

Il ne lit aucun contenu, sauf la première ligne de `ProjectSettings/ProjectVersion.txt`."""
import fnmatch
import os
import re
import time
from collections import Counter
from pathlib import Path

IGNORES_VIDE = (".git", ".gitignore", ".gitattributes", "README*", "LICENSE*", ".claude", ".vscode", ".idea")
DOSSIERS_SAUTES = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "Library", "Temp",
                   "obj", "bin", ".factory")
FICHIERS_CLES = ("README*", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod",
                 "pom.xml", "build.gradle", "*.csproj", "*.sln", "ProjectSettings/ProjectVersion.txt",
                 "Gemfile", "composer.json", "Dockerfile", "CLAUDE.md")
DELAI_S = 2.0
MAX_ARBRE = 200
MAX_FICHIERS = 100_000
PROFONDEUR_ARBRE = 2
NOMS_ENVIRONNEMENT = (("package.json", "Node.js"), ("pyproject.toml", "Python"), ("requirements.txt", "Python"),
                      ("*.csproj", ".NET"), ("*.sln", ".NET"), ("Cargo.toml", "Rust"), ("go.mod", "Go"),
                      ("pom.xml", "Java"), ("build.gradle", "Java"), ("Gemfile", "Ruby"),
                      ("composer.json", "PHP"), ("Dockerfile", "Docker"))


def _correspond(nom, motifs):
    return any(fnmatch.fnmatchcase(nom, m) for m in motifs)


def _cas(d):
    if (d / ".factory" / "factory.json").is_file():
        return "installe"
    if (d / ".factory").exists():
        # une configuration faite à la main (sa propre factory, ou un branchement sans fichier de factory) :
        # `appliquer` la refuserait, la discussion serait perdue ; c'est le guide de passage qui s'applique
        return "factory_propre"
    try:
        noms = [p.name for p in d.iterdir()]
    except OSError:
        return "vide"
    if all(_correspond(n, IGNORES_VIDE) for n in noms):
        return "vide"
    return "existant"


def _git(d):
    if not (d / ".git").exists():
        return {"depot": False, "distant": None}
    distant = None
    try:
        texte = (d / ".git" / "config").read_text(encoding="utf-8", errors="replace")
        m = re.search(r'\[remote "[^"]+"\][^\[]*?url\s*=\s*(\S+)', texte)
        distant = m.group(1) if m else None
    except OSError:
        pass
    return {"depot": True, "distant": distant}


def _est_lien(chemin):
    try:
        return os.path.islink(chemin) or (hasattr(os.path, "isjunction") and os.path.isjunction(chemin))
    except OSError:
        return True


def _parcourir(d, horloge=time.monotonic):
    """(arbre, extensions, nombre, tronque) ; ne suit aucun lien, saute les dossiers lourds, s'arrête à DELAI_S ou à
    MAX_FICHIERS (`tronque` est alors vrai)."""
    debut = horloge()
    arbre, ext, nombre = [], Counter(), 0
    pile = [(d, 0)]
    while pile:
        dossier, prof = pile.pop()
        try:
            entrees = sorted(os.scandir(dossier), key=lambda e: e.name)
        except OSError:
            continue
        for e in entrees:
            if horloge() - debut > DELAI_S or nombre >= MAX_FICHIERS:
                return arbre, ext, nombre, True
            chemin = Path(e.path)
            if _est_lien(chemin):
                continue
            rel = chemin.relative_to(d).as_posix()
            try:
                est_dossier = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if est_dossier:
                if e.name in DOSSIERS_SAUTES:
                    continue
                if prof < PROFONDEUR_ARBRE and len(arbre) < MAX_ARBRE:
                    arbre.append(rel + "/")
                pile.append((chemin, prof + 1))
            else:
                nombre += 1
                suffixe = chemin.suffix.lower()
                if suffixe:
                    ext[suffixe] += 1
                if prof < PROFONDEUR_ARBRE and len(arbre) < MAX_ARBRE:
                    arbre.append(rel)
    return arbre, ext, nombre, False


def _fichiers_cles(d):
    trouves = []
    for motif in FICHIERS_CLES:
        if "/" in motif:
            if (d / motif).is_file():
                trouves.append(motif)
            continue
        try:
            noms = sorted(e.name for e in os.scandir(d) if e.is_file(follow_symlinks=False))
        except OSError:
            continue
        trouves += [n for n in noms if fnmatch.fnmatchcase(n, motif) and n not in trouves]
    return trouves


def _environnement(d, cles):
    env = []
    for motif, nom in NOMS_ENVIRONNEMENT:
        if any(fnmatch.fnmatchcase(c, motif) for c in cles) and nom not in env:
            env.append(nom)
    if "ProjectSettings/ProjectVersion.txt" in cles:
        try:
            with open(d / "ProjectSettings" / "ProjectVersion.txt", encoding="utf-8", errors="replace") as f:
                version = f.readline().strip()
        except OSError:
            version = ""
        env.append("moteur de jeu, version " + (version or "inconnue"))
    return env


def examiner(dossier, horloge=time.monotonic):
    d = Path(dossier)
    arbre, ext, nombre, tronque = _parcourir(d, horloge)
    cles = _fichiers_cles(d)
    return {
        "cas": _cas(d),
        "factory": (d / ".factory" / "factory.json").is_file(),
        "inventaire": {
            "arbre": arbre,
            "fichiers_cles": cles,
            "extensions": [[e, n] for e, n in ext.most_common(10)],
            "nb_fichiers": f"{nombre}+" if tronque else nombre,
            "tronque": tronque,
            "git": _git(d),
        },
        "environnement": _environnement(d, cles),
    }
