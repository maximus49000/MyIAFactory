"""Le modèle nécessaire d'une tâche, et le modèle de la fiche d'un agent comme plafond (conception
`2026-11-12-modele-par-tache-design.md`). Fonctions pures, sans IA.

Le modèle nécessaire est une propriété de l'étape du workflow : `modele` (Haiku, Sonnet ou Opus, jamais Fable) posé
avec sa `justification` quand le workflow est proposé ; à défaut, déduit de la nature de l'étape (la table du
recrutement) ; nature inconnue : le modèle du rôle. Un agent prend toute tâche de son rôle dont le modèle nécessaire est
au plus son plafond (le modèle de sa fiche) et la fait tourner exactement sur ce modèle.
"""
from orchestrateur import recrutement as rc
from orchestrateur import workflows as wf

MODELES = rc.MODELES                       # les modèles qu'un outil choisit (jamais Fable)
FABLE = "Fable"
# Une étape (ou une montée depuis Opus) peut demander Fable : une proposition, jamais un départ sans l'accord du
# Directeur pour cette tâche (décision `fable_tache`) ; sans accord, la tâche part sur Opus.
MODELES_D_ETAPE = MODELES + (FABLE,)
ORDRE = ("haiku", "sonnet", "opus", "fable")
PLAFOND_PAR_DEFAUT = rc.PLAFOND_PAR_DEFAUT  # un nouvel agent : Opus (Fable seulement avec l'accord du Directeur)
ETAPES_DE_FLUX = "flux:"
# Les tâches que le moteur crée hors du flux et qui refont le travail d'un rôle : le modèle de l'étape de ce rôle.
ETAPES_DU_ROLE = ("relecture", "correction", "retour", "demande")
# Cadrage, prototype, installation : le modèle de la fiche de l'agent, comme avant (`None`).


def rang(modele):
    """Le rang d'un modèle (Haiku < Sonnet < Opus < Fable) ; un nom inconnu compte comme Sonnet."""
    m = str(modele or "").lower()
    return next((i for i, n in enumerate(ORDRE) if n in m), 1)


def nom(modele):
    """Le nom affiché d'un modèle (`sonnet` → `Sonnet`)."""
    return ORDRE[rang(modele)].capitalize()


def plafonne(modele, plafond):
    """Le modèle, ramené au plafond s'il le dépasse."""
    return modele if rang(modele) <= rang(plafond) else plafond


def de_l_etape(e, fiches=()):
    """`{modele, raison, source}` d'une étape d'agent (`None` pour une validation du Directeur). `source` : `workflow`
    (posé avec le workflow), `deduit` (nature de l'étape ou du rôle) ou `role` (nature inconnue : le modèle du rôle,
    d'après `fiches`, Sonnet sans fiche)."""
    if not isinstance(e, dict) or wf.est_validation(e):
        return None
    if isinstance(e.get("modele"), str) and e["modele"] in MODELES_D_ETAPE:
        j = e.get("justification")
        return {"modele": e["modele"], "source": "workflow",
                "raison": j.strip() if isinstance(j, str) and j.strip() else "fixé avec le workflow"}
    n = rc._nature(f"{e.get('nom') or ''} {e.get('id') or ''}") or rc._nature(str(e.get("role") or ""))
    if n:
        return {"modele": n[0], "source": "deduit", "raison": f"déduit de l'étape : {n[1]}"}
    modele, raison = rc.modele_du_role([x for x in fiches if x.get("role") and x["role"] == e.get("role")])
    return {"modele": modele, "source": "role", "raison": f"nature de l'étape inconnue : {raison}"}


def _etape(f, t, fonctionnalites):
    etape = str(t.get("etape") or "")
    if etape.startswith(ETAPES_DE_FLUX):
        sid = etape[len(ETAPES_DE_FLUX):]
        return next((e for w in wf.tous(f) for e in w["flux"] if e.get("id") == sid), None)
    if etape in ETAPES_DU_ROLE and t.get("role"):
        fonc = next((x for x in fonctionnalites if x.get("id") == t.get("fonctionnalite")), None)
        w = wf.de_la_fonctionnalite(f, fonc)
        return next((e for e in (w or {}).get("flux") or [] if not wf.est_validation(e) and e.get("role") == t["role"]),
                    None)
    return None


def etape_de_la_tache(f, t, fonctionnalites=()):
    """L'étape du workflow que la tâche `t` fait (sa `service` en est le service), ou `None`."""
    return _etape(f, t, fonctionnalites)


def lieu_de_la_tache(f, t, fonctionnalites=()):
    """Le `lieu` écrit de l'étape que la tâche fait (`local` ou `indifférent`), ou `None` (pas d'étape, pas de lieu)."""
    return wf.lieu(_etape(f, t, fonctionnalites))


