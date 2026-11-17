"""Exécution déportée : `lancer.py deporter <type> [--dossier D] [--reglages R] [--sans-attendre] [--poste] [-- <commande>]`.

Lance l'action `<type>` (tests, apk, charge…) là où le Directeur l'a réglée :
- au poste (ou avec `--poste`) : la commande locale part par `campagne.executer`, comme `lancer.py tests` ;
- sur GitHub : l'exécution du commit courant (une seule par commit : un deuxième appelant la réutilise si elle est en
  cours ou réussie ; une exécution terminée en échec est refaite) est suivie jusqu'au bout ; 0 si le job de l'action
  réussit, 1 sinon. Ce commit doit déjà être poussé (jamais poussé ici : le travail de l'agent n'est pas à nous) et le
  workflow doit être dans sa branche.
- une action au poste qui consomme la production d'une action sur GitHub (les tests d'un projet générique consomment
  l'APK) attend d'abord cette exécution, télécharge l'artefact, puis lance la commande locale ; job amont échoué :
  code 5.

Codes : 0 réussi, 1 action échouée, 2 usage ou lieu refusé, 3 `--sans-attendre` refusé, 4 `gh` indisponible ou réseau
absent, 5 amont échoué, 6 travail non poussé (origin/<branche> n'est pas au commit courant), 7 workflow absent de la
branche. Jamais de bascule silencieuse vers le poste.

Pendant l'attente, `~/MyIAFactory/deport-en-cours/<id>.json` = {action, attend, lieu, dossier, depuis, battement}
(`battement` rafraîchi chaque minute) dit au bureau quel agent attend quoi ; retiré à la fin, même sur exception.
Un verrou `<commit>-<workflow>.lock` (création exclusive) évite que deux agents déclenchent deux exécutions.

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import campagne  # noqa: E402
import deport_depot  # noqa: E402
import github_actions  # noqa: E402
from bureau.deport import a_attendre, lieu_effectif  # noqa: E402
from bureau.deport_types import catalogue_du_projet  # noqa: E402

BUREAU = Path("~/MyIAFactory/bureau.json").expanduser()
EN_COURS = Path("~/MyIAFactory/deport-en-cours").expanduser()
USAGE = ("Usage : lancer.py deporter <type> [--dossier <dossier>] [--reglages <fichier>] [--sans-attendre] [--poste] "
         "[-- <commande locale>]")
PROPOSITION = "relance avec --poste après accord du Directeur"
MSG_NON_POUSSE = "pousse d'abord ton travail : le commit courant n'est pas sur le dépôt distant."
MSG_SANS_WORKFLOW = ("le workflow n'est pas dans ta branche : fusionne deport/workflow (validé par le Directeur) "
                     "dans ta branche, puis réessaie")
VERROU_PERIME_S = 300
PAS_VERROU_S = 2
ESSAIS_APPARITION = 12
PAUSE_APPARITION_S = 5
DELAI_GIT_S = 60


def _maintenant():
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- fichier d'attente -------------------------------------------------------------------------------------------

def _chemin_attente(id_, repertoire):
    return Path(repertoire) / (str(id_) + ".json")


def _ecrire(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(chemin))


def ecrire_attente(id_, action, produit, lieu, dossier=None, repertoire=EN_COURS):
    """Déclare qu'un agent attend `produit` (venu de `lieu`) pour lancer `action`."""
    maintenant = _maintenant()
    _ecrire(_chemin_attente(id_, repertoire), {"action": action, "attend": produit, "lieu": lieu,
                                               "dossier": str(dossier or ""), "depuis": maintenant,
                                               "battement": maintenant})


def battre(id_, repertoire=EN_COURS):
    """Rafraîchit `battement` : l'agent attend toujours (un fichier sans battement récent est un reste)."""
    chemin = _chemin_attente(id_, repertoire)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    donnees["battement"] = _maintenant()
    _ecrire(chemin, donnees)


def retirer_attente(id_, repertoire=EN_COURS):
    try:
        _chemin_attente(id_, repertoire).unlink()
    except OSError:
        pass


# --- lieux -------------------------------------------------------------------------------------------------------

def _lieux_ecrits(chemin):
    """Les lieux écrits tels quels dans la clé `deport` d'un fichier JSON (sans les défauts) ; {} si illisible."""
    try:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    d = donnees.get("deport") if isinstance(donnees, dict) else None
    lieux = d.get("lieux") if isinstance(d, dict) else None
    return dict(lieux) if isinstance(lieux, dict) else {}


