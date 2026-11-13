"""Le calcul des coûts : des usages (tokens) aux euros estimés, du total au détail. Pur.

Prix d'un usage = tokens × prix par million du modèle à la date de première apparition de l'usage.
Un modèle sans prix n'est jamais compté à zéro : l'usage est montré avec ses tokens, exclu des
euros, et un avertissement le dit.
"""
import statistics
from datetime import timedelta

from .empreinte import Cumul, avec_equivalences
from .statuts import TRES_ANCIEN, lire_date

PERIODES = ("aujourdhui", "7j", "30j")
DUREES = {"7j": timedelta(days=7), "30j": timedelta(days=30)}
COMPTEURS = ("entree", "sortie", "cache_lecture", "cache_ecriture")
SANS = ""  # clé de « hors tâche » et de « sans étape » : aucun identifiant réel n'est vide
ETAPE_ORCHESTRATION = "orchestration"  # l'étape des usages du moteur (ses appels de jugement) : la facturation les isole
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
    return {"total": 0.0, "taches": {}, "modeles": {}, "usages": [], "sans_prix": {},
            "_co2": Cumul(), "_modeles_co2": {}}


def _ajouter_co2(groupe, u):
    """Range l'empreinte estimée d'un usage (ses tokens de sortie) dans son groupe, sa tâche, son étape et son modèle.
    Elle ne dépend pas du prix : un modèle sans prix a quand même son empreinte."""
    groupe["_co2"].ajouter(u["modele"], u.get("sortie") or 0)
    tache = groupe["taches"].setdefault(u.get("tache") or SANS, {"total": 0.0, "etapes": {}, "sans_prix": 0})
    tache.setdefault("_co2", Cumul()).ajouter(u["modele"], u.get("sortie") or 0)
    etape = u.get("etape") or SANS
    tache.setdefault("_etapes_co2", {}).setdefault(etape, Cumul()).ajouter(u["modele"], u.get("sortie") or 0)
    groupe["_modeles_co2"].setdefault(u["modele"], Cumul()).ajouter(u["modele"], u.get("sortie") or 0)


def _ajouter(groupe, u, cout):
    """Range un usage dans son groupe. Sans prix, il ne compte pour aucun euro mais sa tâche le porte
    (`sans_prix` : nombre d'usages exclus), pour qu'un coût incomplet ne passe jamais pour complet."""
    tache = groupe["taches"].setdefault(u.get("tache") or SANS, {"total": 0.0, "etapes": {}, "sans_prix": 0})
    if u.get("reparti"):   # une part de lot répartie au temps ou à parts égales : une estimation, pas une mesure
        tache["reparti"] = True
    if cout is None:
        tache["sans_prix"] += 1
        s = groupe["sans_prix"].setdefault(u["modele"], {"modele": u["modele"], "tokens": 0, "usages": 0})
        s["tokens"] += sum(u.get(c) or 0 for c in COMPTEURS)
        s["usages"] += 1
        return
    groupe["total"] += cout
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
    # L'empreinte estimée : une clé n'existe que s'il y a une valeur (jamais zéro à la place d'un inconnu).
    co2 = groupe.pop("_co2").vue()
    if co2:
        groupe["co2"] = co2
    modeles_co2 = {k: v.vue() for k, v in groupe.pop("_modeles_co2").items()}
    modeles_co2 = {k: v for k, v in modeles_co2.items() if v}
    if modeles_co2:
        groupe["modeles_co2"] = modeles_co2
    for t in groupe["taches"].values():
        c = t.pop("_co2", None)
        if c and c.vue():
            t["co2"] = c.vue()
        etapes = {k: v.vue() for k, v in (t.pop("_etapes_co2", None) or {}).items()}
        etapes = {k: v for k, v in etapes.items() if v}
        if etapes:
            t["etapes_co2"] = etapes
    groupe["sans_prix"] = sorted(groupe["sans_prix"].values(), key=lambda x: x["modele"])
    groupe["usages"].sort(key=lambda x: (x["t"], x["id"]))


def _noms_partenaires(r):
    cats = (((r or {}).get("partenaires") or {}).get("categories")) or {}
    return {p.get("id"): p.get("nom") for liste in cats.values() if isinstance(liste, list)
            for p in liste if isinstance(p, dict)}


