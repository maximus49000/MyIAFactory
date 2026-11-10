"""L'état servi à la page : relevé + équipe + horloge."""
from . import releve as modreleve
from . import statuts


def _fraicheur(titulaire, defaut):
    v = titulaire.get("fraicheur_min")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return v
    return defaut


def construire(r, eq, maintenant, fraicheur_min):
    en_pause = r["factory"].get("etat") == "en pause"
    taches_de = {}
    for t in r["taches"]:
        taches_de.setdefault(t.get("titulaire"), []).append(t)

    agents = []
    presents = set()
    for ti in r["titulaires"]:
        cle = ti["cle"]
        siennes = taches_de.get(cle, [])
        if not statuts.present(ti, siennes, maintenant):
            continue
        presents.add(cle)
        st = statuts.statut(siennes, maintenant, _fraicheur(ti, fraicheur_min), en_pause)
        fiche = eq.agent(cle, chef=bool(ti.get("chef")))
        agents.append({
            "id": cle,
            "prenom": fiche["prenom"],
            "service": None if ti.get("chef") else ti.get("service"),
            "lieu": ti["lieu"],
            "modele": fiche.get("modele") or ti.get("modele") or "?",
            "couleur": fiche["couleur"],
            "chef": bool(ti.get("chef")),
            "statut": st["statut"],
            "bulle": st["bulle"],
            "taches": [x["id"] for x in siennes if x.get("active")],
        })

    taches = [{
        "id": t["id"], "titre": t["titre"], "colonne": t["colonne"],
        "agent": t.get("titulaire") if t.get("titulaire") in presents else None,
        "etape": t.get("etape") or "", "maj": t.get("maj"), "postit": t.get("postit", True),
    } for t in r["taches"]]

    return {
        "version": 1,
        "horodatage": maintenant.isoformat(),
        "projet": r["projet"],
        "erreur": None,
        "factory": statuts.factory(r["factory"], r["taches"], maintenant, fraicheur_min),
        "services": r["services"],
        "colonnes": r["colonnes"],
        "file": r["file"],
        "decisions": r["decisions"],
        "agents": agents,
        "taches": taches,
    }


def erreur(message, maintenant):
    return {
        "version": 1, "horodatage": maintenant.isoformat(), "projet": "", "erreur": message,
        "factory": {"etat": "inconnu", "depuis": None, "derniere_activite": None, "inactive": False},
        "services": [], "colonnes": [], "file": {"visibles": [], "reste": 0}, "decisions": 0,
        "agents": [], "taches": [],
    }


def agents_locaux_au_travail(e):
    return sum(1 for a in e["agents"]
               if a["lieu"] == "local" and a["statut"] == "travail" and not a["chef"])


def lire(regl, eq, maintenant):
    r, message = modreleve.obtenir(regl)
    if r is None:
        return erreur(message, maintenant)
    try:
        return construire(r, eq, maintenant, regl.get("fraicheur_min", 30))
    except Exception as e:  # un relevé inattendu ne doit jamais faire tomber le serveur
        return erreur(f"Relevé inutilisable : {e}", maintenant)
