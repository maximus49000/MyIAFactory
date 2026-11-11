"""L'estimation du coût d'un élément passé par le workflow : une fourchette, pas un chiffre."""
import json
import statistics
from pathlib import Path

from bureau import reglages
from bureau.usage import HistoriqueUsage

# (bas, haut) en tokens par étape d'un élément, tant qu'aucune mesure ne les remplace.
DEFAUTS_TOKENS = {"Haiku": (40_000, 150_000), "Sonnet": (80_000, 300_000), "Opus": (80_000, 300_000)}
PART_SORTIE = 0.2
USAGES_MIN = 5
MODELE_CADRAGE = "Sonnet"


def usages_du_genre(bureau_json, genre):
    """Les usages enregistrés par les projets du bureau qui ont ce genre (rien si le genre est nul)."""
    if not genre:
        return []
    try:
        projets = reglages.lire_bureau(bureau_json)["projets"]
    except (reglages.ReglagesInvalides, OSError):
        return []
    sortie = []
    for p in projets:
        chemin = Path(p["chemin"])
        try:
            r = json.loads(chemin.read_text(encoding="utf-8-sig"))
            factory = json.loads((chemin.parent / r["orchestrateur"]).read_text(encoding="utf-8-sig"))
        except (ValueError, OSError, KeyError, TypeError):
            continue
        if isinstance(factory, dict) and factory.get("genre") == genre:
            sortie += HistoriqueUsage(chemin.parent / "usage-historique.jsonl").lire()
    return sortie


def _total(u):
    return sum(u.get(c) or 0 for c in ("entree", "sortie", "cache_lecture", "cache_ecriture"))


def _tokens(modele, usages):
    mesures = sorted(_total(u) for u in usages if u.get("modele") == modele)
    if len(mesures) >= USAGES_MIN:
        q = statistics.quantiles(mesures, n=4, method="inclusive")
        return [int(q[0]), int(q[2])], "mesures"
    bas, haut = DEFAUTS_TOKENS[modele]
    return [bas, haut], "defauts"


def _euros(tokens, prix):
    p_in, p_out = prix["entree"], prix["sortie"]
    return [t * ((1 - PART_SORTIE) * p_in + PART_SORTIE * p_out) for t in tokens]


def estimer(flux, agents, usages, prix_de):
    modele_du_role = {}
    for a in agents:
        modele_du_role.setdefault(a["role"], a["modele"])
    etapes = [("cadrage", MODELE_CADRAGE)]
    for e in flux:
        if e["role"] not in modele_du_role:
            raise ValueError(f"Aucun agent pour le rôle « {e['role']} » (étape « {e['id']} »).")
        etapes.append((e["id"], modele_du_role[e["role"]]))
    detail = []
    for nom, modele in etapes:
        tokens, source = _tokens(modele, usages)
        detail.append({"etape": nom, "modele": modele, "tokens": tokens, "source": source})
    tokens = [sum(d["tokens"][0] for d in detail), sum(d["tokens"][1] for d in detail)]
    sources = {d["source"] for d in detail}
    source = sources.pop() if len(sources) == 1 else "mixte"
    prix = {m: prix_de(m) for _, m in etapes}
    euros = None
    if all(prix.values()):
        bas = sum(_euros([d["tokens"][0]], prix[d["modele"]])[0] for d in detail)
        haut = sum(_euros([d["tokens"][1]], prix[d["modele"]])[0] for d in detail)
        euros = [round(bas, 2), round(haut, 2)]
    base = {"mesures": "d'après les usages déjà mesurés sur cette machine",
            "defauts": "d'après des valeurs par défaut (aucune mesure suffisante)",
            "mixte": "d'après des mesures pour certaines étapes, des valeurs par défaut pour les autres"}[source]
    explication = f"Estimation par élément passé par le workflow, {base}."
    if euros is None:
        explication += " Euros : prix inconnu pour au moins un modèle."
    return {"tokens": tokens, "euros": euros, "source": source, "detail": detail, "explication": explication}
