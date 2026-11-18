"""L'anonymisation d'une leçon avant son partage : on doit pouvoir y lire des concepts, jamais retrouver le projet.

Trois niveaux, réglés au bureau :
- `standard` : le filtre automatique. Les mots du projet (mots interdits, nom, dossier, dépôt) deviennent « le
  projet » ; adresses web, e-mails, adresses IP, chemins, noms de fichiers propres au projet, références de tickets ou
  de tâches, identifiants, empreintes et longs nombres sont remplacés par un mot générique.
- `renforce` (par défaut) : le filtre, puis une relecture par Claude qui réécrit la leçon en concepts généraux, puis le
  filtre de nouveau. Sans relecture possible, la leçon attend (jamais envoyée sans elle).
- `strict` : comme `renforce`, puis le Directeur relit et valide le texte exact avant tout envoi.
"""
import re

from .memoire import normaliser_mot

NIVEAUX = ("standard", "renforce", "strict")
NIVEAU_DEFAUT = "renforce"
LIBELLES = {"standard": "Standard (filtre automatique)", "renforce": "Renforcé (filtre + relecture par Claude)",
            "strict": "Strict (renforcé + votre validation de chaque leçon)"}

# Des noms de fichiers que tout projet partage : ils disent un outil, pas un projet.
FICHIERS_COMMUNS = {
    "package.json", "package-lock.json", "tsconfig.json", "readme.md", "claude.md", "agents.md", "dockerfile",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "manage.py", "conftest.py", "__init__.py",
    ".gitignore", ".env", ".env.example", "makefile", "cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "settings.gradle", "androidmanifest.xml", "vite.config.js", "vite.config.ts", "webpack.config.js",
    "jest.config.js", "vitest.config.ts", "playwright.config.ts", "index.html", "index.js", "index.ts", "main.py",
    "app.py", "docker-compose.yml", "composer.json", "gemfile", "pubspec.yaml", "launch.json", "settings.json",
}

_REGLES = [
    ("adresse", re.compile(r"\b(?:https?|ftp|ssh|git)://[^\s)>\]\"'`]+|\bwww\.[^\s)>\]\"'`]+", re.I), "<adresse>"),
    ("e-mail", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "<e-mail>"),
    ("adresse IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<adresse IP>"),
    ("chemin", re.compile(r"(?:\b[A-Za-z]:\\|\\\\)[^\s\"'`<>|]*|(?<![\w<])(?:~|\.{1,2})?/(?:[\w.@-]+/)+[\w.@-]*"),
     "<chemin>"),
    ("empreinte", re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,64}\b", re.I), "<empreinte>"),
    ("identifiant", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
     "<identifiant>"),
    ("référence", re.compile(r"(?<![\w<])(?:#\d+|[A-Z]{2,10}-\d+|[tfe]\d{1,5}(?:-\w+)?)\b"), "<référence>"),
    ("nombre", re.compile(r"\b\d{5,}\b"), "<nombre>"),
]
_FICHIER = re.compile(r"(?<![\w<./\\-])([\w-]+(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]{0,5})\b")
_EXTENSIONS_FICHIER = {
    "py", "js", "ts", "tsx", "jsx", "mjs", "cjs", "json", "md", "html", "css", "scss", "java", "kt", "kts", "cs",
    "go", "rs", "rb", "php", "sql", "db", "sqlite", "xml", "yml", "yaml", "toml", "ini", "cfg", "txt", "csv", "xlsx",
    "xls", "docx", "pptx", "pdf", "png", "jpg", "jpeg", "svg", "gif", "vue", "svelte", "sh", "ps1", "bat", "dart",
    "swift", "gradle", "lock", "log", "env", "c", "h", "cpp", "hpp",
}


def mots_du_projet(mots_interdits=(), nom=None, base=None, depot=None):
    """Tout ce qui nomme le projet : ses mots interdits, son nom, le nom de son dossier, son dépôt (« compte/dépôt »)."""
    mots = [str(m) for m in (mots_interdits or ()) if str(m or "").strip()]
    for x in (nom, base):
        if x and str(x).strip():
            mots.append(str(x).strip())
    if depot:
        m = re.search(r"[:/]([^/:\s]+)/([^/\s]+?)(?:\.git)?/?$", str(depot))
        if m:
            mots += [m.group(1), m.group(2)]
    vus, sortie = set(), []
    for m in mots:
        cle = normaliser_mot(m)
        if len(cle) >= 3 and cle not in vus:   # « ui », « js » : trop courts pour nommer un projet
            vus.add(cle)
            sortie.append(m)
    return sortie


