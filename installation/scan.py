"""Le scan d'un répertoire existant, pour la création d'un projet (comme la lecture d'un projet existant à
l'installation, `skills/installer/SKILL.md` §3b) : l'inventaire de `examen.examiner` (déterministe, sans jamais lire une
valeur de clé), puis le résumé du métier (300 mots au plus) rédigé par un agent Haiku en lecture seule dans ce
répertoire. Le chef de la création reçoit le tout (`connaissance`) et n'a lui-même aucun outil.

Un résumé impossible (couche API, appel raté) n'empêche pas le scan : l'inventaire reste, `avertissement` dit pourquoi."""
import json
from pathlib import Path

from installation import examen
from installation.dossier import Echec
from moteur import appel

OUTILS_LECTURE = ["Read", "Glob", "Grep"]
MODELE_RESUME = "haiku"
MOTS_RESUME_MAX = 300
CARACTERES_RESUME_MAX = 3000
CONSIGNE = (
    "Tu lis un répertoire de projet existant (ton dossier courant) pour en faire connaître le métier à un chef qui va "
    "organiser un nouveau projet autour de lui. Tu reçois l'inventaire du répertoire (arbre, fichiers clés, extensions, "
    "environnement). Lis les fichiers clés, la documentation et un échantillon représentatif du code (pas tout) avec "
    "Read, Glob et Grep, et rien d'autre. Ne lis jamais un fichier de secrets (`.env`, clés, jetons, identifiants) et "
    "ne recopie jamais une valeur de clé. Rends UN résumé du métier en 300 mots au plus : le domaine, ce que le projet "
    "produit et pour qui, ses outils, son état, ses conventions (tests, structure), et ce qu'un agent devrait trouver "
    "dans son environnement (langage, version, dépendances, outils). Du texte simple, sans JSON ni introduction.")


def verifier_repertoire(chemin):
    """Le répertoire à scanner, résolu, ou `Echec` : il existe, c'est un dossier, et ce n'est pas la skill."""
    if not isinstance(chemin, str) or not chemin.strip():
        raise Echec("Le répertoire à scanner est vide.")
    d = Path(chemin.strip()).expanduser()
    if not d.is_dir():
        raise Echec(f"Le répertoire à scanner n'existe pas : {d}. Donnez le chemin d'un dossier existant.")
    d = d.resolve()
    from installation import creation
    if creation._dans(d, Path(creation.mep.RACINE)) or creation._dans(d, creation.dossier.skill()):
        raise Echec("Le dossier de la skill MyIAFactory ne se scanne pas : choisissez le répertoire de votre projet.")
    return d


def _resume(repertoire, inventaire, appeler, couche):
    """(le texte, les usages, l'avertissement) : un seul des deux premiers a un sens, l'avertissement dit l'échec."""
    if couche != "claude":
        return None, [], "Le résumé n'est rédigé qu'avec claude (la couche API ne lit pas de fichiers) : l'inventaire seul est donné."
    try:
        r = appeler(CONSIGNE, json.dumps(inventaire, ensure_ascii=False, indent=1), MODELE_RESUME, couche=couche,
                    outils=OUTILS_LECTURE, dossier_travail=str(repertoire), delai_s=300)
    except appel.ErreurAppel as e:
        return None, list(e.usages or []), f"Le résumé n'a pas pu être rédigé ({e.raison}) : l'inventaire seul est donné."
    texte = (r.texte or "").strip()[:CARACTERES_RESUME_MAX]
    return (texte or None), list(r.usages or []), (None if texte else "Le résumé est vide : l'inventaire seul est donné.")


def scanner(chemin, *, couche, appeler=appel.appeler, examiner=examen.examiner):
    """`(connaissance, usages)` du répertoire : `{repertoire, inventaire, environnement, partenaires_declares, resume,
    avertissement}`. `Echec` si le répertoire ne convient pas."""
    repertoire = verifier_repertoire(chemin)
    releve = examiner(str(repertoire))
    resume, usages, avertissement = _resume(repertoire, releve["inventaire"], appeler, couche)
    return {"repertoire": str(repertoire), "inventaire": releve["inventaire"], "environnement": releve["environnement"],
            "partenaires_declares": releve["partenaires_declares"], "resume": resume,
            "avertissement": avertissement}, usages
