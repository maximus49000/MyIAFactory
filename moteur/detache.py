"""Les agents locaux détachés du moteur : relancer le moteur n'interrompt plus leur travail.

Un agent local (`claude -p`) tourne dans un processus à lui, sans fenêtre et sans lien avec le moteur : son entrée est
un fichier, sa sortie `stream-json` va dans un fichier du projet, rien ne passe par un tuyau que l'arrêt du moteur
couperait. Tout est dans `<dossier de la factory>/agents-en-cours/`, par tâche (la première du lot) :
- `<tache>.json` : l'état (`pid`, `debut_processus`, `debut`, `tache`, `taches`, `agent`, `modele`, `lot`, `matiere`,
  `genre` « tache » ou « reponse », `dossier`) ;
- `<tache>.jsonl` : le flux de l'agent ; `<tache>.err` : sa sortie d'erreur ; `<tache>.entree` : son message ;
  `<tache>.consigne.md` : sa consigne ;
- `<tache>.arrete` : posé par le bureau (« Optimiser la charge ») avant d'arrêter l'agent : sa fin n'est pas une panne
  à réessayer, c'est une tâche arrêtée par l'utilisateur (`ArretDemande`) ;
- `<tache>.questions.json` : les questions de l'utilisateur à transmettre à la fin de la tâche (gardées à part : elles
  survivent à l'effacement de l'agent et à une relance).

Le moteur qui démarre retrouve ces agents (`Registre.issue`) : vivant, il l'attend ; mort avec une ligne `result`, il
lit ce résultat ; mort sans résultat, la tâche est reprise comme avant (« nouvel essai »). Un départ demandé pour une
tâche dont l'agent vit encore se rattache à lui au lieu d'en lancer un second.

Le bureau lit les mêmes fichiers, en lecture seule, pour dire depuis quand l'agent travaille et sa dernière action
(`ajouter_au_travail`) : le nom d'un outil et d'un fichier, jamais le contenu d'une commande ni d'un fichier.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from moteur import verrou

DOSSIER = "agents-en-cours"
PAS_S = 2                       # l'attente relit l'agent toutes les 2 s
GRACE_APRES_RESULTAT_S = 10     # un agent qui a rendu sa ligne `result` mais ne se ferme pas : attendu 10 s, pas plus
QUEUE_OCTETS = 65536            # la dernière action se lit dans la fin du flux seulement
MAX_ACTION = 80
OPTIONS_CONSIGNE = ("--append-system-prompt-file", "--system-prompt-file")
ARRET = "agent arrêté par l'utilisateur depuis le bureau"
VARIABLE_TACHE = "MYIAFACTORY_TACHE"    # la clé de l'agent dans l'environnement de ses commandes (voir `outils/campagne`)


class ArretDemande(TimeoutError):
    """L'utilisateur a arrêté l'agent depuis le bureau : la tâche ne repart pas d'elle-même (voir `agents`)."""

    def __init__(self):
        super().__init__(ARRET)


def demander_arret(dossier_factory, cle):
    """Pour le bureau, juste avant d'arrêter l'agent `cle` : sa fin sera lue comme un arrêt voulu. Ne lève jamais."""
    try:
        d = dossier(dossier_factory)
        _preparer(d)
        (d / f"{_nom(cle)}.arrete").write_text("arrêté depuis le bureau\n", encoding="utf-8")
    except OSError:
        pass


def annuler_arret(dossier_factory, cle):
    """L'arrêt n'a pas eu lieu (l'arrêt a échoué) : la marque est retirée. Ne lève jamais."""
    try:
        (dossier(dossier_factory) / f"{_nom(cle)}.arrete").unlink()
    except OSError:
        pass


def dossier(dossier_factory):
    return Path(dossier_factory) / DOSSIER


def _nom(cle):
    return re.sub(r"[^\w.-]", "_", str(cle))


def _preparer(d):
    """Crée le dossier ; il n'entre jamais dans le dépôt du projet (le moteur y fait `git add -A` après chaque tâche)."""
    d.mkdir(parents=True, exist_ok=True)
    ignore = d / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")


# --- Le processus.