def _lieux(dossier, reglages, bureau):
    """`(lieux effectifs {action: lieu}, catalogue)` : surcharge du projet, sinon défaut du bureau, sinon poste."""
    catalogue = catalogue_du_projet(dossier)[1]
    chemin = Path(reglages) if reglages else Path(dossier) / ".factory" / "reglages.json"
    globaux, projet = _lieux_ecrits(bureau), _lieux_ecrits(chemin)
    return {a: lieu_effectif(globaux, projet, a) for a in catalogue}, catalogue


def lieux_refuses(lieux, action, catalogue):
    """Les lieux que `deporter` ne sait pas servir (ni `poste` ni `github`, ex. `serveur` écrit à la main) pour
    l'action et les actions dont elle dépend : jamais de repli silencieux sur le poste."""
    refus = []
    for a in [action] + [d for d in catalogue[action]["consomme"] if d in lieux]:
        if lieux[a] not in ("poste", "github"):
            refus.append("Le lieu « %s » de l'action « %s » n'est pas disponible : seuls « poste » et « github » le "
                         "sont. Corrigez les réglages du projet, ou relancez avec --poste après accord du "
                         "Directeur." % (lieux[a], a))
    return refus


def doit_passer_par_deporter(action, lieux, catalogue):
    """Vrai si l'action tourne sur GitHub, ou si elle dépend de la production d'une action d'un autre lieu (il y a
    alors une attente à faire) ; un lieu que `deporter` ne sert pas passe aussi par lui, qui le refuse."""
    if action not in catalogue:
        return False
    return (lieux[action] == "github" or bool(a_attendre(lieux, action, catalogue))
            or bool(lieux_refuses(lieux, action, catalogue)))


def _analyser(argv):
    """`(options, commande)` ou `None` si l'usage est faux ; `options` : type, dossier, reglages, attendre, poste."""
    argv = list(argv)
    commande = []
    if "--" in argv:
        i = argv.index("--")
        argv, commande = argv[:i], argv[i + 1:]
    opt = {"type": None, "dossier": None, "reglages": None, "attendre": True, "poste": False}
    while argv:
        o = argv.pop(0)
        if o in ("--dossier", "--reglages") and argv:
            opt[o[2:]] = argv.pop(0)
        elif o == "--sans-attendre":
            opt["attendre"] = False
        elif o == "--poste":
            opt["poste"] = True
        elif not o.startswith("--") and opt["type"] is None:
            opt["type"] = o
        else:
            print("Option inconnue : %s" % o, file=sys.stderr)
            return None
    return opt, commande


def _avant_double_tiret(argv):
    argv = list(argv)
    return argv[:argv.index("--")] if "--" in argv else argv


def _lieux_des_options(argv, bureau):
    analyse = _analyser(_avant_double_tiret(argv))
    if analyse is None:
        return None
    opt = analyse[0]
    dossier = str(Path(opt["dossier"] or os.getcwd()).resolve())
    return _lieux(dossier, opt["reglages"], bureau)


def faut_deporter(action, argv, bureau=BUREAU):
    """Pour `lancer.py tests` : cette action, avec les options (`--dossier`, `--reglages`) de `argv`, passe-t-elle par
    `deporter` ? Faux (le poste, comme toujours) si on ne sait pas lire les options."""
    lus = _lieux_des_options(argv, bureau)
    return bool(lus) and doit_passer_par_deporter(action, lus[0], lus[1])


def lieu_de(action, argv, bureau=BUREAU):
    """Le lieu effectif de `action` pour les options (`--dossier`, `--reglages`) de `argv` ; le poste si on ne sait pas."""
    lus = _lieux_des_options(argv, bureau)
    return lus[0].get(action, "poste") if lus else "poste"


# --- git ---------------------------------------------------------------------------------------------------------

