"""Enveloppe de la CLI `gh` pour l'exécution déportée : déclarer une exécution GitHub Actions, la suivre, en télécharger
un artefact, lire la visibilité du dépôt.

Tout prend un `lancer` compatible `subprocess.run` (injectable : les tests n'appellent jamais le vrai `gh`). Le code est
exécuté par des agents : Python 3.9 (pas de `X | Y`, pas de `match`). Aucun jeton n'est lu, affiché ni journalisé :
`gh` garde lui-même son authentification.
"""
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MSG_CONNEXION = "gh n'est pas installé ou pas connecté : lancez `gh auth login` (portées repo et workflow)."
PAS_S = 60
DELAI_COMMANDE_S = 120
ECHECS_TOLERES = 3


class Gh_indisponible(Exception):
    """`gh` est absent, non connecté, ou la commande a échoué : l'opération ne peut pas continuer."""


def _lancer(argv: List[str], lancer, dossier: Optional[str] = None):
    try:
        r = lancer(argv, cwd=dossier, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   timeout=DELAI_COMMANDE_S)
    except subprocess.TimeoutExpired as e:
        raise Gh_indisponible("gh ne répond pas (plus de %d s)." % DELAI_COMMANDE_S) from e
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise Gh_indisponible(MSG_CONNEXION) from e
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()[:300]
        raise Gh_indisponible("gh %s a échoué (%s) : %s" % (" ".join(argv[1:3]), r.returncode, detail))
    return r.stdout or ""


def _json(argv: List[str], lancer, dossier: Optional[str] = None):
    brut = _lancer(argv, lancer, dossier)
    try:
        return json.loads(brut)
    except ValueError as e:
        raise Gh_indisponible("réponse de gh illisible (%s)" % " ".join(argv[1:3])) from e


def gh_pret(lancer: Callable = subprocess.run) -> Tuple[bool, str]:
    try:
        _lancer(["gh", "auth", "status"], lancer)
    except Gh_indisponible:
        return False, MSG_CONNEXION
    return True, "gh est prêt."


def visibilite(depot_dossier: str, lancer: Callable = subprocess.run) -> str:
    v = _json(["gh", "repo", "view", "--json", "visibility"], lancer, depot_dossier)
    return "public" if str(v.get("visibility", "")).upper() == "PUBLIC" else "prive"


def declencher(depot_dossier: str, workflow: str, ref: str, entrees: Dict, lancer: Callable = subprocess.run) -> None:
    argv = ["gh", "workflow", "run", workflow, "--ref", ref]
    for cle, valeur in (entrees or {}).items():
        if isinstance(valeur, bool):
            valeur = "true" if valeur else "false"
        argv += ["-f", "%s=%s" % (cle, valeur)]
    _lancer(argv, lancer, depot_dossier)


def _instant(texte):
    return datetime.fromisoformat(texte.replace("Z", "+00:00"))


def _duree(v) -> int:
    try:
        return int((_instant(v["updatedAt"]) - _instant(v["createdAt"])).total_seconds())
    except (KeyError, TypeError, ValueError):
        return 0


def _jobs(v) -> List[Dict]:
    return [{"name": j.get("name"), "conclusion": j.get("conclusion") or None}
            for j in (v.get("jobs") or []) if isinstance(j, dict)]


def _resume(v, run_id=None) -> Dict:
    r = {"id": run_id if run_id is not None else v.get("databaseId"), "statut": v.get("status"),
         "conclusion": v.get("conclusion") or None, "duree_s": _duree(v), "url": v.get("url", "")}
    if "jobs" in v:      # présents seulement quand `gh run view` les a rendus : `[{name, conclusion}]`
        r["jobs"] = _jobs(v)
    return r


def execution_du_commit(depot_dossier: str, workflow: str, commit: str,
                        lancer: Callable = subprocess.run) -> Optional[Dict]:
    liste = _json(["gh", "run", "list", "--workflow", workflow, "--commit", commit, "--limit", "1", "--json",
                   "databaseId,status,conclusion,createdAt,updatedAt,url"], lancer, depot_dossier)
    return _resume(liste[0]) if liste else None


def suivre(depot_dossier: str, run_id: int, dormir: Callable = time.sleep, dire: Callable = print,
           delai_s: int = 3600, lancer: Callable = subprocess.run) -> Dict:
    ecoule = 0
    echecs = 0
    resume = {"id": run_id, "statut": None, "conclusion": None, "duree_s": 0, "url": ""}
    while True:
        try:
            v = _json(["gh", "run", "view", str(run_id), "--json", "status,conclusion,createdAt,updatedAt,url,jobs"],
                      lancer, depot_dossier)
        except Gh_indisponible:
            echecs += 1
            if echecs > ECHECS_TOLERES:
                raise
            v = None
        if v is not None:
            echecs = 0
            resume = _resume(v, run_id)
            if resume["statut"] == "completed":
                return resume
        if ecoule >= delai_s:
            resume["conclusion"] = "timeout"
            return resume
        if v is None:
            dire("exécution %s : gh ne répond pas, nouvel essai (%d min)" % (run_id, ecoule // 60))
        else:
            dire("exécution %s : %s (%d min)" % (run_id, resume["statut"], ecoule // 60))
        attente = min(PAS_S, delai_s - ecoule)
        dormir(attente)
        ecoule += attente


def jobs_du_run(depot_dossier: str, run_id: int, lancer: Callable = subprocess.run) -> List[Dict]:
    """Les jobs d'une exécution : `[{name, conclusion}]` (le nom du job est l'id de l'action qui l'a produit)."""
    return _jobs(_json(["gh", "run", "view", str(run_id), "--json", "jobs"], lancer, depot_dossier))


def telecharger(depot_dossier: str, run_id: int, nom: str, dossier: str, lancer: Callable = subprocess.run) -> str:
    """Télécharge l'artefact `nom` dans `dossier` et rend le premier fichier trié trouvé, ou le dossier s'il est vide."""
    _lancer(["gh", "run", "download", str(run_id), "-n", nom, "-D", dossier], lancer, depot_dossier)
    fichiers = sorted(p for p in Path(dossier).rglob("*") if p.is_file())
    return str(fichiers[0]) if fichiers else dossier


def executions_recentes(depot_dossier: str, limite: int = 100, lancer: Callable = subprocess.run) -> List[Dict]:
    """Les `limite` dernières exécutions du dépôt, telles que `gh run list --json` les rend (clés de gh conservées)."""
    liste = _json(["gh", "run", "list", "-L", str(limite), "--json",
                   "databaseId,name,status,conclusion,createdAt,updatedAt,startedAt,headSha,url"],
                  lancer, depot_dossier)
    return [v for v in liste if isinstance(v, dict)] if isinstance(liste, list) else []


def quota_actions(lancer: Callable = subprocess.run) -> Optional[Tuple[float, int]]:
    """`(minutes_utilisées, minutes_incluses)` officielles du compte, ou `None` si GitHub ne les donne pas (la portée
    `user` du jeton manque : l'API de facturation répond 404). Lecture seule ; ne change jamais le jeton."""
    try:
        login = _lancer(["gh", "api", "user", "--jq", ".login"], lancer).strip()
        if not login:
            return None
        v = _json(["gh", "api", "users/%s/settings/billing/actions" % login], lancer)
        utilisees, incluses = v.get("total_minutes_used"), v.get("included_minutes")
        if isinstance(utilisees, (int, float)) and isinstance(incluses, (int, float)) and incluses > 0:
            return float(utilisees), int(incluses)
    except (Gh_indisponible, AttributeError):
        pass
    return None
