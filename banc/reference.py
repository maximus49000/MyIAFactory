"""La mesure de référence : ce que la conversation orchestratrice de l'essai a consommé (sous-agents exclus).

Un appel = un message distinct du modèle dans la transcription (un message rejoué ne compte qu'une fois). Les messages
des sous-agents (`isSidechain`) et leurs fichiers (`subagents/`) ne sont pas lus. Le coût en euros vient des prix du
bureau (`bureau/prix.py`, `bureau/cout.py`).
"""
import json
from pathlib import Path

from bureau import cout
from orchestrateur.transcriptions import CHAMPS

COMPTEURS = tuple(v for _, v in CHAMPS)


def reference(transcription, prix_de=None, date_iso=None):
    """`{"appels", "tokens", "par_modele": {modele: Usage}, "euros", "sans_prix"}` de la conversation `transcription`.
    `euros` est `None` sans `prix_de` ; `sans_prix` liste les modèles dont le prix manque (le coût est alors partiel)."""
    vus, par_modele, appels = set(), {}, 0
    with open(Path(transcription), encoding="utf-8", errors="replace") as f:
        for brut in f:
            try:
                d = json.loads(brut)
            except ValueError:
                continue
            m = d.get("message") if isinstance(d, dict) else None
            if (d.get("type") != "assistant" or d.get("isSidechain") or not isinstance(m, dict)
                    or not isinstance(m.get("usage"), dict)):
                continue
            if m.get("id") in vus:
                continue
            vus.add(m.get("id"))
            appels += 1
            u = par_modele.setdefault(str(m.get("model") or "inconnu"),
                                      {"modele": str(m.get("model") or "inconnu"), **{c: 0 for c in COMPTEURS}})
            for source, cible in CHAMPS:
                n = m["usage"].get(source)
                u[cible] += n if isinstance(n, int) and n > 0 else 0
    tokens = sum(u[c] for u in par_modele.values() for c in COMPTEURS)
    euros, sans_prix = cout_euros(par_modele.values(), prix_de, date_iso) if prix_de else (None, [])
    return {"appels": appels, "tokens": tokens, "par_modele": par_modele, "euros": euros, "sans_prix": sans_prix}


def cout_euros(usages, prix_de, date_iso=None):
    """(euros, modèles sans prix) d'une suite d'usages (`modele` et les quatre compteurs)."""
    total, sans_prix = 0.0, []
    for u in usages:
        p = prix_de(u["modele"], date_iso or "")[0]
        if not p:
            if u["modele"] not in sans_prix:
                sans_prix.append(u["modele"])
            continue
        total += cout._cout(u, p)
    return round(total, 6), sans_prix
