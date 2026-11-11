"""Les agents cloud : des sessions cloud de Claude Code (sur l'abonnement), lancées et relevées par le moteur.

Aucune API ne rend la fin d'une session cloud, son texte ni ses tokens. Le contrat est donc le dépôt :
- **le départ** : le moteur pousse le dépôt du projet (la session clone la branche poussée) puis lance
  `claude --cloud "<message de départ>"` ; la sortie donne l'identifiant et l'adresse de la session ;
- **le retour** : le message de départ demande à l'agent de committer son rapport structuré dans
  `.factory/rapports/<tâche>.json` sur sa branche `claude/…` et de la pousser ; le moteur fait un `git fetch`, cherche ce
  fichier sur les branches `claude/…`, l'applique comme un rapport local, puis **fusionne la branche** ;
- **une suite** (l'accord de l'utilisateur) : `claude -p "<texte>" --cloud <session>`.

Toute commande passe par `executer(argv, cwd, delai_s) -> (code, sortie en octets)` (remplaçable pour les essais). Aucune
clé n'est lue ni transmise : `ANTHROPIC_API_KEY` est retirée de l'environnement, pour rester sur l'abonnement.
"""
import os
import re
import subprocess

from moteur import appel, rapport

DOSSIER_RAPPORTS = ".factory/rapports"
PREFIXE_BRANCHES = "claude/"
DELAI_GIT_S = 120
DELAI_CLAUDE_S = 300
LONGUEUR_MAX_DEPART = 24000     # une ligne de commande Windows ne passe pas 32 767 caractères
_ADRESSE = re.compile(r"https://claude\.ai/code/[A-Za-z0-9_./-]*[A-Za-z0-9_]")
_SESSION = re.compile(r"\b(session_[A-Za-z0-9]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")


class ErreurCloud(Exception):
    """Le départ, la relève ou la fusion d'une session cloud n'a pas pu se faire."""

    def __init__(self, raison):
        super().__init__(raison)
        self.raison = raison


def chemin_rapport(tache):
    return f"{DOSSIER_RAPPORTS}/{tache}.json"


def _executer(argv, cwd, delai_s):
    env = {k: v for k, v in os.environ.items() if k != appel.VARIABLE_CLE}
    env["GIT_TERMINAL_PROMPT"] = "0"
    fini = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=delai_s, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return fini.returncode, fini.stdout if fini.returncode == 0 or fini.stdout else fini.stderr


def _lancer(executer, argv, cwd, delai_s):
    try:
        return (executer or _executer)(argv, str(cwd), delai_s)
    except (subprocess.TimeoutExpired, TimeoutError):
        raise ErreurCloud(f"délai dépassé ({delai_s} s) : {' '.join(argv[:2])}")
    except OSError as e:
        raise ErreurCloud(f"{argv[0]} n'a pas pu être lancé : {e}")


def _texte(octets):
    return (octets or b"").decode("utf-8", "replace").strip()


def _git(executer, dossier, *args, delai_s=DELAI_GIT_S):
    return _lancer(executer, ["git", *args], dossier, delai_s)


def prerequis(dossier_projet, *, executer=None, trouver=appel.trouver_claude):
    """`None` si le cloud est possible (le projet est sur GitHub, `claude` est là), sinon la raison, en français."""
    if not trouver():
        return "la commande claude n'est pas installée"
    try:
        code, sortie = _git(executer, dossier_projet, "remote", "get-url", "origin", delai_s=30)
    except ErreurCloud:
        return "git n'est pas utilisable"
    if code != 0 or "github.com" not in _texte(sortie):
        return "le projet n'est pas sur GitHub"
    return None


