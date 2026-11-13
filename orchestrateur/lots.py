"""Les lots par modèle : regrouper les tâches prêtes d'un même modèle (et d'un même lieu) derrière un seul agent,
un seul départ et un seul contexte, puis répartir le coût du lot entre ses tâches.

Pur : aucune entrée-sortie. L'outil de l'orchestrateur (`lancer lots`, `lancer usage`) s'en sert.
"""
from bureau.statuts import TRES_ANCIEN, lire_date

MAX_TACHES_LOT = 5
COMPTEURS = ("entree", "sortie", "cache_lecture", "cache_ecriture")
MIN_MESURES = 10   # en dessous, la taille conseillée reste le maximum : rien n'est assez mesuré
ROLE_RELECTEUR = "relecteur"


def _tokens(usage):
    return sum(usage.get(c) or 0 for c in COMPTEURS)


def _cout_par_tache(usages):
    """[tokens d'une tâche] : les usages d'une même tâche s'additionnent ; un usage sans tâche compte seul."""
    par_tache, seuls = {}, []
    for u in usages:
        if u.get("tache"):
            par_tache[u["tache"]] = par_tache.get(u["tache"], 0) + _tokens(u)
        else:
            seuls.append(_tokens(u))
    return list(par_tache.values()) + seuls


def taille_conseillee(usages, modele):
    """La taille d'un lot de ce modèle, d'après les mesures du projet.

    `usages` : les usages du projet, chacun avec `modele`, ses compteurs, et facultativement `tache`, `lot` (id du lot,
    absent pour une tâche faite seule) et `rang` (rang de la tâche dans son lot, à partir de 1). On compare le coût
    moyen en tokens d'une tâche faite seule à celui d'une tâche au rang k d'un lot. Rend le plus grand k, de 1 à
    `MAX_TACHES_LOT`, tel que chaque rang jusqu'à k coûte en moyenne au plus autant qu'une tâche seule (un rang sans
    mesure ne coupe pas). Moins de 10 tâches seules ou moins de 10 tâches en lot : `MAX_TACHES_LOT`."""
    du_modele = [u for u in usages if u.get("modele") == modele]
    seules = _cout_par_tache([u for u in du_modele if not u.get("lot")])
    en_lot = [u for u in du_modele if u.get("lot") and isinstance(u.get("rang"), int) and u["rang"] >= 1]
    if len(seules) < MIN_MESURES or len(_cout_par_tache(en_lot)) < MIN_MESURES:
        return MAX_TACHES_LOT
    seule = sum(seules) / len(seules)
    taille = 1
    for k in range(1, MAX_TACHES_LOT + 1):
        rang = _cout_par_tache([u for u in en_lot if u["rang"] == k])
        if rang and sum(rang) / len(rang) > seule:
            break
        taille = k
    return taille


