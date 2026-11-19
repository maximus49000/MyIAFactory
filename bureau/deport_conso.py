"""Exécution déportée : résultats des actions sur GitHub et consommation de minutes (quota des dépôts privés).

Cœur pur (`cumuler`, `etat_quota`) et coquille d'entrée-sortie (`conso`). Compatible Python 3.9 : pas de `X | Y`, pas
de `match`. Le cache `~/MyIAFactory/deport-conso.json` n'est lu et écrit que par ce module (écriture atomique).

`conso` ne lit jamais `gh` dans le fil de l'appelant : elle rend tout de suite la dernière valeur du cache (ou « lecture
en cours » à vide) et lance, si la dernière tentative (réussie ou non) date de plus de 5 minutes, un rafraîchissement
dans un fil daemon, un seul à la fois par dépôt. Aucun verrou n'est tenu pendant les appels à `gh`.
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
DELAI_S = 300      # `gh` n'est relancé qu'une fois toutes les 5 minutes, après un succès comme après un échec
NB_EXECUTIONS = 100
MAX_JOBS_PAR_LECTURE = 10   # lectures de jobs (une par exécution terminée encore inconnue) par rafraîchissement
NB_DERNIERS = 8             # lignes de « derniers résultats » (une par job d'action)
SEUIL_ALERTE = 0.8
NOM_CACHE = "deport-conso.json"
_VERROU = threading.Lock()      # protège le cache et `_EN_COURS` ; jamais tenu pendant un appel à gh
_EN_COURS = {}                  # dépôt -> fil de rafraîchissement en cours
ARRET = threading.Event()       # levé par `arreter` : les rafraîchissements s'interrompent entre deux appels à gh

MSG_ESTIMATION = "estimation par les durées ; `gh auth refresh -h github.com -s user` pour le quota officiel"
MSG_BASSE = " (estimation basse : le détail des jobs manque pour certaines exécutions, durée de l'exécution comptée)"


class _Arret(Exception):
    pass


def _github_actions():
    if _OUTILS not in sys.path:
        sys.path.insert(0, _OUTILS)
    import github_actions
    return github_actions


def _milliers(n):
    return "{:,}".format(int(n)).replace(",", " ")


def _instant(texte):
    return datetime.fromisoformat(str(texte).replace("Z", "+00:00"))


def _secondes(debut, fin):
    return (_instant(fin) - _instant(debut)).total_seconds()


def _minutes(secondes):
    """Minute entamée = minute facturée : arrondi à la minute supérieure."""
    return max(0, math.ceil(secondes / 60.0 - 1e-9))


def _lignes(ex):
    """Les lignes facturables d'une exécution terminée : `[(action, minutes, duree_s, conclusion, estimation)]`.
    Une ligne par job de dates lisibles (action = nom du job, `ceil` par job) ; sans aucun job daté, une ligne pour
    toute l'exécution (action = son `name`, `ceil` sur sa durée, `estimation` vrai : durée murale, estimation basse)."""
    if ex.get("status") != "completed":
        return []
    lignes = []
    for j in ex.get("jobs") or []:
        if not isinstance(j, dict) or not j.get("name"):
            continue
        try:
            d = _secondes(j["debut"], j["fin"])
        except (KeyError, TypeError, ValueError):
            continue
        lignes.append((str(j["name"]), _minutes(d), max(0, int(d)), j.get("conclusion") or None, False))
    if lignes:
        return lignes
    try:
        d = _secondes(ex.get("startedAt") or ex["createdAt"], ex["updatedAt"])
    except (KeyError, TypeError, ValueError):
        return []
    return [(str(ex.get("name") or "inconnue"), _minutes(d), max(0, int(d)), ex.get("conclusion") or None, True)]


def _mois_de(ex):
    try:
        return _instant(ex.get("startedAt") or ex["createdAt"]).astimezone(timezone.utc).strftime("%Y-%m")
    except (KeyError, TypeError, ValueError):
        return None


def cumuler(executions, mois):
    """`{projet: {action: {"minutes": float, "executions": int}}}` pour le mois `AAAA-MM`.

    Chaque exécution porte son `projet`. GitHub facture chaque JOB à la minute entamée : une action = un job (son nom),
    ses minutes = sa durée arrondie à la minute supérieure (ratio Linux 1 : seuls des exécuteurs `ubuntu` sont utilisés,
    donc durée du job = minutes), et les jobs parallèles s'additionnent. Les jobs sans dates (ignorés, ex. sautés) ne
    comptent pas. Sans aucun job daté, repli sur la durée de l'exécution, arrondie, nommée par le `name` de l'exécution
    (estimation basse). Une exécution non terminée ou d'un autre mois est ignorée."""
    total = {}
    for ex in executions or []:
        if not isinstance(ex, dict) or _mois_de(ex) != mois:
            continue
        for action, minutes, _d, _c, _e in _lignes(ex):
            cellule = total.setdefault(str(ex.get("projet", "")), {}).setdefault(
                action, {"minutes": 0.0, "executions": 0})
            cellule["minutes"] += float(minutes)
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
        if ARRET.is_set():
            raise _Arret()
        ex = dict(v)
        jobs = connus.get(v.get("databaseId"))
        if not isinstance(jobs, list):
            jobs = None
        if jobs is None and v.get("status") == "completed" and lectures < MAX_JOBS_PAR_LECTURE:
            lectures += 1
            try:
                jobs = ga.jobs_du_run(dossier, v.get("databaseId"), lancer)
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
    texte = q["texte"]
    if any(ligne[4] for e in executions if _mois_de(e) == mois for ligne in _lignes(e)):
        texte += MSG_BASSE
    termines = [e for e in executions if e.get("status") == "completed"]
    termines.sort(key=lambda e: str(e.get("startedAt") or e.get("createdAt") or ""), reverse=True)
    derniers = []
    for e in termines:
        for action, _m, duree, conclusion, _est in _lignes(e):
            derniers.append({"action": action, "libelle": libelles.get(action, action), "conclusion": conclusion,
                             "duree_s": duree, "url": e.get("url", "")})
    return {"niveau": q["niveau"], "texte": texte, "mois": mois, "minutes_total": round(utilisees, 1),
            "quota": quota["incluses"] if quota else None, "restantes": q["restantes"], "public": public,
            "par_action": par_action, "derniers": derniers[:NB_DERNIERS]}


