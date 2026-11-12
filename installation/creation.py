"""Créer un projet vide depuis le bureau : son dossier, sa configuration sans workflow ni agent, son inscription au
bureau commun, et, si demandé, son dépôt GitHub privé.

Le projet est vide d'organisation jusqu'à sa première demande (le moteur propose alors son workflow). Un échec avant
l'inscription ne laisse rien : ni dossier à moitié écrit, ni bureau changé. Un échec de GitHub ne défait rien : le projet
reste créé, en local, et le résultat dit pourquoi.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from bureau import reglages as regl
from installation import dossier, mise_en_place as mep
from installation.dossier import Echec
from orchestrateur import factory as fa
from orchestrateur.memoire import executer_git

DELAI_GH_S = 120
LONGUEUR_MAX_NOM = 100
INTERDITS = set('<>:"/\\|?*')
RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
MESSAGE_PREMIER_COMMIT = "Création du projet avec MyIAFactory"


def executer_gh(args, cwd):
    """(code, sortie) d'une commande gh. Jamais de question posée au clavier."""
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}
    try:
        p = subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True, timeout=DELAI_GH_S, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"gh n'a pas pu s'exécuter : {e}"
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace").strip()


def verifier_nom(nom):
    """Le nom nettoyé, ou `Echec` : il devient le nom d'un dossier, sous Windows comme ailleurs."""
    if not isinstance(nom, str) or not nom.strip():
        raise Echec("Donnez un nom au projet.")
    nom = nom.strip()
    if len(nom) > LONGUEUR_MAX_NOM:
        raise Echec(f"Le nom du projet est trop long ({LONGUEUR_MAX_NOM} caractères au plus).")
    if nom in (".", "..") or nom.endswith("."):
        raise Echec("Le nom du projet ne peut pas être « . », « .. » ni finir par un point.")
    if any(c in INTERDITS or ord(c) < 32 for c in nom):
        raise Echec('Le nom du projet ne peut pas contenir les caractères < > : " / \\ | ? *.')
    if nom.split(".")[0].rstrip().upper() in RESERVES:
        raise Echec(f"« {nom} » est un nom réservé par Windows : choisissez-en un autre.")
    return nom


def _dans(chemin, parent):
    try:
        Path(chemin).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def verifier_parent(parent):
    """Le dossier parent, ou `Echec` : il existe, c'est un dossier, et ce n'est pas la skill."""
    parent = Path(str(parent)).expanduser() if parent else None
    if parent is None or not parent.is_dir():
        raise Echec(f"Le répertoire parent n'existe pas : {parent if parent else '(vide)'}. Donnez le chemin d'un "
                    "dossier existant.")
    racine = Path(mep.RACINE)
    if _dans(parent, racine) or _dans(parent, dossier.skill()):
        raise Echec("Le projet ne peut pas être créé dans le dossier de la skill MyIAFactory : choisissez un autre "
                    "répertoire parent.")
    return parent.resolve()


def _lire_origine(reglages_origine):
    """Les réglages repris du projet d'origine : {charge_max, moteur, modele_orchestrateur, agents_locaux_max,
    consignes}. Rien (valeurs par défaut) sans origine ; `Echec` si l'origine est illisible."""
    if reglages_origine is None:
        return {}
    chemin = Path(reglages_origine)
    try:
        r = json.loads(chemin.read_text(encoding="utf-8-sig"))
        if not isinstance(r, dict):
            raise ValueError("un objet JSON est attendu")
        repris = {"charge_max": r.get("charge_max"), "moteur": r.get("moteur")}
        if r.get("orchestrateur"):   # un projet sans orchestrateur n'a ni modèle ni consignes à reprendre
            f = fa.lire(chemin.parent / r["orchestrateur"])
            repris.update(modele_orchestrateur=f["modele_orchestrateur"], agents_locaux_max=f["agents_locaux_max"],
                          consignes=f["consignes"].read_text(encoding="utf-8-sig")
                          if f["consignes"] and f["consignes"].is_file() else None)
    except (OSError, ValueError, fa.FactoryInvalide) as e:
        raise Echec(f"Les réglages du projet d'origine sont illisibles ; le projet n'a pas été créé. {e}")
    return repris


def _consignes_par_defaut():
    return ("# Consignes propres du projet\n\nProjet créé vide depuis le bureau : son workflow sera proposé à sa "
            "première demande.\n")


