"""Des résultats bruts d'un passage aux chiffres du rapport (`banc.rapport`) : appels, tokens, euros, questions."""
from banc import construire
from banc.reference import COMPTEURS, cout_euros


def _tokens(usages):
    return sum(u.get(c) or 0 for u in usages for c in COMPTEURS)


def _questions(suivi):
    """Les messages d'agents qui attendent une réponse de l'utilisateur."""
    return sum(1 for f in suivi.get("fonctionnalites") or [] for m in f.get("discussion") or []
               if m.get("auteur") != "utilisateur" and m.get("attend") is True)


def mesure_moteur(r, scenario, prix_de=None, date_iso=None):
    """Le moteur joué (`banc.jouer.jouer_moteur`) : l'orchestration (ses appels de jugement) à part de la production
    (les rapports rejoués). `attendu` : l'attendu du scénario coché d'après le suivi obtenu."""
    jug, prod = r["usages_jugement"], r["usages_production"]
    f = {"appels": len(r["appels"]), "tokens": _tokens(jug) + _tokens(prod), "questions": _questions(r["suivi"]),
         "ecarts": list(r["ecarts"]), "euros_orchestration": None, "euros_production": None, "euros_total": None}
    if prix_de:
        f["euros_orchestration"], _ = cout_euros(jug, prix_de, date_iso)
        f["euros_production"], _ = cout_euros(prod, prix_de, date_iso)
        f["euros_total"] = round(f["euros_orchestration"] + f["euros_production"], 6)
    obtenu = construire._attendu(r["suivi"], scenario.gestes)
    f["attendu"] = [x in obtenu for x in scenario.attendu]
    return f


def mesure_orchestrateur_actuel(reference, scenario, prix_de=None, date_iso=None):
    """La mesure de l'essai (`banc.reference`) : la conversation orchestratrice ; la production, ce que ses sous-agents
    ont coûté (les usages des rapports du scénario)."""
    production = [r["usage"] for r in scenario.rapports]
    f = {"appels": reference["appels"], "tokens": reference["tokens"], "questions": (scenario.donnees.get("essai") or {}).get("questions"),
         "euros_orchestration": reference.get("euros"), "euros_production": None, "euros_total": None,
         "attendu": [True] * len(scenario.attendu), "ecarts": []}
    if prix_de:
        f["euros_production"], _ = cout_euros(production, prix_de, date_iso)
        if f["euros_orchestration"] is not None:
            f["euros_total"] = round(f["euros_orchestration"] + f["euros_production"], 6)
    return f


def mesure_agent_seul(r, scenario, prix_de=None, date_iso=None):
    """L'agent seul : tout est de la production (il n'orchestre rien)."""
    f = {"appels": r["appels"], "tokens": _tokens(r["usages"]), "questions": r["questions"], "ecarts": [],
         "euros_orchestration": 0.0 if prix_de else None, "euros_production": None, "euros_total": None,
         "attendu": None}
    if r.get("erreur"):
        f["ecarts"].append("Passage interrompu : " + r["erreur"])
    if prix_de:
        f["euros_production"], _ = cout_euros(r["usages"], prix_de, date_iso)
        f["euros_total"] = f["euros_production"]
    return f
