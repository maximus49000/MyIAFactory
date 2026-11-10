"""Le calcul des coûts : des usages (tokens) aux euros estimés, du total au détail. Pur.

Prix d'un usage = tokens × prix par million du modèle à la date de première apparition de l'usage.
Un modèle sans prix n'est jamais compté à zéro : l'usage est montré avec ses tokens, exclu des
euros, et un avertissement le dit.
"""
import statistics
from datetime import timedelta

from .statuts import TRES_ANCIEN, lire_date

PERIODES = ("aujourdhui", "7j", "30j")
DUREES = {"7j": timedelta(days=7), "30j": timedelta(days=30)}
COMPTEURS = ("entree", "sortie", "cache_lecture", "cache_ecriture")
SANS = ""  # clé de « hors tâche » et de « sans étape » : aucun identifiant réel n'est vide
FACTEUR_TACHE_CHERE = 3
MIN_RETOURS = 2


def id_source(service, genre, tache):
    return f"source:{service}:{genre}:{tache or ''}"


def euros_en_clair(x):
    """« ≈ 4,20 € » ; sous un centime, quatre décimales."""
    texte = f"{x:,.4f}" if abs(x) < 0.01 else f"{x:,.2f}"
    return "≈ " + texte.replace(",", " ").replace(".", ",") + " €"


def _dans_la_periode(t, periode, maintenant):
    d = lire_date(t)
    if d == TRES_ANCIEN:
        return False
    if periode == "aujourdhui":
        return d.astimezone(maintenant.tzinfo).date() == maintenant.date()
    return d >= maintenant - DUREES[periode]


def _cout(u, p):
    """Euros d'un usage ; un prix de cache absent compte au prix d'entrée (estimation prudente)."""
    total = 0.0
    for c in COMPTEURS:
        prix_million = p.get(c)
        if prix_million is None:
            prix_million = p["entree"]
        total += (u.get(c) or 0) * prix_million
    return total / 1_000_000


def _niveau(p):
    return p["entree"] + p["sortie"]


def _vide():
    return {"total": 0.0, "taches": {}, "modeles": {}, "usages": []}


def _ajouter(groupe, u, cout):
    if cout is None:
        return
    groupe["total"] += cout
    tache = groupe["taches"].setdefault(u.get("tache") or SANS, {"total": 0.0, "etapes": {}})
    tache["total"] += cout
    etape = u.get("etape") or SANS
    tache["etapes"][etape] = tache["etapes"].get(etape, 0.0) + cout
    groupe["modeles"][u["modele"]] = groupe["modeles"].get(u["modele"], 0.0) + cout


def _arrondir(groupe):
    groupe["total"] = round(groupe["total"], 6)
    for t in groupe["taches"].values():
        t["total"] = round(t["total"], 6)
        t["etapes"] = {k: round(v, 6) for k, v in t["etapes"].items()}
    groupe["modeles"] = {k: round(v, 6) for k, v in groupe["modeles"].items()}
    groupe["usages"].sort(key=lambda x: (x["t"], x["id"]))


def facturation(usages, prix_de, r, periode, maintenant):
    """Les coûts de la période. `prix_de(modele, date_iso) -> (prix | None, date, ancien)`."""
    if periode not in PERIODES:
        raise ValueError(f"période inconnue « {periode} »")
    services, direction = {}, _vide()
    sans_prix, dates, anciens = {}, [], 0
    lignes = []  # (service, usage, cout, prix)
    for u in usages:
        if not _dans_la_periode(u.get("t"), periode, maintenant):
            continue
        p, date_prix, ancien = prix_de(u["modele"], u.get("t_prix") or u.get("t"))
        cout = _cout(u, p) if p else None
        tokens = {c: u.get(c) or 0 for c in COMPTEURS}
        if cout is None:
            s = sans_prix.setdefault(u["modele"], {"modele": u["modele"], "tokens": 0, "usages": 0})
            s["tokens"] += sum(tokens.values())
            s["usages"] += 1
        else:
            dates.append(date_prix)
            anciens += 1 if ancien else 0
        groupe = services.setdefault(u["service"], _vide()) if u.get("service") else direction
        _ajouter(groupe, u, cout)
        groupe["usages"].append({
            "id": u["id"], "tache": u.get("tache"), "agent": u.get("agent"), "modele": u["modele"],
            "etape": u.get("etape"), "t": u.get("t"), "tokens": tokens,
            "cout": round(cout, 6) if cout is not None else None,
            "prix_du": date_prix if cout is not None else None, "ancien": bool(ancien and cout is not None)})
        if u.get("service"):
            lignes.append((u["service"], u, cout, p))
    for g in list(services.values()) + [direction]:
        _arrondir(g)
    gestion = 0.0  # le bureau ne consomme aucun token ; ses requêtes de prix ne coûtent que du temps
    total = sum(g["total"] for g in services.values()) + direction["total"] + gestion
    return {
        "total": round(total, 6), "gestion": gestion,
        "sans_prix": sorted(sans_prix.values(), key=lambda x: x["modele"]),
        "services": services, "direction": direction,
        "sources": _sources(services, lignes, r),
        "prix_du": max(dates) if dates else None,
        "avertissement": _avertissement(sans_prix, anciens),
    }