def _github(projet, nom, git, gh):
    """Crée le dépôt privé et pousse. Rend « fait » ou la raison (et le geste pour le faire à la main)."""
    code, sortie = gh(["auth", "status"], projet)
    if code != 0:
        absent = "pas pu s'exécuter" in sortie
        return ("GitHub n'a pas été fait : gh (l'outil GitHub) n'est pas installé sur ce poste." if absent else
                "GitHub n'a pas été fait : gh n'est pas connecté à votre compte. Lancez « gh auth login », puis, dans "
                f"le dossier du projet : gh repo create {nom} --private --source . --push.")
    for args in (["init"], ["add", "."], ["commit", "-m", MESSAGE_PREMIER_COMMIT]):
        code, sortie = git(args, projet)
        if code != 0 and "pas pu s'exécuter" in sortie:
            return ("GitHub n'a pas été fait : git n'est pas installé sur ce poste. Installez git, puis, dans le "
                    f"dossier du projet : git init, git add ., git commit, gh repo create {nom} --private --source . --push.")
        if code != 0:
            return f"GitHub n'a pas été fait : git {args[0]} a échoué. {sortie}"[:400]
    code, sortie = gh(["repo", "create", nom, "--private", "--source", ".", "--push"], projet)
    if code != 0:
        return f"GitHub n'a pas été fait : le dépôt n'a pas pu être créé. {sortie}"[:400]
    return "fait"


def creer_projet(parent, nom, *, origine=None, mots_interdits=(), facturation=False, github=False, description=None,
                 genre=None, bureau_json, git=executer_git, gh=executer_gh, maintenant=None):
    """Crée `<parent>/<nom>/` avec sa configuration `.factory/` sans workflow ni agent, l'inscrit au bureau commun
    `bureau_json`, puis, si `github`, crée son dépôt privé.

    `origine` : le fichier de réglages du projet d'origine (charge, modèle de l'orchestrateur, agents locaux, couche du
    moteur et consignes en sont repris), ou rien. Rend {"reglages": Path, "id": str, "projet": Path, "github":
    "fait" | "non demandé" | <la raison>}. `Echec(message)` : rien n'est créé."""
    from datetime import datetime
    nom = verifier_nom(nom)
    parent = verifier_parent(parent)
    projet = parent / nom
    if projet.exists():
        raise Echec(f"« {nom} » existe déjà dans {parent} : choisissez un autre nom.")
    if genre is not None and not (isinstance(genre, str) and fa.MOTIF_GENRE.match(genre)):
        raise Echec("Le genre du projet est un identifiant (minuscules, chiffres et tirets).")
    if description is not None and not (isinstance(description, str) and description.strip()):
        description = None
    repris = _lire_origine(origine)
    interdits = [m.strip() for m in mots_interdits if isinstance(m, str) and m.strip()]
    if nom.lower() not in {m.lower() for m in interdits}:
        interdits.append(nom)   # le nom du projet ne part jamais dans la mémoire publique de la skill
    reglages_json = projet / ".factory" / "reglages.json"
    bureau_json = Path(bureau_json)
    try:
        mep._controler_bureau(bureau_json, reglages_json)
    except Echec as e:
        raise Echec(f"{e} Retirez-en un du bureau avant d'en créer un autre.") from None
    p = {"nom": nom, "mots_interdits": interdits, "services": [], "flux": [], "agents": [], "briefs": {},
         "facturation": bool(facturation), "controles": [], "description": description,
         "consignes": repris.get("consignes") or _consignes_par_defaut(),
         "modele_orchestrateur": repris.get("modele_orchestrateur") or "Sonnet",
         "agents_locaux_max": repris.get("agents_locaux_max") or 2,
         "charge_max": repris.get("charge_max") or 70,
         "moteur": repris.get("moteur") or {"couche": "claude"}}
    bureau_avant = mep._lire_octets(bureau_json)
    try:
        projet.mkdir()
        tmp = projet / ".factory.tmp"
        mep._ecrire_configuration(tmp, p, genre, maintenant or datetime.now())
        tmp.rename(projet / ".factory")
        mep.regler_gitignore(projet)
        mep.inscrire(bureau_json, reglages_json)
        fa.lire(projet / ".factory" / "factory.json")
    except BaseException as e:
        shutil.rmtree(projet, ignore_errors=True)
        mep._remettre(bureau_json, bureau_avant)
        if isinstance(e, (OSError, fa.FactoryInvalide)):
            raise Echec(f"Le projet n'a pas pu être créé : {e}") from e
        raise
    inscrit = next(x for x in regl.lire_bureau(bureau_json)["projets"]
                   if x["chemin"].resolve() == reglages_json.resolve())
    return {"reglages": reglages_json, "id": inscrit["id"], "projet": projet,
            "github": _github(projet, nom, git, gh) if github else "non demandé"}
