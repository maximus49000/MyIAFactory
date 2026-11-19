"""Exécution déportée : `lancer.py deporter <type> [--dossier D] [--reglages R] [--sans-attendre] [--poste] [-- <commande>]`.

Lance l'action `<type>` (tests, apk, charge…) là où le Directeur l'a réglée :
- au poste (ou avec `--poste`) : la commande locale part par `campagne.executer`, comme `lancer.py tests` ;
- sur GitHub : l'exécution du commit courant est suivie jusqu'au bout ; 0 si le job de l'action réussit, 1 sinon. Une
  exécution de ce commit est réutilisée (en cours, ou terminée avec les jobs NÉCESSAIRES réussis : celui de l'action
  et ceux dont il dépend ; un job sans rapport en échec, ex. lint, ne compte pas). Un job nécessaire en échec n'est
  relancé qu'UNE fois par (commit, job) (marqueur `<commit>-<workflow>-<job>.relance` à côté du verrou) ; ensuite
  code 1 (ou 5) « déjà relancé une fois pour ce commit : corrige le code ». Ce commit doit déjà être poussé (jamais
  poussé ici : le travail de l'agent n'est pas à nous), sans modification suivie non commitée hors `.factory/`, et le
  workflow doit être dans sa branche.
- une action au poste qui consomme la production d'une action sur GitHub (les tests d'un projet générique consomment
  l'APK) attend d'abord cette exécution, télécharge l'artefact dans `~/MyIAFactory/artefacts/<commit>/<produit>`
  (réutilisé s'il y est déjà), puis lance la commande locale avec son chemin dans `MYIAFACTORY_ARTEFACT_<PRODUIT>` ;
  job amont échoué : code 5.
- le projet est le plus proche dossier (`--dossier` ou ses parents) qui contient `.factory/` : un agent peut donner
  un sous-dossier (catalogue, lieux et nom du workflow restent ceux du projet).

Codes : 0 réussi, 1 action échouée, 2 usage ou lieu refusé, 3 `--sans-attendre` refusé, 4 `gh` indisponible ou réseau
absent, 5 amont échoué, 6 travail non poussé (origin/<branche> n'est pas au commit courant, ou modifications suivies
non commitées), 7 workflow absent de la branche, 8 quota GitHub probablement épuisé (cache de consommation au niveau
« dépassé », ou exécution en `startup_failure`) : proposer le poste au Directeur. Jamais de bascule silencieuse.

Pendant l'attente, `~/MyIAFactory/deport-en-cours/<id>.json` = {action, attend, lieu, dossier, agent, depuis,
battement} (`agent` : la clé que le moteur exporte dans `MYIAFACTORY_AGENT`, absente pour un appel à la main ;
`battement` rafraîchi chaque minute) dit au bureau quel agent attend quoi ; retiré à la fin, même sur exception.
Un verrou `<commit>-<workflow>.lock` (création exclusive) évite que deux agents déclenchent deux exécutions.

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""
import contextlib
import json
import os
import shutil
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
from bureau import deport_conso  # noqa: E402
from bureau.deport import a_attendre, lieu_effectif  # noqa: E402
from bureau.deport_types import catalogue_du_projet, racine_du_projet  # noqa: E402

BUREAU = Path("~/MyIAFactory/bureau.json").expanduser()
EN_COURS = Path("~/MyIAFactory/deport-en-cours").expanduser()
ARTEFACTS = Path("~/MyIAFactory/artefacts").expanduser()
VARIABLE_AGENT = "MYIAFACTORY_AGENT"
MAX_FICHIERS_LISTES = 10
USAGE = ("Usage : lancer.py deporter <type> [--dossier <dossier>] [--reglages <fichier>] [--sans-attendre] [--poste] "
         "[-- <commande locale>]")
PROPOSITION = "relance avec --poste après accord du Directeur"
MSG_NON_POUSSE = "pousse d'abord ton travail : le commit courant n'est pas sur le dépôt distant."
MSG_SANS_WORKFLOW = ("le workflow n'est pas dans ta branche : fusionne deport/workflow (validé par le Directeur) "
                     "dans ta branche, puis réessaie. GitHub exige aussi, pour le déclencher à la main "
                     "(workflow_dispatch), que le fichier du workflow soit sur la branche par défaut du dépôt (ou la "
                     "branche visée)")
MSG_QUOTA = ("Proposition : passer au poste, avec l'accord du Directeur (--poste). Rien ne bascule tout seul ; ne "
             "corrige pas le code : il n'est pas en cause.")
MSG_DEJA_RELANCE = "déjà relancé une fois pour ce commit : corrige le code"
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


def ecrire_attente(id_, action, produit, lieu, dossier=None, repertoire=EN_COURS, agent=None):
    """Déclare qu'un agent attend `produit` (venu de `lieu`) pour lancer `action`. `agent` : la clé de l'agent (par
    défaut `MYIAFACTORY_AGENT`, exportée par le moteur) ; sans elle (appel à la main), le dossier seul l'identifie."""
    maintenant = _maintenant()
    agent = agent if agent is not None else os.environ.get(VARIABLE_AGENT, "")
    donnees = {"action": action, "attend": produit, "lieu": lieu, "dossier": str(dossier or ""), "depuis": maintenant,
               "battement": maintenant}
    if agent:
        donnees["agent"] = str(agent)
    _ecrire(_chemin_attente(id_, repertoire), donnees)


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
    """`(lieux effectifs {action: lieu}, catalogue)` : surcharge du projet, sinon défaut du bureau, sinon poste. Le
    projet est le plus proche dossier (`dossier` ou ses parents) qui contient `.factory/`."""
    projet = racine_du_projet(dossier)
    catalogue = catalogue_du_projet(projet)[1]
    chemin = Path(reglages) if reglages else Path(projet) / ".factory" / "reglages.json"
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


