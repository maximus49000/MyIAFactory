"""La publication des livrables d'un projet en « releases » GitHub privées (le suivi des livrables se fait sur GitHub).

Un livrable téléchargeable (apk, aab, zip, exe…) n'entre jamais dans l'historique git : il est attaché à une release du
dépôt du projet, `v<numéro>` d'après le numéro du fichier (`FM_Stats_121.apk` → `v121`), sinon `v<date>`. Une release qui
existe déjà n'est pas refaite (rejouable sans effet). Un échec (gh absent ou déconnecté, projet pas sur GitHub, fichier
trop gros) est dit en clair et ne bloque jamais la livraison locale.
"""
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from installation.creation import executer_gh

EXTENSIONS = (".apk", ".aab", ".zip", ".exe", ".msi", ".dmg", ".ipa")
TAILLE_MAX = 2000 * 1024 * 1024        # GitHub : 2 Gio par fichier attaché à une release
DELAI_PUBLICATION_S = 900              # l'envoi d'un apk de 70 Mo peut durer plusieurs minutes sur une connexion lente
_NUMERO = re.compile(r"(\d+)\.[A-Za-z0-9]+$")


def executer_gh_long(args, cwd):
    """(code, sortie) d'une commande gh qui envoie un fichier : le même exécuteur, avec un délai long."""
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}
    try:
        p = subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True, timeout=DELAI_PUBLICATION_S, env=env,
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"gh n'a pas pu s'exécuter : {e}"
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace").strip()


def publiable(chemin):
    """Vrai pour un livrable téléchargeable (par son extension)."""
    return Path(str(chemin)).suffix.lower() in EXTENSIONS


def tag_de(fichier, maintenant=None):
    """`v<numéro du fichier>` (`FM_Stats_121.apk` → `v121`), sinon `v<date>-<heure>`."""
    m = _NUMERO.search(Path(str(fichier)).name)
    if m:
        return f"v{int(m.group(1))}"
    return "v" + (maintenant or datetime.now()).strftime("%Y%m%d-%H%M")


def _dernier_mot(sortie):
    lignes = [x.strip() for x in str(sortie).splitlines() if x.strip()]
    return lignes[-1] if lignes else ""


def depot_sur_github(projet, git):
    """Vrai si l'origine du dépôt du projet est sur GitHub."""
    code, sortie = git(["remote", "get-url", "origin"], projet)
    return code == 0 and "github.com" in sortie


def publier_fichier(projet, fichier, titre, git, gh, gh_long=None, maintenant=None):
    """Publie un fichier en release privée. Rend `{"fait": bool, "chemin", "tag", "url"?, "texte"}` ; ne lève jamais."""
    gh_long = gh_long or gh
    nom = Path(str(fichier)).name
    sortie_ko = {"fait": False, "chemin": str(fichier), "tag": None}
    p = Path(str(fichier))
    if not p.is_file():
        return {**sortie_ko, "texte": f"« {nom} » est introuvable : rien n'a été publié."}
    if p.stat().st_size > TAILLE_MAX:
        return {**sortie_ko, "texte": f"« {nom} » dépasse 2 Go, la limite de GitHub pour un fichier de release."}
    tag = tag_de(p, maintenant)
    deja, sortie = gh(["release", "view", tag, "--json", "url", "--jq", ".url"], projet)
    if deja == 0 and sortie.strip():
        return {"fait": True, "chemin": str(fichier), "tag": tag, "url": _dernier_mot(sortie),
                "texte": f"« {nom} » est déjà publié ({tag})."}
    code, sortie = gh_long(["release", "create", tag, str(p), "--title", (titre or nom)[:200], "--notes",
                            f"Livrable {nom}, publié automatiquement par MyIAFactory."], projet)
    if code != 0:
        return {**sortie_ko, "tag": tag, "texte": f"La release {tag} n'a pas pu être créée : {sortie}"[:400]}
    return {"fait": True, "chemin": str(fichier), "tag": tag, "url": _dernier_mot(sortie),
            "texte": f"« {nom} » publié en release {tag}."}


def publier_livrables(projet, livrables, resoudre, git, gh=executer_gh, gh_long=None, maintenant=None):
    """Publie les livrables téléchargeables d'une liste `[{chemin, titre}]` ; `resoudre(chemin)` rend le fichier réel.
    Rend `{"fait": bool, "texte": str, "releases": [{chemin, tag, url?, fait, texte}]}`. Rien n'est fait si le projet
    n'est pas sur GitHub ou si gh n'est pas connecté : le texte dit quoi faire."""
    candidats = [x for x in livrables if publiable(x.get("chemin"))]
    if not candidats:
        return {"fait": True, "texte": "Aucun livrable téléchargeable à publier.", "releases": []}
    if not depot_sur_github(projet, git):
        return {"fait": False, "releases": [], "texte": (
            "Le projet n'est pas encore sur GitHub : créez d'abord le dépôt (« Créer le dépôt Git »), la livraison "
            "automatique publiera ensuite chaque livrable.")}
    code, sortie = gh(["auth", "status"], projet)
    if code != 0:
        return {"fait": False, "releases": [], "texte": (
            "gh n'est pas installé ou pas connecté à votre compte : lancez « gh auth login », puis relancez la "
            "publication.")}
    releases = [{**publier_fichier(projet, resoudre(x["chemin"]), x.get("titre"), git, gh, gh_long, maintenant),
                 "chemin": x["chemin"]} for x in candidats]      # le chemin du livrable, pas celui du fichier résolu
    tout = all(r["fait"] for r in releases)
    return {"fait": tout, "releases": releases,
            "texte": " ".join(r["texte"] for r in releases)[:600]}
