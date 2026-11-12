"""Jouer un scénario contre le moteur : la factory du scénario, le rejoueur à la place des agents, les gestes de
l'utilisateur donnés quand le moteur attend. Seuls les appels de jugement sont réels (`appeler`) ; le rapport rend ce
qu'ils ont coûté, avec la production rejouée et les écarts avec l'essai."""
import json
from pathlib import Path

from banc.rejoueur import Rejoueur
from moteur import boucle, regles
from orchestrateur import factory as fa
from orchestrateur import workflows as wf

MAX_TOURS = 600
# Une leçon validée de genre ou de skill s'écrit dans la skill (ce dépôt) : le banc n'en valide jamais. Les leçons
# notées par les agents restent comptées dans le suivi.
GESTES_IGNORES = ("lecon",)


def poste_pret(outils):
    """Le poste du banc : l'essai rejoué a été fait, ses outils étaient là. Aucun agent d'installation n'est recruté (le
    banc ne dépend pas de la machine qui le joue)."""
    return [dict(o, etat="en_place") for o in outils]


class Parcours:
    """Les gestes du parcours d'une nouvelle demande, que l'essai de référence (fait avant ce parcours) n'a pas : la
    demande de l'essai est du genre du projet, le workflow proposé est accepté, une proposition ratée laisse continuer
    avec le workflow actuel. Chaque question n'est répondue qu'une fois."""

    def __init__(self, projet):
        self.projet, self.repondues = projet, set()

    def geste(self, etat):
        for d in etat.get("decisions") or []:
            if d["id"] in self.repondues:
                continue
            if d["genre"] == "organisation" and (d.get("organisation") or {}).get("workflow"):
                self.repondues.add(d["id"])
                return {"type": "organisation", "decision": d["id"], "verdict": "accepter"}
            if d["genre"] == "genre_fonctionnalite":
                self.repondues.add(d["id"])
                g = {"type": "genre_fonctionnalite", "decision": d["id"], "fonctionnalite": d["portee"]}
                if d.get("incertain") and etat.get("genre"):
                    return {**g, "choix": "meme"}
                return {**g, "choix": "ici", "genre": etat.get("genre") or d.get("propose")}
        for f in etat.get("fonctionnalites") or []:
            detail = regles.lancer(self.projet, "detail", {"fonctionnalite": f["id"]})
            discussion = detail.get("discussion") or []
            if not discussion:
                continue
            k, dernier = len(discussion) - 1, discussion[-1]
            choix = [c for q in dernier.get("questions") or [] for c in q.get("choix") or []]
            if dernier["auteur"] != "utilisateur" and regles.CONTINUER in choix and (f["id"], k) not in self.repondues:
                self.repondues.add((f["id"], k))
                return {"type": "message", "fonctionnalite": f["id"], "texte": regles.CONTINUER}
        return None


def vers_l_essai(fac, fonc, etape, role):
    """L'étape et le rôle d'une tâche, ramenés au flux de l'essai : le workflow proposé à la fonctionnalité (`f1-…`) n'a
    pas les identifiants de l'essai. Une étape va à celle de l'essai de même rôle, sinon de même rang."""
    w = wf.de_la_fonctionnalite(fac, fonc)
    flux = fac["flux"]
    if not w or w["id"] == wf.PRINCIPAL or not flux:
        return etape, role
    etapes = w["flux"]

    def correspondante(i):
        x = etapes[i]
        return next((s for s in flux if s["role"] == x["role"]), flux[i] if i < len(flux) else None)

    roles = {x["role"]: c["role"] for i, x in enumerate(etapes) if (c := correspondante(i))}
    if etape and etape.startswith(regles.ETAPES_DE_FLUX):
        i = next((i for i, x in enumerate(etapes) if x["id"] == etape[len(regles.ETAPES_DE_FLUX):]), None)
        c = correspondante(i) if i is not None else None
        if c:
            etape = regles.ETAPES_DE_FLUX + c["id"]
    return etape, roles.get(role, role)


class Compteur:
    """Enveloppe `appeler` : garde chaque appel de jugement (type d'appel, modèle) et ce qu'il a coûté."""

    def __init__(self, appeler):
        self.appeler, self.appels = appeler, []

    def __call__(self, consigne, dossier, modele, **options):
        r = self.appeler(consigne, dossier, modele, **options)
        self.appels.append({"modele": modele, "usages": [dict(u) for u in r.usages]})
        return r


class AgentsReels:
    """Les vrais agents (`moteur.agents.executer_agent`) à la place du rejoueur, pour le passage complet en vrai."""

    def __init__(self, executer_agent):
        self.executer_agent, self.rendus, self.ecarts = executer_agent, [], []

    def __call__(self, depart, matiere, **options):
        e = self.executer_agent(depart, matiere, **options)
        self.rendus.append((options.get("tache"), e.erreur))
        if e.erreur:
            self.ecarts.append(f"Agent en échec sur la tâche {options.get('tache')} : {e.erreur}"[:300])
        return e


def jouer_moteur(scenario, dossier, appeler, *, couche="claude", max_tours=MAX_TOURS, executer_agent=None):
    """Rend `{"tours", "appels", "usages_jugement", "usages_production", "ecarts", "etat", "suivi", "gestes_restants",
    "demandes_en_attente"}`. Avec `executer_agent` (les vrais agents), le passage est complet : rien n'est rejoué, et les
    écarts sont les agents en échec."""
    dossier = Path(dossier)
    factory = scenario.materialiser(dossier)
    projet = regles.Projet(factory, couche, feu_vert=lambda: True, prerequis=lambda: "banc d'essai : pas de cloud",
                           verifier_environnement=poste_pret)
    parcours = Parcours(projet)

    def decrire(tache):
        t = regles.lancer(projet, "detail", {"tache": tache})
        suivi = json.loads((dossier / "suivi.json").read_text(encoding="utf-8"))
        fonc = next((f for f in suivi["fonctionnalites"] if f["id"] == t.get("fonctionnalite")), None)
        etape, role = vers_l_essai(fa.lire(factory), fonc, t.get("etape"), t.get("role"))
        d = {"etape": etape, "role": role, "element": t.get("element")}
        lot = (t.get("lot") or {}).get("id")
        if lot:     # les éléments du lot, dans son ordre : le rejoueur leur donne leur rang
            toutes = json.loads((dossier / "suivi.json").read_text(encoding="utf-8"))["taches"]
            membres = sorted((x for x in toutes if (x.get("lot") or {}).get("id") == lot), key=lambda x: x["lot"]["rang"])
            d["elements"] = [x["element"] for x in membres if x.get("element") is not None]
        return d

    rejoueur = Rejoueur(scenario, decrire) if executer_agent is None else AgentsReels(executer_agent)
    compteur = Compteur(appeler)
    moteur = boucle.Moteur([projet], appeler=compteur, executer_agent=rejoueur, synchrone=True,
                           commit=lambda *a: None)
    calmes, tours = 0, 0
    while tours < max_tours and calmes < 3:
        tours += 1
        avant = (len(compteur.appels), len(rejoueur.rendus), len(rejoueur.ecarts), scenario.suivant)
        moteur.tour()
        etat = regles.lancer(projet, "etat")
        geste = parcours.geste(etat) or scenario.prochain_geste(etat)
        if geste is not None and geste.get("type") not in GESTES_IGNORES:
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
