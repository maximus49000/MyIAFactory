"""Le dossier stable ~/MyIAFactory : la skill, le bureau commun, les propositions en attente."""
import os
import subprocess
import sys
from pathlib import Path

from orchestrateur.memoire import executer_git

DEPOT = "https://github.com/maximus49000/MyIAFactory.git"
PREFIXE_SKILL = "~/MyIAFactory/skill"


class Echec(Exception):
    """Un refus à dire tel quel à l'utilisateur."""


def racine():
    return Path("~/MyIAFactory").expanduser()


def skill():
    return racine() / "skill"


def bureau():
    return racine() / "bureau.json"


def propositions():
    return racine() / "propositions"


def creer_lien(cible, lien):
    """Une jonction sous Windows (sans droits d'administrateur), un lien symbolique ailleurs."""
    cible, lien = Path(cible), Path(lien)
    lien.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        p = subprocess.run(["cmd", "/c", "mklink", "/J", str(lien), str(cible)], capture_output=True)
        if p.returncode != 0:
            raise Echec("Le lien vers la skill n'a pas pu être créé : "
                        + (p.stdout + p.stderr).decode("oem", "replace").strip())
    else:
        os.symlink(cible, lien, target_is_directory=True)


def _est_depot(chemin):
    return (chemin / ".git").exists()


def preparer(lier=None, git=executer_git, lien=creer_lien):
    """Crée ou met à jour le dossier stable. Rend {"skill", "action", "message"}."""
    s = skill()
    if lier is not None:
        lier = Path(lier).expanduser()
        if not (lier / "orchestrateur" / "outil.py").is_file():
            raise Echec(f"« {lier} » n'est pas un clone de la skill (orchestrateur/outil.py introuvable).")
    if s.exists() and lier is not None and s.resolve() == lier.resolve():
        return {"skill": str(s), "action": "deja_lie", "message": f"Le dossier stable pointe déjà sur {lier}."}
    if s.exists() and lier is not None:
        raise Echec(f"{s} existe déjà et ne pointe pas sur {lier} : renommez-le (ou supprimez-le s'il ne garde aucune "
                    "leçon à pousser), puis relancez `preparer --lier`.")
    if s.exists() and _est_depot(s):
        # --rebase : une leçon ou un genre gardés en local (push refusé) ne doivent pas figer la copie
        code, sortie = git(["pull", "--rebase"], s)
        if code == 0:
            msg = "La skill est à jour."
        else:
            git(["rebase", "--abort"], s)
            msg = "La skill n'a pas pu être mise à jour (la version présente est gardée) : " + sortie[:300]
        return {"skill": str(s), "action": "mise_a_jour", "message": msg}
    if lier is not None:
        lien(lier, s)
        return {"skill": str(s), "action": "lien", "message": f"Le dossier stable pointe sur {lier}."}
    racine().mkdir(parents=True, exist_ok=True)
    code, sortie = git(["clone", DEPOT, str(s)], racine())
    if code != 0:
        raise Echec("La skill n'a pas pu être téléchargée (réseau ou droits) : " + sortie[:300])
    return {"skill": str(s), "action": "clone", "message": f"La skill a été téléchargée dans {s}."}
