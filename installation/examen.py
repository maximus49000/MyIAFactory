"""L'examen du dossier d'un projet : vide, existant, déjà installé. Borné, sans réseau, n'écrit rien.

Il ne lit aucun contenu, sauf la première ligne de `ProjectSettings/ProjectVersion.txt` et, pour les partenaires déjà
définis, les noms et adresses des serveurs de `.mcp.json`, les dépendances déclarées (`package.json`,
`requirements.txt`, `pyproject.toml`) et les **noms** des variables de `.env.example`. Jamais le `.env`."""
import fnmatch
import json
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


# Paquets des partenaires connus (npm et PyPI) -> id du catalogue.
PAQUETS_PARTENAIRES = {
    "elevenlabs": "elevenlabs", "@elevenlabs/elevenlabs-js": "elevenlabs", "openai": "openai",
    "replicate": "replicate", "fal-client": "fal", "@fal-ai/client": "fal", "@fal-ai/serverless-client": "fal",
    "stability-sdk": "stability", "deepl": "deepl", "deepl-node": "deepl", "cartesia": "cartesia",
    "@cartesia/cartesia-js": "cartesia", "assemblyai": "assemblyai", "@deepgram/sdk": "deepgram",
    "deepgram-sdk": "deepgram", "lumaai": "luma", "runwayml": "runway", "@runwayml/sdk": "runway",
    "stripe": "stripe", "twilio": "twilio", "@sendgrid/mail": "sendgrid", "sendgrid": "sendgrid", "resend": "resend",
    "@supabase/supabase-js": "supabase", "supabase": "supabase", "@sentry/node": "sentry",
    "@sentry/browser": "sentry", "@sentry/react": "sentry", "sentry-sdk": "sentry",
    "@pinecone-database/pinecone": "pinecone", "pinecone": "pinecone", "pinecone-client": "pinecone",
    "@google/genai": "google-gemini", "google-genai": "google-gemini", "google-generativeai": "google-gemini",
    "@mistralai/mistralai": "mistral", "mistralai": "mistral", "groq-sdk": "groq", "groq": "groq",
    "cohere": "cohere", "cohere-ai": "cohere", "mapbox-gl": "mapbox", "posthog-js": "posthog", "posthog": "posthog",
    "@tavily/core": "tavily", "tavily-python": "tavily", "exa-js": "exa", "exa-py": "exa",
    "@mendable/firecrawl-js": "firecrawl", "firecrawl-py": "firecrawl", "qdrant-client": "qdrant",
    "@qdrant/js-client-rest": "qdrant", "weaviate-client": "weaviate", "chromadb": "chroma",
    "@notionhq/client": "notion", "@slack/web-api": "slack", "slack-sdk": "slack", "@linear/sdk": "linear",
    "mixpanel": "mixpanel", "@upstash/redis": "upstash", "@neondatabase/serverless": "neon", "convex": "convex",
}
OCTETS_MAX_MANIFESTE = 512 * 1024
_NOM_PAQUET = re.compile(r"^\s*([A-Za-z0-9@][A-Za-z0-9@/._-]*)")
_NOM_VARIABLE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _lire_borne(chemin):
    try:
        if chemin.is_file() and not _est_lien(chemin) and chemin.stat().st_size <= OCTETS_MAX_MANIFESTE:
            return chemin.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        pass
    return None


def _dependances(d):
    """Les noms des dépendances déclarées (jamais leurs versions ni le reste du fichier)."""
    noms = set()
    texte = _lire_borne(d / "package.json")
    if texte:
        try:
            pj = json.loads(texte)
            for c in ("dependencies", "devDependencies", "optionalDependencies"):
                if isinstance(pj.get(c), dict):
                    noms |= set(pj[c])
        except (ValueError, AttributeError):
            pass
    texte = _lire_borne(d / "requirements.txt")
    for ligne in (texte or "").splitlines():
        m = _NOM_PAQUET.match(ligne.split("#")[0])
        if m:
            noms.add(m.group(1))
    texte = _lire_borne(d / "pyproject.toml")
    for m in re.finditer(r'"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:[<>=!~;].*?)?"', texte or ""):
        noms.add(m.group(1))
    return {n.lower().replace("_", "-") if not n.startswith("@") else n.lower() for n in noms}


def _partenaires_declares(d):
    """Les partenaires déjà définis dans le projet : serveurs de `.mcp.json` (nom et adresse seulement), paquets connus
    dans les dépendances, noms des variables de `.env.example` (avec le partenaire qui les attend, s'il est connu)."""
    from partenaires.catalogue import lire
    from partenaires.detection import _lire_json
    mcp = []
    m = _lire_json(d / ".mcp.json") if _lire_borne(d / ".mcp.json") is not None else None
    serveurs = m.get("mcpServers") if isinstance(m, dict) else None
    if isinstance(serveurs, dict):
        for nom, s in list(serveurs.items())[:50]:
            url = s.get("url") if isinstance(s, dict) else None
            mcp.append({"nom": str(nom), "url": url if isinstance(url, str) else None})
    deps = _dependances(d)
    paquets = [{"paquet": p, "id": PAQUETS_PARTENAIRES[p]} for p in sorted(deps) if p in PAQUETS_PARTENAIRES]
    try:
        par_variable = {v: p["id"] for p in lire()["partenaires"] for c in p.get("connexions") or []
                        for v in c.get("variables") or []}
    except (OSError, ValueError):
        par_variable = {}
    variables = []
    for ligne in (_lire_borne(d / ".env.example") or "").splitlines()[:500]:
        mv = _NOM_VARIABLE.match(ligne)
        if mv and not ligne.lstrip().startswith("#"):
            variables.append({"nom": mv.group(1), "id": par_variable.get(mv.group(1))})
    return {"mcp": mcp, "paquets": paquets, "variables": variables}


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
        "partenaires_declares": _partenaires_declares(d),
    }
