"""Jouer un scénario contre le moteur : la factory du scénario, le rejoueur à la place des agents, les gestes de
l'utilisateur donnés quand le moteur attend. Seuls les appels de jugement sont réels (`appeler`) ; le rapport rend ce
qu'ils ont coûté, avec la production rejouée et les écarts avec l'essai."""
import json
from pathlib import Path

from banc.rejoueur import Rejoueur
from moteur import boucle, regles

MAX_TOURS = 600


class Compteur:
    """Enveloppe `appeler` : garde chaque appel de jugement (type d'appel, modèle) et ce qu'il a coûté."""

    def __init__(self, appeler):
        self.appeler, self.appels = appeler, []

    def __call__(self, consigne, dossier, modele, **options):
        r = self.appeler(consigne, dossier, modele, **options)
        self.appels.append({"modele": modele, "usages": [dict(u) for u in r.usages]})
        return r


def jouer_moteur(scenario, dossier, appeler, *, couche="claude", max_tours=MAX_TOURS):
    """Rend `{"tours", "appels", "usages_jugement", "usages_production", "ecarts", "etat", "suivi", "gestes_restants",
    "demandes_en_attente"}`."""
    dossier = Path(dossier)
    factory = scenario.materialiser(dossier)
    projet = regles.Projet(factory, couche, feu_vert=lambda: True, prerequis=lambda: "banc d'essai : pas de cloud")

    def decrire(tache):
        t = regles.lancer(projet, "detail", {"tache": tache})
        return {"etape": t.get("etape"), "role": t.get("role"), "element": t.get("element")}

    rejoueur = Rejoueur(scenario, decrire)
    compteur = Compteur(appeler)
    moteur = boucle.Moteur([projet], appeler=compteur, executer_agent=rejoueur, synchrone=True,
                           commit=lambda *a: None)
    calmes, tours = 0, 0
    while tours < max_tours and calmes < 3:
        tours += 1
        avant = (len(compteur.appels), len(rejoueur.rendus), len(rejoueur.ecarts), scenario.suivant)
        moteur.tour()
        etat = regles.lancer(projet, "etat")
        geste = scenario.prochain_geste(etat)
        if geste is not None:
            regles.lancer(projet, "actions", {**geste, "t": regles.su.maintenant()})
        change = avant != (len(compteur.appels), len(rejoueur.rendus), len(rejoueur.ecarts), scenario.suivant)
        calmes = 0 if (change or geste is not None) else calmes + 1
    suivi = json.loads((dossier / "suivi.json").read_text(encoding="utf-8"))
    usages = suivi.get("usage") or []
    return {"tours": tours, "appels": [{"modele": a["modele"]} for a in compteur.appels],
            "usages_jugement": [u for u in usages if u.get("etape") == "orchestration"],
            "usages_production": [u for u in usages if u.get("etape") != "orchestration"],
            "ecarts": list(rejoueur.ecarts), "etat": regles.lancer(projet, "etat"), "suivi": suivi,
            "gestes_restants": scenario.restants, "journal": list(moteur.journal),
            "demandes_en_attente": [d for d in suivi["demandes"] if d["statut"] == "en attente"]}
