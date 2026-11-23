"""Analyse d'un projet et profil d'exécution des tests (conception § 5.11 et § 5.14).

`analyser(racine)` déduit des fichiers d'un projet sa ou ses familles (Python, Node, Gradle Android…), ses versions
d'outils, la commande de test, les dépendances, les ressources, et si le projet peut partir au serveur. C'est du CODE
SENSIBLE : il lit des fichiers écrits par des agents.

- Lecture bornée : seuls les fichiers de la liste fermée `LUS` sont lus, `MAX_LU` octets au plus chacun (64 Ko pour la CI),
  80 lectures au plus ; jamais un lien, jamais un fichier de secrets (`tests_instantane.EXCLUS`, comparés à chaque segment).
  Le parcours des noms est borné (profondeur 4, 5 000 entrées, `DOSSIERS_SAUTES`). Les verrous (`VERROUS`) ne sont pas lus
  mais hachés par blocs (64 Mo au plus) : leur contenu ne sert qu'à l'empreinte.
- Rien n'est exécuté : ni `gradlew`, ni `npm`, ni `python setup.py`. Tout se lit par motifs (JSON, `tomllib`, expressions
  régulières sur des lignes simples).
- Une valeur lue (version, mémoire) n'entre dans le profil que si elle a la forme attendue ; sinon elle est rejetée, la
  raison est dite (jamais la valeur) et la confiance tombe à `basse`. Aucun texte du projet n'est recopié dans une commande :
  les commandes viennent d'une table, du catalogue ou de la commande enregistrée.

Python 3.12, bibliothèque standard.
"""
import fnmatch
import hashlib
import json
import os
import re
import shlex
import sys
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from collections import deque
from typing import Callable, Dict, List, Optional, Tuple

ICI = Path(__file__).resolve().parent
for _dossier in (str(ICI), str(ICI.parent)):
    if _dossier not in sys.path:
        sys.path.insert(0, _dossier)

import tests_instantane  # noqa: E402
from bureau.deport_types import CATALOGUES, GENERIQUE  # noqa: E402
from installation import examen  # noqa: E402

FAMILLES = ("python", "node", "gradle-android", "gradle-jvm", "maven", "dotnet", "go", "rust", "godot", "unity", "ruby",
            "php", "make")

MAX_LU = 256 * 1024
MAX_CI = 64 * 1024
MAX_LECTURES = 80
MAX_VERROU = 64 * 1024 * 1024
MAX_ENTREES = 5000
MAX_PAR_DOSSIER = 1000
PROFONDEUR = 4
MAX_XMX_MO = 8192

# La liste fermée des fichiers lus (motifs `fnmatch` sur le chemin relatif, `/` partout ; `*` traverse les dossiers).
LUS = (
    "pyproject.toml", "requirements*.txt", "setup.cfg", "tox.ini", "pytest.ini", ".python-version", ".tool-versions",
    "package.json", ".nvmrc", ".node-version",
    "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "*/build.gradle",
    "*/build.gradle.kts", "gradle.properties", "gradle/wrapper/gradle-wrapper.properties",
    "gradle/libs.versions.toml", "*AndroidManifest.xml",
    "pom.xml", "*/pom.xml", ".mvn/wrapper/maven-wrapper.properties",
    "*.csproj", "*.sln", "global.json",
    "go.mod", "Cargo.toml", "rust-toolchain", "rust-toolchain.toml", ".cargo/config.toml", ".cargo/config",
    "project.godot", "ProjectSettings/ProjectVersion.txt", "Packages/manifest.json",
    "Gemfile", ".ruby-version", "composer.json", "Makefile",
    ".github/workflows/*.yml", ".github/workflows/*.yaml",
)
# Les verrous : hachés, jamais lus (conception § 5.13).
VERROUS = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock", "go.sum",
           "packages.lock.json", "Gemfile.lock", "composer.lock", "Packages/packages-lock.json", "gradle.lockfile")

# Ressources par famille (§ 5.14) : cpus, mémoire (Mo), durée (s). L'instantané max vient de `limites_pour`.
_RESSOURCES = {
    "python": (4, 8192, 1800), "make": (4, 8192, 1800), "ruby": (4, 8192, 1800), "php": (4, 8192, 1800),
    "node": (2, 4096, 1800),
    "gradle-android": (4, 8192, 2700), "gradle-jvm": (4, 8192, 2700), "maven": (4, 8192, 2700),
    "dotnet": (4, 4096, 1800), "go": (4, 4096, 1800),
    "rust": (4, 8192, 2700),
    "godot": (2, 4096, 1200),
    "unity": (4, 10240, 3600),
}
_CACHES = {"python": "venv", "node": "node_modules", "gradle-android": "gradle-user-home",
           "gradle-jvm": "gradle-user-home", "maven": "m2", "dotnet": "nuget", "go": "gomodcache", "rust": "cargo",
           "unity": "library", "ruby": "bundler", "php": "composer"}
# (gestionnaire, le téléchargement exécute-t-il du code du projet ou de ses dépendances ?) : prudent par défaut.
_GESTIONNAIRES = {"python": ("pip", True), "node": ("npm", True), "gradle-android": ("gradle", True),
                  "gradle-jvm": ("gradle", True), "maven": ("maven", True), "dotnet": ("nuget", False),
                  "go": ("go", False), "rust": ("cargo", True), "unity": ("upm", False), "ruby": ("bundler", True),
                  "php": ("composer", True)}

_VERSION = re.compile(r"v?(\d{1,4}(?:\.\d{1,4}){0,3})")
_VERSION_UNITY = re.compile(r"\d{1,4}\.\d{1,2}\.\d{1,3}[abfp]\d{1,3}")
_REVISION_UNITY = re.compile(r"[0-9a-f]{12}")
_EXPORT_CI = re.compile(r"\b(java|node|python|go|dotnet)-version:\s*\[?\s*['\"]?(\d{1,4}(?:\.\d{1,4})*)")
_N1_TFM = re.compile(r"\bnet4\d\d?\b")