def _ajouter_partenaire(partenaires, u, taux_de, noms):
    """Range l'usage d'un partenaire : son coût d'origine est gardé ; un coût en dollars est converti au taux du jour
    de l'usage (figé à sa première apparition) ; un coût absent, ou dans une devise sans taux, est « non chiffré »."""
    g = partenaires.setdefault(u["partenaire"], {"nom": noms.get(u["partenaire"]) or u["partenaire"], "total": 0.0,
                                                 "origine": {}, "estime": False, "non_chiffre": 0, "usages": 0,
                                                 "taches": {}})
    g["usages"] += 1
    g["estime"] = g["estime"] or bool(u.get("estime"))
    cout, devise, euros = u.get("cout"), u.get("devise"), None
    if cout is not None and devise:
        g["origine"][devise] = g["origine"].get(devise, 0) + cout
        if devise == "EUR":
            euros = cout
        elif devise == "USD" and taux_de is not None:
            taux, _ = taux_de(u.get("t_prix") or u.get("t"))
            euros = cout * taux if taux else None
    if euros is None:
        g["non_chiffre"] += 1
        return
    g["total"] += euros
    tache = u.get("tache") or SANS
    g["taches"][tache] = g["taches"].get(tache, 0.0) + euros


def _arrondir_partenaires(partenaires):
    for g in partenaires.values():
        g["total"] = round(g["total"], 6)
        g["origine"] = [{"montant": round(m, 6), "devise": d} for d, m in sorted(g["origine"].items())]
        g["taches"] = {k: round(v, 6) for k, v in g["taches"].items()}
    return partenaires