def lieu_impose(lieu_etape, lieu_metier):
    """Le lieu que la tâche impose à son agent : celui de son étape quand il est écrit (`local` ; `indifférent` : aucun,
    même si le métier est réservé), sinon celui du métier (`local`, `cloud` ou `None`)."""
    if lieu_etape == wf.LIEU_LOCAL:
        return "local"
    if lieu_etape == wf.LIEU_CLOUD:
        return "cloud"
    if lieu_etape == wf.LIEU_INDIFFERENT:
        return None
    return lieu_metier if lieu_metier in ("local", "cloud") else None


def de_la_tache(f, t, fiches, fonctionnalites=()):
    """`{modele, raison, source, ramene}` : le modèle nécessaire de la tâche `t` (montée comprise), ou `None` quand
    c'est le modèle de la fiche de l'agent qui vaut (cadrage, prototype, installation, tâche sans étape connue). Si aucun
    agent du rôle n'a un plafond suffisant, le modèle est ramené au plus haut plafond du rôle (`ramene`) : la tâche part
    au lieu d'attendre."""
    e = _etape(f, t, fonctionnalites)
    m = de_l_etape(e, fiches) if e is not None else None
    if m is None:
        return None
    m = dict(m, ramene=False)
    montee = t.get("montee")
    if isinstance(montee, dict) and isinstance(montee.get("a"), str) and montee["a"].strip():
        m.update(modele=nom(montee["a"]), source="montee",
                 raison=f"monté depuis {montee.get('de') or '?'} : {montee.get('raison') or 'montée de modèle'}")
    du_role = [x for x in fiches if x.get("role") and x["role"] == t.get("role")]   # un polyvalent n'a pas de plafond
    if du_role:
        haut = max((x["modele"] for x in du_role), key=rang)
        if rang(haut) < rang(m["modele"]):
            m.update(modele=nom(haut), ramene=True,
                     raison=f"{m['raison']} ; ramené au plafond de l'équipe ({nom(haut)}) : aucun agent du rôle au-dessus")
    return m


def modeles_sur_les_etapes(flux, nouveaux):
    """`(flux, agents)` d'un workflow proposé : les nouveaux agents ont le plafond Opus (`PLAFOND_PAR_DEFAUT`) ; le
    modèle justifié d'un nouvel agent (une proposition à l'ancienne forme) va sur les étapes de son rôle qui n'ont pas
    déjà le leur. Les étapes gardent `modele` et `justification` ; rien n'est modifié en place."""
    par_role = {}
    for a in nouveaux:
        if a.get("modele") in MODELES:
            j = a.get("justification")
            par_role.setdefault(a.get("role"), (a["modele"], j.strip() if isinstance(j, str) and j.strip()
                                                else "le modèle proposé pour le rôle"))
    sortie = []
    for e in flux:
        e = dict(e)
        if not wf.est_validation(e) and e.get("modele") not in MODELES and e.get("role") in par_role:
            e["modele"], e["justification"] = par_role[e["role"]]
        sortie.append(e)
    return sortie, [dict(a, modele=PLAFOND_PAR_DEFAUT) for a in nouveaux]


def estime(e, agents):
    """Le modèle d'une étape pour l'estimation d'un workflow pas encore en place : son modèle nécessaire (posé, sinon
    déduit ; nature inconnue : celui du premier agent du rôle), ramené au plus haut plafond des `agents` du rôle ; Fable
    est compté Opus (l'accord du Directeur n'est pas donné). `None` pour une validation, ou sans agent du rôle."""
    du_role = [a for a in agents if isinstance(a, dict) and a.get("role") == (e or {}).get("role")]
    m = de_l_etape(e)
    if m is None or not du_role:
        return None
    modele = m["modele"] if m["source"] != "role" else du_role[0].get("modele")
    if not all(a.get("sans_plafond") for a in du_role):    # un agent polyvalent (métier) n'a pas de plafond
        modele = plafonne(modele, max((a.get("modele") for a in du_role), key=rang))
    return "Opus" if rang(modele) >= rang(FABLE) else modele   # Fable compté Opus tant que l'accord n'est pas donné


def possibles(fiches, role, modele):
    """Les fiches du rôle dont le plafond suffit au modèle nécessaire, le plus petit plafond d'abord (à égalité, l'ordre
    des fiches) ; sans modèle, toutes les fiches du rôle dans leur ordre. Puis les agents polyvalents (fiche sans rôle),
    dans leur ordre : ils prennent n'importe quel métier et n'ont pas de plafond. Un projet sans agent polyvalent : rien
    ne change."""
    du_role = [x for x in fiches if x.get("role") and x["role"] == role]
    polyvalents = [x for x in fiches if not x.get("role") and not x.get("retrait_prevu")
                  and not x.get("retire")]   # un retrait prévu ou fait n'est plus choisi
    if not modele:
        return du_role + polyvalents
    return sorted((x for x in du_role if rang(x.get("modele")) >= rang(modele)),
                  key=lambda x: rang(x.get("modele"))) + polyvalents