def debut_processus(pid):
    """L'heure de création du processus (un nombre opaque), pour ne pas confondre un agent mort avec un autre processus
    qui aurait repris son numéro. `None` si on ne sait pas la lire."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)    # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            t = [ctypes.c_ulonglong() for _ in range(4)]
            if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
                return None
            return int(t[0].value)
        finally:
            k.CloseHandle(h)
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


def processus_vivant(etat):
    """L'agent de cet état tourne encore (le même processus, pas un autre qui aurait repris son numéro)."""
    pid = etat.get("pid") if isinstance(etat, dict) else None
    if not verrou.pid_vivant(pid):
        return False
    attendu = etat.get("debut_processus")
    return attendu is None or debut_processus(pid) in (None, attendu)


def lancer_processus(argv, entree, sortie, erreurs, env, cwd):
    """Lance `argv` détaché du moteur et sans fenêtre : entrée lue dans le fichier `entree`, sorties écrites dans les
    fichiers `sortie` et `erreurs`. Sous Windows, l'agent sort aussi du groupe de tâches du moteur quand le système le
    permet (sinon il y reste : il ne dépend déjà plus d'aucun tuyau du moteur). Rend le `Popen`."""
    base = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    essais = [base | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0), base] if sys.platform == "win32" else [base]
    for n, drapeaux in enumerate(essais):
        with open(entree, "rb") as fin, open(sortie, "wb") as fout, open(erreurs, "wb") as ferr:
            try:
                return subprocess.Popen(argv, stdin=fin, stdout=fout, stderr=ferr, env=env, cwd=cwd,
                                        creationflags=drapeaux, close_fds=True, start_new_session=os.name != "nt")
            except OSError:
                if n + 1 == len(essais):
                    raise


def tuer_processus(pid):
    """Arrête l'agent et ce qu'il a lancé (délai dépassé)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import signal
            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass


# --- Le flux.

def _lignes(chemin, queue=None):
    try:
        with open(chemin, "rb") as f:
            if queue:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - queue))
            brut = f.read()
    except OSError:
        return []
    rendu = []
    for ligne in brut.decode("utf-8", "replace").splitlines():
        try:
            d = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(d, dict):
            rendu.append(d)
    return rendu


def a_un_resultat(chemin):
    return any(d.get("type") == "result" for d in _lignes(chemin, QUEUE_OCTETS))


def _fichier_court(chemin, dossier_projet):
    if not isinstance(chemin, str) or not chemin.strip():
        return "un fichier"
    p = Path(chemin.replace("\\", "/"))
    if dossier_projet:
        try:
            p = (p if p.is_absolute() else Path(dossier_projet) / p).resolve().relative_to(Path(dossier_projet).resolve())
        except (ValueError, OSError):
            p = Path(p.name)
    elif p.is_absolute():
        p = Path(p.name)
    texte = p.as_posix()
    return texte if len(texte) <= 60 else "…" + texte[-59:]


VERBES_FICHIER = {"Edit": "modifie", "MultiEdit": "modifie", "NotebookEdit": "modifie", "Write": "écrit", "Read": "lit"}
VERBES = {"Grep": "cherche dans les fichiers", "Glob": "cherche dans les fichiers", "WebFetch": "consulte le web",
          "WebSearch": "consulte le web", "TodoWrite": "organise son travail", "Task": "délègue une recherche",
          "Agent": "délègue une recherche", "Skill": "suit une méthode"}


def derniere_action(lignes, dossier_projet):
    """La dernière action de l'agent dans son flux, dite courte : « modifie scenes/combat.gd », « lance python »,
    « rédige ». Jamais le contenu d'une commande, d'un fichier ou d'un message. `None` s'il n'a encore rien fait."""
    for d in reversed(lignes):
        if d.get("type") != "assistant":
            continue
        contenu = (d.get("message") or {}).get("content")
        if not isinstance(contenu, list):
            continue
        for bloc in reversed(contenu):
            if not isinstance(bloc, dict):
                continue
            if bloc.get("type") == "tool_use":
                nom, entree = str(bloc.get("name") or ""), bloc.get("input") or {}
                if nom in VERBES_FICHIER:
                    chemin = entree.get("file_path") or entree.get("notebook_path") or entree.get("path")
                    return f"{VERBES_FICHIER[nom]} {_fichier_court(chemin, dossier_projet)}"[:MAX_ACTION]
                if nom in ("Bash", "PowerShell"):
                    # le programme qui tourne : le dernier d'une chaîne « a && b && c », avant tout « | tail » de mise
                    # en forme, jamais le « cd dossier && » du début (essais réels : « lance cd », « lance ls » pour
                    # « cd … && ls … && grep … && python tests »)
                    etapes = [e.split("|", 1)[0].split() for e in re.split(r"&&|\|\||;", str(entree.get("command") or ""))]
                    utiles = [m for m in etapes if m and m[0].lower() not in ("cd", "set-location", "pushd", "export")]
                    mot = utiles[-1][0] if utiles else ""
                    mot = re.sub(r"[^\w.-]", "", Path(mot.strip("\"'").replace("\\", "/")).name)[:20]
                    return f"lance {mot}" if mot else "lance une commande"
                if nom in VERBES:
                    return VERBES[nom]
                outil = re.sub(r"[^\w.-]", "", nom)[:30]
                return f"utilise {outil or 'un outil'}"
            if bloc.get("type") == "text":
                return "rédige"
    return None


