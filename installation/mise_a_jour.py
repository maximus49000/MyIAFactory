"""La skill se met à jour toute seule (conception 2026-11-16-mise-a-jour-automatique-design.md).

`verifier(depot)` va chercher les nouveautés du dépôt de la skill et les prend quand rien de local ne s'y oppose :

- rien de neuf au distant : `a_jour` ;
- des fichiers suivis modifiés : `bloquee` (un développement en cours n'est jamais écrasé ; les fichiers non suivis
  ne comptent pas) ;
- des commits locaux non poussés, tous dans la mémoire (leçons gardées faute de droits) : `git pull --rebase`, un
  conflit étant défait ; un commit qui touche autre chose : `bloquee` ;
- sinon : avance rapide (`git merge --ff-only`), `mise_a_jour`.

Jamais de pile (`stash`), de `reset` ni de `--force`. Rend {etat, message, version, commits, fichiers}.
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from orchestrateur.memoire import executer_git

INTERVALLE_S = 15 * 60
MEMOIRE = "orchestrateur/memoire/"
ETATS = ("a_jour", "mise_a_jour", "bloquee", "injoignable", "sans_suivi")


def racine_du_code():
    """Le dépôt du code qui tourne : `~/MyIAFactory/skill`, ou le clone lié par `preparer --lier`."""
    return Path(__file__).resolve().parent.parent


def fichier_etat():
    return Path("~/MyIAFactory/mise-a-jour.json").expanduser()


def _resultat(etat, message, version="", commits=(), fichiers=()):
    return {"etat": etat, "message": message, "version": version, "commits": list(commits), "fichiers": list(fichiers)}


def _lignes(sortie):
    return [x.strip() for x in sortie.splitlines() if x.strip()]


def verifier(depot=None, git=executer_git):
    d = Path(depot) if depot is not None else racine_du_code()
    code, _ = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], d)
    if code != 0:
        return _resultat("sans_suivi", "Pas de branche suivie sur GitHub : la skill n'est pas mise à jour.")
    code, sortie = git(["fetch", "-q"], d)
    if code != 0:
        return _resultat("injoignable", f"Le dépôt de la skill est injoignable (réseau ?) : {sortie[:200]}")
    version = git(["rev-parse", "--short", "HEAD"], d)[1].strip()
    code, sortie = git(["log", "--format=%h %s", "HEAD..@{u}"], d)
    nouveaux = _lignes(sortie) if code == 0 else []
    if not nouveaux:
        return _resultat("a_jour", f"La skill est à jour ({version}).", version)
    code, sortie = git(["diff", "--name-only", "HEAD"], d)   # suivis et modifiés, indexés ou non
    modifies = _lignes(sortie)
    if code != 0 or modifies:
        return _resultat("bloquee", f"{len(nouveaux)} mise(s) à jour en attente : des fichiers de la skill sont modifiés "
                         "sur ce poste (rien n'est écrasé ; committez et poussez, ou annulez ces modifications).",
                         version, nouveaux, modifies)
    code, sortie = git(["diff", "--name-only", "@{u}...HEAD"], d)
    locaux = _lignes(sortie) if code == 0 else []
    hors_memoire = [f for f in locaux if not f.startswith(MEMOIRE)]
    if hors_memoire:
        return _resultat("bloquee", f"{len(nouveaux)} mise(s) à jour en attente : ce poste a des commits non poussés "
                         "(un développement en cours) ; poussez-les pour reprendre les mises à jour.",
                         version, nouveaux, hors_memoire)
    if locaux:   # seulement des leçons gardées en local : elles passent au-dessus des nouveautés
        code, sortie = git(["pull", "--rebase", "-q"], d)
        if code != 0:
            git(["rebase", "--abort"], d)
            return _resultat("bloquee", "Mise à jour en attente : une leçon locale entre en conflit avec le dépôt "
                             f"(rien n'est changé). {sortie[:200]}", version, nouveaux, locaux)
    else:
        code, sortie = git(["merge", "--ff-only", "-q", "@{u}"], d)
        if code != 0:
            return _resultat("bloquee", f"Mise à jour impossible en avance rapide (rien n'est changé). {sortie[:200]}",
                             version, nouveaux)
    nouvelle = git(["rev-parse", "--short", "HEAD"], d)[1].strip()
    return _resultat("mise_a_jour", f"Skill mise à jour : {version} → {nouvelle} ({len(nouveaux)} commit(s)).",
                     nouvelle, nouveaux)


def verifier_et_noter(depot=None, git=executer_git, chemin=None):
    """`verifier`, puis l'état écrit pour le bureau. C'est ce que branchent le moteur et le lancement du bureau."""
    r = verifier(depot, git)
    try:
        ecrire_etat(r, chemin)
    except OSError:
        pass   # l'état est un confort : la mise à jour, elle, est faite
    return r


def suivre(depot=None, git=executer_git, chemin=None):
    """Ce que branche le moteur : `verifier_et_noter`, et en plus la version du code avec laquelle il a démarré. Si
    le dépôt a changé depuis (mis à jour par le lancement du bureau, ou par un autre chemin), le résultat dit
    `mise_a_jour` : le moteur tourne sur un code qui n'est plus celui du disque et doit se relancer."""
    d = Path(depot) if depot is not None else racine_du_code()
    code, sortie = git(["rev-parse", "--short", "HEAD"], d)
    depart = sortie.strip() if code == 0 else None

    def verifier_maintenant():
        r = verifier_et_noter(d, git, chemin)
        if r["etat"] != "mise_a_jour" and depart and r.get("version") and r["version"] != depart:
            r = {**r, "etat": "mise_a_jour",
                 "message": f"La skill a changé sur ce poste ({depart} → {r['version']}) : passage à la nouvelle version."}
        return r
    return verifier_maintenant


def relancer_le_bureau(lanceur=None):
    """Relance le bureau qui tourne (lancé par l'installation), pour qu'il passe au nouveau code ; un bureau arrêté
    n'est pas démarré. Rend une phrase pour le journal du moteur."""
    if lanceur is None:
        from installation import lanceur
    from bureau import reglages
    try:
        port = reglages.lire_bureau(lanceur.dossier.bureau())["port"]
    except Exception:
        return "pas de bureau commun : rien à relancer."
    if not lanceur.repond(port):
        return "aucun bureau ne tourne : il prendra la nouvelle version à son prochain lancement."
    try:
        r = lanceur.lancer(relancer=True)
    except lanceur.Echec as e:
        return f"non relancé ({e})"
    return f"relancé sur la nouvelle version ({r['url']})."


def ecrire_etat(resultat, chemin=None, t=None):
    """L'état de la dernière vérification, pour le bureau : `~/MyIAFactory/mise-a-jour.json`."""
    chemin = Path(chemin) if chemin is not None else fichier_etat()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    donnees = {**resultat, "t": t or datetime.now().astimezone().isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
