"""Le rapport du banc : par façon de faire, les appels, les tokens, le coût, la part orchestration / production, les
questions, le résultat attendu et les écarts ; puis les trois objectifs de la conception (section 9), tenus ou non.

`resultats` : `{"moteur": F, "orchestrateur_actuel": F, "agent_seul": F}` (chacun facultatif), où `F` est
    {"appels": int, "tokens": int, "euros_orchestration": float | None, "euros_production": float | None,
     "euros_total": float | None, "questions": int, "attendu": [bool, …] (dans l'ordre de `attendu`), "ecarts": [textes]}
Un chiffre absent s'écrit « non mesuré » : jamais zéro.
"""
SEUIL_ORCHESTRATION_EUROS = 0.10
NOMS = (("moteur", "Le moteur"), ("moteur_vrai", "Le moteur, agents réels (passage complet)"),
        ("orchestrateur_actuel", "L'orchestrateur actuel (mesure de l'essai)"), ("agent_seul", "Un agent seul"))


def _n(v):
    return "non mesuré" if v is None else f"{v:,}".replace(",", " ")


def _euros(v):
    return "non mesuré" if v is None else f"{v:.2f} €".replace(".", ",")


def _part(f):
    o, p = f.get("euros_orchestration"), f.get("euros_production")
    if o is None or p is None or o + p == 0:
        return "non mesuré"
    return f"{100 * o / (o + p):.0f} % orchestration / {100 * p / (o + p):.0f} % production"


def objectifs(resultats, attendu):
    """Les trois objectifs : `[(texte, "tenu" | "non tenu" | "non mesuré", détail)]`. L'orchestration se lit sur le moteur
    rejoué ; le total et le résultat, sur le passage en vrai quand il existe (le rejoueur ne produit rien de neuf)."""
    m, a, o = resultats.get("moteur") or {}, resultats.get("agent_seul") or {}, resultats.get("orchestrateur_actuel") or {}
    vrai = resultats.get("moteur_vrai")
    complet = vrai or m
    passage = " (passage en vrai)" if vrai else ""
    lignes = []
    orch = m.get("euros_orchestration")
    lignes.append((f"Coût de l'orchestration du moteur ≤ {SEUIL_ORCHESTRATION_EUROS:.2f} €".replace(".", ","),
                   "non mesuré" if orch is None else ("tenu" if orch <= SEUIL_ORCHESTRATION_EUROS else "non tenu"),
                   f"{_euros(orch)}, contre {_euros(o.get('euros_orchestration'))} pour l'orchestrateur actuel"))
    t_m, t_a = complet.get("euros_total"), a.get("euros_total")
    lignes.append(("Coût total du moteur < coût total de l'agent seul (passage complet)",
                   "non mesuré" if t_m is None or t_a is None else ("tenu" if t_m < t_a else "non tenu"),
                   f"{_euros(t_m)}{passage} contre {_euros(t_a)}"))
    coche = complet.get("attendu")
    if coche is None or len(coche) != len(attendu):
        lignes.append(("Même résultat : tout l'attendu, et pas plus de questions que dans l'essai", "non mesuré",
                       "résultat attendu non coché"))
    else:
        manque = [attendu[i] for i, ok in enumerate(coche) if not ok]
        q_m, q_o = complet.get("questions"), o.get("questions")
        trop = q_m is not None and q_o is not None and q_m > q_o
        etat = "tenu" if not manque and not trop else "non tenu"
        detail = (f"manque : {'; '.join(manque)}" if manque else "tout l'attendu est là") + \
                 f" ; questions : {_n(q_m)} (essai : {_n(q_o)})" + passage
        lignes.append(("Même résultat : tout l'attendu, et pas plus de questions que dans l'essai", etat, detail))
    return lignes


def rapport(resultats, attendu):
    """Le rapport, en Markdown."""
    sortie = ["# Rapport du banc d'essai", ""]
    for cle, nom in NOMS:
        f = resultats.get(cle)
        sortie += [f"## {nom}", ""]
        if not f:
            sortie += ["Non joué.", ""]
            continue
        sortie += [f"- Appels : {_n(f.get('appels'))}", f"- Tokens : {_n(f.get('tokens'))}",
                   f"- Coût : {_euros(f.get('euros_total'))} (orchestration {_euros(f.get('euros_orchestration'))}, "
                   f"production {_euros(f.get('euros_production'))})", f"- Part : {_part(f)}",
                   f"- Questions posées à l'utilisateur : {_n(f.get('questions'))}"]
        coche = f.get("attendu")
        if coche is not None and len(coche) == len(attendu):
            sortie += ["- Résultat attendu :"] + [f"  - [{'x' if ok else ' '}] {texte}" for ok, texte in zip(coche, attendu)]
        else:
            sortie += ["- Résultat attendu : non coché"]
        ecarts = f.get("ecarts") or []
        if ecarts:
            sortie += [f"- Écarts avec l'essai ({len(ecarts)}) :"] + [f"  - {e}" for e in ecarts]
        sortie.append("")
    sortie += ["## Les objectifs", ""]
    for texte, etat, detail in objectifs(resultats, attendu):
        sortie.append(f"- **{etat.capitalize()}** — {texte} ({detail})")
    return "\n".join(sortie) + "\n"