def lire_avancement(chemin):
    """La liste d'avancement que l'agent écrit lui-même (`<tâche>.avancement.json`) : `{"points": [{"texte", "fait"}],
    "en_cours": texte | None, "maj": heure ISO du fichier}`. `None` si elle manque, est illisible ou mal formée : la
    fiche se rabat alors sur la phase déduite du flux."""
    try:
        if Path(chemin).stat().st_size > MAX_AVANCEMENT_OCTETS:     # une liste de quelques lignes : jamais un gros fichier
            return None
        brut = json.loads(Path(chemin).read_text(encoding="utf-8"))
        maj = Path(chemin).stat().st_mtime
    except (OSError, ValueError):
        return None
    points = brut.get("points") if isinstance(brut, dict) else None
    if not isinstance(points, list):
        return None
    rendu = [{"texte": str(p["texte"])[:120], "fait": p.get("fait") is True}
             for p in points[:MAX_POINTS] if isinstance(p, dict) and isinstance(p.get("texte"), str)]
    en_cours = brut.get("en_cours")
    return {"points": rendu, "en_cours": en_cours[:120] if isinstance(en_cours, str) and en_cours.strip() else None,
            "maj": _iso(maj)}


DUREES = "durees-agents.jsonl"      # dans le dossier de la factory : la durée réelle de chaque agent, notée à sa fin
MAX_DUREES_LUES = 500
MAX_AVANCEMENT_OCTETS = 65536
MAX_POINTS = 30
def noter_duree(dossier_factory, etat, t_fin=None):
    """Note la durée réelle d'un agent fini (de son démarrage à maintenant) pour chaque tâche qu'il portait : la source du
    « temps restant » de la fiche (les dates `debut`/`fin` du suivi ne mesurent pas le travail). Ne lève jamais."""
    try:
        debut = etat.get("debut")
        if not isinstance(debut, (int, float)) or isinstance(debut, bool):
            return
        duree = int((time.time() if t_fin is None else t_fin) - debut)
        if duree < 0:
            return
        lignes = "".join(json.dumps({"tache": tid, "duree_s": duree, "t": _iso(time.time() if t_fin is None else t_fin)})
                         + "\n" for tid in etat.get("taches") or [etat.get("tache")] if isinstance(tid, str))
        if lignes:
            with open(Path(dossier_factory) / DUREES, "a", encoding="utf-8") as f:
                f.write(lignes)
    except Exception:
        pass


def lire_durees(dossier_factory):
    """Les dernières durées notées : `[{"tache", "duree_s", "t"}]`, vide si le fichier manque ; les lignes abîmées sont
    ignorées."""
    try:
        brut = (Path(dossier_factory) / DUREES).read_text(encoding="utf-8").splitlines()[-MAX_DUREES_LUES:]
    except OSError:
        return []
    rendu = []
    for ligne in brut:
        try:
            d = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("tache"), str) and isinstance(d.get("duree_s"), (int, float)):
            rendu.append(d)
    return rendu