def former(taches, tailles=None, premier=1):
    """Les lots des tâches prêtes. Chaque tâche : `{"id", "modele", "lieu", "role", "depend_de": [ids]}`, dans l'ordre
    d'origine. Rend `[{"lot": "L<n>", "modele", "lieu", "taches": [ids]}]`, numérotés à partir de `premier`.

    Glouton et stable : tant qu'il reste des tâches, on prend celles dont les dépendances sont formées dans un lot
    précédent ou placées plus tôt dans le lot courant (un lot s'exécute dans l'ordre, d'une traite : une chaîne d'un
    même modèle reste une seule conversation) ; on continue le lot courant avec la première tâche prête de même modèle et même lieu (dans l'ordre
    d'origine), sinon on ouvre un lot sur la première tâche prête. Une relecture forme toujours un lot à elle seule ;
    un lot s'arrête à `tailles[modele]` (au plus `MAX_TACHES_LOT`). Une tâche d'une étape « regroupée » porte `groupe`
    (l'id de l'étape) : son lot (`regroupe: True`) réunit toutes les tâches prêtes de cette étape, sans limite de taille,
    et jamais une tâche d'une autre étape. Lève `ValueError` sur un cycle ou une
    dépendance inconnue."""
    tailles = tailles or {}
    ids = [t["id"] for t in taches]
    if len(set(ids)) != len(ids):
        raise ValueError("Identifiants de tâche en double.")
    for t in taches:
        inconnues = [d for d in t.get("depend_de") or [] if d not in ids]
        if inconnues:
            raise ValueError(f"La tâche {t['id']} dépend de tâches inconnues : {', '.join(inconnues)}.")
    restantes, formees, lots = list(taches), set(), []
    while restantes:
        courant, avant = None, set(formees)   # `avant` : ce que les lots précédents ont formé
        while True:
            dispo = avant | set(courant["taches"]) if courant else avant
            pretes = [t for t in restantes if all(d in dispo for d in t.get("depend_de") or [])]
            if courant is None:
                if not pretes:
                    noms = ", ".join(t["id"] for t in restantes)
                    raise ValueError(f"Cycle de dépendances entre les tâches : {noms}.")
                t = pretes[0]
                courant = {"lot": f"L{premier + len(lots)}", "modele": t["modele"], "lieu": t["lieu"], "taches": [t["id"]]}
                groupe = t.get("groupe")
                if groupe:      # une étape « regroupée » : un lot qui ne se coupe pas (voir `moteur.regles`)
                    courant["regroupe"] = True
                restantes.remove(t)
                if t.get("role") == ROLE_RELECTEUR:
                    break
                continue
            # un lot « regroupé » garde toutes les tâches prêtes de son étape (sans limite de taille) et n'en reçoit
            # aucune d'une autre étape ; un lot ordinaire n'en reçoit aucune d'une étape regroupée
            taille = max(1, min(tailles.get(courant["modele"], MAX_TACHES_LOT), MAX_TACHES_LOT))
            if len(courant["taches"]) >= taille and not groupe:
                break
            suite = next((t for t in pretes if t["modele"] == courant["modele"] and t["lieu"] == courant["lieu"]
                          and t.get("groupe") == groupe and t.get("role") != ROLE_RELECTEUR), None)
            if suite is None:
                break
            courant["taches"].append(suite["id"])
            restantes.remove(suite)
        lots.append(courant)
        formees.update(courant["taches"])
    return lots


def _secondes(debut, fin):
    """La durée en secondes entre deux dates ISO, ou `None` si l'une manque, est illisible ou n'est pas positive."""
    if not isinstance(debut, str) or not isinstance(fin, str):
        return None
    d, f = lire_date(debut), lire_date(fin)
    if d == TRES_ANCIEN or f == TRES_ANCIEN:
        return None
    try:
        duree = (f - d).total_seconds()
    except TypeError:   # une date avec fuseau et une sans
        return None
    return duree if duree > 0 else None


def mode_repartition(taches):
    """`"temps"` quand chaque tâche a une durée positive, sinon `"egal"` (parts égales)."""
    return "temps" if taches and all(_secondes(t.get("debut"), t.get("fin")) is not None for t in taches) else "egal"


def repartir(total, taches):
    """Répartit chaque compteur de `total` entre les tâches du lot, au prorata des durées `fin - debut` (à parts égales
    si une durée manque ou vaut 0), en entiers, par la méthode des plus forts restes : la somme des parts vaut
    exactement le total. `taches` : `[{"id", "debut", "fin"}]`. Rend `{id: {compteur: part}}`."""
    if not taches:
        return {}
    if mode_repartition(taches) == "temps":
        poids = [round(_secondes(t["debut"], t["fin"]) * 1000) or 1 for t in taches]
    else:
        poids = [1] * len(taches)
    somme = sum(poids)
    parts = {t["id"]: {} for t in taches}
    for compteur in COMPTEURS:
        valeur = int(total.get(compteur) or 0)
        bases = [valeur * p // somme for p in poids]
        restes = [valeur * p % somme for p in poids]
        manque = valeur - sum(bases)
        ordre = sorted(range(len(taches)), key=lambda k: (-restes[k], k))
        for k in ordre[:manque]:
            bases[k] += 1
        for t, part in zip(taches, bases):
            parts[t["id"]][compteur] = part
    return parts
