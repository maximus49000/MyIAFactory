"""L'accord d'outil : un agent arrêté faute d'un programme du shell que sa fiche ne lui ouvre pas.

Le moteur lit la commande refusée (`permission_denials` de la sortie de `claude -p`, voir `appel`), en tire le programme
(le premier mot de chaque commande du shell, nom seul) et décide, **en code** :
- le programme est connu du projet (un exécutable déclaré dans son environnement, ou un outil de base déjà ouvert aux
  agents) : le moteur ouvre `Bash(<programme>:*)` à cet agent et relance la tâche ;
- sinon (programme inconnu, outil autre que le shell, commande illisible) : une décision au bureau de direction.
Jamais `Bash` seul, jamais un premier mot qui n'est ni un nom simple ni un chemin absolu (chemin relatif, option,
variable, substitution), jamais un programme que le projet n'a pas déclaré, ni un programme désigné par son chemin,
sans l'accord du Directeur.
"""
import re

from moteur.environnement import MOTIF_EXECUTABLE
from orchestrateur import fiches as fi

COUPE = 160
SEPARATEURS = re.compile(r"&&|\|\||[;|&\n\r]")
TRANSPARENTS = ("cd",)      # aller dans un dossier ne demande aucun accord : ce n'est pas le programme qui manque
SECRET = re.compile(r"(?i)(-{0,2}[\w-]*(?:pass|pwd|secret|token|apikey|api-key|credential)[\w-]*)([=\s:]+)(\S+)")
EXTENSIONS = (".exe", ".cmd", ".bat", ".com")


def _normal(nom):
    nom = str(nom).strip().lower()
    for e in EXTENSIONS:
        if nom.endswith(e):
            return nom[:-len(e)]
    return nom


normal = _normal
_PREMIER_MOT = re.compile(r"""^\s*(?:"([^"]+)"|'([^']+)'|(\S+))""")
# Les redirections (`2>&1`, `> x.log`, `< x`) ne sont pas des programmes : `&` de `2>&1` n'est pas un séparateur.
_REDIRECTIONS = re.compile(r"""\d*>&\d+|&>\s*(?:"[^"]*"|'[^']*'|\S+)|\d*>>?\s*(?:"[^"]*"|'[^']*'|\S+)|<\s*(?:"[^"]*"|\S+)""")
# Les programmes dont un outil de l'agent tient lieu : on lui dit d'employer l'outil plutôt que d'ouvrir le programme.
REMPLACANTS = {"ls": "Glob", "dir": "Glob", "find": "Glob", "cat": "Read", "type": "Read", "head": "Read",
               "tail": "Read", "grep": "Grep", "rg": "Grep", "findstr": "Grep"}


def _morceaux(commande):
    return SEPARATEURS.split(_REDIRECTIONS.sub(" ", commande or ""))


def formes_a_corriger(commande, ouvert):
    """Ce que l'agent doit écrire autrement pour que sa fiche couvre sa commande (une phrase par correction) :
    un programme ouvert (`ouvert(nom)` vrai, nom normalisé ou chemin) appelé entre guillemets ou par son chemin au lieu
    de son nom, ou un programme dont un outil tient lieu (`ls` → Glob). Liste vide : rien à corriger dans la forme."""
    corrections = []
    for morceau in _morceaux(commande):
        m = _PREMIER_MOT.match(morceau)
        if not m:
            continue
        cite = m.group(1) or m.group(2)
        mot = (cite or m.group(3)).strip()
        if mot in TRANSPARENTS:
            continue
        if mot in REMPLACANTS and not ouvert(mot):
            corrections.append(f"au lieu de « {mot} », emploie ton outil {REMPLACANTS[mot]}")
            continue
        if cite and (MOTIF_EXECUTABLE.match(mot) or fi.est_chemin(mot)) and ouvert(_normal(mot)):
            corrections.append(f"appelle « {mot} » sans guillemets, au début de la commande")
            continue
        if "/" in mot or "\\" in mot:
            if fi.est_chemin(mot) and not cite and ouvert(_normal(mot)):
                continue      # le chemin lui-même est ouvert : la forme est bonne
            nom = _normal(re.split(r"[\\/]", mot)[-1])
            if MOTIF_EXECUTABLE.match(nom) and ouvert(nom):
                corrections.append(f"appelle « {nom} » par son nom (il est dans le PATH), jamais par son chemin")
    return corrections


def programmes(commande):
    """Les programmes d'une commande du shell, dans l'ordre et sans doublon (`cd` mis à part). `None` si l'un des
    premiers mots n'est pas un nom de programme simple : chemin, option, variable, guillemet, substitution."""
    vus = []
    for morceau in _morceaux(commande):
        mots = morceau.split()
        if not mots:
            continue
        mot = mots[0]
        if not MOTIF_EXECUTABLE.match(mot) and not fi.est_chemin(mot):
            return None
        if mot not in TRANSPARENTS and mot not in vus:
            vus.append(mot)
    return vus


def programme_refuse(commandes, outils):
    """`(programme, commande)` : le programme que la fiche (`outils`) n'ouvre pas dans la première commande refusée qui
    n'en nomme qu'un, avec cette commande ; `(None, commande)` si aucune ne permet de choisir (la première commande,
    ou `None`, est alors rendue)."""
    ouverts, tout = fi.programmes_ouverts({"outils": ", ".join(outils)})
    ouverts = {_normal(p) for p in ouverts}
    for commande in commandes:
        manquants = [p for p in programmes(commande) or [] if _normal(p) not in ouverts]
        if len(manquants) == 1 and not tout:
            return manquants[0], commande
    return None, (commandes[0] if commandes else None)


def declares(environnement):
    """Les exécutables que le projet déclare (`environnement[].executables`, installés ou à installer), sans casse ni
    extension."""
    noms = set()
    for outil in environnement or []:
        for n in (outil.get("executables") or []) if isinstance(outil, dict) else []:
            if isinstance(n, str) and n.strip():
                noms.add(_normal(n))
    return noms


def origine(programme, environnement):
    """Pourquoi le programme est « connu du projet » : `"déclaré du projet"`, `"de base des agents"` ou `None`. Un
    programme désigné par son chemin n'est jamais connu : il revient au Directeur."""
    if fi.est_chemin(programme):
        return None
    p = _normal(programme)
    if p in declares(environnement):
        return "déclaré du projet"
    de_base, _ = fi.programmes_ouverts({"outils": None})
    if p in {_normal(x) for x in de_base}:
        return "de base des agents"
    return None


def montrer(commande):
    """La commande refusée, telle que le bureau la montre : une ligne, les valeurs qui ressemblent à un secret
    remplacées, coupée."""
    if not commande:
        return ""
    ligne = " ".join(str(commande).split())
    ligne = SECRET.sub(lambda m: m.group(1) + m.group(2) + "***", ligne)
    return ligne if len(ligne) <= COUPE else ligne[:COUPE - 1].rstrip() + "…"