_COMPILATION = ("gradle", "assemble", "compile", "build")
_TESTS = re.compile(r"\btests?\b|pytest|unittest|connectedandroidtest|\badb\b|\bemulator\b")


def phase_du_flux(lignes):
    """Ce que l'agent est en train de faire, d'après sa dernière action : « lecture », « modification », « compilation »,
    « tests » ou « autre » ; `None` sans action. Jamais le contenu d'une commande."""
    for d in reversed(lignes):
        if d.get("type") != "assistant":
            continue
        contenu = (d.get("message") or {}).get("content")
        if not isinstance(contenu, list):
            continue
        for bloc in reversed(contenu):
            if not isinstance(bloc, dict) or bloc.get("type") != "tool_use":
                continue
            nom = bloc.get("name")
            if nom in ("Read", "Grep", "Glob"):
                return "lecture"
            if nom in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
                return "modification"
            if nom in ("Bash", "PowerShell"):
                commande = str((bloc.get("input") or {}).get("command") or "").lower()
                if _TESTS.search(commande):
                    return "tests"
                if any(m in commande for m in _COMPILATION):
                    return "compilation"
            return "autre"
    return None


def _iso(t):
    try:
        return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def moment_de_la_derniere_action(lignes):
    """L'heure ISO locale de la dernière ligne qui n'est pas un signe de vie (`tool_progress`), d'après son
    `timestamp` ; `None` si aucune n'en porte."""
    for d in reversed(lignes):
        if d.get("type") == "tool_progress" or not isinstance(d.get("timestamp"), str):
            continue
        try:
            return datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).astimezone().isoformat(
                timespec="seconds")
        except ValueError:
            continue
    return None


_CONSO = {}     # chemin du flux -> (octets lus, {id de message: (modèle, usage)}) : le flux n'est relu que pour la suite


def conso_en_cours(flux):
    """Ce que l'agent a consommé jusqu'ici, d'après les messages de son flux (un message compté une fois, sa dernière
    valeur) : `[{modele, entree, sortie, cache_lecture, cache_ecriture}]`, un par modèle, au format des usages du
    relevé. Le coût d'une tâche en cours se calcule ainsi avant son rapport."""
    cle = str(flux)
    lu, messages = _CONSO.get(cle, (0, {}))
    try:
        taille = flux.stat().st_size
        if taille < lu:                       # un nouveau flux (essai suivant) : on repart de zéro
            lu, messages = 0, {}
        with open(flux, "rb") as f:
            f.seek(lu)
            bloc = f.read()
    except OSError:
        return []
    fin = bloc.rfind(b"\n")
    if fin >= 0:
        for brute in bloc[:fin].split(b"\n"):
            try:
                d = json.loads(brute)
            except ValueError:
                continue
            m = d.get("message") if isinstance(d, dict) and d.get("type") == "assistant" else None
            u = m.get("usage") if isinstance(m, dict) else None
            if isinstance(u, dict) and isinstance(m.get("id"), str) and str(m.get("model", "")).startswith("claude"):
                messages[m["id"]] = (m["model"], u)
        lu += fin + 1
    _CONSO[cle] = (lu, messages)
    par_modele = {}
    for modele, u in messages.values():
        c = par_modele.setdefault(modele, {"modele": modele, "entree": 0, "sortie": 0, "cache_lecture": 0,
                                          "cache_ecriture": 0})
        for nom, champ in (("entree", "input_tokens"), ("sortie", "output_tokens"),
                           ("cache_lecture", "cache_read_input_tokens"), ("cache_ecriture", "cache_creation_input_tokens")):
            v = u.get(champ)
            c[nom] += v if isinstance(v, int) and not isinstance(v, bool) else 0
    return list(par_modele.values())


FINS_DE_LISTE = ("termine", "terminé", "terminee", "terminée", "fini", "finie", "fait", "faite", "done")