def _git(argv, cwd):
    """(code, sortie) d'une commande git ; (127, message) si git est absent."""
    try:
        f = subprocess.run(["git"] + list(argv), cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=DELAI_GIT_S, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    return f.returncode, (f.stdout or f.stderr or "")


class _Refus(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def _etat_du_depot(racine, fichier, git):
    """`(commit, branche)` du HEAD, après avoir vérifié que la branche distante est exactement à ce commit (« poussé »)
    et que le workflow est dans la branche. `branche` est le nom de la branche distante visée."""
    code, sortie = git(["rev-parse", "HEAD"], racine)
    if code != 0 or not sortie.strip():
        raise _Refus(6, "Ce dossier n'est pas un dépôt git avec un commit : %s" % MSG_NON_POUSSE)
    commit = sortie.strip()
    code, sortie = git(["rev-parse", "--abbrev-ref", "HEAD"], racine)
    courante = sortie.strip() if code == 0 else ""
    if not courante or courante == "HEAD":
        raise _Refus(6, "Tête détachée : place-toi sur une branche, pousse-la, puis réessaie.")
    code, sortie = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], racine)
    suivi = sortie.strip() if code == 0 and "/" in sortie else "origin/" + courante
    code, sortie = git(["rev-parse", "--verify", "-q", "refs/remotes/" + suivi], racine)
    if code != 0 or not sortie.strip():
        raise _Refus(6, "pousse ta branche : %s n'existe pas sur le dépôt distant." % suivi)
    if sortie.strip() != commit:
        raise _Refus(6, "pousse ta branche : %s n'est pas à ton commit (%s)." % (suivi, commit[:8]))
    code, _ = git(["cat-file", "-e", "HEAD:.github/workflows/%s.yml" % fichier], racine)
    if code != 0:
        raise _Refus(7, MSG_SANS_WORKFLOW)
    return commit, suivi.partition("/")[2]


# --- verrou de la course -----------------------------------------------------------------------------------------

