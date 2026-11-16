"""Les modules de test touchés par des fichiers modifiés : de quoi ne pas relancer toute la suite à chaque changement.

Un module de test dépend d'un fichier quand il l'atteint, directement ou de proche en proche :
- par un import Python (`import a.b`, `from a import b`, `from a.b import c`) ;
- par une mention de son nom de fichier dans le texte d'un fichier Python : c'est ainsi qu'un test atteint un outil
  lancé en sous-processus (`verifier_interface.py`, `outil.py`…).

La sélection penche toujours du côté prudent : deux fichiers du même nom sont tous deux suivis ; un fichier modifié que
rien ne cite est cherché par le nom de son dossier ; s'il reste introuvable, toute la suite est rendue. Les documents
(`docs/`, fichiers `.md`) ne demandent aucun test.
"""
import ast
import re
import subprocess
from pathlib import Path

IGNORES = {".git", "__pycache__", "node_modules", "vendor"}


def _fichiers_python(racine):
    return [p for p in racine.rglob("*.py") if not IGNORES & set(p.relative_to(racine).parts)]


def _nom_de_module(racine, chemin):
    parties = list(chemin.relative_to(racine).with_suffix("").parts)
    if parties[-1] == "__init__":
        parties = parties[:-1]
    return ".".join(parties)


def _imports(texte):
    """Les noms de modules importés (et, pour `from a import b`, aussi `a.b`, qui peut être un sous-module)."""
    try:
        arbre = ast.parse(texte)
    except SyntaxError:
        return set()
    noms = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            noms.add(n.module)
            noms.update(f"{n.module}.{a.name}" for a in n.names)
    return noms


class Graphe:
    def __init__(self, racine):
        self.racine = Path(racine)
        self.fichiers = _fichiers_python(self.racine)
        self.textes = {p: p.read_text(encoding="utf-8", errors="replace") for p in self.fichiers}
        par_module = {_nom_de_module(self.racine, p): p for p in self.fichiers}
        self._cites = {}
        self.dependants = {p: set() for p in self.fichiers}   # fichier -> les fichiers Python qui en dépendent
        for p, texte in self.textes.items():
            for nom in _imports(texte):
                cible = par_module.get(nom)
                if cible is not None and cible != p:
                    self.dependants[cible].add(p)

    def _citants(self, motif):
        """Les fichiers Python dont le texte cite `motif` (un nom de fichier ou de dossier, en mot entier)."""
        if motif not in self._cites:
            r = re.compile(r"(?<![\w.-])" + re.escape(motif) + r"(?![\w-])")
            self._cites[motif] = {p for p, t in self.textes.items() if motif in t and r.search(t)}
        return self._cites[motif]

    def _script(self, p):
        """Un fichier lancé comme programme (`if __name__ == "__main__"`) : on l'atteint aussi par son nom cité."""
        return "__main__" in self.textes.get(p, "") and p.name != "__init__.py"

    def _citants_du_programme(self, p):
        """Les fichiers qui lancent ce programme par son chemin : `dossier/nom.py` ou `"dossier" / "nom.py"` ; depuis
        son propre dossier, `"nom.py"` entre guillemets suffit (`Path(__file__).parent / "nom.py"`), comme partout
        quand son nom est unique. Une simple mention dans un texte ne relie pas : deux `outil.py` reliaient tout."""
        cle = ("programme", p)
        if cle not in self._cites:
            d, n = re.escape(p.parent.name), re.escape(p.name)
            par_chemin = re.compile(rf"{d}/{n}|['\"]{d}['\"]\s*/\s*['\"]{n}['\"]")
            # le nom seul, entre guillemets, mais pas précédé d'un autre dossier (`"orchestrateur" / "outil.py"`)
            par_nom = re.compile(rf"(?<!/ )(?<!/)['\"]{n}['\"]")
            unique = sum(1 for f in self.fichiers if f.name == p.name) == 1
            self._cites[cle] = {f for f, t in self.textes.items() if f != p and p.name in t and (
                par_chemin.search(t) or ((unique or f.parent == p.parent) and par_nom.search(t)))}
        return self._cites[cle]

    def _cite_par_dossiers(self, chemin):
        """Un fichier que rien ne cite : le premier de ses dossiers (du plus proche au plus lointain) qui l'est."""
        d = chemin.parent
        while d != self.racine and d != d.parent:
            citants = self._citants(d.name)
            if citants:
                return citants
            d = d.parent
        return set()

    def touches(self, modifies):
        """`(modules de test, raison)` pour des chemins relatifs modifiés ; `(None, raison)` : toute la suite."""
        depart, introuvables = set(), []
        for rel in modifies:
            chemin = self.racine / rel
            if rel.endswith(".md") or rel.startswith("docs/"):
                continue
            if chemin in self.dependants:     # un fichier Python : ses imports, et son nom s'il est un programme
                depart.add(chemin)
                continue
            citants = self._citants(chemin.name) or self._cite_par_dossiers(chemin)
            if not citants:
                introuvables.append(rel)
            depart |= citants
        if introuvables:
            return None, f"rien ne cite {', '.join(introuvables[:3])} : toute la suite"
        vus, pile = set(depart), list(depart)
        while pile:   # de proche en proche : imports, et noms cités des programmes lancés en sous-processus
            p = pile.pop()
            suivants = set(self.dependants.get(p, ())) | (self._citants_du_programme(p) if self._script(p) else set())
            for q in suivants - vus:
                vus.add(q)
                pile.append(q)
        tests = sorted(p.stem for p in vus if p.parent == self.racine / "tests" and p.stem.startswith("test_"))
        return tests, f"{len(modifies)} fichier(s) modifié(s)"


def fichiers_modifies(racine, reference="origin/main"):
    """Ce qui diffère de `reference` : commits de la branche, modifications en cours et fichiers nouveaux."""
    def git(*args):
        p = subprocess.run(["git", *args], cwd=str(racine), capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.stdout.decode("utf-8", "replace").splitlines() if p.returncode == 0 else []
    noms = set(git("diff", "--name-only", f"{reference}...HEAD")) | set(git("diff", "--name-only", "HEAD"))
    noms |= set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(n.strip() for n in noms if n.strip())