def facturation(usages, prix_de, r, periode, maintenant, taux_de=None):
    """Les coûts de la période. `prix_de(modele, date_iso) -> (prix | None, date, ancien)` ;
    `taux_de(date_iso) -> (euros pour un dollar | None, date)` convertit les coûts des partenaires en dollars."""
    if periode not in PERIODES:
        raise ValueError(f"période inconnue « {periode} »")
    services, direction, orchestration = {}, _vide(), _vide()
    sans_prix, dates, anciens = {}, [], 0
    lignes = []  # (service, usage, cout, prix)
    partenaires, noms = {}, _noms_partenaires(r)
    total_co2 = Cumul()   # l'empreinte estimée de tout (voir empreinte.py)
    for u in usages:
        if not _dans_la_periode(u.get("t"), periode, maintenant):
            continue
        if u.get("genre") == "partenaire":
            _ajouter_partenaire(partenaires, u, taux_de, noms)
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
        if u.get("etape") == ETAPE_ORCHESTRATION:   # les appels de jugement du moteur : à part de la production
            groupe = orchestration
        else:
            groupe = services.setdefault(u["service"], _vide()) if u.get("service") else direction
        _ajouter(groupe, u, cout)
        _ajouter_co2(groupe, u)
        total_co2.ajouter(u["modele"], u.get("sortie") or 0)
        un_co2 = Cumul()
        un_co2.ajouter(u["modele"], u.get("sortie") or 0)
        groupe["usages"].append({**({"co2": un_co2.vue()} if un_co2.vue() else {}),
            "id": u["id"], "tache": u.get("tache"), "agent": u.get("agent"), "modele": u["modele"],
            "etape": u.get("etape"), "t": u.get("t"), "tokens": tokens,
            **({"lot": u["lot"]} if u.get("lot") else {}), **({"reparti": u["reparti"]} if u.get("reparti") else {}),
            "cout": round(cout, 6) if cout is not None else None,
            "prix_du": date_prix if cout is not None else None, "ancien": bool(ancien and cout is not None)})
        if u.get("service"):
            lignes.append((u["service"], u, cout, p))
    for g in list(services.values()) + [direction, orchestration]:
        _arrondir(g)
    gestion = 0.0  # le bureau ne consomme aucun token ; ses requêtes de prix ne coûtent que du temps
    total = sum(g["total"] for g in services.values()) + direction["total"] + orchestration["total"] + gestion
    return {
        **({"co2": avec_equivalences(total_co2.vue())} if total_co2.vue() else {}),
        "total": round(total, 6), "gestion": gestion,
        "sans_prix": sorted(sans_prix.values(), key=lambda x: x["modele"]),
        "services": services, "direction": direction, "orchestration": orchestration,
        "sources": _sources(services, lignes, r),
        "prix_du": max(dates) if dates else None,
        "avertissement": _avertissement(sans_prix, anciens),
        "partenaires": _arrondir_partenaires(partenaires),
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


INCOMPLET = " Des usages à prix inconnu ne sont pas comptés dans ce coût."


def _sources(services, lignes, r):
    """Les sources d'amélioration, par service (la direction n'en a pas)."""
    taches = _titres(r)
    out = []
    for sid, g in services.items():
        incomplet = {i: (INCOMPLET if t["sans_prix"] else "") for i, t in g["taches"].items()}
        couts = {i: t["total"] for i, t in g["taches"].items() if i != SANS and t["total"] > 0}
        # Tâches qui coûtent plus de trois fois la médiane du service.
        if couts:
            mediane = statistics.median(couts.values())
            for i, c in couts.items():
                if mediane > 0 and c > FACTEUR_TACHE_CHERE * mediane:
                    out.append({"id": id_source(sid, "tache_chere", i), "genre": "tache_chere", "service": sid,
                                "tache": i, "texte": f"Tâche « {_nom_tache(taches, i)} » : coût de "
                                                     f"{euros_en_clair(c)} pour une médiane de "
                                                     f"{euros_en_clair(mediane)} dans le service."
                                                     + incomplet[i]})
        out += _modele_trop_fort(sid, [x for x in lignes if x[0] == sid and x[3]], taches)
        # Tâches qui ont reçu plusieurs retours : la part du coût qu'elles représentent.
        for i, c in couts.items():
            retours = (taches.get(i) or {}).get("retours")
            n = len(retours) if isinstance(retours, list) else 0
            if n >= MIN_RETOURS and g["total"] > 0:
                part = round(100 * c / g["total"])
                out.append({"id": id_source(sid, "allers_retours", i), "genre": "allers_retours", "service": sid,
                            "tache": i, "texte": f"Tâche « {_nom_tache(taches, i)} » : {n} retours, "
                                                 f"{euros_en_clair(c)} ({part} % du coût du service)."
                                                 + incomplet[i]})
    out.sort(key=lambda s: (s["service"], s["genre"], s["tache"]))
    return out


def _modele_trop_fort(sid, lignes, taches):
    """Un usage du modèle le plus cher du service, à une étape où les autres usages sont, en médiane,
    d'un modèle moins cher. Une source par tâche."""
    if not lignes:
        return []
    niveau_de = {}  # modèle -> son niveau sur la période (le taux du jour ne doit pas en faire deux modèles)
    for _, u, _, p in lignes:
        niveau_de[u["modele"]] = max(niveau_de.get(u["modele"], 0.0), _niveau(p))
    lignes = [(s, u, c, niveau_de[u["modele"]]) for s, u, c, _ in lignes]
    plus_cher = max(n for _, _, _, n in lignes)
    niveaux = {}  # étape -> niveaux de tous ses usages
    for _, u, _, n in lignes:
        if u.get("etape"):
            niveaux.setdefault(u["etape"], []).append(n)
    medianes = {}  # étape -> médiane des autres usages qu'un usage du modèle le plus cher
    for etape, liste in niveaux.items():
        autres = list(liste)
        if plus_cher in autres:
            autres.remove(plus_cher)
        medianes[etape] = statistics.median(autres) if autres else None
    par_tache = {}
    for _, u, _, n in lignes:
        etape, tache = u.get("etape"), u.get("tache")
        if not etape or not tache or n < plus_cher:
            continue
        mediane = medianes.get(etape)
        if mediane is not None and n > mediane:
            par_tache.setdefault(tache, {})[etape] = (u["modele"], n, mediane)
    out = []
    for tache, etapes in par_tache.items():
        constats = "; ".join(f"étape « {e} » faite avec « {m} » ({euros_en_clair(n)}/M de tokens entrée + "
                             f"sortie) quand les autres usages de l'étape sont en médiane à {euros_en_clair(med)}/M"
                             for e, (m, n, med) in sorted(etapes.items()))
        out.append({"id": id_source(sid, "modele_trop_fort", tache), "genre": "modele_trop_fort",
                    "service": sid, "tache": tache,
                    "texte": f"Tâche « {_nom_tache(taches, tache)} » : {constats}."})
    return out


def couts_fonctionnalite(usages, prix_de, r, fonctionnalite):
    """Le coût de chaque tâche d'une fonctionnalité, depuis toujours (pas de période : c'est le prix de la
    fonctionnalité). Un usage sans prix connu n'est compté dans aucun euro mais sa tâche le signale (`sans_prix`)."""
    taches = {t["id"]: t for t in r.get("taches") or [] if t.get("fonctionnalite") == fonctionnalite}
    if any(isinstance(f, dict) and f.get("id") == fonctionnalite and f.get("etape") == "deplacee"
           for f in r.get("fonctionnalites") or []):
        taches = {}   # partie dans un autre projet : ce qui y a été fait n'est pas un coût de livraison ici
    lignes, total_co2 = {}, Cumul()
    for u in usages:
        if u.get("tache") not in taches or u.get("genre") == "partenaire":   # des tokens seulement
            continue
        t = taches[u["tache"]]
        ligne = lignes.setdefault(u["tache"], {"id": u["tache"], "titre": t.get("titre") or u["tache"],
                                              "total": 0.0, "sans_prix": 0, "modeles": {}, "tokens": 0,
                                              "lignes": t.get("lignes") if isinstance(t.get("lignes"), int) else None})
        ligne["tokens"] += sum(u.get(c) or 0 for c in COMPTEURS)   # l'échelle, même sans prix connu
        ligne.setdefault("_co2", Cumul()).ajouter(u["modele"], u.get("sortie") or 0)
        total_co2.ajouter(u["modele"], u.get("sortie") or 0)
        p, _, _ = prix_de(u["modele"], u.get("t_prix") or u.get("t"))
        if not p:
            ligne["sans_prix"] += 1
            continue
        c = _cout(u, p)
        ligne["total"] += c
        ligne["modeles"][u["modele"]] = ligne["modeles"].get(u["modele"], 0.0) + c
    ordre = list(taches)
    sortie = sorted(lignes.values(), key=lambda x: ordre.index(x["id"]))
    for x in sortie:
        x["total"] = round(x["total"], 6)
        x["modeles"] = {k: round(v, 6) for k, v in x["modeles"].items()}
        c = x.pop("_co2").vue()
        if c:
            x["co2"] = c
    co2 = avec_equivalences(total_co2.vue())
    return {**({"co2": co2} if co2 else {}),
            "total": round(sum(x["total"] for x in sortie), 6), "taches": sortie,
            "sans_prix": sum(x["sans_prix"] for x in sortie), "tokens": sum(x["tokens"] for x in sortie),
            # aucune ligne notée : inconnu, pas zéro
            "lignes": sum(x["lignes"] for x in sortie if x["lignes"] is not None)
                      if any(x["lignes"] is not None for x in sortie) else None}


def cout_des_usages(usages, prix_de, date_iso=None):
    """`{total, sans_prix, tokens}` de quelques usages (un usage sans prix connu n'est compté dans aucun euro)."""
    total, sans_prix, tokens = 0.0, 0, 0
    for u in usages:
        tokens += sum(u.get(c) or 0 for c in COMPTEURS)
        p, _, _ = prix_de(u["modele"], u.get("t_prix") or u.get("t") or date_iso)
        if not p:
            sans_prix += 1
            continue
        total += _cout(u, p)
    return {"total": round(total, 6), "sans_prix": sans_prix, "tokens": tokens}


def couts_taches(usages, prix_de, r):
    """Le coût de chaque tâche du projet, depuis toujours : `{id: {total, sans_prix, tokens}}` (les tâches sans usage
    noté n'y sont pas). Les tokens d'un partenaire ne sont pas des euros ici."""
    ids = {t["id"] for t in r.get("taches") or []}
    par_tache = {}
    for u in usages:
        if u.get("tache") in ids and u.get("genre") != "partenaire":
            par_tache.setdefault(u["tache"], []).append(u)
    return {tid: cout_des_usages(us, prix_de) for tid, us in par_tache.items()}