def liste_finie(liste):
    """Vrai quand la liste d'avancement d'une tâche dit qu'elle est finie : `en_cours` vaut « termine » (ou proche), ou
    tous ses points sont cochés sans rien d'autre en cours."""
    if not isinstance(liste, dict):
        return False
    en_cours = liste.get("en_cours")
    if isinstance(en_cours, str) and en_cours.strip().lower().rstrip(".!") in FINS_DE_LISTE:
        return True
    points = liste.get("points") or []
    return bool(points) and not en_cours and all(p.get("fait") for p in points)


def tache_du_lot_en_cours(ids, listes):
    """La tâche d'un lot que sa session fait maintenant : la première, dans l'ordre du lot, dont la liste ne dit pas
    qu'elle est finie ; toutes finies : la dernière (l'agent rédige son compte rendu)."""
    return next((tid for tid in ids if not liste_finie(listes.get(tid))), ids[-1])


def ajouter_au_travail(taches, dossier_factory, vivant=processus_vivant, attentes_tests=None):
    """Pour le bureau : chaque tâche dont l'agent local tourne reçoit `travail` = `{depuis, agent, action, action_t,
    vie_t, conso}` (heures ISO ; `vie_t` : la dernière ligne écrite, signes de vie d'une commande en cours compris ;
    `conso` : voir `conso_en_cours` ; `phase`, `avancement` : voir `phase_du_flux`, `lire_avancement`). Un agent
    mort dont le résultat n'est pas encore lu donne `agent_termine` = `{t}` à la place. Lecture seule ; un agent qui ne tourne plus n'est pas montré. Ne lève jamais.
    Dans un lot, seule la tâche que la session fait (`tache_du_lot_en_cours`) reçoit `travail` (avec `lot` : `{rang,
    total}`), est dite active et porte l'agent ; les autres reçoivent `dans_le_lot` = `{etat: "faite" | "a_venir",
    agent, courante, rang, total, avancement}`. `attentes_tests` : `{clé de l'agent: {depuis, motif}}`, les agents qui
    attendent le verrou de tests du poste (`outils/campagne.en_attente`) ; leur tâche en cours reçoit `attente_tests`."""
    try:
        d = dossier(dossier_factory)
        if not d.is_dir():
            return taches
        travail, termines, dans_le_lot = {}, {}, {}
        for f in sorted(d.glob("*.json")):
            if f.name.endswith((".questions.json", ".avancement.json")):
                continue
            try:
                etat = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(etat, dict) or etat.get("genre") == "reponse":
                continue
            if not vivant(etat):
                flux = f.with_suffix(".jsonl")
                if a_un_resultat(flux):
                    # l'agent a fini et rendu son résultat que le moteur n'a pas encore lu : dit à part
                    try:
                        fini = _iso(flux.stat().st_mtime)
                    except OSError:
                        fini = None
                    for tid in etat.get("taches") or [etat.get("tache")]:
                        if isinstance(tid, str) and fini:
                            termines[tid] = {"t": fini}
                continue
            debut = etat.get("debut")
            if not isinstance(debut, (int, float)) or isinstance(debut, bool):
                continue
            flux = f.with_suffix(".jsonl")
            lignes = _lignes(flux, QUEUE_OCTETS)
            action = derniere_action(lignes, etat.get("dossier"))
            try:
                vie_t = _iso(flux.stat().st_mtime)      # la dernière ligne écrite, signes de vie compris
            except OSError:
                vie_t = None
            # l'heure de la dernière vraie action (pas d'un signe de vie) ; à défaut, la dernière ligne écrite
            action_t = (moment_de_la_derniere_action(lignes) or vie_t) if action else None
            if _iso(debut) is None:
                continue
            info = {"depuis": _iso(debut), "agent": etat.get("agent"), "action": action, "action_t": action_t,
                    "vie_t": vie_t, "conso": conso_en_cours(flux), "phase": phase_du_flux(lignes),
                    "avancement": lire_avancement(f.with_suffix(".avancement.json"))}
            if (attentes_tests or {}).get(f.stem):     # l'agent attend le verrou de tests du poste
                info["attente_tests"] = dict(attentes_tests[f.stem])
            ids = [tid for tid in etat.get("taches") or [etat.get("tache")] if isinstance(tid, str)]
            listes = {tid: lire_avancement(f.parent / f"{tid}.avancement.json") for tid in ids}
            if len(ids) < 2:
                for tid in ids:
                    travail[tid] = {**info, "avancement": listes[tid] or info["avancement"]}
                continue
            # Un lot : une seule session fait ses tâches l'une après l'autre. Seule celle qu'elle fait reçoit `travail`
            # (essai réel du 2026-11-18 : t68 finie disait « En cours : termine » et t69, que Hugo faisait, restait
            # sans agent ni activité : l'utilisateur croyait l'agent arrêté).
            courante = tache_du_lot_en_cours(ids, listes)
            for rang, tid in enumerate(ids, 1):
                if tid == courante:
                    travail[tid] = {**info, "avancement": listes[tid], "lot": {"rang": rang, "total": len(ids)}}
                else:
                    faite = ids.index(tid) < ids.index(courante)
                    a = listes[tid]
                    dans_le_lot[tid] = {"etat": "faite" if faite else "a_venir", "agent": etat.get("agent"),
                                        "courante": courante, "rang": rang, "total": len(ids),
                                        "avancement": dict(a, en_cours=None) if a and faite else a}
        for t in taches:
            if not isinstance(t, dict):
                continue
            if t.get("id") in travail:
                t["travail"] = dict(travail[t["id"]])
                if t["travail"].get("lot"):     # la tâche que la session du lot fait : active, avec son agent
                    t["active"] = True
                    t["agent"] = t.get("agent") or t["travail"].get("agent")
            elif t.get("id") in dans_le_lot:
                t["dans_le_lot"] = dict(dans_le_lot[t["id"]])
                t["agent"] = t.get("agent") or t["dans_le_lot"].get("agent")
                if t["dans_le_lot"]["etat"] == "faite":
                    t["active"] = False      # finie : la session est passée à la suivante du lot
            elif t.get("id") in termines:
                t["agent_termine"] = dict(termines[t["id"]])
    except Exception:     # le bureau ne tombe jamais pour une aide
        pass
    return taches


