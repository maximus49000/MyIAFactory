"""Conseil sur le meilleur lieu d'exécution (poste, github, serveur) pour une action : logique pure, ni E/S ni réseau.

La fonction ne fait que conseiller : jamais de déplacement automatique. Les raisons sont courtes, en français, et ne
citent ni hôte, ni chemin, ni secret.
"""
from dataclasses import dataclass, field

LIEUX = ("poste", "github", "serveur")
SEUIL_CHARGE = 0.85      # au-delà, le lieu est déconseillé
SEUIL_QUOTA = 0.15       # quota GitHub restant en dessous duquel github est déconseillé
ECART_MIN = 0.15         # écart relatif de durée exigé sur le suivant pour recommander
ECART_CHARGE = 0.15      # écart de charge exigé (repli sur les règles)
NOMS = {"poste": "Le poste", "github": "GitHub", "serveur": "Le serveur"}


@dataclass(frozen=True)
class Mesures:
    duree_min: dict = field(default_factory=dict)       # lieu -> durée mesurée en minutes (ou None)
    charge_poste: float | None = None                   # 0 à 1
    charge_serveur: float | None = None                 # 0 à 1
    quota_github_restant: float | None = None           # 0 à 1
    serveur_joignable: bool = True


def _charge(lieu, mes):
    return {"poste": mes.charge_poste, "serveur": mes.charge_serveur}.get(lieu)


def _duree(lieu, mes):
    d = (mes.duree_min or {}).get(lieu)
    return float(d) if isinstance(d, (int, float)) and not isinstance(d, bool) and d > 0 else None


def _entree(niveau, raison, fondee):
    return {"niveau": niveau, "raison": raison, "fondee_sur": fondee}


def recommander(action, lieux_permis, mesures):
    """`{lieu: {niveau, raison, fondee_sur}}` pour poste, github et serveur. Au plus un lieu « recommande »."""
    sortie = {}
    candidats = []
    for lieu in LIEUX:
        if not (lieux_permis or {}).get(lieu) is True:
            sortie[lieu] = _entree("indisponible", f"{NOMS[lieu]} ne peut pas faire cette action pour l'instant.", "regles")
        elif lieu == "serveur" and not mesures.serveur_joignable:
            sortie[lieu] = _entree("indisponible", "Le serveur ne répond pas.", "regles")
        elif (_charge(lieu, mesures) or 0) > SEUIL_CHARGE:
            sortie[lieu] = _entree("deconseille", f"{NOMS[lieu]} est très chargé.", "mesures")
        elif lieu == "github" and mesures.quota_github_restant is not None and mesures.quota_github_restant < SEUIL_QUOTA:
            sortie[lieu] = _entree("deconseille", "Le quota GitHub restant est presque épuisé.", "mesures")
        else:
            candidats.append(lieu)

    mesure = bool(candidats) and all(_duree(c, mesures) is not None for c in candidats)
    fondee = "mesures" if mesure else "regles"
    gagnant = None
    if mesure:
        ordre = sorted(candidats, key=lambda c: _duree(c, mesures))
        if len(ordre) == 1 or _duree(ordre[1], mesures) >= _duree(ordre[0], mesures) * (1 + ECART_MIN):
            gagnant = ordre[0]
            raison_gagnant = "Le plus rapide d'après les durées mesurées."
        else:
            raison_gagnant = ""
    else:
        connues = sorted((c for c in candidats if _charge(c, mesures) is not None), key=lambda c: _charge(c, mesures))
        if connues:
            reste = [_charge(c, mesures) for c in connues[1:]]
            if not reste or min(reste) - _charge(connues[0], mesures) >= ECART_CHARGE or len(candidats) == 1:
                gagnant = connues[0]
        raison_gagnant = "Le moins chargé d'après les règles simples."
    if gagnant == "serveur" and mesures.charge_serveur is None:
        gagnant = None          # sans charge connue, le serveur n'est jamais présenté comme le meilleur choix
    for c in candidats:
        if c == gagnant:
            sortie[c] = _entree("recommande", raison_gagnant, fondee)
        elif mesure and c == "serveur" and mesures.charge_serveur is None:
            sortie[c] = _entree("possible", "Charge du serveur inconnue.", fondee)
        else:
            sortie[c] = _entree("possible", "Utilisable ; pas de net avantage constaté.", fondee)
    return {lieu: sortie[lieu] for lieu in LIEUX}