@dataclass(frozen=True)
class Profil:
    familles: Tuple[str, ...] = ()
    outils: dict = field(default_factory=dict)
    commandes: List[List[str]] = field(default_factory=list)
    deps: dict = field(default_factory=dict)            # par famille : gestionnaire, verrou, empreinte, reseau, execute_du_code
    caches: List[str] = field(default_factory=list)
    ressources: dict = field(default_factory=dict)      # cpus, memoire_mo, disque_mo, kvm, gpu, duree_s
    isolement: str = "standard"
    non_deportable: Optional[str] = None
    confiance: str = "basse"
    empreinte: str = ""
    raisons: Tuple[str, ...] = ()                       # pourquoi la confiance n'est pas haute (jamais une valeur lue)

    def vers_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=True)

    @staticmethod
    def depuis_json(texte: str) -> "Profil":
        x = json.loads(texte)
        if not isinstance(x, dict):
            raise ValueError("profil illisible")
        return Profil(familles=tuple(x.get("familles") or ()), outils=dict(x.get("outils") or {}),
                      commandes=[list(c) for c in x.get("commandes") or []], deps=dict(x.get("deps") or {}),
                      caches=list(x.get("caches") or []), ressources=dict(x.get("ressources") or {}),
                      isolement=x.get("isolement", "standard"), non_deportable=x.get("non_deportable"),
                      confiance=x.get("confiance", "basse"), empreinte=x.get("empreinte", ""),
                      raisons=tuple(x.get("raisons") or ()))