def _modifies(racine, git):
    """Les fichiers suivis modifiés et non commités, hors `.factory/` (l'état de la factory, que le moteur réécrit
    sans cesse : ce n'est pas du code testé)."""
    code, sortie = git(["status", "--porcelain", "--untracked-files=no"], racine)
    if code != 0:
        return []
    fichiers = []
    for ligne in sortie.splitlines():
        chemin = ligne[3:].strip().split(" -> ")[-1].strip('"')
        if chemin and not (chemin == ".factory" or chemin.startswith(".factory/")):
            fichiers.append(chemin)
    return fichiers


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
    modifies = _modifies(racine, git)
    if modifies:
        plus = len(modifies) - MAX_FICHIERS_LISTES
        raise _Refus(6, "Modifications suivies non commitées : %s%s. GitHub teste le commit poussé, pas ton arbre de "
                        "travail : commite et pousse ces changements (ou annule-les), puis relance."
                     % (", ".join(modifies[:MAX_FICHIERS_LISTES]), " (et %d autres)" % plus if plus > 0 else ""))
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
         bureau=BUREAU, repertoire_attente=EN_COURS, artefacts=ARTEFACTS, cache_conso=None):
    """`artefacts` : où vont les artefacts téléchargés (`<artefacts>/<commit>/<produit>`) ; `cache_conso` : le dossier
    du cache de consommation (None : celui de `bureau.deport_conso`, `~/MyIAFactory`)."""
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

    def lancer_au_poste(env=None):
        if env:      # les chemins des artefacts téléchargés (MYIAFACTORY_ARTEFACT_<PRODUIT>)
            return executer_poste(commande, dossier=dossier, attendre=opt["attendre"], env=env)
        return executer_poste(commande, dossier=dossier, attendre=opt["attendre"])

    if lieux[action] != "github" and not amont:
        return lancer_au_poste()

    id_ = "%s-%s-%s" % (os.getpid(), threading.get_ident(), action)
    contexte = {"action": action, "lieux": lieux, "catalogue": catalogue, "amont": amont, "opt": opt,
                "dossier": dossier, "projet": racine_du_projet(dossier), "gh": gh, "git": git, "dormir": dormir,
                "dire": dire, "id": id_, "repertoire": repertoire_attente, "artefacts": artefacts,
                "cache_conso": cache_conso, "lancer_au_poste": lancer_au_poste}
    try:
        return _sur_github(contexte)
    except _Refus as r:
        if r.message:
            dire(r.message)
        return r.code
    except gh.Gh_indisponible as e:
        dire("%s\nPas de bascule silencieuse vers le poste : %s." % (e, PROPOSITION))
        return 4
    finally:
        retirer_attente(id_, repertoire_attente)


def lancer_tests(argv, bureau=BUREAU, deporter_main=None, campagne_main=None):
    """`lancer.py tests …` : par `deporter` si les tests tournent sur GitHub ou attendent une production d'ailleurs ;
    sinon par la campagne du poste, comme toujours."""
    argv = list(argv)
    if faut_deporter("tests", argv, bureau):
        return (deporter_main or main)(["tests"] + argv)
    return (campagne_main or campagne.main)(argv)


def _jobs_necessaires(cibles, lieux, catalogue):
    """Les jobs dont dépend le résultat voulu : les `cibles` sur GitHub et, de proche en proche, ceux sur GitHub dont
    elles consomment la production (un job amont en échec fait sauter le job qui l'attend)."""
    vus, a_voir = [], list(cibles)
    while a_voir:
        a = a_voir.pop(0)
        if a in vus or lieux.get(a) != "github" or a not in catalogue:
            continue
        vus.append(a)
        a_voir.extend(catalogue[a]["consomme"])
    return vus


