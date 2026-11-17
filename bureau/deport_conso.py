"""Exécution déportée : résultats des actions sur GitHub et consommation de minutes (quota des dépôts privés).

Cœur pur (`cumuler`, `etat_quota`) et coquille d'entrée-sortie (`conso`). Compatible Python 3.9 : pas de `X | Y`, pas
de `match`. Le cache `~/MyIAFactory/deport-conso.json` n'est lu et écrit que par ce module (écriture atomique).
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_OUTILS = str(Path(__file__).resolve().parent.parent / "outils")

DOSSIER = None     # remplacé par les tests : dossier du cache (jamais le vrai `~/MyIAFactory`)
LANCER = None      # remplacé par les tests : compatible `subprocess.run` (jamais le vrai `gh`)
DELAI_S = 300      # `gh` n'est lu qu'une fois toutes les 5 minutes
NB_EXECUTIONS = 100
MAX_JOBS_PAR_LECTURE = 10   # lectures de jobs (une par exécution terminée encore inconnue) par rafraîchissement
NB_DERNIERS = 5
SEUIL_ALERTE = 0.8
NOM_CACHE = "deport-conso.json"
_VERROU = threading.Lock()

MSG_ESTIMATION = "estimation par les durées ; `gh auth refresh -h github.com -s user` pour le quota officiel"


def _github_actions():
    if _OUTILS not in sys.path:
        sys.path.insert(0, _OUTILS)
    import github_actions
    return github_actions


def _milliers(n):
    return "{:,}".format(int(n)).replace(",", " ")


def _instant(texte):
    return datetime.fromisoformat(str(texte).replace("Z", "+00:00"))


def _actions_du_run(ex):
    """Les actions d'une exécution : les noms de ses jobs (le workflow nomme chaque job d'après son action) quand on les
    a lus, sinon le `name` de l'exécution."""
    jobs = [j for j in (ex.get("jobs") or []) if isinstance(j, str) and j]
    if jobs:
        return jobs
    return [str(ex.get("name") or "inconnue")]


def _debut(ex):
    return ex.get("startedAt") or ex["createdAt"]


def _duree_s(ex):
    return (_instant(ex["updatedAt"]) - _instant(_debut(ex))).total_seconds()


def _minutes_facturees(ex):
    """Minutes facturées d'une exécution terminée : sa durée arrondie À LA MINUTE SUPÉRIEURE (GitHub facture chaque job
    à la minute entamée), ou None si elle n'est pas terminée ou sans dates lisibles."""
    if ex.get("status") != "completed":
        return None
    try:
        return max(0, math.ceil(_duree_s(ex) / 60.0 - 1e-9))
    except (KeyError, TypeError, ValueError):
        return None


def _mois_de(ex):
    try:
        return _instant(_debut(ex)).astimezone(timezone.utc).strftime("%Y-%m")
    except (KeyError, TypeError, ValueError):
        return None


def cumuler(executions, mois):
    """`{projet: {action: {"minutes": float, "executions": int}}}` pour le mois `AAAA-MM`.

    Chaque exécution porte son `projet`. Minutes = durée arrondie à la minute supérieure, par exécution (la durée vaut
    les minutes : seuls des exécuteurs `ubuntu` sont utilisés, ratio Linux 1). Une exécution non terminée, sans dates
    lisibles ou d'un autre mois est ignorée. Action : les noms des jobs quand on les a (les minutes de l'exécution se
    répartissent à parts égales entre eux), sinon le `name` de l'exécution."""
    total = {}
    for ex in executions or []:
        if not isinstance(ex, dict) or _mois_de(ex) != mois:
            continue
        minutes = _minutes_facturees(ex)
        if minutes is None:
            continue
        actions = _actions_du_run(ex)
        projet = total.setdefault(str(ex.get("projet", "")), {})
        for action in actions:
            cellule = projet.setdefault(action, {"minutes": 0.0, "executions": 0})
            cellule["minutes"] += minutes / float(len(actions))
            cellule["executions"] += 1
    return total


def etat_quota(minutes_utilisees, quota, public):
    """`{"niveau": "ok"|"alerte"|"depasse", "restantes": int|None, "texte": str}`.
    Dépôt public : illimité, `ok`. Privé sans quota connu (`None`) : `ok`, estimation. Alerte dès 80 %, dépassé dès
    100 % avec la proposition de passer au poste : jamais de bascule automatique."""
    utilisees = max(0.0, float(minutes_utilisees or 0))
    if public:
        return {"niveau": "ok", "restantes": None, "texte": "Dépôt public : minutes illimitées, aucun quota."}
    if quota is None or quota <= 0:
        return {"niveau": "ok", "restantes": None,
                "texte": "%s min utilisées ce mois (%s)." % (_milliers(math.ceil(utilisees)), MSG_ESTIMATION)}
    restantes = max(0, int(quota - utilisees))
    base = "%s / %s min" % (_milliers(math.ceil(utilisees)), _milliers(quota))
    if utilisees >= quota:
        return {"niveau": "depasse", "restantes": 0,
                "texte": "%s : quota dépassé. Proposition : passer au poste, avec votre accord (rien ne bascule "
                         "tout seul)." % base}
    if utilisees >= SEUIL_ALERTE * quota:
        return {"niveau": "alerte", "restantes": restantes,
                "texte": "%s : %d %% du quota, il reste %s min. Pensez à ramener des actions au poste."
                         % (base, int(100 * utilisees / quota), _milliers(restantes))}
    return {"niveau": "ok", "restantes": restantes,
            "texte": "%s utilisées ce mois, il en reste %s." % (base, _milliers(restantes))}


