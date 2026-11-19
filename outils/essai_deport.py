"""Essai de l'exécution déportée : GitHub construit l'APK ET passe les tests unitaires, on mesure le temps de toute la
procédure et la charge de l'ordinateur local pendant ce temps, pour la comparer au même travail fait au poste.

    py -3.12 outils/essai_deport.py --dossier <projet> [--mode local|github|les-deux] [--runs N] [--intervalle S]
                                    [--forcer] [--simuler] [--confirme] [--rapports DOSSIER] [--java-home JDK]

Sans `--confirme`, l'outil affiche seulement le plan et s'arrête (code 0) : jamais d'exécution GitHub ni de build
Gradle par mégarde. `--simuler` déroule tout avec des faux, sans rien toucher. Rien n'est jamais poussé ; les portées
de `gh` ne sont jamais changées ; aucune précondition n'est corrigée automatiquement.

Codes : 0 réussi, 1 une commande ou un run mesuré a échoué (le rapport est écrit), 2 usage, 10 `gh` non prêt,
11 travail non poussé, 12 modifications suivies hors `.factory/`, 13 workflow absent du commit, 14 poste déjà chargé,
15 `gh` indisponible pendant la mesure.

Reste compatible Python 3.9 : pas de `X | Y`, pas de `match`.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import deport_depot  # noqa: E402
import deporter  # noqa: E402
import github_actions  # noqa: E402
from bureau import charge  # noqa: E402
from bureau.deport_conso import _minutes, _secondes  # noqa: E402
from bureau.deport_types import catalogue_du_projet  # noqa: E402

CODE_ECHEC = 1
CODE_USAGE = 2
CODE_GH = 10
CODE_NON_POUSSE = 11
CODE_MODIFS = 12
CODE_WORKFLOW = 13
CODE_CHARGE = 14
CODE_GH_INDISPONIBLE = 15

SEUIL_CHARGE_CPU = 60.0
DUREE_CHARGE_INITIALE_S = 10
ACTIONS = ("apk", "tests")
RAPPORTS = Path("~/MyIAFactory/essais-deport").expanduser()
PAS_SONDE_S = 15              # `suivre` interroge GitHub tous les PAS_S ; on le fait plus souvent pour mesurer finement
ESSAIS_APPARITION = 24
PAUSE_APPARITION_S = 5
DELAI_COMMANDE_S = 3600

MSG_WORKFLOW = ("le workflow n'est pas dans le commit courant : le Directeur doit le valider et le pousser depuis le "
                "bureau (« Valider et pousser »), puis fusionner la branche deport/workflow dans la branche du projet "
                "et pousser.")
AVERTISSEMENT = ("Pour une mesure valable, arrêtez tout autre travail lourd du poste (agents, émulateurs, tests, "
                 "navigateurs gourmands) avant de lancer l'essai.")
MSG_VALIDITE = ("La comparaison des temps n'est valable que si le poste était au repos pendant la partie locale.")


class Refus(Exception):
    """Une précondition n'est pas remplie : message clair et code de sortie propre, rien n'est corrigé."""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


# --- échantillonneur de charge -----------------------------------------------------------------------------------

def _sonde_par_defaut():
    sonde = charge.Sonde()
    sonde.lire()                 # la première lecture du CPU n'a pas de point de comparaison : on l'amorce
    return sonde.lire


def _stats(valeurs):
    if not valeurs:
        return {"min": 0.0, "moyenne": 0.0, "max": 0.0, "p95": 0.0}
    tri = sorted(valeurs)
    rang = max(1, int(math.ceil(0.95 * len(tri) - 1e-9)))
    return {"min": float(tri[0]), "moyenne": float(sum(tri)) / len(tri), "max": float(tri[-1]),
            "p95": float(tri[rang - 1])}


def resume(echantillons):
    """`{nb, duree_s, cpu: {min, moyenne, max, p95}, ram: {...}}` de `[(t_s, cpu_pct, ram_pct)]`."""
    ech = list(echantillons)
    duree = (ech[-1][0] - ech[0][0]) if ech else 0
    return {"nb": len(ech), "duree_s": duree, "cpu": _stats([e[1] for e in ech]), "ram": _stats([e[2] for e in ech])}


class Echantillonneur:
    """Mesure la charge du poste toutes les `intervalle_s` secondes dans un fil de fond : `[(t_s, cpu, ram)]` (t depuis
    le démarrage). Un échantillon au départ, un à l'arrêt. `mesurer` rend `{cpu, memoire}` ou `None`."""

    def __init__(self, intervalle_s=5, mesurer=None, horloge=time.monotonic):
        self.intervalle_s = intervalle_s
        self._mesurer = mesurer
        self.horloge = horloge
        self.echantillons = []
        self.fil = None
        self._stop = threading.Event()
        self._debut = None
        self._verrou = threading.Lock()

    def _noter(self):
        try:
            m = self._mesurer()
        except Exception:      # une lecture ratée ne doit jamais interrompre l'essai
            m = None
        if m:
            with self._verrou:
                self.echantillons.append((self.horloge() - self._debut, float(m["cpu"]), float(m["memoire"])))

    def _boucle(self):
        while not self._stop.wait(self.intervalle_s):
            self._noter()

    def demarrer(self):
        if self._mesurer is None:
            self._mesurer = _sonde_par_defaut()
        self._debut = self.horloge()
        self._stop.clear()
        self._noter()
        self.fil = threading.Thread(target=self._boucle, name="echantillonneur", daemon=True)
        self.fil.start()

    def arreter(self):
        self._stop.set()
        if self.fil is not None:
            self.fil.join(10)
        if self._debut is not None:
            self._noter()

    def resume(self):
        with self._verrou:
            return resume(list(self.echantillons))

    def __enter__(self):
        self.demarrer()
        return self

    def __exit__(self, *exc):
        self.arreter()
        return False