def _jobs(gh, racine, run):
    """Les jobs du run (`[{name, conclusion}]`), demandés à gh si le résumé ne les a pas ; None si inconnus."""
    jobs = run.get("jobs")
    if jobs is None and hasattr(gh, "jobs_du_run"):
        try:
            jobs = gh.jobs_du_run(str(racine), run["id"])
        except gh.Gh_indisponible:
            jobs = None
        if jobs is not None:
            run["jobs"] = jobs
    return jobs


def _job_reussi(gh, racine, run, action):
    """L'action a-t-elle réussi ? On juge son job (son nom est l'id de l'action) ; sans jobs, le run entier."""
    for j in _jobs(gh, racine, run) or []:
        if j.get("name") == action:
            return j.get("conclusion") == "success"
    return run.get("conclusion") == "success"


def _marqueur(repertoire, commit, fichier, job):
    return Path(repertoire) / ("%s-%s-%s.relance" % (commit, fichier, job))


def _quota_depasse(c):
    """Vrai si la dernière lecture de la consommation (cache du bureau, sans appel à gh) dit le quota dépassé."""
    projet = Path(c["projet"])
    cles = [str(projet), str(projet / ".factory"), str(c["dossier"])]
    return deport_conso.niveau_en_cache(cles, cache=c["cache_conso"]) == "depasse"


def _refus_quota(constat):
    return _Refus(8, "%s. %s" % (constat, MSG_QUOTA))


def _refus_startup(run):
    return _refus_quota("Exécution %s en « startup_failure » (%s) : quota probablement épuisé (ou workflow refusé par "
                        "GitHub au démarrage)" % (run.get("id"), run.get("url", "")))


def _obtenir_run(c, racine, workflow, fichier, commit, branche, necessaires, code_echec, dormir):
    """Le run de ce commit : celui d'un autre appelant s'il est en cours, ou terminé avec les jobs nécessaires réussis ;
    sinon un seul déclenchement (un job nécessaire en échec n'est relancé qu'une fois par commit)."""
    gh, opt, dire = c["gh"], c["opt"], c["dire"]
    run = gh.execution_du_commit(str(racine), workflow, commit)
    echecs = []
    if run is not None and run.get("statut") != "completed":
        dire("Une exécution de ce commit tourne déjà (%s) : on la suit." % run.get("url", ""))
        return run
    if run is not None:
        if run.get("conclusion") == "startup_failure":
            raise _refus_startup(run)
        echecs = [j for j in necessaires if not _job_reussi(gh, racine, run, j)]
        if not echecs:
            return run
        deja = [j for j in echecs if _marqueur(c["repertoire"], commit, fichier, j).exists()]
        if deja:
            raise _Refus(code_echec, "Le job « %s » a encore échoué (%s) : %s."
                         % (", ".join(deja), run.get("url", ""), MSG_DEJA_RELANCE))
    if not opt["attendre"]:
        raise _Refus(3, "Refusé : aucune exécution utilisable de ce commit sur GitHub et --sans-attendre est donné.")
    if _quota_depasse(c):
        raise _refus_quota("Quota GitHub Actions dépassé d'après la dernière lecture de la consommation : "
                           "l'exécution n'est pas lancée")
    if run is not None:
        dire("exécution précédente échouée : nouvelle exécution lancée (une seule fois pour ce commit)")
        for j in echecs:
            try:
                _marqueur(c["repertoire"], commit, fichier, j).write_text(_maintenant(), encoding="utf-8")
            except OSError:
                pass
    ancien = run.get("id") if run is not None else None
    dire("Déclenchement de l'exécution sur GitHub (branche %s, commit %s)." % (branche, commit[:8]))
    try:
        gh.declencher(str(racine), workflow, branche, {})
    except gh.Gh_indisponible as e:
        texte = str(e).lower()
        if "404" in texte or "not find" in texte or "not found" in texte:
            raise _Refus(7, "GitHub ne trouve pas le workflow %s (%s) : %s." % (workflow, e, MSG_SANS_WORKFLOW))
        raise
    for _ in range(ESSAIS_APPARITION):
        run = gh.execution_du_commit(str(racine), workflow, commit)
        if run is not None and run.get("id") != ancien:
            return run
        dormir(PAUSE_APPARITION_S)
    raise _Refus(4, "L'exécution déclenchée n'apparaît pas sur GitHub. %s." % PROPOSITION)


def _nom_variable(produit):
    return "MYIAFACTORY_ARTEFACT_" + "".join(ch if ch.isalnum() else "_" for ch in str(produit).upper())