def _hexa(objet) -> str:
    return hashlib.sha256(json.dumps(objet, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def empreinte_profil(profil: Profil) -> str:
    """64 hexa de la forme canonique triée du profil, hors `confiance`, `raisons` et `empreinte` : ce qui change l'image
    ou les dépendances change l'empreinte."""
    forme = asdict(profil)
    for cle in ("confiance", "raisons", "empreinte"):
        forme.pop(cle, None)
    return _hexa(forme)


def empreinte_image(profil: Profil) -> str:
    """64 hexa des seuls `outils` : ce qui décide de l'image."""
    return _hexa(profil.outils)


# ---------------------------------------------------------------- dépendances (§ 5.13, tâche 14d)

# Table FERMÉE des échauffements, miroir de `ECH` dans `serveur_ovh/taches/lancer_tests.sh` (qui fait foi au serveur ; la
# concordance est vérifiée par test) et du plan de `taches/tests_hote.py` ; ici pour l'affichage et la route. `execute_du_code` :
# l'outil exécute du code du projet ou de ses dépendances (réseau seulement avec l'accord du Directeur, sortie limitée).
ECHAUFFEMENTS = {
    "npm": {"commande": ["npm", "ci", "--ignore-scripts"], "duree_s": 900, "plafond_go": 2, "execute_du_code": False},
    "pnpm": {"commande": ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"], "duree_s": 900, "plafond_go": 2,
             "execute_du_code": False},
    "yarn": {"commande": ["yarn", "install", "--frozen-lockfile", "--ignore-scripts"], "duree_s": 900, "plafond_go": 2,
             "execute_du_code": False},
    "pip": {"commande": ["pip", "install", "--only-binary=:all:", "-r", "requirements.txt"], "duree_s": 900,
            "plafond_go": 2, "execute_du_code": False},
    "pip-sources": {"commande": ["pip", "install", "-r", "requirements.txt"], "duree_s": 900, "plafond_go": 2,
                    "execute_du_code": True},
    "gradle": {"commande": ["./gradlew", "--no-daemon", "dependencies"], "duree_s": 1800, "plafond_go": 6,
               "execute_du_code": True},
    "maven": {"commande": ["mvn", "-B", "dependency:go-offline"], "duree_s": 1800, "plafond_go": 6, "execute_du_code": True},
    "dotnet": {"commande": ["dotnet", "restore"], "duree_s": 1800, "plafond_go": 6, "execute_du_code": False},
    "cargo": {"commande": ["cargo", "fetch"], "duree_s": 1800, "plafond_go": 6, "execute_du_code": False},
    "go": {"commande": ["go", "mod", "download"], "duree_s": 900, "plafond_go": 2, "execute_du_code": False},
    "unity": {"commande": ["unity-editor", "-batchmode", "-quit"], "duree_s": 3600, "plafond_go": 10, "execute_du_code": True},
}
_CLE_DE_FAMILLE = {"python": "pip", "node": "npm", "gradle-android": "gradle", "gradle-jvm": "gradle", "maven": "maven",
                   "dotnet": "dotnet", "go": "go", "rust": "cargo", "unity": "unity"}
# Manifestes hachés à défaut de verrou (« sans verrou » : le cache est dit non verrouillé, § 5.13).
_MANIFESTES = {"npm": ("package.json",), "pnpm": ("package.json",), "yarn": ("package.json",), "cargo": ("Cargo.toml",),
               "go": ("go.mod",)}


def cle_echauffement(profil: Profil, famille: Optional[str] = None) -> Optional[str]:
    """La clé d'échauffement (table `ECHAUFFEMENTS`) de `famille` (par défaut la première famille qui en a une) ; Node : le
    gestionnaire du profil (npm, pnpm, yarn). None : aucune."""
    familles = [famille] if famille else [f for f in profil.familles if f in _CLE_DE_FAMILLE]
    if not familles or familles[0] not in _CLE_DE_FAMILLE:
        return None
    f = familles[0]
    if f == "node":
        g = (profil.deps.get("node") or {}).get("gestionnaire")
        return g if g in ("npm", "pnpm", "yarn") else "npm"
    return _CLE_DE_FAMILLE[f]


def empreinte_deps(profil: Profil, racine: str, lire: Optional[Callable[[str], Optional[str]]] = None,
                   famille: Optional[str] = None) -> Optional[str]:
    """16 hexa du cache de dépendances de `famille` (par défaut la première qui a un échauffement) : SHA-256 de la clé, du
    verrou (ou du verrou implicite Gradle/Maven, déjà dans `profil.deps`), à défaut du manifeste lu par `lire` (lecture
    bornée de `LUS`), et de `empreinte_image`. None si aucune dépendance (pas d'échauffement, rien à hacher, ou un
    `package.json` sans dépendances)."""
    cle = cle_echauffement(profil, famille)
    if cle is None or cle == "unity":
        return None
    f = famille or next(x for x in profil.familles if x in _CLE_DE_FAMILLE)
    d = profil.deps.get(f) or {}
    if cle == "pip" and not re.fullmatch(r"requirements[^/]*\.txt", str(d.get("verrou") or "")):
        return None       # pip n'installe que des requirements*.txt (poetry/uv : pas d'échauffement, comme avant)
    base = d.get("empreinte")
    if not base:
        lire = lire or _lecteur_defaut(str(racine))
        textes = [(n, lire(n)) for n in _MANIFESTES.get(cle, ())]
        textes = [(n, t) for n, t in textes if isinstance(t, str)]
        if not textes:
            return None
        if cle in ("npm", "pnpm", "yarn"):
            pj = _json(textes[0][1])
            if not any(isinstance(pj.get(k), dict) and pj[k] for k in ("dependencies", "devDependencies",
                                                                       "optionalDependencies")):
                return None
        base = hashlib.sha256("\n".join("%s\n%s" % x for x in textes).encode("utf-8")).hexdigest()
    return hashlib.sha256(f"{cle}\n{base}\n{empreinte_image(profil)}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- ressources

def _taille_mo(texte: str) -> Optional[int]:
    m = re.fullmatch(r"(\d{1,6})([kmgKMG]?)", texte)
    if not m:
        return None
    n, unite = int(m.group(1)), m.group(2).lower()
    return {"": n // (1024 * 1024), "k": n // 1024, "m": n, "g": n * 1024}[unite]


def ressources_par_defaut(famille: str, xmx_mo: Optional[int] = None) -> dict:
    """Le tableau du § 5.14. Gradle : `-Xmx` du projet + 4 096 Mo, 6 144 au moins (`xmx_mo` borné à `MAX_XMX_MO`) ; sans
    `-Xmx` : 8 192."""
    cpus, memoire, duree = _RESSOURCES.get(famille, (4, 8192, 1800))
    if famille in ("gradle-android", "gradle-jvm") and xmx_mo:
        memoire = max(6144, min(xmx_mo, MAX_XMX_MO) + 4096)
    disque = tests_instantane.limites_pour(famille)["max_total"] // (1024 * 1024)
    return {"cpus": cpus, "memoire_mo": memoire, "disque_mo": disque, "kvm": False, "gpu": False, "duree_s": duree}


# ---------------------------------------------------------------- lecture bornée

def _limite(rel: str) -> int:
    return MAX_CI if rel.startswith(".github/workflows/") else MAX_LU


def _est_lu(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, m) for m in LUS)


def _est_verrou(rel: str) -> bool:
    return rel in VERROUS


def _lecteur_defaut(racine: str) -> Callable[[str], Optional[str]]:
    base = Path(racine)

    def lire(rel: str) -> Optional[str]:
        if not _est_lu(rel) or not tests_instantane.nom_sur(rel) or tests_instantane._exclu(rel):
            return None
        chemin = base
        for segment in rel.split("/"):
            chemin = chemin / segment
            if examen._est_lien(chemin):
                return None
        try:
            if chemin.stat().st_size > _limite(rel):
                return None
        except OSError:
            return None
        return examen._lire_borne(chemin)
    return lire


def _scanner(racine: str) -> Tuple[List[str], List[str], bool]:
    """(fichiers, dossiers, tronqué) relatifs (jamais un lien, jamais un nom exclu ni un dossier sauté). Parcours en
    largeur (les dossiers de premier niveau d'abord), `MAX_PAR_DOSSIER` entrées par dossier, `MAX_ENTREES` en tout ; le
    plafond est vérifié dans la boucle d'un dossier ; `tronqué` si l'un des deux est atteint."""
    fichiers, dossiers, tronque = [], [], False
    file = deque([("", 0)])
    while file:
        sous, profondeur = file.popleft()
        try:
            entrees = sorted(os.scandir(os.path.join(racine, sous) if sous else racine),
                             key=lambda e: (not e.is_dir(follow_symlinks=False), e.name))
        except OSError:
            continue
        if len(entrees) > MAX_PAR_DOSSIER:
            entrees, tronque = entrees[:MAX_PAR_DOSSIER], True
        for e in entrees:
            if len(fichiers) + len(dossiers) >= MAX_ENTREES:
                return fichiers, dossiers, True
            rel = sous + "/" + e.name if sous else e.name
            try:
                if e.is_symlink() or examen._est_lien(Path(e.path)):
                    continue
                est_dossier = e.is_dir(follow_symlinks=False)
                est_fichier = e.is_file(follow_symlinks=False)
            except OSError:
                continue
            if not tests_instantane.nom_sur(rel) or tests_instantane._exclu(rel):
                continue
            if est_dossier:
                if e.name in examen.DOSSIERS_SAUTES:
                    continue
                dossiers.append(rel)
                if profondeur < PROFONDEUR:
                    file.append((rel, profondeur + 1))
            elif est_fichier:
                fichiers.append(rel)
    return fichiers, dossiers, tronque


def _catalogue_borne(racine: str) -> dict:
    """Le catalogue du genre lu dans `.factory/factory.json` ou `factory.json` : 64 Ko au plus, jamais un lien (ni le
    fichier ni un dossier du chemin) ; sinon le catalogue générique."""
    for rel in (".factory/factory.json", "factory.json"):
        chemin = Path(racine)
        suspect = False
        for segment in rel.split("/"):
            chemin = chemin / segment
            if examen._est_lien(chemin):
                suspect = True
        try:
            if suspect or not chemin.is_file() or chemin.stat().st_size > MAX_CI:
                continue
            donnees = _json(chemin.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            continue
        genre = donnees.get("genre")
        if isinstance(genre, str) and genre in CATALOGUES:
            return CATALOGUES[genre]
    return GENERIQUE


def _hacher_verrou(racine: str, rel: str) -> Optional[str]:
    chemin = Path(racine, *rel.split("/"))
    try:
        if examen._est_lien(chemin) or not chemin.is_file() or chemin.stat().st_size > MAX_VERROU:
            return None
        h = hashlib.sha256()
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloc)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------- petits lecteurs

def _json(texte: Optional[str]) -> dict:
    try:
        x = json.loads(texte or "")
    except (ValueError, RecursionError):
        return {}
    return x if isinstance(x, dict) else {}


def _toml(texte: Optional[str]) -> dict:
    try:
        return tomllib.loads(texte or "")
    except (tomllib.TOMLDecodeError, RecursionError, ValueError):
        return {}


def _premiere_ligne(texte: str) -> str:
    return (texte.strip().splitlines() or [""])[0].strip()


class _Contexte:
    def __init__(self, textes: Dict[str, str], fichiers: List[str], dossiers: List[str], tronque: bool = False):
        self.T, self.F, self.D = textes, set(fichiers), set(dossiers)
        self.fichiers = fichiers
        self.raisons: List[str] = ["parcours des fichiers tronqué (trop d'entrées)"] if tronque else []
        self.rejete = tronque
        self.plafond = False        # une valeur lue n'est pas exacte : confiance moyenne au plus
        self.versions_fichier: Dict[str, str] = {}      # outil de la CI -> version lue dans un fichier du projet

    def refuser(self, outil: str, source: str) -> None:
        self.raisons.append("version %s illisible (%s)" % (outil, source))
        self.rejete = True

    def version(self, outil: str, source: str, valeur: str, ci: Optional[str] = None) -> Optional[str]:
        """La version si elle a la forme `18.20.4` (un `v` initial est retiré), sinon None et la raison est dite."""
        m = _VERSION.fullmatch(valeur.strip())
        if not m:
            self.refuser(outil, source)
            return None
        if ci:
            self.versions_fichier.setdefault(ci, m.group(1))
        return m.group(1)

    def approximer(self, raison: str) -> None:
        self.raisons.append(raison)
        self.plafond = True

    def tout(self, motif: str) -> List[str]:
        return sorted(n for n in self.T if fnmatch.fnmatchcase(n, motif))


def _exacte(texte, operateurs=("==", "~=")) -> Optional[str]:
    """La version d'une contrainte exacte (`==3.11`, `~=3.11`, `==3.11.*`, ou `18.20.4` / `=18.20.4` pour Node) ; une
    borne (`>=`, `<`, `^`, `||`) ne désigne aucune version : None."""
    if not isinstance(texte, str):
        return None
    m = re.fullmatch(r"\s*(==|~=|=)?\s*(\d{1,4}(?:\.\d{1,4}){1,3})(?:\.\*)?\s*", texte)
    return m.group(2) if m and (m.group(1) or "") in operateurs else None


def _numero(texte: str) -> Optional[str]:
    m = re.search(r"(\d{1,4}(?:\.\d{1,4}){0,2})", texte or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------- familles
# Chaque détecteur rend None (famille absente) ou {"outils": {}, "commande": [..] | None, "verrou": [noms], "xmx": int|None}

def _python(c: _Contexte):
    marques = [n for n in c.F if re.fullmatch(r"requirements[^/]*\.txt", n)] + \
              [n for n in ("pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini") if n in c.F]
    if not marques:
        return None
    pytest = "pytest.ini" in c.F or any("pytest" in c.T.get(n, "").lower() for n in marques)
    outils = {}
    v = None
    if ".python-version" in c.T:
        v = c.version("python", ".python-version", _premiere_ligne(c.T[".python-version"]), "python")
    elif "pyproject.toml" in c.T:
        requis = _toml(c.T["pyproject.toml"]).get("project", {}).get("requires-python")
        exacte = _exacte(requis)
        if exacte:
            v = c.version("python", "pyproject.toml", exacte, "python")
        elif isinstance(requis, str):
            c.approximer("version python non exacte dans pyproject.toml")
    elif ".tool-versions" in c.T:
        m = re.search(r"^python\s+(\S+)", c.T[".tool-versions"], re.M)
        if m:
            v = c.version("python", ".tool-versions", m.group(1), "python")
    if v:
        outils["python"] = v
    commande = ["pytest"] if pytest else ["python3", "-m", "unittest", "discover"]
    verrous = [n for n in ("poetry.lock", "uv.lock") if n in c.F] or sorted(n for n in c.F if re.fullmatch(r"requirements[^/]*\.txt", n))
    return {"outils": outils, "commande": commande, "verrou": verrous}


def _node(c: _Contexte):
    if "package.json" not in c.F:
        return None
    pj = _json(c.T.get("package.json"))
    outils = {}
    v = None
    if ".nvmrc" in c.T:
        v = c.version("node", ".nvmrc", _premiere_ligne(c.T[".nvmrc"]), "node")
    elif ".node-version" in c.T:
        v = c.version("node", ".node-version", _premiere_ligne(c.T[".node-version"]), "node")
    elif isinstance(pj.get("engines"), dict) and isinstance(pj["engines"].get("node"), str):
        exacte = _exacte(pj["engines"]["node"], ("=", ""))
        if exacte:
            v = c.version("node", "package.json", exacte, "node")
        else:
            c.approximer("version node non exacte dans package.json")
    elif ".tool-versions" in c.T:
        m = re.search(r"^node(?:js)?\s+(\S+)", c.T[".tool-versions"], re.M)
        if m:
            v = c.version("node", ".tool-versions", m.group(1), "node")
    if v:
        outils["node"] = v
    gestionnaire = "npm"
    if "pnpm-lock.yaml" in c.F:
        gestionnaire = "pnpm"
    elif "yarn.lock" in c.F:
        gestionnaire = "yarn"
    elif isinstance(pj.get("packageManager"), str):
        nom = pj["packageManager"].split("@")[0]
        if nom in ("npm", "pnpm", "yarn"):
            gestionnaire = nom
    scripts = pj.get("scripts")
    a_test = isinstance(scripts, dict) and isinstance(scripts.get("test"), str)
    verrous = [n for n in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock") if n in c.F]
    return {"outils": outils, "commande": [gestionnaire, "test"] if a_test else None, "verrou": verrous[:1],
            "gestionnaire": gestionnaire}


def _gradle(c: _Contexte):
    if not any(n in c.F for n in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")):
        return None
    android = any(fnmatch.fnmatchcase(n, "*AndroidManifest.xml") for n in c.F)
    sources = [t for n, t in sorted(c.T.items(), key=lambda x: (x[0].count("/"), x[0]))
               if fnmatch.fnmatchcase(n, "*build.gradle") or fnmatch.fnmatchcase(n, "*build.gradle.kts")]
    texte = "\n".join(sources)
    outils = {}
    m = re.search(r"gradle-(\d{1,3}(?:\.\d{1,3}){1,2})-(?:bin|all)\.zip",
                  c.T.get("gradle/wrapper/gradle-wrapper.properties", ""))
    if m:
        outils["gradle"] = m.group(1)
    m = re.search(r"JavaVersion\.VERSION_(\d{1,2})(?:_(\d{1,2}))?", texte) or None
    jdk = None
    if m:
        jdk = m.group(2) if m.group(1) == "1" and m.group(2) else m.group(1)
    else:
        m = re.search(r"(?:jvmToolchain\(|JavaLanguageVersion\.of\()\s*(\d{1,2})\s*\)", texte)
        jdk = m.group(1) if m else None
    if jdk:
        outils["jdk"] = c.version("jdk", "build.gradle", jdk, "java")
    if android:
        info = {"compileSdk": None, "build_tools": None, "ndk": None, "agp": None}
        m = re.search(r"compileSdk(?:Version)?\s*(?:=\s*)?(\d{2,3})\b", texte) or \
            re.search(r"compileSdk\s*\{[^}]{0,200}?release\((\d{2,3})", texte)
        if m:
            info["compileSdk"] = int(m.group(1))
        m = re.search(r"buildToolsVersion\s*(?:=\s*)?[\"'](\d{1,3}(?:\.\d{1,3}){1,3})[\"']", texte)
        if m:
            info["build_tools"] = m.group(1)
        m = re.search(r"ndkVersion\s*(?:=\s*)?[\"'](\d{1,3}(?:\.\d{1,3}){1,3})[\"']", texte)
        if m:
            info["ndk"] = m.group(1)
        m = re.search(r"com\.android\.(?:application|library)[\"')\s]{1,6}version\s*[\"'](\d{1,3}\.\d{1,3}\.\d{1,3})[\"']",
                      texte) or re.search(r"com\.android\.tools\.build:gradle:(\d{1,3}\.\d{1,3}\.\d{1,3})", texte)
        if m:
            info["agp"] = m.group(1)
        elif "gradle/libs.versions.toml" in c.T:
            agp = _toml(c.T["gradle/libs.versions.toml"]).get("versions", {}).get("agp")
            if isinstance(agp, str) and re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", agp):
                info["agp"] = agp
        outils["android"] = info
    xmx = None
    m = re.search(r"org\.gradle\.jvmargs\s*=[^\n]*?-Xmx(\d+[kKmMgG]?)", c.T.get("gradle.properties", ""))
    if m:
        xmx = _taille_mo(m.group(1))
    implicite = [n for n in c.T if n in ("settings.gradle", "settings.gradle.kts", "gradle.properties",
                                         "gradle/libs.versions.toml", "gradle/wrapper/gradle-wrapper.properties")
                 or fnmatch.fnmatchcase(n, "*build.gradle") or fnmatch.fnmatchcase(n, "*build.gradle.kts")]
    famille = "gradle-android" if android else "gradle-jvm"
    return {"famille": famille, "outils": {k: v for k, v in outils.items() if v}, "xmx": xmx,
            "commande": ["./gradlew", "testDebugUnitTest" if android else "test"],
            "verrou": [n for n in ("gradle.lockfile",) if n in c.F], "implicite": implicite}


def _maven(c: _Contexte):
    if "pom.xml" not in c.F:
        return None
    outils = {}
    texte = c.T.get("pom.xml", "")
    m = re.search(r"<(?:maven\.compiler\.release|maven\.compiler\.source|java\.version)>\s*(\d{1,2}(?:\.\d{1,2})?)\s*<", texte)
    if m:
        outils["jdk"] = c.version("jdk", "pom.xml", m.group(1), "java")
    m = re.search(r"apache-maven-(\d{1,2}\.\d{1,2}\.\d{1,2})", c.T.get(".mvn/wrapper/maven-wrapper.properties", ""))
    if m:
        outils["maven"] = m.group(1)
    enveloppe = ".mvn/wrapper/maven-wrapper.properties" in c.F
    return {"outils": {k: v for k, v in outils.items() if v},
            "commande": ["./mvnw", "-B", "test"] if enveloppe else ["mvn", "-B", "test"], "verrou": [],
            "implicite": sorted(n for n in c.T if n == "pom.xml" or fnmatch.fnmatchcase(n, "*/pom.xml"))}


def _dotnet(c: _Contexte):
    projets = [n for n in c.F if n.endswith((".csproj", ".sln"))]
    if not projets:
        return None
    outils = {}
    version = _version_sdk(c)
    if version:
        outils["dotnet"] = version
    return {"outils": outils, "commande": ["dotnet", "test"], "verrou": [n for n in ("packages.lock.json",) if n in c.F]}


def _version_sdk(c: _Contexte) -> Optional[str]:
    sdk = _json(c.T.get("global.json")).get("sdk")
    if isinstance(sdk, dict) and isinstance(sdk.get("version"), str):
        return c.version("dotnet", "global.json", sdk["version"])
    meilleur = None
    for nom in c.tout("*.csproj"):
        for m in re.finditer(r"<TargetFrameworks?>([^<]{1,200})<", c.T[nom]):
            for tfm in m.group(1).split(";"):
                v = re.fullmatch(r"net(\d{1,2}\.\d)", tfm.strip())
                if v and (meilleur is None or float(v.group(1)) > float(meilleur)):
                    meilleur = v.group(1)
    return meilleur


def _go(c: _Contexte):
    if "go.mod" not in c.F:
        return None
    texte = c.T.get("go.mod", "")
    outils = {}
    m = re.search(r"^toolchain\s+go(\d{1,2}\.\d{1,3}(?:\.\d{1,3})?)\s*$", texte, re.M) or \
        re.search(r"^go\s+(\d{1,2}\.\d{1,3}(?:\.\d{1,3})?)\s*$", texte, re.M)
    if m:
        outils["go"] = m.group(1)
    return {"outils": outils, "commande": ["go", "test", "./..."], "verrou": [n for n in ("go.sum",) if n in c.F]}


def _rust(c: _Contexte):
    if "Cargo.toml" not in c.F:
        return None
    outils = {}
    canal = None
    if "rust-toolchain.toml" in c.T:
        canal = _toml(c.T["rust-toolchain.toml"]).get("toolchain", {}).get("channel")
    elif "rust-toolchain" in c.T:
        brut = _premiere_ligne(c.T["rust-toolchain"])
        canal = _toml(c.T["rust-toolchain"]).get("toolchain", {}).get("channel") if "[" in c.T["rust-toolchain"] else brut
    if canal is None:
        canal = _toml(c.T.get("Cargo.toml")).get("package", {}).get("rust-version")
    if isinstance(canal, str):
        if re.fullmatch(r"stable|beta|nightly(-\d{4}-\d{2}-\d{2})?", canal):
            outils["rust"] = canal
        else:
            v = c.version("rust", "rust-toolchain", canal)
            if v:
                outils["rust"] = v
    return {"outils": outils, "commande": ["cargo", "test"], "verrou": [n for n in ("Cargo.lock",) if n in c.F]}


def _godot(c: _Contexte):
    if "project.godot" not in c.F:
        return None
    outils = {}
    m = re.search(r'config/features\s*=\s*PackedStringArray\(\s*"(\d{1,2}\.\d{1,2})"', c.T.get("project.godot", ""))
    if m:
        outils["godot"] = m.group(1)
    commande = ["godot", "--headless", "--script", "res://tests/lanceur.gd"] if "tests/lanceur.gd" in c.F else None
    return {"outils": outils, "commande": commande, "verrou": []}


def _unity(c: _Contexte):
    if "ProjectSettings/ProjectVersion.txt" not in c.F:
        return None
    texte = c.T.get("ProjectSettings/ProjectVersion.txt", "")
    outils = {}
    m = re.search(r"^m_EditorVersion:\s*(\S+)\s*$", texte, re.M)
    if m:
        if _VERSION_UNITY.fullmatch(m.group(1)):
            outils["unity"] = m.group(1)
        else:
            c.refuser("unity", "ProjectVersion.txt")
    m = re.search(r"^m_EditorVersionWithRevision:[^\n(]*\(([^)\n]*)\)", texte, re.M)
    if m and _REVISION_UNITY.fullmatch(m.group(1)):
        outils["unity_revision"] = m.group(1)
    git = False
    deps = _json(c.T.get("Packages/manifest.json")).get("dependencies")
    if isinstance(deps, dict):
        git = any(isinstance(v, str) and (v.startswith("git") or ".git" in v) for v in deps.values())
    commande = ["unity-editor", "-batchmode", "-nographics", "-projectPath", "/work", "-runTests", "-testPlatform",
                "EditMode", "-testResults", "/tmp/resultats.xml", "-logFile", "/tmp/unity.log"]
    return {"outils": outils, "commande": commande, "verrou": [n for n in ("Packages/packages-lock.json",) if n in c.F],
            "git": git}


def _ruby(c: _Contexte):
    if "Gemfile" not in c.F:
        return None
    outils = {}
    if ".ruby-version" in c.T:
        v = c.version("ruby", ".ruby-version", _premiere_ligne(c.T[".ruby-version"]))
        if v:
            outils["ruby"] = v
    return {"outils": outils, "commande": ["bundle", "exec", "rake", "test"], "verrou": [n for n in ("Gemfile.lock",) if n in c.F]}


def _php(c: _Contexte):
    if "composer.json" not in c.F:
        return None
    cj = _json(c.T.get("composer.json"))
    outils = {}
    requis = cj.get("require", {}).get("php") if isinstance(cj.get("require"), dict) else None
    if isinstance(requis, str) and _numero(requis):
        v = c.version("php", "composer.json", _numero(requis))
        if v:
            outils["php"] = v
    scripts = cj.get("scripts")
    a_test = isinstance(scripts, dict) and "test" in scripts
    return {"outils": outils, "commande": ["composer", "test"] if a_test else None,
            "verrou": [n for n in ("composer.lock",) if n in c.F]}


def _make(c: _Contexte):
    if "Makefile" not in c.F:
        return None
    a_test = re.search(r"^test\s*:", c.T.get("Makefile", ""), re.M) is not None
    return {"outils": {}, "commande": ["make", "test"] if a_test else None, "verrou": []}


_DETECTEURS = (("python", _python), ("node", _node), ("gradle", _gradle), ("maven", _maven), ("dotnet", _dotnet),
               ("go", _go), ("rust", _rust), ("godot", _godot), ("unity", _unity), ("ruby", _ruby), ("php", _php),
               ("make", _make))


# ---------------------------------------------------------------- non déportable (§ 5.14)

def _contexte_leger(racine: str, lire: Optional[Callable[[str], Optional[str]]]) -> _Contexte:
    fichiers, dossiers, tronque = _scanner(str(racine))
    return _contexte_lu(str(racine), fichiers, dossiers, lire or _lecteur_defaut(str(racine)), tronque)


def _contexte_lu(racine: str, fichiers: List[str], dossiers: List[str], lire, tronque: bool = False) -> _Contexte:
    cibles = sorted((n for n in fichiers if _est_lu(n)), key=lambda n: (n.count("/"), n))[:MAX_LECTURES]
    textes = {}
    for rel in cibles:
        t = lire(rel)
        if isinstance(t, str):
            textes[rel] = t[:_limite(rel)]
    return _Contexte(textes, fichiers, dossiers, tronque)


def _non_deportable(c: _Contexte) -> Optional[str]:
    """N1, N2 et N6 du § 5.14, par noms et motifs ; N3 à N5 viennent du profil forcé ou de l'évaluation."""
    projets = "\n".join(c.T[n] for n in c.tout("*.csproj"))
    if re.search(r"<TargetFrameworkVersion>\s*v4\.", projets) or any(_N1_TFM.fullmatch(t.strip()) for m in
            re.finditer(r"<TargetFrameworks?>([^<]{1,200})<", projets) for t in m.group(1).split(";")):
        return "N1 : chaîne d'outils propre à Windows (.NET Framework)"
    if re.search(r"<(?:UseWPF|UseWindowsForms)>\s*true\s*<", projets, re.I):
        return "N1 : chaîne d'outils propre à Windows (WPF ou Windows Forms)"
    if any(n.endswith(".vcxproj") for n in c.F):
        return "N1 : chaîne d'outils propre à Windows (C++ MSBuild)"
    if any(d.endswith((".xcodeproj", ".xcworkspace")) for d in c.D) or "Podfile" in c.F:
        return "N2 : macOS ou iOS (Xcode)"
    for nom in c.tout("*.csproj"):
        for m in re.finditer(r"<RuntimeIdentifiers?>([^<]{1,200})<", c.T[nom]):
            if any(re.search(r"-(?:arm|arm64|x86)$", r.strip()) for r in m.group(1).split(";")):
                return "N6 : architecture autre que x86_64 imposée"
    for nom in (".cargo/config.toml", ".cargo/config"):
        cible = _toml(c.T.get(nom)).get("build", {}).get("target")
        if isinstance(cible, str) and not cible.startswith("x86_64"):
            return "N6 : architecture autre que x86_64 imposée"
    return None


def non_deportable(racine: str, lire: Optional[Callable[[str], Optional[str]]] = None) -> Optional[str]:
    """La raison N1, N2 ou N6 du § 5.14 détectée statiquement, ou None."""
    return _non_deportable(_contexte_leger(racine, lire))


# ---------------------------------------------------------------- CI

def _ci(c: _Contexte, commande: Optional[List[str]]) -> Tuple[bool, bool]:
    """(confirme, contredit) : les versions et la commande lues dans `.github/workflows`, comparées à celles du projet."""
    versions: Dict[str, set] = {}
    lignes: List[str] = []
    for nom in c.tout(".github/workflows/*"):
        texte = c.T[nom]
        for m in _EXPORT_CI.finditer(texte):
            versions.setdefault(m.group(1), set()).add(m.group(2))
        lignes += re.findall(r"^\s*-?\s*run:\s*(.{1,300})$", texte, re.M)
    confirme = contredit = False
    for outil, lues in c.versions_fichier.items():
        if outil in versions:
            # majeure.mineure pour python, go et dotnet ; la majeure pour node et java (et ce que le fichier précise)
            n = 2 if outil in ("python", "go", "dotnet") else 1
            lue = lues.split(".")[:n]
            if any(v.split(".")[:len(lue)] == lue for v in versions[outil]):
                confirme = True
            else:
                contredit = True
    if commande and any(" ".join(commande) in ligne for ligne in lignes):
        confirme = True
    return confirme, contredit


# ---------------------------------------------------------------- analyse

def _commande_donnee(commande, catalogue) -> Optional[List[str]]:
    if commande:
        return [str(x) for x in commande]
    texte = ((catalogue or {}).get("tests") or {}).get("commande")
    if isinstance(texte, str) and texte.strip():
        try:
            return shlex.split(texte)
        except ValueError:
            return None
    return None


_FAMILLE_DE_COMMANDE = {
    "npm": "node", "npx": "node", "node": "node", "pnpm": "node", "yarn": "node", "jest": "node", "vitest": "node",
    "python": "python", "python3": "python", "py": "python", "pytest": "python", "gradlew": "gradle", "gradle": "gradle",
    "mvn": "maven", "mvnw": "maven", "dotnet": "dotnet", "go": "go", "cargo": "rust", "godot": "godot",
    "unity-editor": "unity", "unity": "unity", "bundle": "ruby", "rake": "ruby", "composer": "php", "php": "php",
    "make": "make"}


def _famille_cible(donnee: Optional[List[str]], familles: List[str]) -> Optional[str]:
    """La famille qui reçoit la commande enregistrée ou celle du catalogue : celle de son exécutable (npm → node,
    ./gradlew → gradle-android ou gradle-jvm…), à défaut la première détectée."""
    if not familles or not donnee:
        return familles[0] if familles else None
    nom = re.sub(r"\.(exe|cmd|bat)$", "", os.path.basename(donnee[0].replace("\\", "/")).lower())
    voulue = _FAMILLE_DE_COMMANDE.get(nom)
    for f in familles:
        if f == voulue or (voulue == "gradle" and f.startswith("gradle")):
            return f
    return familles[0]


# Familles que chaque raison de non_deportable concerne : N1 (.NET Framework, WPF, C++ MSBuild), N2 (Xcode : aucune de nos
# familles de tests ne l'utilise), N6 (cible Cargo ou RuntimeIdentifier hors x86_64).
_CONCERNEES = {"N1": ("dotnet",), "N2": (), "N6": ("rust", "dotnet")}


def _famille_lancee(lancee: List[str]) -> Optional[str]:
    """La famille de l'exécutable de la commande lancée (npx → node, ./gradlew → gradle…), ou None si inconnue."""
    if not lancee:
        return None
    return _FAMILLE_DE_COMMANDE.get(re.sub(r"\.(exe|cmd|bat)$", "", os.path.basename(str(lancee[0]).replace("\\", "/")).lower()))


def _non_deportable_de(raison: Optional[str], lancee: Optional[List[str]]) -> Optional[str]:
    """`raison` (celle du projet entier) ne vaut que pour la commande lancée si sa famille est concernée ; une commande dont la
    famille est inconnue garde la raison du projet (jamais de route sur un doute)."""
    if raison is None or not lancee:
        return raison
    famille = _famille_lancee(lancee)
    if famille is None:
        return raison
    concernees = _CONCERNEES.get(raison.split(" ", 1)[0], None)
    if concernees is None or famille in concernees:
        return raison
    return None


def analyser(racine: str, commande: Optional[List[str]] = None, catalogue=None, lire=None,
             lancee: Optional[List[str]] = None) -> Profil:
    """Le profil d'exécution du projet `racine`. Pur : ne lit que `LUS` (par `lire`, `(chemin relatif) -> Optional[str]`,
    par défaut une lecture bornée qui refuse liens et exclus), hache les `VERROUS`, n'exécute rien. `commande` (la commande
    enregistrée de l'action `tests`) puis la commande du catalogue (celui du genre du projet à défaut de `catalogue`)
    priment sur la CI, qui prime sur la déduction ; elles s'appliquent à la famille de leur exécutable. `lancee` (facultatif) :
    la commande réellement lancée ; `non_deportable` ne dit alors que ce qui concerne sa famille (un projet React Native avec
    ios/ reste déportable pour jest), et reste celui du projet entier si la famille de la commande est inconnue."""
    racine = str(racine)
    if catalogue is None:
        catalogue = _catalogue_borne(racine)
    fichiers, dossiers, tronque = _scanner(racine)
    c = _contexte_lu(racine, fichiers, dossiers, lire or _lecteur_defaut(racine), tronque)
    donnee = _commande_donnee(commande, catalogue)

    familles, outils, commandes, deps, caches = [], {}, [], {}, []
    xmx, git_upm, explicites = None, False, 0
    ci_confirme = ci_contredit = False
    trouves = [(r.get("famille", nom), r) for nom, detecteur in _DETECTEURS for r in [detecteur(c)] if r is not None]
    cible = _famille_cible(donnee, [f for f, _ in trouves])
    for famille, r in trouves:
        premiere = famille == cible
        familles.append(famille)
        for k, v in r["outils"].items():
            if k in outils and outils[k] != v:
                c.raisons.append("outil %s : deux versions différentes dans le projet" % k)
                c.rejete = True
            else:
                outils.setdefault(k, v)
        cmd = (donnee if (premiere and donnee) else None) or r["commande"]
        if premiere and donnee:
            explicites += 1
        if cmd:
            commandes.append(cmd)
        gestionnaire, code = _GESTIONNAIRES.get(famille, (None, False))
        gestionnaire = r.get("gestionnaire", gestionnaire)
        verrou = r["verrou"][0] if r["verrou"] else None
        if verrou:
            empreinte = _hacher_verrou(racine, verrou)
        else:
            textes = ["%s\n%s" % (n, c.T[n]) for n in sorted(r.get("implicite", ())) if n in c.T]
            empreinte = hashlib.sha256("\n".join(textes).encode("utf-8")).hexdigest() if textes else None
        deps[famille] = {"gestionnaire": gestionnaire, "verrou": verrou, "empreinte": empreinte,
                         "reseau": gestionnaire is not None, "execute_du_code": code}
        if famille in _CACHES:
            caches.append(_CACHES[famille])
        xmx = r.get("xmx") or xmx
        git_upm = git_upm or bool(r.get("git"))
        confirme, contredit = _ci(c, cmd)
        ci_confirme, ci_contredit = ci_confirme or confirme, ci_contredit or contredit
    if "unity" in familles:
        deps["unity"]["reseau"] = True
        deps["unity"]["git"] = git_upm

    if xmx and xmx > MAX_XMX_MO:
        c.approximer("mémoire Gradle plafonnée (-Xmx du projet trop grand)")
    raisons = list(c.raisons)
    if ci_contredit:
        raisons.append("la CI et les fichiers du projet ne disent pas la même version")
    if not familles:
        raisons.append("pile inconnue")
    if c.rejete or ci_contredit or not familles:
        confiance = "basse"
    elif c.plafond:
        confiance = "moyenne"
    elif explicites or ci_confirme:
        confiance = "haute"
    else:
        confiance = "moyenne"

    res = {"cpus": 0, "memoire_mo": 0, "disque_mo": 0, "kvm": False, "gpu": False, "duree_s": 0}
    for f in familles:
        r = ressources_par_defaut(f, xmx)
        for k in ("cpus", "memoire_mo", "disque_mo", "duree_s"):
            res[k] = max(res[k], r[k])
    if not familles:
        res = ressources_par_defaut("python")
    profil = Profil(familles=tuple(familles), outils=outils, commandes=commandes, deps=deps, caches=caches,
                    ressources=res, isolement="licence" if "unity" in familles else "standard",
                    non_deportable=_non_deportable_de(_non_deportable(c), lancee), confiance=confiance, raisons=tuple(raisons))
    return replace(profil, empreinte=empreinte_profil(profil))