def _avertissement(sans_prix, anciens):
    morceaux = []
    if sans_prix:
        n = sum(s["usages"] for s in sans_prix.values())
        noms = ", ".join(sorted(sans_prix)[:5]) + ("…" if len(sans_prix) > 5 else "")
        morceaux.append(f"{n} usage(s) à prix inconnu ({noms}) : exclus des euros, tokens montrés.")
    if anciens:
        morceaux.append(f"{anciens} usage(s) antérieur(s) au premier prix enregistré : "
                        "prix du jour de l'installation.")
    return " ".join(morceaux) or None


def _titres(r):
    taches = (r or {}).get("taches") or []
    return {t.get("id"): t for t in taches if isinstance(t, dict)}


def _nom_tache(taches, i):
    t = taches.get(i) or {}
    titre = t.get("titre")
    return titre if isinstance(titre, str) and titre else i


def _sources(services, lignes, r):
    """Les sources d'amélioration, par service (la direction n'en a pas)."""
    taches = _titres(r)
    out = []
    for sid, g in services.items():
        couts = {i: t["total"] for i, t in g["taches"].items() if i != SANS and t["total"] > 0}
        # Tâches qui coûtent plus de trois fois la médiane du service.
        if couts:
            mediane = statistics.median(couts.values())
            for i, c in couts.items():
                if mediane > 0 and c > FACTEUR_TACHE_CHERE * mediane:
                    out.append({"id": id_source(sid, "tache_chere", i), "genre": "tache_chere", "service": sid,
                                "tache": i, "texte": f"Tâche « {_nom_tache(taches, i)} » : coût de "
                                                     f"{euros_en_clair(c)} pour une médiane de "
                                                     f"{euros_en_clair(mediane)} dans le service."})
        out += _modele_trop_fort(sid, [x for x in lignes if x[0] == sid and x[3]], taches)
        # Tâches qui ont reçu plusieurs retours : la part du coût qu'elles représentent.
        for i, c in couts.items():
            retours = (taches.get(i) or {}).get("retours")
            n = len(retours) if isinstance(retours, list) else 0
            if n >= MIN_RETOURS and g["total"] > 0:
                part = round(100 * c / g["total"])
                out.append({"id": id_source(sid, "allers_retours", i), "genre": "allers_retours", "service": sid,
                            "tache": i, "texte": f"Tâche « {_nom_tache(taches, i)} » : {n} retours, "
                                                 f"{euros_en_clair(c)} ({part} % du coût du service)."})
    out.sort(key=lambda s: (s["service"], s["genre"], s["tache"]))
    return out


def _modele_trop_fort(sid, lignes, taches):
    """Un usage du modèle le plus cher du service, à une étape où les autres usages sont, en médiane,
    d'un modèle moins cher. Une source par tâche."""
    if not lignes:
        return []
    plus_cher = max(_niveau(p) for _, _, _, p in lignes)
    niveaux = {}  # étape -> niveaux de tous ses usages
    for _, u, _, p in lignes:
        if u.get("etape"):
            niveaux.setdefault(u["etape"], []).append(_niveau(p))
    medianes = {}  # étape -> médiane des autres usages qu'un usage du modèle le plus cher
    for etape, liste in niveaux.items():
        autres = list(liste)
        if plus_cher in autres:
            autres.remove(plus_cher)
        medianes[etape] = statistics.median(autres) if autres else None
    par_tache = {}
    for _, u, _, p in lignes:
        etape, tache = u.get("etape"), u.get("tache")
        if not etape or not tache or _niveau(p) < plus_cher:
            continue
        mediane = medianes.get(etape)
        if mediane is not None and _niveau(p) > mediane:
            par_tache.setdefault(tache, {})[etape] = (u["modele"], _niveau(p), mediane)
    out = []
    for tache, etapes in par_tache.items():
        constats = "; ".join(f"étape « {e} » faite avec « {m} » ({euros_en_clair(n)}/M de tokens entrée + "
                             f"sortie) quand les autres usages de l'étape sont en médiane à {euros_en_clair(med)}/M"
                             for e, (m, n, med) in sorted(etapes.items()))
        out.append({"id": id_source(sid, "modele_trop_fort", tache), "genre": "modele_trop_fort",
                    "service": sid, "tache": tache,
                    "texte": f"Tâche « {_nom_tache(taches, tache)} » : {constats}."})
    return out