def charge_initiale(mesurer, duree_s=DUREE_CHARGE_INITIALE_S, dormir=time.sleep):
    """CPU moyen (%) du poste sur `duree_s` secondes, une lecture par seconde (la première amorce la mesure)."""
    valeurs = []
    for i in range(duree_s + 1):
        m = mesurer()
        if m:
            valeurs.append(float(m["cpu"]))
        if i < duree_s:
            dormir(1)
    valeurs = valeurs[1:] if len(valeurs) > 1 else valeurs
    return sum(valeurs) / len(valeurs) if valeurs else 0.0


# --- mesure locale -----------------------------------------------------------------------------------------------

def traduire(commande, windows):
    """La commande du catalogue en liste d'arguments ; sous Windows `./gradlew` devient `gradlew.bat`."""
    argv = commande.split()
    if windows and argv and argv[0] in ("./gradlew", "gradlew"):
        argv[0] = "gradlew.bat"
    return argv


def executer_au_poste(argv, dossier, java_home=None):
    """Lance la commande dans le dossier du projet et rend son code ; la sortie n'est gardée qu'en queue d'écran."""
    argv = list(argv)
    local = os.path.join(dossier, argv[0])
    if os.path.exists(local):
        argv[0] = local
    env = dict(os.environ)
    if java_home:
        env["JAVA_HOME"] = java_home
    with tempfile.TemporaryFile() as sortie:
        try:
            r = subprocess.run(argv, cwd=dossier, env=env, stdout=sortie, stderr=subprocess.STDOUT,
                               timeout=DELAI_COMMANDE_S, stdin=subprocess.DEVNULL)
            code = r.returncode
        except subprocess.TimeoutExpired:
            code = 124
        if code != 0:
            sortie.seek(0)
            queue = sortie.read()[-600:].decode("utf-8", errors="replace")
            print("  fin de la sortie de %s :\n%s" % (" ".join(argv[1:]), queue))
    return code