def _vide(texte, mois):
    return {"niveau": "ok", "texte": texte, "mois": mois, "minutes_total": 0, "quota": None, "restantes": None,
            "public": False, "par_action": [], "derniers": []}


def _travail(cle, chemin, ancien, lancer, maintenant):
    """Le rafraîchissement, dans son fil : gh sans aucun verrou, puis une écriture courte du cache."""
    try:
        try:
            entree = _rafraichir(cle, ancien, lancer, maintenant)
        except _Arret:
            return
        except Exception:   # panne de gh ou donnée inattendue : on garde l'ancienne valeur et on note l'échec
            entree = None
        with _VERROU:
            donnees = _lire_cache(chemin)
            depots = donnees.get("depots") if isinstance(donnees.get("depots"), dict) else {}
            if entree is not None:
                depots[cle] = entree
            else:
                depots[cle] = dict(depots.get(cle) or {}, echec_a=maintenant)
            _ecrire_cache(chemin, {"depots": depots})
    finally:
        with _VERROU:
            _EN_COURS.pop(cle, None)


def attendre(delai_s=10):
    """Attend la fin des rafraîchissements en cours (tests, arrêt propre)."""
    with _VERROU:
        fils = list(_EN_COURS.values())
    for f in fils:
        f.join(delai_s)


def arreter(delai_s=10):
    """Interrompt les rafraîchissements en cours et attend leur fin."""
    ARRET.set()
    try:
        attendre(delai_s)
    finally:
        ARRET.clear()


def niveau_en_cache(dossiers, cache=None, maintenant=None):
    """Le niveau du quota (`ok`, `alerte`, `depasse`) d'après la dernière lecture en cache du premier de `dossiers`
    (les clés possibles du projet : son dossier, son `.factory`) qui y figure ; `None` si aucun n'y est. Lecture seule,
    sans `gh` ; ne lève jamais (pour `lancer.py deporter`, avant de déclencher une exécution)."""
    try:
        maintenant_s = float((maintenant or time.time)())
        mois = datetime.fromtimestamp(maintenant_s, timezone.utc).strftime("%Y-%m")
        depots = _lire_cache(_chemin(cache)).get("depots")
        if not isinstance(depots, dict):
            return None
        for cle in dossiers:
            entree = depots.get(str(cle))
            if isinstance(entree, dict) and ("lu_a" in entree or entree.get("executions")):
                return _vue(entree, {}, str(cle), mois)["niveau"]
    except Exception:
        pass
    return None


def conso(dossier, libelles, lieux, maintenant=None, lancer=None, cache=None):
    """L'objet `conso` du projet, ou `None` si aucune de ses actions n'est au lieu `github` (aucun appel à `gh`).
    `libelles` : `{action: libellé}` ; `lieux` : `{action: lieu}`. Répond toujours tout de suite : la dernière valeur du
    cache, ou « lecture en cours » / « indisponible » à vide ; le rafraîchissement (au plus toutes les 5 minutes, échec
    compris) se fait dans un fil daemon. Ne lève jamais."""
    if not any(lieu == "github" for lieu in (lieux or {}).values()):
        return None
    try:
        maintenant_s = float((maintenant or time.time)())
        mois = datetime.fromtimestamp(maintenant_s, timezone.utc).strftime("%Y-%m")
        chemin = _chemin(cache)
        cle = str(dossier)
        with _VERROU:
            donnees = _lire_cache(chemin)
            depots = donnees.get("depots") if isinstance(donnees.get("depots"), dict) else {}
            entree = depots.get(cle) if isinstance(depots.get(cle), dict) else {}
            derniere = max(float(entree.get("lu_a", 0) or 0), float(entree.get("echec_a", 0) or 0))
            if cle not in _EN_COURS and not ARRET.is_set() and not 0 <= maintenant_s - derniere < DELAI_S:
                fil = threading.Thread(target=_travail, daemon=True,
                                       args=(cle, chemin, entree, lancer or LANCER or subprocess.run, maintenant_s))
                _EN_COURS[cle] = fil
                fil.start()
        echec = float(entree.get("echec_a", 0) or 0) > float(entree.get("lu_a", 0) or 0)
        if not entree.get("executions") and "lu_a" not in entree:
            return _vide("Consommation indisponible (gh ne répond pas)." if echec
                         else "Consommation GitHub : lecture en cours…", mois)
        vue = _vue(entree, libelles or {}, cle, mois)
        if echec:
            vue["texte"] += " (dernière lecture conservée : gh ne répond pas)"
        return vue
    except Exception:
        return None
