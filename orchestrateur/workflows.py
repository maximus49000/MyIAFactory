"""Les workflows d'un projet : un par fonctionnalité, plus le workflow principal du projet.

Un projet existant n'a que `genre` et `flux` : il se lit comme un projet à un seul workflow, `principal`. Un projet qui
a une clé `workflows` y ajoute ceux de ses fonctionnalités (`{id, fonctionnalite, genre, flux}`), dans l'ordre de leur
création. Les identifiants d'étape sont uniques dans tout le projet : ce sont les identifiants des colonnes du tableau.
Fonctions pures sur le dict rendu par `factory.lire`.
"""

PRINCIPAL = "principal"
CLE_VALIDATION = "validation"   # `{"id", "nom", "validation": true}` : une étape où le Directeur valide, sans agent
ETAPES_CACHANT_LES_COLONNES = ("terminee", "deplacee")   # une fonctionnalité finie ou partie ailleurs n'a plus de colonnes


def est_validation(etape):
    """Vrai pour une étape de validation du Directeur (sans rôle ni service)."""
    return isinstance(etape, dict) and etape.get(CLE_VALIDATION) is True


# le modèle nécessaire d'une étape ; Fable n'y est qu'une proposition (la tâche attend l'accord du Directeur)
MODELES_D_ETAPE = ("Haiku", "Sonnet", "Opus", "Fable")
# Le lieu d'une étape d'agent (facultatif) : `local`, elle exige les logiciels du poste (un agent local la fait) ;
# `indifférent`, n'importe quel agent, cloud compris (écrit, il l'emporte sur le `Lieu :` du métier). Absent : le
# `Lieu :` du métier de l'étape, comme avant. Jamais sur une validation du Directeur.
LIEU_LOCAL, LIEU_INDIFFERENT = "local", "indifférent"
LIEUX_D_ETAPE = (LIEU_LOCAL, LIEU_INDIFFERENT)


def lieu(etape):
    """Le `lieu` écrit d'une étape d'agent (`local` ou `indifférent`), ou `None` (absent, inconnu, validation)."""
    if not isinstance(etape, dict) or est_validation(etape):
        return None
    return etape.get("lieu") if etape.get("lieu") in LIEUX_D_ETAPE else None


def etape_ecrite(e):
    """L'étape telle que la factory la garde : `{id, nom, validation}` ou `{id, nom, role, service}`, avec le modèle
    nécessaire de l'étape (`modele`) et sa `justification` quand le workflow les a posés, et son `lieu` s'il est écrit."""
    if est_validation(e):
        return {"id": e["id"], "nom": e["nom"], CLE_VALIDATION: True}
    sortie = {c: e[c] for c in ("id", "nom", "role", "service")}
    if isinstance(e.get("modele"), str) and e["modele"] in MODELES_D_ETAPE:
        sortie["modele"] = e["modele"]
        if isinstance(e.get("justification"), str) and e["justification"].strip():
            sortie["justification"] = e["justification"].strip()
    if lieu(e):
        sortie["lieu"] = e["lieu"]
    return sortie


def etapes_d_agent(flux):
    """Les étapes du flux qui sont tenues par un agent (sans les validations du Directeur)."""
    return [e for e in flux if not est_validation(e)]


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


def de_creation(f, genre=None):
    """Le workflow de genre du projet (défini à sa création) : sans fonctionnalité, ni le principal ; `genre` ou, à
    défaut, le genre du projet. None s'il n'y en a pas."""
    voulu = genre or f.get("genre")
    if not voulu:
        return None
    return next((w for w in tous(f) if w["fonctionnalite"] is None and w["id"] != PRINCIPAL
                 and w.get("genre") == voulu), None)


def copie_pour(w, fid):
    """La copie d'un workflow de genre pour la fonctionnalité `fid` : étapes préfixées par `<fid>-`."""
    return {"id": f"w-{fid}", "fonctionnalite": fid, "genre": w["genre"],
            "flux": [{**e, "id": f"{fid}-{e['id']}"} for e in w["flux"]]}


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
        if w["fonctionnalite"] is None and w["id"] != PRINCIPAL:
            continue   # un workflow de genre n'a pas de colonnes : ses copies par fonctionnalité en ont
        for e in w["flux"]:
            c = {"id": e["id"], "nom": e["nom"], "genre": w.get("genre"), "workflow": w["id"]}
            if est_validation(e):
                c[CLE_VALIDATION] = True
            if lieu(e):        # écrit seulement quand l'étape le porte : un projet sans lieu garde ses colonnes
                c["lieu"] = e["lieu"]
            sortie.append(c)
    sortie.append({"id": "fait", "nom": "Fait", "terminee": True})
    return sortie