# --- Les questions de l'utilisateur, transmises à la fin de la tâche.

def _chemin_questions(dossier_factory, tache):
    return dossier(dossier_factory) / f"{_nom(tache)}.questions.json"


def _questions_et_demandes(dossier_factory, tache):
    """`[{texte, demande?}]` : une question est un texte (ancien format) ou `{texte, demande}` (la demande du bureau
    d'où elle vient, pour suivre le retour jusqu'à la réponse de l'agent)."""
    try:
        q = json.loads(_chemin_questions(dossier_factory, tache).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    sortie = []
    for x in q if isinstance(q, list) else []:
        if isinstance(x, str):
            sortie.append({"texte": x})
        elif isinstance(x, dict) and isinstance(x.get("texte"), str):
            sortie.append({"texte": x["texte"], **({"demande": x["demande"]} if isinstance(x.get("demande"), str)
                                                   else {})})
    return sortie


def questions(dossier_factory, tache):
    return [x["texte"] for x in _questions_et_demandes(dossier_factory, tache)]


def ajouter_question(dossier_factory, tache, texte, demande=None):
    chemin = _chemin_questions(dossier_factory, tache)
    _preparer(chemin.parent)
    _ecrire(chemin, _questions_et_demandes(dossier_factory, tache)
            + [{"texte": str(texte), **({"demande": demande} if demande else {})}])


def prendre_questions_et_demandes(dossier_factory, tache):
    """`(questions, demandes)` en attente pour la tâche, retirées du fichier."""
    q = _questions_et_demandes(dossier_factory, tache)
    try:
        _chemin_questions(dossier_factory, tache).unlink()
    except OSError:
        pass
    return [x["texte"] for x in q], [x["demande"] for x in q if x.get("demande")]


def prendre_questions(dossier_factory, tache):
    """Les questions en attente pour la tâche, retirées du fichier."""
    return prendre_questions_et_demandes(dossier_factory, tache)[0]


def _ecrire(chemin, objet):
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(objet, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, chemin)


# --- Le registre d'un projet.

def _nouvelles_actions(flux, lu):
    """`(nouvelle position, vrai si une ligne complète écrite depuis `lu` est une vraie action)` : tout sauf les signes
    de vie (`tool_progress`). Lit seulement la suite du fichier."""
    try:
        with open(flux, "rb") as f:
            f.seek(lu)
            bloc = f.read()
    except OSError:
        return lu, False
    fin = bloc.rfind(b"\n")
    if fin < 0:
        return lu, False
    lignes = [x for x in bloc[:fin].split(b"\n") if x.strip()]
    return lu + fin + 1, any(b'"tool_progress"' not in x for x in lignes)


class Registre:
    """Les agents détachés d'un projet. `lancer`, `vivant`, `tuer`, `dormir`, `horloge` sont là pour les essais (un faux
    `claude`) ; `noter_abonnement` : l'instantané d'abonnement lu dans le flux est gardé (jamais pendant les essais)."""

    def __init__(self, dossier_factory, *, lancer=lancer_processus, vivant=processus_vivant, tuer=tuer_processus,
                 dormir=time.sleep, horloge=time.time, noter_abonnement=True, pas_s=PAS_S):
        self.dossier = dossier(dossier_factory)
        self.lancer, self.vivant, self.tuer = lancer, vivant, tuer
        self.dormir, self.horloge, self.pas_s = dormir, horloge, pas_s
        self.noter_abonnement = noter_abonnement

    def chemin(self, cle, suffixe):
        return self.dossier / f"{_nom(cle)}{suffixe}"

    def lire_etat(self, cle):
        try:
            etat = json.loads(self.chemin(cle, ".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return etat if isinstance(etat, dict) else None

    def entrees(self):
        """Les états de tous les agents connus (`cle` ajoutée), par nom de fichier."""
        if not self.dossier.is_dir():
            return []
        rendu = []
        for f in sorted(self.dossier.glob("*.json")):
            if f.name.endswith((".questions.json", ".avancement.json")):
                continue
            cle = f.name[:-len(".json")]
            etat = self.lire_etat(cle)
            if etat is not None:
                rendu.append({**etat, "cle": cle})
        return rendu

    def issue(self, cle):
        """« vivant », « resultat » (mort, sa ligne `result` est là), « mort » (sans résultat) ou `None` (inconnu)."""
        etat = self.lire_etat(cle)
        if etat is None:
            return None
        if self.vivant(etat):
            return "vivant"
        return "resultat" if a_un_resultat(self.chemin(cle, ".jsonl")) else "mort"

    def effacer(self, cle):
        """Oublie l'agent (ses questions restent) et la liste d'avancement de chaque tâche qu'il portait."""
        etat = self.lire_etat(cle) or {}
        for tid in etat.get("taches") or []:
            if isinstance(tid, str):
                try:
                    self.chemin(tid, ".avancement.json").unlink()
                except OSError:
                    pass
        for suffixe in (".json", ".jsonl", ".err", ".entree", ".consigne.md", ".arrete", ".avancement.json"):
            try:
                self.chemin(cle, suffixe).unlink()
            except OSError:
                pass

    def executeur(self, cle, infos, *, rattacher=False):
        """Un exécuteur pour `appel.appeler(executer=…)` : `(argv, entree, env, cwd, delai_s) -> (code, sortie)`.
        Un agent de cette tâche qui vit encore : on l'attend au lieu d'en lancer un autre. `rattacher` (le moteur
        redémarre) : au premier appel, un agent mort dont le résultat est là est lu tel quel ; les essais suivants
        (rapport illisible) lancent un nouvel agent."""
        premier = [rattacher]

        def executer(argv, entree, env, cwd, delai_s):
            rattache, premier[0] = premier[0], False
            issue = self.issue(cle)
            if issue == "mort" and self._prendre_arret(cle):    # arrêté depuis le bureau avant que le moteur le voie
                raise ArretDemande()
            if issue == "vivant" or (rattache and issue == "resultat"):
                return self.attendre(cle, delai_s)
            return self.attendre(cle, delai_s, self._lancer(cle, infos, argv, entree, env, cwd))

        executer.noter_abonnement = self.noter_abonnement
        return executer

    def arret_demande(self, cle):
        """Vrai si le bureau a demandé l'arrêt de cet agent (la marque reste)."""
        return self.chemin(cle, ".arrete").is_file()

    def _prendre_arret(self, cle):
        """Vrai (une seule fois) si le bureau a demandé l'arrêt de cet agent."""
        try:
            self.chemin(cle, ".arrete").unlink()
            return True
        except OSError:
            return False

    def _lancer(self, cle, infos, argv, entree, env, cwd):
        self.effacer(cle)        # les restes d'un essai précédent
        _preparer(self.dossier)
        argv = list(argv)
        for i, a in enumerate(argv[:-1]):
            if a in OPTIONS_CONSIGNE:    # la consigne vivait dans un dossier temporaire du moteur : copiée ici
                copie = self.chemin(cle, ".consigne.md")
                shutil.copyfile(argv[i + 1], copie)
                argv[i + 1] = str(copie)
        self.chemin(cle, ".entree").write_bytes(entree or b"")
        # la clé de l'agent, héritée par ses commandes : une campagne de tests qui attend son tour dit pour qui (le bureau)
        env = {**(os.environ if env is None else env), VARIABLE_TACHE: cle}
        p = self.lancer(argv, str(self.chemin(cle, ".entree")), str(self.chemin(cle, ".jsonl")),
                        str(self.chemin(cle, ".err")), env, cwd)
        etat = {"genre": "tache", **infos, "cle": cle, "pid": p.pid, "debut_processus": debut_processus(p.pid),
                "debut": self.horloge(), "dossier": str(cwd) if cwd else None}
        etat.setdefault("tache", cle)
        _ecrire(self.chemin(cle, ".json"), etat)
        return p

    def attendre(self, cle, delai_s, processus=None):
        """Attend la fin de l'agent (ou sa ligne `result`) ; bloqué (aucune action réelle depuis `delai_s`), l'arrête
        et lève `TimeoutError`. Rend `(code, sortie)` : le code n'est connu que d'un agent lancé par ce moteur ; sinon 0 si la
        ligne `result` est là, 1 sinon."""
        etat = self.lire_etat(cle) or {}
        flux, vu_resultat = self.chemin(cle, ".jsonl"), None
        # L'agent n'est arrêté que s'il est bloqué : aucune action réelle (commande lancée, résultat reçu, texte…)
        # depuis `delai_s`. Les signes de vie que `claude` écrit pendant une commande (`tool_progress`) ne comptent pas :
        # une suite de tests de 10 min n'est pas un blocage, une commande figée au-delà de `delai_s` en est un. Essai
        # réel : une tâche avec deux suites de tests de 10 min était tuée à 30 min depuis son début et relancée de zéro.
        lu, actif = 0, self.horloge()
        while True:
            fini = processus.poll() is not None if processus is not None else not self.vivant(etat)
            if fini:
                break
            if a_un_resultat(flux):
                vu_resultat = vu_resultat if vu_resultat is not None else self.horloge()
                if self.horloge() - vu_resultat >= GRACE_APRES_RESULTAT_S:
                    break
            lu, agi = _nouvelles_actions(flux, lu)
            if agi:
                actif = self.horloge()
            if self.horloge() - actif > delai_s:
                self.tuer(etat.get("pid") if processus is None else processus.pid)
                if processus is not None:
                    try:
                        processus.wait(timeout=10)
                    except (subprocess.TimeoutExpired, OSError):
                        pass
                raise TimeoutError(f"agent bloqué : aucune action depuis {delai_s} s")
            self.dormir(self.pas_s)
        if not a_un_resultat(flux) and self._prendre_arret(cle):
            raise ArretDemande()
        try:
            sortie = flux.read_bytes()
        except OSError:
            sortie = b""
        if a_un_resultat(flux):
            noter_duree(self.dossier.parent, etat)
        code = getattr(processus, "returncode", None) if processus is not None else None
        if code is None or (code != 0 and a_un_resultat(flux)):
            code = 0 if a_un_resultat(flux) else 1
        if code != 0 and not sortie.strip():
            try:
                sortie = self.chemin(cle, ".err").read_bytes()
            except OSError:
                pass
        return code, sortie
