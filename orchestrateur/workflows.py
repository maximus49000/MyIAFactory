"""Les workflows d'un projet : un par fonctionnalité, plus le workflow principal du projet.

Un projet existant n'a que `genre` et `flux` : il se lit comme un projet à un seul workflow, `principal`. Un projet qui
a une clé `workflows` y ajoute ceux de ses fonctionnalités (`{id, fonctionnalite, genre, flux}`), dans l'ordre de leur
création. Les identifiants d'étape sont uniques dans tout le projet : ce sont les identifiants des colonnes du tableau.
Fonctions pures sur le dict rendu par `factory.lire`.
"""

PRINCIPAL = "principal"
ETAPES_CACHANT_LES_COLONNES = ("terminee", "deplacee")   # une fonctionnalité finie ou partie ailleurs n'a plus de colonnes


def tous(f):
    """Les workflows du projet `{id, fonctionnalite, genre, flux}`, le principal d'abord (rien s'il n'a pas de flux)."""
    sortie = []
    if f.get("flux"):
        sortie.append({"id": PRINCIPAL, "fonctionnalite": None, "genre": f.get("genre"), "flux": f["flux"]})
    sortie += [dict(w) for w in f.get("workflows") or []]
    return sortie


def de_la_fonctionnalite(f, fonc):
    """Le workflow de `fonc["workflow"]`, sinon le principal (None si le projet n'en a pas)."""
    voulu = (fonc or {}).get("workflow")
    ws = tous(f)
    if voulu:
        w = next((x for x in ws if x["id"] == voulu), None)
        if w is not None:
            return w
    return next((x for x in ws if x["id"] == PRINCIPAL), None)


def genre_de(f, fonc):
    """Le genre de la fonctionnalité, sinon celui du projet."""
    return (fonc or {}).get("genre") or f.get("genre")


def ids_etapes(f):
    """Toutes les étapes de tous les workflows (les identifiants de colonnes, finies ou non)."""
    return [e["id"] for w in tous(f) for e in w["flux"]]


def premiere_etape(f, fonc):
    """La première étape du workflow de la fonctionnalité (None si le projet n'a aucun workflow)."""
    w = de_la_fonctionnalite(f, fonc)
    return w["flux"][0]["id"] if w and w["flux"] else None


def colonnes(f, fonctionnalites):
    """Les colonnes du tableau : cadrage, les étapes des workflows dont la fonctionnalité est en cours (le principal
    toujours), puis fait."""
    par_id = {x["id"]: x for x in fonctionnalites}
    sortie = [{"id": "cadrage", "nom": "Cadrage"}]
    for w in tous(f):
        fonc = par_id.get(w["fonctionnalite"]) if w["fonctionnalite"] else None
        if fonc is not None and fonc.get("etape") in ETAPES_CACHANT_LES_COLONNES:
            continue
        for e in w["flux"]:
            sortie.append({"id": e["id"], "nom": e["nom"], "genre": w.get("genre"), "workflow": w["id"]})
    sortie.append({"id": "fait", "nom": "Fait", "terminee": True})
    return sortie
