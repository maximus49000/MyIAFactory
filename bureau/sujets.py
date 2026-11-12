"""Les sujets qui ont consommé Claude sur une période (une semaine du forfait) : un arbre projet → fonctionnalité →
tâche → étape, plus l'orchestration, la direction et les échanges de création. Pur.

Une « ligne » est un usage placé dans l'arbre : `{chemin: [(id, nom, genre), …], t (epoch), euros | None, modele, sortie,
duree | None}`. Chaque nœud cumule tout ce qui est en dessous (euros, usages sans prix, empreinte) ; seul le nœud où
s'arrête le chemin d'un usage porte ses `marques` (les instants d'appel, pour le graphique). Les partenaires (voix,
images) ne sont pas du quota Claude : ils n'y figurent pas. Un usage sans prix n'est jamais compté à zéro : il est
compté dans `sans_prix` et exclu des euros.
"""
from datetime import datetime

from . import cout
from .empreinte import Cumul

SEP = "\x1f"   # sépare les identifiants d'un chemin dans l'`id` d'un nœud (jamais présent dans un identifiant)
RACINE_CREATIONS = ("creations", "Échanges de création", "creations")


def epoch(iso):
    """Les secondes epoch d'une date ISO 8601 (une date sans fuseau est lue en heure locale), ou None."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _duree(u):
    d = u.get("duree")
    return float(d) if isinstance(d, (int, float)) and not isinstance(d, bool) and d >= 0 else None


def lignes_projet(pid, nom, usages, releve, prix_de, debut, fin):
    """Les lignes d'un projet pour les usages datés dans [debut, fin] (secondes epoch)."""
    r = releve or {}
    taches = {t["id"]: t for t in r.get("taches") or [] if isinstance(t, dict) and t.get("id")}
    fonctionnalites = {f["id"]: f for f in r.get("fonctionnalites") or [] if isinstance(f, dict) and f.get("id")}
    sortie = []
    for u in usages:
        if u.get("genre") == "partenaire":
            continue
        t = epoch(u.get("t"))
        if t is None or not debut <= t <= fin:
            continue
        p = prix_de(u["modele"], u.get("t_prix") or u.get("t"))[0]
        chemin = [(pid, nom, "projet")]
        tache = u.get("tache")
        if u.get("etape") == cout.ETAPE_ORCHESTRATION:
            chemin.append(("orchestration", "Orchestration", "groupe"))
        elif tache:
            fid = (taches.get(tache) or {}).get("fonctionnalite")
            if fid:
                chemin.append((f"f:{fid}", (fonctionnalites.get(fid) or {}).get("nom") or fid, "fonctionnalite"))
            else:
                chemin.append(("hors-fonctionnalite", "Hors fonctionnalité", "fonctionnalite"))
            chemin.append((f"t:{tache}", (taches.get(tache) or {}).get("titre") or tache, "tache"))
            etape = u.get("etape")
            chemin.append((f"e:{etape or ''}", etape or "Sans étape", "etape"))
        elif not u.get("service"):
            chemin.append(("direction", "Direction", "groupe"))
        else:
            chemin.append(("hors-tache", "Hors tâche", "groupe"))
        sortie.append({"chemin": chemin, "t": t, "euros": cout._cout(u, p) if p else None, "modele": u["modele"],
                       "sortie": u.get("sortie") or 0, "duree": _duree(u)})
    return sortie


def lignes_creation(groupe_id, groupe_nom, usages, euros_de, debut, fin):
    """Les lignes d'un échange de création (un brouillon, ou « abandonnés ») ; `euros_de(usage) -> float | None`."""
    sortie = []
    for u in usages:
        t = epoch(u.get("t")) if isinstance(u, dict) else None
        if t is None or not debut <= t <= fin:
            continue
        sortie.append({"chemin": [RACINE_CREATIONS, (groupe_id, groupe_nom, "echange")], "t": t,
                       "euros": euros_de(u), "modele": u.get("modele"), "sortie": u.get("sortie") or 0,
                       "duree": _duree(u)})
    return sortie


def _noeud(identifiant, nom, genre):
    return {"id": identifiant, "nom": nom, "genre": genre, "euros": 0.0, "sans_prix": 0, "n": 0, "_co2": Cumul(),
            "marques": [], "_enfants": {}}


def _ajouter(n, ligne):
    n["n"] += 1
    if ligne["euros"] is None:
        n["sans_prix"] += 1
    else:
        n["euros"] += ligne["euros"]
    n["_co2"].ajouter(ligne["modele"], ligne["sortie"])


def _vue(n):
    enfants = [_vue(e) for e in n["_enfants"].values()]
    enfants.sort(key=lambda e: (-e["euros"], e["nom"]))
    co2 = n["_co2"].vue()
    marques = sorted(n["marques"], key=lambda m: m["t"])
    return {"id": n["id"], "nom": n["nom"], "genre": n["genre"], "euros": round(n["euros"], 6),
            "sans_prix": n["sans_prix"], "n": n["n"], **({"co2": co2} if co2 else {}),
            "marques": marques, "enfants": enfants}


def arbre(lignes):
    """`{euros, sans_prix, n, co2?, sujets: [nœud]}` : les nœuds triés par coût décroissant à chaque niveau."""
    racine = _noeud("", "", "racine")
    for ligne in lignes:
        courant, suite = racine, []
        _ajouter(racine, ligne)
        for identifiant, nom, genre in ligne["chemin"]:
            suite.append(identifiant)
            cle = SEP.join(suite)
            courant = courant["_enfants"].setdefault(cle, _noeud(cle, nom, genre))
            _ajouter(courant, ligne)
        courant["marques"].append({"t": round(ligne["t"]), "euros": None if ligne["euros"] is None
                                   else round(ligne["euros"], 6), "modele": ligne["modele"], "duree": ligne["duree"]})
    v = _vue(racine)
    return {k: v[k] for k in ("euros", "sans_prix", "n", "co2") if k in v} | {"sujets": v["enfants"]}