# -- coquille d'entrée-sortie ------------------------------------------------

def _chemin(dossier=None):
    d = dossier if dossier is not None else DOSSIER
    base = Path(d) if d is not None else Path("~/MyIAFactory").expanduser()
    return base / NOM_CACHE


def _lire_cache(chemin):
    try:
        d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _ecrire_cache(chemin, donnees):
    """Écriture atomique (fichier temporaire puis `os.replace`) ; un échec d'écriture n'arrête rien."""
    chemin = Path(chemin)
    tmp = None
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), prefix=".deport-conso-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)
        os.replace(tmp, str(chemin))
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _rafraichir(dossier, ancien, lancer, maintenant):
    """Nouvelle entrée de cache du dépôt ; lève `Gh_indisponible` si la liste des exécutions échoue."""
    ga = _github_actions()
    brutes = ga.executions_recentes(dossier, NB_EXECUTIONS, lancer)
    connus = {e.get("databaseId"): e.get("jobs") for e in (ancien.get("executions") or []) if isinstance(e, dict)}
    lectures = 0
    executions = []
    for v in brutes:
        ex = dict(v)
        jobs = connus.get(v.get("databaseId"))
        if jobs is None and v.get("status") == "completed" and lectures < MAX_JOBS_PAR_LECTURE:
            lectures += 1
            try:
                jobs = [j["name"] for j in ga.jobs_du_run(dossier, v.get("databaseId"), lancer) if j.get("name")]
            except ga.Gh_indisponible:
                jobs = None
        if jobs is not None:
            ex["jobs"] = jobs
        executions.append(ex)
    try:
        public = ga.visibilite(dossier, lancer) == "public"
    except ga.Gh_indisponible:
        public = ancien.get("public")
    quota = None
    if public is False:
        officiel = ga.quota_actions(lancer)
        if officiel is not None:
            quota = {"utilisees": officiel[0], "incluses": officiel[1]}
    return {"lu_a": maintenant, "public": public, "quota": quota, "executions": executions}


def _vue(entree, libelles, projet, mois):
    """L'objet `conso` servi au bureau, calculé depuis une entrée de cache."""
    executions = [dict(e, projet=projet) for e in entree.get("executions") or [] if isinstance(e, dict)]
    cumul = cumuler(executions, mois).get(projet, {})
    par_action = [{"action": a, "libelle": libelles.get(a, a), "minutes": round(c["minutes"], 1),
                   "executions": c["executions"]} for a, c in sorted(cumul.items())]
    estimees = sum(c["minutes"] for c in cumul.values())
    quota = entree.get("quota") if isinstance(entree.get("quota"), dict) else None
    public = entree.get("public") is True
    utilisees = quota["utilisees"] if quota else estimees
    q = etat_quota(utilisees, quota["incluses"] if quota else None, public)
    termines = [e for e in executions if e.get("status") == "completed"]
    termines.sort(key=lambda e: str(e.get("startedAt") or e.get("createdAt") or ""), reverse=True)
    derniers = []
    for e in termines[:NB_DERNIERS]:
        action = _actions_du_run(e)[0]
        try:
            duree = int(_duree_s(e))
        except (KeyError, TypeError, ValueError):
            duree = 0
        derniers.append({"action": action, "libelle": libelles.get(action, action),
                         "conclusion": e.get("conclusion") or None, "duree_s": max(0, duree), "url": e.get("url", "")})
    return {"niveau": q["niveau"], "texte": q["texte"], "mois": mois, "minutes_total": round(utilisees, 1),
            "quota": quota["incluses"] if quota else None, "restantes": q["restantes"], "public": public,
            "par_action": par_action, "derniers": derniers}


def conso(dossier, libelles, lieux, maintenant=None, lancer=None, cache=None):
    """L'objet `conso` du projet, ou `None` si aucune de ses actions n'est au lieu `github` (aucun appel à `gh`).
    `libelles` : `{action: libellé}` ; `lieux` : `{action: lieu}`. Lit `gh` au plus toutes les 5 minutes ; une panne rend
    la dernière valeur du cache, ou « indisponible » sans cache. Ne lève jamais."""
    if not any(lieu == "github" for lieu in (lieux or {}).values()):
        return None
    try:
        maintenant_s = float((maintenant or time.time)())
        mois = datetime.fromtimestamp(maintenant_s, timezone.utc).strftime("%Y-%m")
        chemin = _chemin(cache)
        cle = str(dossier)
        indisponible = False
        with _VERROU:
            donnees = _lire_cache(chemin)
            depots = donnees.get("depots") if isinstance(donnees.get("depots"), dict) else {}
            entree = depots.get(cle) if isinstance(depots.get(cle), dict) else {}
            lu_a = float(entree.get("lu_a", 0)) if entree else 0.0
            if not entree or not 0 <= maintenant_s - lu_a < DELAI_S:
                try:
                    entree = _rafraichir(cle, entree, lancer or LANCER or subprocess.run, maintenant_s)
                    depots[cle] = entree
                    _ecrire_cache(chemin, {"depots": depots})
                except Exception:   # panne de gh ou donnée inattendue : la dernière valeur connue
                    indisponible = True
        if not entree:
            return {"niveau": "ok", "texte": "Consommation indisponible (gh ne répond pas).", "mois": mois,
                    "minutes_total": 0, "quota": None, "restantes": None, "public": False, "par_action": [],
                    "derniers": []}
        vue = _vue(entree, libelles or {}, cle, mois)
        if indisponible:
            vue["texte"] += " (dernière lecture conservée : gh ne répond pas)"
        return vue
    except Exception:
        return None
