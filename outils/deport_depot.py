"""Exécution déportée : aperçu, validation et envoi du workflow GitHub Actions du projet.

Rien n'est jamais envoyé sans la validation explicite du Directeur : `apercu` ne fait que lire ; `appliquer` reçoit
l'empreinte que le Directeur a vue et refuse si le contenu voulu a changé depuis. L'envoi se fait sur la branche de
travail `deport/workflow` seulement (jamais la branche courante ni la principale) depuis un dossier de travail git
temporaire : la branche courante et le dossier du projet restent intacts. Toute commande git passe par
`moteur.git_sur` (une à la fois par dépôt).

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_github  # noqa: E402
from bureau.deport import ACTIONS  # noqa: E402
from moteur import git_sur  # noqa: E402

BRANCHE = "deport/workflow"
DELAI_GIT_S = 120
DELAI_PUSH_S = 300
_NOM_DEFAUT = "myiafactory"


def nom_fichier(texte):
    """Un nom de fichier sûr (minuscules, chiffres, tirets) tiré du nom du dossier du projet."""
    ascii_ = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or _NOM_DEFAUT


def _executer(argv, cwd, delai_s):
    env = {k: v for k, v in os.environ.items()}
    env["GIT_TERMINAL_PROMPT"] = "0"
    fini = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=delai_s, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return fini.returncode, fini.stdout if fini.returncode == 0 or fini.stdout else fini.stderr


def _racine_du_depot(dossier):
    """Le plus proche dossier (le projet, puis ses parents) qui contient `.git` ; sinon le dossier du projet."""
    dossier = Path(dossier).resolve()
    for d in (dossier, *dossier.parents):
        if (d / ".git").exists():
            return d
    return dossier


def _nom_du_projet(dossier):
    dossier = Path(dossier).resolve()
    return dossier.parent.name if dossier.name == ".factory" else dossier.name


def _voulu(dossier, reglages):
    """(actions sur GitHub, nom du projet, nom du fichier, texte voulu ou None sans action) ; ValueError si une
    commande manque."""
    deport = (reglages or {}).get("deport") or {}
    lieux = deport.get("lieux") or {}
    actions = [a for a in ACTIONS if lieux.get(a) == "github"]
    nom = _nom_du_projet(dossier)
    fichier = nom_fichier(nom)
    if not actions:
        return actions, nom, fichier, None
    texte = workflow_github.generer(nom, actions, deport.get("commandes") or {}, deport.get("charge_heure", "03:00"))
    return actions, nom, fichier, texte


def _empreinte_de(texte):
    return texte.split("\n", 1)[0].rpartition("=")[2]


def _chemin(racine, fichier):
    return Path(racine) / ".github" / "workflows" / (fichier + ".yml")


def apercu(dossier, reglages):
    """Ce que le déport écrirait : `{"etat", "diff", "chemin", "empreinte"}`, sans rien écrire.

    `etat` : absent, a_jour, a_valider, modifie_a_la_main, ou aucune_action (rien n'est déporté sur GitHub).
    Lève ValueError (message en français) si une commande manque.
    """
    racine = _racine_du_depot(dossier)
    _, _, fichier, texte = _voulu(dossier, reglages)
    chemin = _chemin(racine, fichier)
    if texte is None:
        return {"etat": "aucune_action", "diff": "", "chemin": str(chemin), "empreinte": ""}
    etat = workflow_github.etat_du_fichier(chemin, texte)
    ancien = chemin.read_bytes().decode("utf-8", errors="replace") if chemin.exists() else ""
    return {"etat": etat, "diff": workflow_github.diff(ancien, texte), "chemin": str(chemin),
            "empreinte": _empreinte_de(texte)}


def _refus(message, **autres):
    return dict({"ok": False, "message": message}, **autres)


def appliquer(dossier, empreinte, reglages, executer=None):
    """Écrit le workflow sur la branche `deport/workflow` et pousse cette branche seule.

    `executer(argv, cwd, delai_s) -> (code, sortie)` (défaut : sous-processus réel). Rend `{"ok", "message", ...}` ;
    un refus n'écrit rien. Le dossier du projet et sa branche courante ne sont jamais touchés.
    """
    executer = executer or _executer
    try:
        _, _, fichier, texte = _voulu(dossier, reglages)
    except ValueError as e:
        return _refus(str(e))
    if texte is None:
        return _refus("Aucune action n'est déportée sur GitHub : rien à envoyer.")
    if not empreinte or empreinte != _empreinte_de(texte):
        return _refus("Le workflow voulu n'est plus à jour : l'aperçu validé est périmé. Rouvrez l'aperçu, relisez-le "
                      "puis validez à nouveau.")
    racine = _racine_du_depot(dossier)

    def git(*args, cwd=None, delai=DELAI_GIT_S):
        dans = str(cwd or racine)
        try:
            return git_sur.executer(lambda argv: executer(argv, dans, delai), racine, ["git", *args])
        except (subprocess.TimeoutExpired, TimeoutError):
            return 124, "délai dépassé (%d s) : git %s" % (delai, args[0])
        except OSError as e:
            return 127, "git n'a pas pu être lancé : %s" % e

    def lu(sortie):
        return (sortie.decode("utf-8", "replace") if isinstance(sortie, bytes) else str(sortie or "")).strip()[:300]

    with git_sur.verrou(racine):
        code, sortie = git("rev-parse", "--abbrev-ref", "HEAD")
        if code != 0:
            return _refus("Le dossier du projet n'est pas un dépôt git utilisable : %s" % lu(sortie))
        if lu(sortie) == BRANCHE:
            return _refus("La branche « %s » est déjà la branche courante : revenez sur la branche principale." % BRANCHE)
        temporaire = tempfile.mkdtemp(prefix="deport-")
        travail = os.path.join(temporaire, "copie")
        cree = False
        try:
            code, sortie = git("worktree", "add", "-q", "--detach", travail, "HEAD")
            if code != 0:
                return _refus("Impossible de préparer la branche de travail : %s" % lu(sortie))
            cree = True
            chemin = _chemin(travail, fichier)
            etat = workflow_github.etat_du_fichier(chemin, texte)
            if etat == "modifie_a_la_main":
                return _refus("Le fichier %s a été modifié à la main : MyIAFactory ne l'écrase pas. Reprenez-le ou "
                              "supprimez-le, puis relancez." % chemin.relative_to(travail).as_posix())
            if etat == "a_jour":
                return {"ok": True, "etat": "a_jour", "message": "Le workflow est déjà à jour : rien à envoyer."}
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(texte.encode("utf-8"))
            relatif = chemin.relative_to(travail).as_posix()
            for args, quoi in ((("checkout", "-q", "-B", BRANCHE), "branche de travail"),
                               (("add", "--", relatif), "préparation"),
                               (("commit", "-q", "-m", "Déport : workflow GitHub Actions des actions déportées",
                                 "--", relatif), "commit")):
                code, sortie = git(*args, cwd=travail)
                if code != 0:
                    return _refus("Échec (%s) : %s" % (quoi, lu(sortie)))
            code, sortie = git("push", "--force", "origin", "%s:refs/heads/%s" % (BRANCHE, BRANCHE), cwd=travail,
                               delai=DELAI_PUSH_S)
            if code != 0:
                return _refus("Échec du push de la branche « %s » : %s" % (BRANCHE, lu(sortie)))
            return {"ok": True, "etat": etat, "branche": BRANCHE,
                    "message": "Workflow envoyé sur la branche « %s » : ouvrez-la sur GitHub pour la fusionner." % BRANCHE}
        finally:
            if cree:
                git("worktree", "remove", "--force", travail)
            shutil.rmtree(temporaire, ignore_errors=True)
            git("worktree", "prune")
