"""L'estimation du coût d'un élément passé par le workflow : une fourchette, pas un chiffre."""
import json
import statistics
from pathlib import Path

from bureau import reglages
from bureau.usage import HistoriqueUsage

# (bas, haut) en tokens par étape d'un élément, tant qu'aucune mesure ne les remplace.
DEFAUTS_TOKENS = {"Haiku": (40_000, 150_000), "Sonnet": (80_000, 300_000), "Opus": (80_000, 300_000)}
PART_SORTIE = 0.2
# Prix d'un token de cache par rapport au prix d'entrée, quand la source des prix ne le donne pas (tarif Anthropic).
RAPPORT_CACHE = {"cache_lecture": 0.1, "cache_ecriture": 1.25}
USAGES_MIN = 5
MODELE_CADRAGE = "Sonnet"


def _genres_du_projet(factory):
    """Les genres d'un projet : le sien et ceux de ses workflows."""
    genres = {factory.get("genre")}
    genres |= {w.get("genre") for w in factory.get("workflows") or [] if isinstance(w, dict)}
    genres.discard(None)
    return genres


def usages_du_genre(bureau_json, genre):
    """Les usages enregistrés par les projets du bureau pour ce genre (rien si le genre est nul). Un usage porte le
    genre de la fonctionnalité de sa tâche ; un usage ancien, sans genre, compte pour le genre de son projet."""
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
        if not isinstance(factory, dict) or genre not in _genres_du_projet(factory):
            continue
        for u in HistoriqueUsage(chemin.parent / "usage-historique.jsonl").lire():
            if (u.get("genre_fonctionnalite") or factory.get("genre")) == genre:
                sortie.append(u)
    return sortie


def _total(u):
    return sum(u.get(c) or 0 for c in ("entree", "sortie", "cache_lecture", "cache_ecriture"))


def _quartiles(valeurs):
    q = statistics.quantiles(sorted(valeurs), n=4, method="inclusive")
    return q[0], q[2]


def _tokens(modele, usages):
    mesures = [u for u in usages if u.get("modele") == modele]
    if len(mesures) >= USAGES_MIN:
        bas, haut = _quartiles([_total(u) for u in mesures])
        return [int(bas), int(haut)], "mesures", mesures
    bas, haut = DEFAUTS_TOKENS[modele]
    return [bas, haut], "defauts", []


def _euros(tokens, prix):
    """Euros de tokens sans détail par compteur (valeurs par défaut) : une part de sortie, le reste en entrée."""
    p_in, p_out = prix["entree"], prix["sortie"]
    return [t * ((1 - PART_SORTIE) * p_in + PART_SORTIE * p_out) for t in tokens]


def _euros_usage(u, prix):
    """Euros d'un usage mesuré, compteur par compteur : un token lu en cache coûte bien moins qu'un token d'entrée."""
    total = (u.get("entree") or 0) * prix["entree"] + (u.get("sortie") or 0) * prix["sortie"]
    for c, rapport in RAPPORT_CACHE.items():
        p = prix.get(c)
        total += (u.get(c) or 0) * (prix["entree"] * rapport if p is None else p)
    return total


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
        tokens, source, mesures = _tokens(modele, usages)
        detail.append({"etape": nom, "modele": modele, "tokens": tokens, "source": source, "_mesures": mesures})
    tokens = [sum(d["tokens"][0] for d in detail), sum(d["tokens"][1] for d in detail)]
    sources = {d["source"] for d in detail}
    source = sources.pop() if len(sources) == 1 else "mixte"
    prix = {m: prix_de(m) for _, m in etapes}
    euros = None
    if all(prix.values()):
        bas = haut = 0.0
        for d in detail:
            p = prix[d["modele"]]
            if d["_mesures"]:
                b, h = _quartiles([_euros_usage(u, p) for u in d["_mesures"]])
            else:
                b, h = _euros(d["tokens"], p)
            bas, haut = bas + b, haut + h
        euros = [round(bas, 2), round(haut, 2)]
    for d in detail:
        del d["_mesures"]
    base = {"mesures": "d'après les usages déjà mesurés sur cette machine",
            "defauts": "d'après des valeurs par défaut (aucune mesure suffisante)",
            "mixte": "d'après des mesures pour certaines étapes, des valeurs par défaut pour les autres"}[source]
    explication = f"Estimation par élément passé par le workflow, {base}."
    if euros is None:
        explication += " Euros : prix inconnu pour au moins un modèle."
    return {"tokens": tokens, "euros": euros, "source": source, "detail": detail, "explication": explication}