def _motif_mot(mot):
    """Le mot, insensible à la casse, aux accents près et aux séparateurs près (« Roadmap Reborn » = « roadmap-reborn »)."""
    parties = [p for p in normaliser_mot(mot).split(" ") if p]
    if not parties:
        return None
    lettres = {"a": "aàâäáã", "e": "eéèêë", "i": "iîïíì", "o": "oôöóò", "u": "uùûüú", "c": "cç", "y": "yÿ", "n": "nñ"}

    def lettre(ch):
        return f"[{lettres[ch]}]" if ch in lettres else re.escape(ch)

    morceaux = ["".join(lettre(ch) for ch in p) for p in parties]
    return re.compile(r"(?<![\w])" + r"[\s\-_'’./\\:]*".join(morceaux) + r"(?![\w])", re.I)


def filtrer(texte, mots=()):
    """(texte filtré, [ce qui a été remplacé, par sorte]). Ne refuse jamais : il remplace."""
    t = str(texte or "")
    vus = []
    for mot in sorted(mots or (), key=lambda m: -len(normaliser_mot(m))):   # les plus longs d'abord
        motif = _motif_mot(mot)
        if motif and motif.search(t):
            t = motif.sub("le projet", t)
            vus.append("nom du projet")
    for sorte, motif, remplacement in _REGLES:
        if motif.search(t):
            t = motif.sub(remplacement, t)
            vus.append(sorte)

    def fichier(m):
        nom = m.group(1)
        if nom.lower() in FICHIERS_COMMUNS or nom.rsplit(".", 1)[-1].lower() not in _EXTENSIONS_FICHIER:
            return nom
        vus.append("nom de fichier")
        return "<fichier ." + nom.rsplit(".", 1)[-1].lower() + ">"

    t = _FICHIER.sub(fichier, t)
    t = re.sub(r"(le projet)(\s+le projet)+", r"\1", t)
    return t, sorted(set(vus))


def reste_identifiant(texte, mots=()):
    """Les mots du projet encore présents (dernier contrôle, après la relecture)."""
    plat = f" {normaliser_mot(texte)} "
    return [m for m in mots if normaliser_mot(m) and f" {normaliser_mot(m)} " in plat]


CONSIGNE_RELECTURE = """Tu anonymises une leçon tirée d'un projet logiciel avant qu'elle soit partagée avec d'autres
équipes. Réécris-la pour qu'on y lise seulement des concepts réutilisables, sans pouvoir retrouver le projet :
- aucun nom de projet, de client, de produit, d'entreprise, de personne, de lieu, de marque propre au projet ;
- aucun nom de fichier, de module, de classe, de fonction, de table, d'écran ou de route propre au projet (dis ce que
  c'est : « le module d'export », « l'écran de saisie ») ; les outils publics (Python, React, Excel, Git…) peuvent rester ;
- aucune adresse, aucun identifiant, aucun numéro de ticket ou de tâche, aucune date, aucun chiffre métier ;
- garde le sens, la règle et la façon d'appliquer la leçon ; reste bref ; écris en français.
Les marqueurs entre chevrons (<chemin>, <adresse>…) viennent d'un premier filtre : supprime-les ou reformule.
Réponds UNIQUEMENT par un objet JSON sur une ligne : {"titre": "<titre court, 60 caractères au plus>",
"texte": "<la leçon réécrite>"}. Si la leçon ne peut pas être rendue générale, réponds {"refus": "<raison>"}."""


def message_relecture(titre, texte):
    return f"Titre : {titre}\n\nLeçon :\n{texte}\n"


def lire_relecture(reponse):
    """{titre, texte} ou {refus} depuis la réponse de Claude ; `ValueError` si elle est illisible."""
    import json
    m = re.search(r"\{.*\}", str(reponse or ""), re.S)
    if not m:
        raise ValueError("relecture illisible (pas de JSON)")
    d = json.loads(m.group(0))
    if isinstance(d.get("refus"), str) and d["refus"].strip():
        return {"refus": d["refus"].strip()[:300]}
    titre, texte = str(d.get("titre") or "").strip(), str(d.get("texte") or "").strip()
    if not texte:
        raise ValueError("relecture sans texte")
    return {"titre": (titre or texte.split(".")[0])[:80], "texte": texte}