def arreter_gradle(dossier, java_home=None):
    """Arrête les démons Gradle/Kotlin (le PC a 7,5 Go) : l'outil du projet s'il existe, sinon `gradlew --stop`."""
    env = dict(os.environ)
    if java_home:
        env["JAVA_HOME"] = java_home
    outil = os.path.join(dossier, "outils", "arret_gradle.py")
    if os.path.exists(outil):
        argv = [sys.executable, "-I", outil]
    else:
        wrapper = os.path.join(dossier, "gradlew.bat" if sys.platform == "win32" else "gradlew")
        argv = [wrapper, "--stop"]
    try:
        subprocess.run(argv, cwd=dossier, env=env, capture_output=True, timeout=120, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        print("Attention : les démons Gradle n'ont pas pu être arrêtés (%s)." % e)


def mesurer_local(dossier, commandes, executer, fabrique, horloge=time.monotonic, arreter=arreter_gradle,
                  windows=None):
    """Lance chaque commande du catalogue au poste, à la suite, avec l'échantillonneur en marche. Rend
    `{commandes: [{nom, commande, duree_s, code, charge}], total_s, charge}`. Les démons sont toujours arrêtés après."""
    windows = (sys.platform == "win32") if windows is None else windows
    resultats = []
    total = fabrique()
    debut = horloge()
    try:
        with total:
            for nom, commande in commandes.items():
                une = fabrique()
                t0 = horloge()
                with une:
                    code = executer(traduire(commande, windows), dossier)
                resultats.append({"nom": nom, "commande": commande, "duree_s": horloge() - t0, "code": code,
                                  "charge": une.resume()})
    finally:
        arreter(dossier)
    return {"commandes": resultats, "total_s": horloge() - debut, "charge": total.resume()}


# --- mesure déportée ---------------------------------------------------------------------------------------------

def verifier_preconditions(dossier, gh, git):
    """Toutes les préconditions de l'essai GitHub ; rend `(racine, commit, branche, fichier_workflow)` ou lève `Refus`.
    Rien n'est corrigé : le message dit quoi faire."""
    pret, message = gh.gh_pret()
    if not pret:
        raise Refus(CODE_GH, message)
    racine = deport_depot._racine_du_depot(dossier)
    fichier = deport_depot.nom_fichier(deport_depot._nom_du_projet(dossier))
    # l'arbre modifié (12) se juge avant l'état du dépôt, qui le refuserait sous le code 11
    code, sortie = git(["status", "--porcelain", "--untracked-files=no"], racine)
    if code != 0:
        raise Refus(CODE_MODIFS, "git status a échoué : %s" % sortie.strip())
    modifs = [ligne for ligne in sortie.splitlines() if ligne.strip()
              and not ligne[3:].strip().strip('"').startswith(".factory/")]
    if modifs:
        raise Refus(CODE_MODIFS, "des fichiers suivis sont modifiés (hors .factory/) : le run mesurerait un autre état "
                                 "que le commit. Fichiers : %s. Validez-les ou annulez-les, puis recommencez."
                    % ", ".join(ligne[3:].strip() for ligne in modifs[:8]))
    try:
        commit, branche = deporter._etat_du_depot(racine, fichier, git)
    except deporter._Refus as r:
        if r.code == 7:
            raise Refus(CODE_WORKFLOW, MSG_WORKFLOW)
        raise Refus(CODE_NON_POUSSE, r.message)
    return racine, commit, branche, fichier + ".yml"


def minutes_facturees(jobs):
    """Minutes facturées : chaque job à la minute entamée, les jobs s'additionnent ; sans dates, rien."""
    total = 0
    for j in jobs:
        try:
            total += _minutes(_secondes(j["debut"], j["fin"]))
        except (KeyError, TypeError, ValueError):
            continue
    return total


def _instant(texte):
    return datetime.fromisoformat(str(texte).replace("Z", "+00:00"))


def _duree_job(j):
    try:
        return int(_secondes(j["debut"], j["fin"]))
    except (KeyError, TypeError, ValueError):
        return None


def _attendre_apparition(gh, racine, workflow, commit, ancien, dormir):
    for _ in range(ESSAIS_APPARITION):
        run = gh.execution_du_commit(str(racine), workflow, commit)
        if run is not None and run.get("id") != ancien:
            return run
        dormir(PAUSE_APPARITION_S)
    raise Refus(CODE_GH_INDISPONIBLE, "L'exécution déclenchée n'apparaît pas sur GitHub.")


def _un_run(numero, racine, workflow, commit, branche, gh, fabrique, dormir, horloge, maintenant, dire):
    ancien = None
    existant = gh.execution_du_commit(str(racine), workflow, commit)
    if existant is not None:
        ancien = existant.get("id")
    echantillonneur = fabrique()
    with echantillonneur:
        t0 = horloge()
        envoye = maintenant()
        dire("Run %d : déclenchement sur GitHub (branche %s)." % (numero, branche))
        gh.declencher(str(racine), workflow, branche, {})
        run = _attendre_apparition(gh, racine, workflow, commit, ancien, dormir)
        apparition = horloge() - t0

        def dire_reel(texte):
            # `suivre` compte PAS_S secondes par tour alors qu'on dort moins : on affiche le temps réellement écoulé
            minutes = int((horloge() - t0) // 60)
            dire(re.sub(r"\(\d+ min\)$", "(%d min)" % minutes, str(texte)))

        def dormir_fin(s):
            dormir(min(s, PAS_SONDE_S))
        # `suivre` compte PAS_S secondes par tour ; on dort moins pour mesurer finement : le délai est mis à l'échelle
        facteur = max(1, int(github_actions.PAS_S // PAS_SONDE_S))
        final = gh.suivre(str(racine), run["id"], dormir=dormir_fin, dire=dire_reel, delai_s=3600 * facteur)
        total = horloge() - t0
    jobs = gh.jobs_du_run(str(racine), final["id"])
    par_nom = {}
    for j in jobs:
        par_nom[j.get("name")] = {"duree_s": _duree_job(j), "conclusion": j.get("conclusion")}
    debuts = []
    for j in jobs:
        try:
            debuts.append(_instant(j["debut"]))
        except (KeyError, TypeError, ValueError):
            pass
    attente = (min(debuts) - envoye).total_seconds() if debuts else None
    return {"numero": numero, "etat": "froid" if numero == 1 else "chaud", "id": final["id"],
            "url": final.get("url", ""), "conclusion": final.get("conclusion"), "total_s": total,
            "duree_run_s": final.get("duree_s"), "apparition_s": apparition, "attente_demarrage_s": attente,
            "jobs": par_nom, "minutes_facturees": minutes_facturees(jobs), "charge_locale": echantillonneur.resume()}


def mesurer_github(dossier, runs, gh, git, fabrique, dormir=time.sleep, horloge=time.monotonic,
                   maintenant=lambda: datetime.now(timezone.utc), dire=print):
    """Déclenche `runs` fois le workflow (un run = les jobs apk et tests en parallèle), un après l'autre ; le premier
    est « froid » (caches vides), les suivants « chauds ». La charge du poste est mesurée pendant toute l'attente."""
    racine, commit, branche, workflow = verifier_preconditions(dossier, gh, git)
    resultats = []
    for n in range(1, runs + 1):
        try:
            resultats.append(_un_run(n, racine, workflow, commit, branche, gh, fabrique, dormir, horloge, maintenant,
                                     dire))
        except github_actions.Gh_indisponible as e:
            raise Refus(CODE_GH_INDISPONIBLE, "%s" % e)
    return resultats


# --- rapport -----------------------------------------------------------------------------------------------------

def construire_rapport(projet, commit, branche, local, runs, maintenant):
    gain = {"temps": [], "charge": [], "quota_minutes": sum(r.get("minutes_facturees") or 0 for r in runs)}
    if local:
        for r in runs:
            gain["temps"].append({"etat": r["etat"], "local_s": local["total_s"], "github_s": r["total_s"],
                                  "gain_s": local["total_s"] - r["total_s"]})
            gain["charge"].append({"etat": r["etat"], "cpu_max_local": local["charge"]["cpu"]["max"],
                                   "cpu_max_attente": r["charge_locale"]["cpu"]["max"],
                                   "ram_max_local": local["charge"]["ram"]["max"],
                                   "ram_max_attente": r["charge_locale"]["ram"]["max"]})
    return {"date": maintenant.isoformat(), "projet": projet, "commit": commit, "branche": branche,
            "local": local, "github": runs, "gain": gain, "avertissement": MSG_VALIDITE}


def ecrire_rapport(rapport, dossier, maintenant):
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / (maintenant.strftime("%Y-%m-%d-%H%M%S") + ".json")
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(chemin))
    return str(chemin)


def _s(valeur):
    return "?" if valeur is None else "%d s" % round(valeur)


def _charge_txt(c):
    return "CPU moyen %.0f %% / max %.0f %%, RAM moyenne %.0f %% / max %.0f %%" % (
        c["cpu"]["moyenne"], c["cpu"]["max"], c["ram"]["moyenne"], c["ram"]["max"])


def resumer(rapport):
    """Le résumé lisible, en français."""
    lignes = ["", "=== Essai d'exécution déportée : %s (commit %s, branche %s) ===" % (
        rapport["projet"], str(rapport["commit"])[:8], rapport["branche"])]
    local = rapport.get("local")
    if local:
        par = {c["nom"]: c for c in local["commandes"]}
        lignes.append("Local : apk %s, tests %s, total %s" % (
            _s(par.get("apk", {}).get("duree_s")), _s(par.get("tests", {}).get("duree_s")), _s(local["total_s"])))
        lignes.append("  charge du poste : " + _charge_txt(local["charge"]))
        for c in local["commandes"]:
            if c["code"] != 0:
                lignes.append("  ATTENTION : %s a échoué (code %s)." % (c["nom"], c["code"]))
    for r in rapport.get("github", []):
        jobs = r["jobs"]
        lignes.append("GitHub run %d (%s) : %s" % (r["numero"], r["etat"], r["conclusion"]))
        lignes.append("  attente de démarrage %s, durée totale %s (run vu par GitHub : %s)" % (
            _s(r["attente_demarrage_s"]), _s(r["total_s"]), _s(r["duree_run_s"])))
        lignes.append("  apk %s, tests %s, %d minutes facturées" % (
            _s(jobs.get("apk", {}).get("duree_s")), _s(jobs.get("tests", {}).get("duree_s")),
            r["minutes_facturees"]))
        lignes.append("  charge locale pendant l'attente : " + _charge_txt(r["charge_locale"]))
    gain = rapport["gain"]
    if gain["temps"] or gain["quota_minutes"]:
        lignes.append("Gain :")
        for t, c in zip(gain["temps"], gain["charge"]):
            signe = "gagnés" if t["gain_s"] >= 0 else "perdus"
            lignes.append("  %s : temps %s local contre %s GitHub, soit %s %s ; CPU max %.0f %% local contre "
                          "%.0f %% pendant l'attente ; RAM max %.0f %% contre %.0f %%" % (
                              t["etat"], _s(t["local_s"]), _s(t["github_s"]), _s(abs(t["gain_s"])), signe,
                              c["cpu_max_local"], c["cpu_max_attente"], c["ram_max_local"], c["ram_max_attente"]))
        lignes.append("  quota consommé : %d minutes GitHub Actions" % gain["quota_minutes"])
    lignes.append(MSG_VALIDITE + " (le poste doit être au repos : sinon la mesure locale est faussée.)")
    return "\n".join(lignes)


# --- simulation --------------------------------------------------------------------------------------------------

class _FauxGh:
    Gh_indisponible = github_actions.Gh_indisponible

    def __init__(self):
        self.ids = []

    def gh_pret(self, *a, **k):
        return True, "gh est prêt (simulation)."

    def declencher(self, *a, **k):
        self.ids.append(900 + len(self.ids))

    def execution_du_commit(self, *a, **k):
        if not self.ids:
            return None
        return {"id": self.ids[-1], "statut": "in_progress", "conclusion": None, "duree_s": 0, "url": ""}

    def suivre(self, dossier, run_id, **k):
        chaud = run_id > 900
        return {"id": run_id, "statut": "completed", "conclusion": "success", "duree_s": 260 if chaud else 480,
                "url": "https://github.com/exemple/depot/actions/runs/%d" % run_id}

    def jobs_du_run(self, dossier, run_id, **k):
        chaud = run_id > 900
        fin_apk, fin_tests = ("10:04:10", "10:02:30") if chaud else ("10:07:30", "10:03:20")
        return [{"name": "apk", "conclusion": "success", "debut": "2026-11-17T10:00:10Z",
                 "fin": "2026-11-17T%sZ" % fin_apk},
                {"name": "tests", "conclusion": "success", "debut": "2026-11-17T10:00:12Z",
                 "fin": "2026-11-17T%sZ" % fin_tests}]


class _Pas:
    """Horloge de simulation : chaque lecture avance de 45 s."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 45.0
        return self.t


# --- ligne de commande -------------------------------------------------------------------------------------------

def _analyser(argv):
    p = argparse.ArgumentParser(prog="essai_deport.py", description="Essai de l'exécution déportée : temps et charge.")
    p.add_argument("--dossier", default=os.getcwd())
    p.add_argument("--mode", choices=("local", "github", "les-deux"), default="les-deux")
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--intervalle", type=float, default=5)
    p.add_argument("--forcer", action="store_true", help="lancer même si le poste est déjà chargé")
    p.add_argument("--simuler", action="store_true", help="déroule l'essai avec des faux, sans rien toucher")
    p.add_argument("--confirme", action="store_true", help="obligatoire pour lancer un vrai build ou un vrai run")
    p.add_argument("--rapports", default=None, help="dossier des rapports JSON (défaut ~/MyIAFactory/essais-deport)")
    p.add_argument("--java-home", default=None)
    return p.parse_args(argv)


def _plan(dossier, mode, runs, commandes, windows):
    lignes = ["Plan de l'essai (rien n'est lancé sans --confirme) :", "  projet : %s" % dossier, "  mode : %s" % mode]
    if mode in ("local", "les-deux"):
        lignes.append("  partie locale (en premier) : " + " puis ".join(
            "%s = %s" % (n, " ".join(traduire(c, windows))) for n, c in commandes.items()))
        lignes.append("    refusée si le CPU du poste dépasse %d %% sur %d s (sauf --forcer) ; les démons Gradle sont "
                      "arrêtés ensuite." % (SEUIL_CHARGE_CPU, DUREE_CHARGE_INITIALE_S))
    if mode in ("github", "les-deux"):
        lignes.append("  partie GitHub : %d run(s) du workflow (jobs apk et tests en parallèle) ; le premier est "
                      "froid, les suivants chauds ; consomme des minutes GitHub Actions" % runs)
        lignes.append("    préconditions : gh prêt, commit poussé, aucune modification suivie, workflow dans le commit")
    lignes.append("  " + AVERTISSEMENT)
    lignes.append("Pour lancer pour de vrai : ajoutez --confirme.")
    return "\n".join(lignes)


def main(argv=None, executer=None, gh=None, git=None, mesurer=None, dormir=time.sleep, arreter=None,
         horloge=time.monotonic, maintenant=lambda: datetime.now(timezone.utc)):
    try:
        a = _analyser(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as e:
        return CODE_USAGE if e.code else 0
    if a.runs < 1:
        print("--runs doit valoir au moins 1.", file=sys.stderr)
        return CODE_USAGE
    dossier = str(Path(a.dossier).resolve())
    genre, catalogue = catalogue_du_projet(dossier)
    if any(x not in catalogue for x in ACTIONS) or not all(catalogue[x]["commande"] for x in ACTIONS):
        print("Ce projet n'a pas les actions apk et tests avec une commande (genre : %s) : l'essai vise un projet "
              "Android natif." % genre, file=sys.stderr)
        return CODE_USAGE
    commandes = {x: catalogue[x]["commande"] for x in ACTIONS}
    windows = sys.platform == "win32"
    simuler = a.simuler
    if simuler:
        a.confirme = True
        horloge = _Pas()
        dormir = lambda s: None          # noqa: E731
        maintenant = lambda: datetime(2026, 11, 17, 10, 0, 0, tzinfo=timezone.utc)   # noqa: E731
        _cpu = iter([(22.0, 55.0), (48.0, 61.0), (83.0, 68.0), (91.0, 70.0), (35.0, 60.0)])
        mesurer = lambda: (lambda v: {"cpu": v[0], "memoire": v[1]})(next(_cpu, (6.0, 52.0)))   # noqa: E731
        executer = lambda argv, d: 0     # noqa: E731
        arreter = lambda d: None         # noqa: E731
        gh = _FauxGh()
        git = _git_simule
    if not a.confirme:
        print(_plan(dossier, a.mode, a.runs, commandes, windows))
        return 0

    gh = gh or github_actions
    git = git or deporter._git
    java_home = a.java_home
    if executer is None:
        def executer(argv, d):
            return executer_au_poste(argv, d, java_home)
    if arreter is None:
        def arreter(d):
            arreter_gradle(d, java_home)
    # sans mesure injectée, chaque échantillonneur a sa propre sonde (le CPU se lit par différence entre deux appels)

    def fabrique():
        return Echantillonneur(a.intervalle if not simuler else 3600, mesurer, horloge)

    print(AVERTISSEMENT)
    local, runs = None, []
    code = 0
    try:
        if a.mode in ("github", "les-deux") and not simuler:
            verifier_preconditions(dossier, gh, git)      # avant le build local : inutile de construire pour rien
        if a.mode in ("local", "les-deux"):
            if not simuler:
                moyenne = charge_initiale(mesurer or _sonde_par_defaut(), dormir=dormir)
                if moyenne > SEUIL_CHARGE_CPU and not a.forcer:
                    raise Refus(CODE_CHARGE, "Le poste est déjà chargé (CPU %.0f %% sur %d s, seuil %d %%) : une "
                                "mesure polluée par un autre travail ne vaut rien. Arrêtez ce travail, ou relancez avec "
                                "--forcer." % (moyenne, DUREE_CHARGE_INITIALE_S, SEUIL_CHARGE_CPU))
            print("Partie locale : %s" % ", ".join(commandes))
            local = mesurer_local(dossier, commandes, executer, fabrique, horloge, arreter, windows)
        if a.mode in ("github", "les-deux"):
            runs = mesurer_github(dossier, a.runs, gh, git, fabrique, dormir, horloge, maintenant, print)
    except Refus as r:
        print(r.message)
        return r.code
    if local and any(c["code"] != 0 for c in local["commandes"]):
        code = CODE_ECHEC
    if any(r["conclusion"] != "success" for r in runs):
        code = CODE_ECHEC
    commit = "simulation" if simuler else _commit(dossier, git)
    rapport = construire_rapport(Path(dossier).name, commit, "simulation" if simuler else _branche(dossier, git),
                                 local, runs, maintenant())
    print(resumer(rapport))
    if simuler and a.rapports is None:
        print("(simulation : rapport non enregistré)")
    else:
        print("Rapport : " + ecrire_rapport(rapport, a.rapports or RAPPORTS, maintenant()))
    return code


def _git_simule(argv, cwd):
    """Un dépôt imaginaire en ordre : poussé, propre, workflow présent."""
    a = list(argv)
    if a[:2] == ["rev-parse", "--abbrev-ref"] and a[-1] == "HEAD":
        return 0, "master\n"
    if a[:1] == ["status"] or a[:2] == ["cat-file", "-e"]:
        return 0, ""
    return 0, "0123456789abcdef\n"


def _commit(dossier, git):
    code, sortie = git(["rev-parse", "HEAD"], deport_depot._racine_du_depot(dossier))
    return sortie.strip() if code == 0 else "inconnu"


def _branche(dossier, git):
    code, sortie = git(["rev-parse", "--abbrev-ref", "HEAD"], deport_depot._racine_du_depot(dossier))
    return sortie.strip() if code == 0 else "inconnue"


if __name__ == "__main__":
    sys.exit(main())