def _premier_fichier(dossier):
    fichiers = sorted(p for p in Path(dossier).rglob("*") if p.is_file())
    return str(fichiers[0]) if fichiers else str(dossier)


def _artefact(c, racine, run, commit, produit):
    """Le chemin de l'artefact `produit` de ce commit, téléchargé une seule fois dans `<artefacts>/<commit>/<produit>`
    (hors du dossier du projet : jamais commité par un `git add -A`), réutilisé ensuite."""
    cible = Path(c["artefacts"]) / commit / produit
    if cible.is_dir() and any(p.is_file() for p in cible.rglob("*")):
        chemin = _premier_fichier(cible)
        c["dire"]("Artefact « %s » déjà téléchargé pour ce commit : %s" % (produit, chemin))
        return chemin
    partiel = cible.with_name("%s.partiel-%s-%s" % (produit, os.getpid(), threading.get_ident()))
    shutil.rmtree(str(partiel), ignore_errors=True)
    partiel.parent.mkdir(parents=True, exist_ok=True)
    try:
        c["gh"].telecharger(str(racine), run["id"], produit, str(partiel))
        if cible.exists() and not any(p.is_file() for p in cible.rglob("*")):
            shutil.rmtree(str(cible), ignore_errors=True)
        try:
            os.replace(str(partiel), str(cible))
        except OSError:
            pass      # un autre appelant l'a déposé entre-temps : le sien sert
    finally:
        shutil.rmtree(str(partiel), ignore_errors=True)
    chemin = _premier_fichier(cible)
    c["dire"]("Artefact « %s » téléchargé : %s" % (produit, chemin))
    return chemin


def _sur_github(c):
    action, lieux, catalogue, amont, opt = c["action"], c["lieux"], c["catalogue"], c["amont"], c["opt"]
    gh, git, dormir, dire, id_, repertoire = c["gh"], c["git"], c["dormir"], c["dire"], c["id"], c["repertoire"]
    pret, message = gh.gh_pret()
    if not pret:
        dire("%s\nPas de bascule silencieuse vers le poste : %s." % (message, PROPOSITION))
        return 4
    racine = deport_depot._racine_du_depot(c["dossier"])
    fichier = deport_depot.nom_fichier(deport_depot._nom_du_projet(c["projet"]))
    commit, branche = _etat_du_depot(racine, fichier, git)
    workflow = fichier + ".yml"
    sur_github = lieux[action] == "github"
    necessaires = _jobs_necessaires([action] if sur_github else amont, lieux, catalogue)
    code_echec = 1 if sur_github else 5
    if opt["attendre"]:
        ecrire_attente(id_, action, amont[0] if amont else action, "github", c["dossier"], repertoire)

    def dormir_battant(s):
        dormir(s)
        battre(id_, repertoire)

    verrou = Path(repertoire) / ("%s-%s.lock" % (commit, fichier))
    with _verrou_du_run(verrou, opt["attendre"], dormir_battant, dire):
        run = _obtenir_run(c, racine, workflow, fichier, commit, branche, necessaires, code_echec, dormir_battant)
    if run.get("statut") != "completed":
        if not opt["attendre"]:
            raise _Refus(3, "Refusé : l'exécution de ce commit n'est pas finie et --sans-attendre est donné.")
        run = gh.suivre(str(racine), run["id"], dormir=dormir_battant, dire=dire)
    if run.get("conclusion") == "timeout":
        dire("Exécution %s : délai dépassé, l'exécution tourne peut-être encore (%s). Relance plus tard : elle sera "
             "suivie, pas refaite." % (run.get("id"), run.get("url", "")))
        return code_echec
    if run.get("conclusion") == "startup_failure":
        raise _refus_startup(run)
    if sur_github:
        reussi = _job_reussi(gh, racine, run, action)
        dire("Exécution %s : %s (%s)." % (run.get("id"), "réussie" if reussi else "échouée (%s)" % run.get("conclusion"),
                                           run.get("url", "")))
        return 0 if reussi else 1
    echecs = [d for d in amont if not _job_reussi(gh, racine, run, d)]
    dire("Exécution %s : %s (%s)." % (run.get("id"), run.get("conclusion"), run.get("url", "")))
    if echecs:
        dire("L'amont (%s) a échoué : « %s » n'est pas lancé." % (", ".join(echecs), action))
        return 5
    env = {}
    for dep in amont:
        produit = catalogue[dep]["produit"]
        if produit:
            env[_nom_variable(produit)] = _artefact(c, racine, run, commit, produit)
            dire("%s=%s" % (_nom_variable(produit), env[_nom_variable(produit)]))
    return c["lancer_au_poste"](env)