def _verrou_perime(chemin, maintenant):
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        pid, debut = donnees.get("pid"), float(donnees.get("t", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        pid, debut = None, 0.0
    return (not campagne.pid_vivant(pid)) or maintenant - debut > VERROU_PERIME_S


@contextlib.contextmanager
def _verrou_du_run(chemin, attendre, dormir, dire):
    """Tenu autour de « chercher un run, sinon le déclencher, attendre son apparition » : deux agents qui demandent le
    même commit ne déclenchent qu'une exécution (le second attend le verrou, puis voit le run). Création exclusive ;
    le verrou d'un processus mort, ou vieux de plus de 5 minutes, est repris."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    deja_dit = False
    while True:
        try:
            fd = os.open(str(chemin), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _verrou_perime(chemin, time.time()):
                try:
                    chemin.unlink()
                except OSError:
                    pass
                continue
            if not attendre:
                raise _Refus(3, "Refusé : un autre appelant déclenche l'exécution de ce commit et --sans-attendre "
                                "est donné.")
            if not deja_dit:
                dire("Un autre appelant déclenche l'exécution de ce commit : on attend.")
                deja_dit = True
            dormir(PAS_VERROU_S)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "t": time.time()}, f)
        break
    try:
        yield
    finally:
        try:
            chemin.unlink()
        except OSError:
            pass


# --- exécution ---------------------------------------------------------------------------------------------------

def main(argv=None, executer_poste=campagne.executer, gh=github_actions, git=_git, dormir=time.sleep, dire=None,
         bureau=BUREAU, repertoire_attente=EN_COURS):
    argv = list(sys.argv[1:] if argv is None else argv)
    if dire is None:
        def dire(texte, **k):
            print(texte, flush=True)
    analyse = _analyser(argv)
    if analyse is None or analyse[0]["type"] is None:
        print(USAGE, file=sys.stderr)
        return 2
    opt, commande = analyse
    dossier = str(Path(opt["dossier"] or os.getcwd()).resolve())
    lieux, catalogue = _lieux(dossier, opt["reglages"], bureau)
    action = opt["type"]
    if action not in catalogue:
        print("Action inconnue pour ce projet : « %s » (attendu : %s)." % (action, ", ".join(catalogue)),
              file=sys.stderr)
        return 2
    if opt["poste"]:
        lieux[action] = "poste"
    refus = lieux_refuses(lieux, action, catalogue)
    if refus:
        print("\n".join(refus), file=sys.stderr)
        return 2
    amont = [d for d in a_attendre(lieux, action, catalogue) if lieux.get(d) == "github"]
    if lieux[action] != "github" and not commande:
        print(USAGE, file=sys.stderr)
        return 2

    def lancer_au_poste():
        return executer_poste(commande, dossier=dossier, attendre=opt["attendre"])

    if lieux[action] != "github" and not amont:
        return lancer_au_poste()

    id_ = "%s-%s-%s" % (os.getpid(), threading.get_ident(), action)
    try:
        return _sur_github(action, lieux, catalogue, amont, opt, dossier, gh, git, dormir, dire, id_,
                           repertoire_attente, lancer_au_poste)
    except _Refus as r:
        if r.message:
            dire(r.message)
        return r.code
    except gh.Gh_indisponible as e:
        dire("%s\nPas de bascule silencieuse vers le poste : %s." % (e, PROPOSITION))
        return 4
    finally:
        retirer_attente(id_, repertoire_attente)


def _reutilisable(run):
    """Un run du commit se réutilise s'il est en cours ou réussi ; terminé en échec ou annulé, il est refait."""
    return run is not None and (run.get("statut") != "completed" or run.get("conclusion") == "success")


def _obtenir_run(gh, racine, workflow, commit, branche, opt, dormir, dire):
    """Le run de ce commit : celui d'un autre appelant s'il est en cours ou réussi, sinon un seul déclenchement."""
    run = gh.execution_du_commit(str(racine), workflow, commit)
    if _reutilisable(run):
        if run.get("statut") != "completed":
            dire("Une exécution de ce commit tourne déjà (%s) : on la suit." % run.get("url", ""))
        return run
    if not opt["attendre"]:
        raise _Refus(3, "Refusé : aucune exécution utilisable de ce commit sur GitHub et --sans-attendre est donné.")
    if run is not None:
        dire("exécution précédente échouée : nouvelle exécution lancée")
    ancien = run.get("id") if run is not None else None
    dire("Déclenchement de l'exécution sur GitHub (branche %s, commit %s)." % (branche, commit[:8]))
    gh.declencher(str(racine), workflow, branche, {})
    for _ in range(ESSAIS_APPARITION):
        run = gh.execution_du_commit(str(racine), workflow, commit)
        if run is not None and run.get("id") != ancien:
            return run
        dormir(PAUSE_APPARITION_S)
    raise _Refus(4, "L'exécution déclenchée n'apparaît pas sur GitHub. %s." % PROPOSITION)


def _job_reussi(gh, racine, run, action):
    """L'action a-t-elle réussi ? On juge son job (son nom est l'id de l'action) ; sans jobs, le run entier."""
    jobs = run.get("jobs")
    if jobs is None and hasattr(gh, "jobs_du_run"):
        try:
            jobs = gh.jobs_du_run(str(racine), run["id"])
        except gh.Gh_indisponible:
            jobs = None
    for j in jobs or []:
        if j.get("name") == action:
            return j.get("conclusion") == "success"
    return run.get("conclusion") == "success"


def _sur_github(action, lieux, catalogue, amont, opt, dossier, gh, git, dormir, dire, id_, repertoire_attente,
                lancer_au_poste):
    pret, message = gh.gh_pret()
    if not pret:
        dire("%s\nPas de bascule silencieuse vers le poste : %s." % (message, PROPOSITION))
        return 4
    racine = deport_depot._racine_du_depot(dossier)
    fichier = deport_depot.nom_fichier(deport_depot._nom_du_projet(dossier))
    commit, branche = _etat_du_depot(racine, fichier, git)
    workflow = fichier + ".yml"
    if opt["attendre"]:
        ecrire_attente(id_, action, amont[0] if amont else action, "github", dossier, repertoire_attente)

    def dormir_battant(s):
        dormir(s)
        battre(id_, repertoire_attente)

    verrou = Path(repertoire_attente) / ("%s-%s.lock" % (commit, fichier))
    with _verrou_du_run(verrou, opt["attendre"], dormir_battant, dire):
        run = _obtenir_run(gh, racine, workflow, commit, branche, opt, dormir_battant, dire)
    if run.get("statut") != "completed":
        if not opt["attendre"]:
            raise _Refus(3, "Refusé : l'exécution de ce commit n'est pas finie et --sans-attendre est donné.")
        run = gh.suivre(str(racine), run["id"], dormir=dormir_battant, dire=dire)
    if lieux[action] == "github":
        reussi = _job_reussi(gh, racine, run, action)
        dire("Exécution %s : %s (%s)." % (run.get("id"), "réussie" if reussi else "échouée (%s)" % run.get("conclusion"),
                                           run.get("url", "")))
        return 0 if reussi else 1
    echecs = [d for d in amont if not _job_reussi(gh, racine, run, d)]
    dire("Exécution %s : %s (%s)." % (run.get("id"), run.get("conclusion"), run.get("url", "")))
    if echecs:
        dire("L'amont (%s) a échoué : « %s » n'est pas lancé." % (", ".join(echecs), action))
        return 5
    for dep in amont:
        produit = catalogue[dep]["produit"]
        if produit:
            cible = os.path.join(dossier, "artefacts", produit)
            chemin = gh.telecharger(str(racine), run["id"], produit, cible)
            dire("Artefact « %s » téléchargé : %s" % (produit, chemin))
    return lancer_au_poste()