def lancer_session(depart, *, dossier_projet, modele, executer=None, trouver=appel.trouver_claude):
    """Pousse le dépôt puis lance la session cloud. Rend `{"session", "adresse"}`. Lève `ErreurCloud`."""
    if len(depart) > LONGUEUR_MAX_DEPART:
        raise ErreurCloud("le message de départ est trop long pour la ligne de commande")
    m = (modele or "").strip().lower()
    if "fable" in m or m not in appel.MODELES:
        raise ErreurCloud("le moteur ne choisit jamais Fable" if "fable" in m else f"modèle inconnu : {modele}")
    claude = trouver()
    if not claude:
        raise ErreurCloud("la commande claude n'est pas installée")
    code, sortie = _git(executer, dossier_projet, "push")
    if code != 0:
        raise ErreurCloud("le dépôt n'a pas pu être poussé : " + _texte(sortie)[:200])
    code, sortie = _lancer(executer, [claude, "--cloud", depart, "--model", m], dossier_projet, DELAI_CLAUDE_S)
    texte = _texte(sortie)
    if code != 0:
        raise ErreurCloud(f"claude --cloud a rendu le code {code} : {texte[:200]}")
    adresse = _ADRESSE.search(texte)
    session = _SESSION.search(texte) or (re.search(r"([A-Za-z0-9_-]+)$", adresse.group(0)) if adresse else None)
    if not session:
        raise ErreurCloud("la sortie de claude --cloud ne donne pas la session : " + texte[:200])
    return {"session": session.group(1), "adresse": adresse.group(0) if adresse else None}


def envoyer_suite(session, texte, *, executer=None, dossier_projet=".", trouver=appel.trouver_claude):
    """Envoie une suite (l'accord de l'utilisateur) à la même session : `claude -p "<texte>" --cloud <session>`."""
    claude = trouver()
    if not claude:
        raise ErreurCloud("la commande claude n'est pas installée")
    code, sortie = _lancer(executer, [claude, "-p", texte, "--cloud", session], dossier_projet, DELAI_CLAUDE_S)
    if code != 0:
        raise ErreurCloud(f"la suite n'a pas pu être envoyée : {_texte(sortie)[:200]}")


def chercher_rapports(dossier_projet, taches, *, executer=None):
    """Après `git fetch`, pour chaque tâche dont `.factory/rapports/<tâche>.json` existe sur une branche `claude/…`,
    `(branche, rapport)`. Un rapport illisible est ignoré (la session peut encore le réécrire)."""
    if not taches:
        return {}
    code, sortie = _git(executer, dossier_projet, "fetch", "--prune", "origin")
    if code != 0:
        raise ErreurCloud("git fetch a échoué : " + _texte(sortie)[:200])
    code, sortie = _git(executer, dossier_projet, "for-each-ref", "--format=%(refname:short)",
                        f"refs/remotes/origin/{PREFIXE_BRANCHES}")
    branches = [b for b in _texte(sortie).splitlines() if b.strip()] if code == 0 else []
    trouves = {}
    for tache in taches:
        for branche in branches:
            code, contenu = _git(executer, dossier_projet, "show", f"{branche}:{chemin_rapport(tache)}", delai_s=30)
            if code != 0:
                continue
            try:
                trouves[tache] = (branche.split("/", 1)[1], rapport.lire(_texte(contenu)))
                break
            except rapport.RapportIllisible:
                continue
    return trouves


def fusionner(dossier_projet, branche, *, executer=None):
    """Fusionne la branche de la session dans la branche du projet, puis pousse. `None` si c'est fait, sinon la raison
    (un conflit : la fusion est annulée, rien n'est cassé)."""
    code, sortie = _git(executer, dossier_projet, "merge", "--no-ff", "-m", f"Factory : fusion de {branche}",
                        f"origin/{branche}")
    if code != 0:
        _git(executer, dossier_projet, "merge", "--abort")
        return "conflit de fusion : " + _texte(sortie)[:200]
    code, sortie = _git(executer, dossier_projet, "push")
    if code != 0:
        return "la fusion est faite mais n'a pas pu être poussée : " + _texte(sortie)[:200]
    return None

