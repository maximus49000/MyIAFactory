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
- `deporter recette-emulateur [--mode scenario|pilote] [--scenario <nom>] [--apk <fichier>]` : l'APK sur un émulateur
  du serveur. Le projet doit être ENREGISTRÉ dans le bureau du Directeur (`bureau.json`) et le lieu `serveur` dans les
  réglages que le bureau enregistre pour lui (accord permanent, pour ce projet et cette action ; ni le défaut du
  bureau, ni un dossier non enregistré, ni un autre fichier donné par `--reglages` ne comptent) ; sinon
  code 2, jamais le poste ni GitHub (`--poste` et `--sans-attendre` ne s'appliquent pas). Le lanceur de tâches vérifie
  le même accord (`serveur-tache lancer` est l'autre porte). L'APK : `--apk`, sinon la production `apk` du projet (artefact GitHub du commit, attendu comme pour les tests,
  ou sortie locale du catalogue, la plus récente) ; aucun APK : code 2. Le lancement passe par le lanceur de tâches
  (`serveur_tache_cli`, Python 3.12 : importé à l'appel seulement, ou `py -3.12 lancer.py serveur-tache` à part sous
  un Python plus ancien). Scénario (par défaut, `--scenario` exigé) : lance, déroule la recette, arrête, rapatrie dans
  `<projet>/.factory/serveur/<id>/`, imprime le manifeste ; 0 seulement si le statut est `ok`, 1 sinon (plantage,
  limite, erreur, serveur injoignable). Pilote : imprime l'identifiant et le mode d'emploi de `serveur-outil`.

`lancer.py tests` (`lancer_tests`) : `--local` le poste ; GitHub par `deporter` ; avec l'accord du Directeur
(`deport_types.refus_route` : projet enregistré, `tests` sur serveur dans ses réglages enregistrés ou par défaut au
bureau) la route du serveur (`outils/tests_serveur.py`, repli au poste par règle) ; `--serveur` la force (2 sans accord) ;
sinon le poste. `deporter tests` réglé sur serveur est refusé (code 2, comme avant ; `--poste` le lance au poste). `lancer.py serveur-tests` (`serveur_tests`)
vérifie le même accord avant tout.

Codes : 0 réussi, 1 action échouée, 2 usage ou lieu refusé, 3 `--sans-attendre` refusé, 4 `gh` indisponible ou réseau
absent (ou Python 3.12 introuvable pour la recette sur émulateur), 5 amont échoué, 6 travail non poussé
(origin/<branche> n'est pas au commit courant, ou modifications suivies non commitées), 7 workflow absent de la branche, 8 quota GitHub probablement épuisé (cache de consommation au niveau
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
from bureau.registre import lieux_du_type  # noqa: E402
from bureau.deport_types import (MSG_RELEASE_SIGNE, MSG_REGLEZ_SERVEUR, SERVICES_PERMANENTS,  # noqa: E402
                                 SERVIES_AU_SERVEUR,
                                 SIGNEES_AU_POSTE, catalogue_du_projet,
                                 racine_du_projet, refus_accord, refus_route, routee_au_serveur, servie_au_serveur)

BUREAU = Path("~/MyIAFactory/bureau.json").expanduser()
EN_COURS = Path("~/MyIAFactory/deport-en-cours").expanduser()
ARTEFACTS = Path("~/MyIAFactory/artefacts").expanduser()
VARIABLE_AGENT = "MYIAFACTORY_AGENT"
MAX_FICHIERS_LISTES = 10
USAGE = ("Usage : lancer.py deporter <type> [--dossier <dossier>] [--reglages <fichier>] [--sans-attendre] [--poste] "
         "[-- <commande locale>]\n"
         "        lancer.py deporter recette-emulateur [--mode scenario|pilote] [--scenario <nom>] [--apk <fichier>] "
         "[--dossier <dossier>] [--reglages <fichier>]\n"
         "        lancer.py deporter service etat|journal [--dossier <dossier>]")
OPTIONS_PYTHON = ["-E", "-s"]       # le Python 3.12 lancé à part : sans variables PYTHON*, sans site utilisateur
MSG_SANS_312 = ("Python 3.12 introuvable : la recette sur émulateur passe par le lanceur de tâches du serveur, qui "
                "l'exige. Installez Python 3.12 (python.org, ou « winget install Python.Python.3.12 »), puis relancez. "
                "Rien n'est lancé au poste à la place.")
OPTIONS_RECETTE = ("mode", "scenario", "apk")
MODES_RECETTE = ("scenario", "pilote")
LANCEUR = Path(__file__).resolve().parent.parent / "lancer.py"
DELAI_SONDE_S = 60
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
MSG_AMONT_GITHUB = "tests au serveur demandés mais l'artefact amont vient de GitHub : tests au poste"


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

def _json_de(chemin):
    """Le contenu JSON d'un fichier ; {} s'il est absent, illisible ou n'est pas un objet."""
    try:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return {}
    return donnees if isinstance(donnees, dict) else {}


def _lieux_ecrits(chemin):
    """Les lieux écrits tels quels dans la clé `deport` d'un fichier JSON (sans les défauts) ; {} si illisible."""
    d = _json_de(chemin).get("deport")
    lieux = d.get("lieux") if isinstance(d, dict) else None
    return dict(lieux) if isinstance(lieux, dict) else {}


def _lieux(dossier, reglages, bureau):
    """`(lieux effectifs {action: lieu}, catalogue)` : surcharge du projet, puis niveau type du bureau
    (`types.<genre>.deport.lieux`), puis défaut global du bureau, sinon poste. Le projet est le plus proche dossier
    (`dossier` ou ses parents) qui contient `.factory/`."""
    projet = racine_du_projet(dossier)
    genre, catalogue = catalogue_du_projet(projet)
    chemin = Path(reglages) if reglages else Path(projet) / ".factory" / "reglages.json"
    globaux, projet = _lieux_ecrits(bureau), _lieux_ecrits(chemin)
    du_type = lieux_du_type(_json_de(bureau), genre)
    # une action au seul serveur ne prend que le réglage du projet, sinon None (non réglée : refusée)
    return {a: lieu_effectif(globaux, projet, a, catalogue, type_=du_type) for a in catalogue}, catalogue


def lieux_refuses(lieux, action, catalogue):
    """Les lieux que `deporter` ne sait pas servir (ni `poste` ni `github`, ex. `serveur` écrit à la main) pour
    l'action et les actions dont elle dépend : jamais de repli silencieux sur le poste. Le serveur n'est servi que pour
    les actions qui le déclarent et que `deporter` y sait lancer (`SERVIES_AU_SERVEUR`) ; celles-là n'ont pas d'autre
    lieu : tout autre réglage (ou aucun) est refusé."""
    refus = []
    for a in [action] + [d for d in catalogue[action]["consomme"] if d in lieux]:
        if lieux.get(a) == "serveur" and routee_au_serveur(a, catalogue):
            continue      # routée par `lancer.py tests` (accord lu à part, `refus_route`), repli au poste possible
        if servie_au_serveur(a, catalogue):
            if lieux.get(a) != "serveur":
                refus.append("« %s » ne tourne que sur le serveur et n'y est pas réglée pour ce projet. %s Jamais de "
                             "repli sur le poste ni sur GitHub." % (a, MSG_REGLEZ_SERVEUR))
            continue
        if lieux[a] not in ("poste", "github"):
            refus.append("Le lieu « %s » de l'action « %s » n'est pas disponible : seuls « poste » et « github » le "
                         "sont. Corrigez les réglages du projet, ou relancez avec --poste après accord du "
                         "Directeur." % (lieux[a], a))
    return refus


def doit_passer_par_deporter(action, lieux, catalogue):
    """Vrai si l'action tourne sur GitHub, ou si elle dépend de la production d'une action d'un autre lieu (il y a
    alors une attente à faire) ; un lieu que `deporter` ne sert pas passe aussi par lui, qui le refuse."""
    if action not in catalogue or action in SERVICES_PERMANENTS:
        return False      # le service permanent n'est pas une action lancée : le moteur le déploie (`deporter service`)
    if servie_au_serveur(action, catalogue):
        # au seul serveur : réglée, seul `deporter` la lance ; non réglée, elle n'est pas déportée (et `deporter`,
        # appelé quand même, la refuse)
        return lieux.get(action) is not None
    if lieux.get(action) == "serveur" and routee_au_serveur(action, catalogue):
        # routée au serveur : `deporter` n'a à intervenir que pour une production attendue de GitHub
        return (any(lieux.get(d) == "github" for d in a_attendre(lieux, action, catalogue))
                or bool(lieux_refuses(lieux, action, catalogue)))
    return (lieux[action] == "github" or bool(a_attendre(lieux, action, catalogue))
            or bool(lieux_refuses(lieux, action, catalogue)))


def _analyser(argv):
    """`(options, commande)` ou `None` si l'usage est faux ; `options` : type, dossier, reglages, attendre, poste, et
    pour la recette sur émulateur mode, scenario, apk (None si absents)."""
    argv = list(argv)
    commande = []
    if "--" in argv:
        i = argv.index("--")
        argv, commande = argv[:i], argv[i + 1:]
    opt = {"type": None, "dossier": None, "reglages": None, "attendre": True, "poste": False, "mode": None,
           "scenario": None, "apk": None}
    while argv:
        o = argv.pop(0)
        if o in ("--dossier", "--reglages", "--mode", "--scenario", "--apk") and argv:
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

def _verrou_perime(chemin, maintenant, etat=None):
    """Le verrou d'un processus mort, d'un pid repris par un autre programme (`campagne.vivant_et_meme` : date de
    création notée `demarre`, sinon postérieure à `t`), ou vieux de plus de 5 minutes. `etat` : pour les tests."""
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        pid, debut, demarre = donnees.get("pid"), float(donnees.get("t", 0)), donnees.get("demarre")
    except (OSError, ValueError, TypeError, AttributeError):
        pid, debut, demarre = None, 0.0, None
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return True
    return (not campagne.vivant_et_meme(pid, demarre, debut, etat=etat)) or maintenant - debut > VERROU_PERIME_S


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
            json.dump({"pid": os.getpid(), "demarre": campagne.mon_demarrage(), "t": time.time()}, f)
        break
    try:
        yield
    finally:
        try:
            chemin.unlink()
        except OSError:
            pass


# --- recette sur émulateur (serveur) -----------------------------------------------------------------------------

def _importer_cli():
    """Le lanceur de tâches du serveur (Python 3.12) : importé ici seulement, jamais au chargement de `deporter`."""
    import serveur_tache_cli
    return serveur_tache_cli


def _sonder(commande):
    """Vrai si `commande` lance un Python 3.12 ou plus récent (sans shell, sans fenêtre)."""
    try:
        f = subprocess.run(list(commande) + OPTIONS_PYTHON
                           + ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=DELAI_SONDE_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False
    return f.returncode == 0


def _sur(chemin, cwd, nt):
    """Un programme qu'on peut lancer sans risque : chemin absolu d'un fichier existant, hors du dossier courant (un
    `py.bat` posé là par un projet ne doit jamais tourner), `.exe` seulement sous Windows."""
    if not chemin or not os.path.isabs(chemin) or not os.path.isfile(chemin):
        return False
    if nt and not chemin.lower().endswith(".exe"):
        return False
    reel, ici = os.path.normcase(os.path.realpath(chemin)), os.path.normcase(os.path.realpath(cwd))
    return not (reel == ici or reel.startswith(ici.rstrip("\\/") + os.sep))


def _python_312(sonder=_sonder, environ=None, executable=None, version=None, nt=None, cwd=None):
    """La commande d'un Python 3.12, vérifiée ; None si aucune. Seulement des lieux fixes et sûrs, jamais une recherche
    qui passerait par le dossier courant (sous Windows, `shutil.which` le fouille en premier) : sous Windows le lanceur
    `%SystemRoot%\\py.exe` puis celui de l'utilisateur (`%LOCALAPPDATA%\\Programs\\Python\\Launcher\\py.exe`), avec
    `-3.12` ; l'interpréteur courant s'il est déjà en 3.12 ; ailleurs `python3.12` des dossiers ABSOLUS du PATH. Tout
    candidat hors `_sur` (relatif, dans le dossier courant, pas `.exe` sous Windows) est écarté."""
    candidats, cwd, nt = _candidats_312(environ, executable, version, nt, cwd)
    for commande in candidats:
        if _sur(commande[0], cwd, nt) and sonder(commande):
            return commande
    return None


def _candidats_312(environ=None, executable=None, version=None, nt=None, cwd=None):
    """`(candidats, cwd, nt)` : les commandes possibles d'un Python 3.12, dans l'ordre (voir `_python_312`)."""
    environ = os.environ if environ is None else environ
    executable = sys.executable if executable is None else executable
    version = tuple(sys.version_info[:2]) if version is None else tuple(version)
    nt = (os.name == "nt") if nt is None else nt
    cwd = os.getcwd() if cwd is None else cwd
    candidats = []
    if nt:
        for base, suite in ((environ.get("SystemRoot"), ("py.exe",)),
                            (environ.get("LOCALAPPDATA"), ("Programs", "Python", "Launcher", "py.exe"))):
            if base:
                candidats.append([os.path.join(base, *suite), "-3.12"])
    if version >= (3, 12) and executable:
        candidats.append([executable])
    if not nt:
        for d in environ.get("PATH", "").split(os.pathsep):
            if d and os.path.isabs(d):
                candidats.append([os.path.join(d, "python3.12")])
    return candidats, cwd, nt


def _raison_sans_312(environ=None, executable=None, version=None, nt=None, cwd=None):
    """Le texte à ajouter quand un lanceur Python existe mais est écarté parce que le dossier courant le contient
    (dossier courant = un de ses ancêtres, ex. le dossier personnel) ; None sinon."""
    candidats, cwd, nt = _candidats_312(environ, executable, version, nt, cwd)
    ecartes = [c[0] for c in candidats
               if c[0] and os.path.isabs(c[0]) and os.path.isfile(c[0]) and not _sur(c[0], cwd, nt)
               and (not nt or c[0].lower().endswith(".exe"))]
    if not ecartes:
        return None
    return ("Python 3.12 existe (%s) mais n'est pas lancé : il se trouve dans le dossier courant (%s) ou en dessous, "
            "et rien n'est lancé depuis le dossier courant par prudence. Relancez depuis le dossier du projet "
            "(--dossier ne suffit pas : c'est le dossier courant qui compte)." % (", ".join(ecartes), cwd))


def _executer(commande):
    """Lance `commande` (une liste, jamais de shell) ; sa sortie est la nôtre. Rend son code de sortie."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(list(commande), stdin=subprocess.DEVNULL).returncode
    except OSError as e:
        print("Lancement du lanceur de tâches impossible (%s)." % type(e).__name__, file=sys.stderr)
        return 4


def _serveur_tache(argv, version=None, importer=_importer_cli, trouver_python=_python_312, executer=_executer,
                   raison=_raison_sans_312):
    """`lancer.py serveur-tache …` : dans ce processus sous Python 3.12 et plus, sinon par un Python 3.12 à part
    (`deporter` reste compatible 3.9 : les agents le lancent), avec `-E -s` (ni variables PYTHON*, ni dossier
    site-packages de l'utilisateur). Rend le code du lanceur ; 4 sans Python 3.12 (`raison` dit pourquoi s'il existe)."""
    version = tuple(sys.version_info[:2]) if version is None else tuple(version)
    if version >= (3, 12):
        return importer().main(list(argv))
    python = trouver_python()
    if not python:
        pourquoi = raison()
        print(("%s %s" % (pourquoi, MSG_SANS_312)) if pourquoi else MSG_SANS_312, file=sys.stderr)
        return 4
    return executer(list(python) + OPTIONS_PYTHON + [str(LANCEUR)] + list(argv))


def _importer_service():
    """Le service permanent côté poste (Python 3.12) : importé ici seulement."""
    import serveur_service
    return serveur_service


def _service_par_defaut(argv):
    """`lancer.py service …` (argv commence par « service ») : dans ce processus sous 3.12, sinon un Python 3.12 à part."""
    return _serveur_tache(argv, importer=_importer_service)


MSG_SERVICE = ("« deporter service » ne lit que l'état ou le journal du service permanent du projet : « python lancer.py "
               "deporter service etat|journal [--dossier <projet>] ». Le déploiement est fait par le moteur après une "
               "livraison validée ; la gestion (redémarrer, arrêter, secrets, jeton) appartient au Directeur, au bureau "
               "(zone Services). Prépare seulement .factory/service.json (voir docs/serveur-services.md).")


def _service(argv, service):
    """`deporter service etat|journal [--dossier D]` : la seule porte des agents vers le service permanent."""
    reste = list(argv[1:])
    sous = reste.pop(0) if reste and not reste[0].startswith("--") else None
    if sous not in ("etat", "journal"):
        print(MSG_SERVICE, file=sys.stderr)
        return 2
    options = []
    while reste:
        o = reste.pop(0)
        if o == "--dossier" and reste:
            options += [o, reste.pop(0)]
        else:
            print("Option inconnue : %s\n%s" % (o, MSG_SERVICE), file=sys.stderr)
            return 2
    return (service or _service_par_defaut)(["service", sous] + options)


def _usage_recette(opt, commande):
    """Le refus d'usage de la recette sur émulateur, ou None."""
    if opt["poste"]:
        return ("--poste ne s'applique pas à la recette sur émulateur : elle ne tourne que sur le serveur. %s"
                % MSG_REGLEZ_SERVEUR)
    if commande:
        return "La recette sur émulateur ne prend pas de commande locale (rien après « -- »).\n" + USAGE
    if not opt["attendre"]:
        return ("--sans-attendre ne s'applique pas à la recette sur émulateur : le lanceur de tâches du serveur attend "
                "son créneau et la fin du scénario.\n" + USAGE)
    mode = opt["mode"] or "scenario"
    if mode not in MODES_RECETTE:
        return "Mode inconnu : « %s » (attendu : scenario ou pilote).\n%s" % (mode, USAGE)
    if mode == "scenario" and not opt["scenario"]:
        return ("Le mode scénario exige --scenario <nom> (la recette .factory/recettes/<nom>.json) ; --mode pilote "
                "pour conduire l'émulateur verbe par verbe.\n" + USAGE)
    return None


def _registre_perime(projet, variante=None):
    """Vrai si le registre des APK connaît des APK de la variante mais aucun ne correspond aux sources actuelles : un APK
    plus ancien (sorti d'un motif de sortie locale) serait périmé, la recette ne le reçoit pas."""
    try:
        racine = str(Path(__file__).resolve().parent.parent)
        if racine not in sys.path:
            sys.path.insert(0, racine)
        from moteur import registre_apk
        r = registre_apk.fournir(str(projet), variante, demander=False)
    except Exception:
        return False
    return r.get("etat") == "a_construire" and r.get("raison") == "perime"


def _apk_du_registre(projet, variante=None):
    """L'APK existant dont l'empreinte des sources correspond au code testé (`moteur/registre_apk.py`), sinon None : la
    recette ne reçoit jamais un APK périmé quand le registre sait que les sources ont changé, et n'en construit pas un
    nouveau quand un correspondant existe."""
    try:
        racine = str(Path(__file__).resolve().parent.parent)
        if racine not in sys.path:
            sys.path.insert(0, racine)
        from moteur import registre_apk
        r = registre_apk.fournir(str(projet), variante, demander=False)
    except Exception:
        return None
    if r.get("etat") != "existant":
        return None
    chemin = (Path(projet) / r["apk"]["chemin"]).resolve()
    return str(chemin) if chemin.is_file() else None


def _apk_de_la_recette(opt, projet, catalogue, action, env):
    """`(chemin, None)` de l'APK, ou `(None, message)` : `--apk`, sinon l'artefact GitHub téléchargé (`env`), sinon la
    sortie locale publiée par le catalogue (`artefact` de l'action productrice), la plus récente."""
    if opt["apk"]:
        chemin = Path(opt["apk"]).resolve()
        if not chemin.is_file():
            return None, "Fichier APK introuvable : %s." % opt["apk"]
        return str(chemin), None
    sources = [catalogue[d] for d in catalogue[action]["consomme"] if d in catalogue and catalogue[d]["produit"]]
    for e in sources:
        chemin = (env or {}).get(_nom_variable(e["produit"]))
        if chemin:
            return chemin, None
    existant = _apk_du_registre(projet, opt.get("variante"))
    if existant:
        return existant, None
    if _registre_perime(projet, opt.get("variante")):
        return None, ("L'APK construit ne correspond plus aux sources de l'application (le code a changé depuis) : une "
                      "construction est nécessaire (« deporter apk » ou la commande du projet), ou donnez --apk <fichier>.")
    motifs = [e["artefact"] for e in sources if e["artefact"]]
    trouves = []
    for motif in motifs:
        try:
            trouves += [p for p in Path(projet).glob(motif) if p.is_file()]
        except (OSError, ValueError):
            continue
    trouves = [p for p in trouves if _apk_utile(p)]      # jamais l'APK des tests instrumentés (androidTest)
    if trouves:
        return str(max(trouves, key=lambda p: p.stat().st_mtime)), None
    return None, ("Aucun APK trouvé pour la recette sur émulateur : ni --apk, ni sortie locale (%s) dans %s. Générez-le "
                  "(« deporter apk » ou la commande du projet), ou donnez --apk <fichier>."
                  % (", ".join(motifs) or "aucune publiée", projet))


def _recette_au_serveur(opt, projet, catalogue, action, env, serveur_tache, dire):
    """Lance la recette sur le serveur par le lanceur de tâches (T7) ; rend son code (2 si aucun APK)."""
    apk, erreur = _apk_de_la_recette(opt, projet, catalogue, action, env)
    if erreur:
        print(erreur, file=sys.stderr)
        return 2
    mode = opt["mode"] or "scenario"
    argv = ["serveur-tache", "lancer", "--apk", apk, "--mode", mode]
    if opt["scenario"]:
        argv += ["--scenario", opt["scenario"]]
    argv += ["--projet", str(projet)]
    if mode == "scenario":
        argv.append("--attendre")      # lance, déroule la recette, arrête, rapatrie et imprime le manifeste
    dire("Recette sur émulateur au serveur (mode %s), APK : %s" % (mode, apk))
    return serveur_tache(argv)


# --- exécution ---------------------------------------------------------------------------------------------------

def main(argv=None, executer_poste=campagne.executer, gh=github_actions, git=_git, dormir=time.sleep, dire=None,
         bureau=BUREAU, repertoire_attente=EN_COURS, artefacts=ARTEFACTS, cache_conso=None, serveur_tache=None,
         noter=None, service=None):
    """`artefacts` : où vont les artefacts téléchargés (`<artefacts>/<commit>/<produit>`) ; `cache_conso` : le dossier
    du cache de consommation (None : celui de `bureau.deport_conso`, `~/MyIAFactory`) ; `serveur_tache` : le lanceur
    de tâches du serveur pour la recette sur émulateur (`argv -> code` ; None : `_serveur_tache`) ; `noter` : qui note
    au journal des tests une campagne faite sur GitHub (None : `bureau.tests_mesures.noter_campagne`) ; `service` : la
    commande du service permanent (`argv -> code` ; None : `lancer.py service`)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["service"]:      # le service permanent : etat et journal seulement (l'accord est relu par la commande)
        return _service(argv, service)
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
    if action in SIGNEES_AU_POSTE:      # jamais lancée ici : aucun agent ne signe ; la marche à suivre
        print(MSG_RELEASE_SIGNE, file=sys.stderr)
        return 2
    au_serveur = servie_au_serveur(action, catalogue)
    if not au_serveur and any(opt[k] is not None for k in OPTIONS_RECETTE):
        print("--mode, --scenario et --apk ne valent que pour %s.\n%s" % (", ".join(SERVIES_AU_SERVEUR), USAGE),
              file=sys.stderr)
        return 2
    if au_serveur:
        # l'accord ne vaut que pour un projet enregistré au bureau, lu dans SES réglages enregistrés (`--reglages`
        # admis seulement s'il est ce fichier) : la même porte que `serveur-tache lancer`
        refus_du_bureau = refus_accord(racine_du_projet(dossier), action, bureau=str(bureau), reglages=opt["reglages"])
        if refus_du_bureau:
            print(refus_du_bureau, file=sys.stderr)
            return 2
        lieux[action] = "serveur"
    if opt["poste"] and not au_serveur:
        lieux[action] = "poste"
    refus = lieux_refuses(lieux, action, catalogue)
    if refus:
        print("\n".join(refus), file=sys.stderr)
        return 2
    erreur = _usage_recette(opt, commande) if au_serveur else None
    if erreur:
        print(erreur, file=sys.stderr)
        return 2
    amont = [d for d in a_attendre(lieux, action, catalogue) if lieux.get(d) == "github"]
    if au_serveur and opt["apk"]:
        amont = []      # l'APK fourni l'emporte : rien à attendre de GitHub
    if not au_serveur and lieux[action] != "github" and not commande:
        print(USAGE, file=sys.stderr)
        return 2

    id_ = "%s-%s-%s" % (os.getpid(), threading.get_ident(), action)

    def lancer_au_poste(env=None):
        if au_serveur:      # jamais le poste : la recette part sur le serveur, l'APK venu de GitHub dans `env`
            retirer_attente(id_, repertoire_attente)      # plus rien n'est attendu de GitHub : pas de fichier figé
            return _recette_au_serveur(opt, racine_du_projet(dossier), catalogue, action, env,
                                       serveur_tache or _serveur_tache, dire)
        if env:      # les chemins des artefacts téléchargés (MYIAFACTORY_ARTEFACT_<PRODUIT>)
            return executer_poste(commande, dossier=dossier, attendre=opt["attendre"], env=env)
        return executer_poste(commande, dossier=dossier, attendre=opt["attendre"])

    if lieux[action] != "github" and not amont:
        if lieux[action] == "serveur" and not au_serveur:
            # routée (`tests`) : seul `lancer.py tests` prend la route du serveur, après l'accord ; `deporter` refuse
            # comme avant (jamais de bascule silencieuse vers le poste)
            print("Le lieu « serveur » de l'action « %s » n'est pas disponible par « deporter » : lancez « lancer.py "
                  "tests [--dossier <dossier>] -- <commande> » (le serveur avec l'accord du Directeur, sinon le poste), "
                  "ou relancez avec --poste." % action, file=sys.stderr)
            return 2
        return lancer_au_poste()
    if lieux[action] == "serveur" and not au_serveur and amont:
        # routée sur serveur mais une production vient de GitHub : la route ne sait pas l'attendre ; le poste, dit
        dire(MSG_AMONT_GITHUB)

    contexte = {"action": action, "lieux": lieux, "catalogue": catalogue, "amont": amont, "opt": opt,
                "dossier": dossier, "projet": racine_du_projet(dossier), "gh": gh, "git": git, "dormir": dormir,
                "dire": dire, "id": id_, "repertoire": repertoire_attente, "artefacts": artefacts,
                "cache_conso": cache_conso, "lancer_au_poste": lancer_au_poste, "commande": commande, "noter": noter}
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


USAGE_TESTS = ("Usage : lancer.py tests [--dossier <dossier>] [--sans-attendre] [--local | --serveur] -- <commande de "
               "test>")
MSG_SANS_312_TESTS = ("Python 3.12 introuvable : la route des tests au serveur l'exige (python.org, ou « winget install "
                      "Python.Python.3.12 »)")


class RouteIndisponible(Exception):
    """La route du serveur ne peut pas être lancée d'ici (pas de Python 3.12, lancement ou import impossible) :
    `raison` est dite en une ligne, puis le poste (ou 4 avec `--serveur`)."""

    def __init__(self, raison):
        Exception.__init__(self, raison)
        self.raison = raison


def _retirer_route(argv):
    """`(argv sans --local/--serveur, local, serveur)` : seulement AVANT `--` (la commande garde les siens), et jamais
    la valeur de `--dossier` ou `--reglages`."""
    argv = list(argv)
    fin = argv.index("--") if "--" in argv else len(argv)
    garde, local, serveur, i = [], False, False, 0
    while i < fin:
        o = argv[i]
        if o in ("--dossier", "--reglages") and i + 1 < fin:
            garde += [o, argv[i + 1]]
            i += 2
            continue
        if o == "--local":
            local = True
        elif o == "--serveur":
            serveur = True
        else:
            garde.append(o)
        i += 1
    return garde + argv[fin:], local, serveur


def _options_campagne(argv):
    """`(dossier, attendre, commande)` de l'usage de la campagne (`[--dossier D] [--sans-attendre] -- <commande>`), ou
    None (la campagne dira l'usage elle-même, comme aujourd'hui)."""
    if "--" not in argv or argv.index("--") == len(argv) - 1:
        return None
    i = argv.index("--")
    options, commande = list(argv[:i]), list(argv[i + 1:])
    dossier, attendre = None, True
    while options:
        o = options.pop(0)
        if o == "--dossier" and options:
            dossier = options.pop(0)
        elif o == "--sans-attendre":
            attendre = False
        else:
            return None
    return dossier, attendre, commande


def _importer_tests_serveur():
    """La route du serveur (Python 3.12) : importée ici seulement, jamais au chargement de `deporter`."""
    import tests_serveur
    return tests_serveur


def _executer_route(commande, run=subprocess.run):
    """Lance `lancer.py serveur-tests …` sous un Python 3.12 à part (liste, jamais de shell ; sorties héritées) ; rend
    son code, 130 sur Ctrl-C ; `RouteIndisponible` si le lancement est impossible (OSError)."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return run(list(commande), stdin=subprocess.DEVNULL).returncode
    except KeyboardInterrupt:
        return 130
    except OSError as e:
        raise RouteIndisponible("Lancement de Python 3.12 impossible (%s : %s)" % (type(e).__name__, e))


def _importer_route(importer):
    """Le module de la route ; `RouteIndisponible` (une ligne, pas de trace) s'il ne s'importe pas."""
    try:
        return importer()
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001 — module absent ou abîmé : dit, puis le poste
        raise RouteIndisponible("Route du serveur indisponible (%s : %s)" % (type(e).__name__, e))


def _route_par_defaut(commande, dossier, attendre, forcer, version=None, importer=_importer_tests_serveur,
                      trouver_python=_python_312, executer=_executer_route):
    """La campagne par `tests_serveur.executer` (dans ce processus sous Python 3.12 et plus, sinon `lancer.py
    serveur-tests` par un Python 3.12 à part, `-E -s`) ; rend son code (130 sur Ctrl-C) ; `RouteIndisponible` sans
    Python 3.12, si son lancement échoue ou si la route ne s'importe pas."""
    version = tuple(sys.version_info[:2]) if version is None else tuple(version)
    if version >= (3, 12):
        try:
            module = _importer_route(importer)
            return module.executer(list(commande), dossier=dossier, attendre=attendre, forcer=forcer)
        except KeyboardInterrupt:
            return 130
    python = trouver_python()
    if not python:
        raise RouteIndisponible(MSG_SANS_312_TESTS)
    argv = list(python) + OPTIONS_PYTHON + [str(LANCEUR), "serveur-tests", "--dossier", str(dossier)]
    argv += ([] if attendre else ["--sans-attendre"]) + (["--serveur"] if forcer else []) + ["--"] + list(commande)
    return executer(argv)


def _amont_github(argv, bureau):
    """Les actions dont `tests` (pris au serveur) attend une production de GitHub, d'après les lieux effectifs."""
    lus = _lieux_des_options(argv, bureau)
    if not lus or "tests" not in lus[1]:
        return []
    lieux, catalogue = lus
    return [d for d in a_attendre(dict(lieux, tests="serveur"), "tests", catalogue) if lieux.get(d) == "github"]


def _juger(dossier, bureau):
    """`(dossier résolu, refus ou None)` ; un dossier illisible est un refus."""
    try:
        dossier = str(Path(dossier or os.getcwd()).resolve())
        return dossier, refus_route(dossier, "tests", bureau=str(bureau))
    except (OSError, ValueError, RuntimeError) as e:
        return str(dossier), "dossier illisible (%s)" % type(e).__name__


def lancer_tests(argv, bureau=BUREAU, deporter_main=None, campagne_main=None, route=None):
    """`lancer.py tests [--local | --serveur] …` (conception § 5.1) :
    1. `--local` : la campagne du poste (verrou), sans rien lire d'autre ;
    2. tests réglés sur GitHub, ou en attente d'une production de GitHub : par `deporter` (sauf `--serveur`) ;
    3. accord du serveur (`refus_route` : projet enregistré au bureau, `tests` sur serveur dans SES réglages
       enregistrés ou par défaut au bureau) : la route (`route(commande, dossier, attendre, forcer)`, défaut
       `_route_par_defaut`), qui se replie au poste par ses règles ; `--serveur` la force (jamais de repli) ;
    4. sinon la campagne du poste, comme toujours (sans un mot si rien ne demande le serveur).
    `--serveur` sans accord : code 2 et la raison, jamais de route ; `--serveur` quand les tests attendent une
    production de GitHub : code 2 (la route ne sait pas l'attendre). Route indisponible (pas de Python 3.12, lancement
    ou import impossible) : le poste avec une ligne (4 avec `--serveur`). Ctrl-C pendant le jugement : 130."""
    argv, local, serveur = _retirer_route(argv)
    poste = campagne_main or campagne.main
    if local and serveur:
        print("--local et --serveur s'excluent.\n" + USAGE_TESTS, file=sys.stderr)
        return 2
    if local:
        return poste(argv)
    try:
        if not serveur and faut_deporter("tests", argv, bureau):
            vers_deporter = True
        else:
            vers_deporter = False
            lues = _options_campagne(argv)
            if lues is not None:
                dossier, attendre, commande = lues
                dossier, refus = _juger(dossier, bureau)
                demande = (not refus) or serveur or lieu_de("tests", argv, bureau) == "serveur"
                amont = _amont_github(argv, bureau) if serveur and not refus else []
    except KeyboardInterrupt:
        return 130
    if vers_deporter:
        return (deporter_main or main)(["tests"] + argv)
    if lues is None:
        if serveur:
            print(USAGE_TESTS, file=sys.stderr)
            return 2
        return poste(argv)
    if refus:
        if serveur:
            print("Tests au serveur refusés : %s" % refus, file=sys.stderr)
            return 2
        if demande:      # le serveur est demandé, sans accord : dit, une ligne
            print("Tests au poste (une campagne à la fois) : %s" % refus.split("\n")[0], file=sys.stderr, flush=True)
        return poste(argv)
    if amont:
        print("Tests au serveur refusés : ils attendent la production « %s » de GitHub, que la route ne sait pas "
              "attendre. Relancez sans --serveur (le poste après GitHub)." % ", ".join(amont), file=sys.stderr)
        return 2
    try:
        return (route or _route_par_defaut)(commande, dossier, attendre, serveur)
    except RouteIndisponible as e:
        if serveur:
            print("%s. Rien n'est lancé au poste (--serveur)." % e.raison, file=sys.stderr)
            return 4
        print("%s : tests au poste (une campagne à la fois)." % e.raison, file=sys.stderr, flush=True)
        return poste(argv)


def serveur_tests(argv, bureau=BUREAU, importer=_importer_tests_serveur, version=None):
    """`lancer.py serveur-tests [--dossier D] [--sans-attendre] [--serveur] -- <commande>` : l'autre porte de la route
    (lancée par `lancer_tests` sous un Python plus ancien, ou à la main). Exige Python 3.12 (4 sinon). Le même accord
    (`refus_route`) est vérifié AVANT d'importer la route : sans lui, code 2 et rien ne part (la route le revérifie).
    Ctrl-C pendant le jugement : 130 ; route qui ne s'importe pas : 4 avec la raison."""
    argv = list(argv)
    options = _retirer_route(argv)
    lues = _options_campagne(options[0]) if not options[1] else None
    if lues is None:
        print("Usage : lancer.py serveur-tests [--dossier <dossier>] [--sans-attendre] [--serveur] -- <commande de "
              "test>", file=sys.stderr)
        return 2
    version = tuple(sys.version_info[:2]) if version is None else tuple(version)
    if version < (3, 12):
        print("%s : relancez par « py -3.12 lancer.py serveur-tests … » (ou « lancer.py tests », qui le trouve)."
              % MSG_SANS_312_TESTS, file=sys.stderr)
        return 4
    try:
        dossier, refus = _juger(lues[0], bureau)
    except KeyboardInterrupt:
        return 130
    if refus:
        print("Tests au serveur refusés : %s" % refus, file=sys.stderr)
        return 2
    try:
        module = _importer_route(importer)
    except KeyboardInterrupt:
        return 130
    except RouteIndisponible as e:
        print("%s. Rien n'est lancé." % e.raison, file=sys.stderr)
        return 4
    # le dossier jugé, déjà résolu : la route ne le résout pas une seconde fois (un lien changé entre-temps)
    return module.main(["--dossier", dossier] + ([] if lues[1] else ["--sans-attendre"])
                       + (["--serveur"] if options[2] else []) + ["--"] + lues[2])


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


def _apk_utile(p):
    """Un APK de l'application, jamais celui des tests instrumentés (`…-androidTest.apk`)."""
    return p.suffix.lower() == ".apk" and "androidtest" not in p.name.lower()


def _premier_fichier(dossier):
    """Le fichier de l'artefact : d'abord un APK de l'application, sinon un fichier qui n'est pas d'androidTest, sinon
    le premier (artefact d'un autre genre)."""
    fichiers = sorted(p for p in Path(dossier).rglob("*") if p.is_file())
    choix = ([p for p in fichiers if _apk_utile(p)] or [p for p in fichiers if "androidtest" not in p.name.lower()]
             or fichiers)
    return str(choix[0]) if choix else str(dossier)


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


def _noter_le_run(c, run, reussi, noter=None):
    """Note au journal des tests du projet la campagne faite sur GitHub (une ligne par exécution : `run` déjà noté,
    rien de plus). Toute erreur est tue : la mesure ne change jamais le code de sortie."""
    try:
        if noter is None:
            from bureau import tests_mesures
            noter = tests_mesures.noter_campagne
        commande = (" ".join(c.get("commande") or []) or (c["catalogue"].get("tests") or {}).get("commande")
                    or "tests")
        noter(c["dossier"], commande=commande, duree_s=run.get("duree_s") or 0, attente_s=0, code=0 if reussi else 1,
              lieu="github", run=run.get("id"))
    except Exception:  # noqa: BLE001 — la mesure ne casse jamais une campagne
        pass


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
        if action == "tests":
            _noter_le_run(c, run, reussi, noter=c.get("noter"))
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
