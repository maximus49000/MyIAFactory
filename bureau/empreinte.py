"""L'empreinte carbone estimée de la consommation de tokens, d'après la méthode EcoLogits.

Attribution : la méthode, les formules, les coefficients et les paramètres de modèles de ce module viennent d'EcoLogits
(genai-impact, https://github.com/genai-impact/ecologits, licence MPL-2.0 ; méthodologie :
https://ecologits.ai/latest/methodology/llm_inference/), lus dans son code source le 2026-11-12 (impacts/llm.py,
tracers/utils.py, data/models.json, data/electricity_mixes.json) et réécrits ici en Python standard. Ce module est un
code à nous, il ne contient aucun code d'EcoLogits. Les paramètres des modèles Claude (taille totale, taille active,
vitesse, délai du premier token) sont des **estimations d'EcoLogits** : Anthropic ne les publie pas.

Ce que c'est, et ses limites :
- une **estimation** donnée en fourchette (gCO2e et Wh), jamais une mesure ;
- seuls les **tokens de sortie** comptent (EcoLogits ne compte pas ceux d'entrée ni ceux du cache) ;
- l'électricité est celle des **États-Unis** (0,3844 kgCO2e/kWh, mix choisi par EcoLogits pour Anthropic) ;
- la fabrication des serveurs (amortie sur 3 ans) est comptée avec l'usage ; la fourchette est ±, sur la taille active
  du modèle et sur le PUE du centre de données ;
- chaque usage (une discussion) est traité comme une seule requête : les cumuls additionnent les usages ;
- un modèle non listé prend l'entrée **la plus proche de la même famille** (haiku, sonnet, opus) et le dit
  (`assimile`) ; un nom de famille seul vaut sa version la plus récente ; une famille inconnue, ou sans donnée
  (Fable : EcoLogits n'en donne ni vitesse ni délai), ne donne **aucune valeur** (jamais de chiffre inventé).
"""
import math
import re

URL_METHODE = "https://ecologits.ai/latest/methodology/llm_inference/"

# Énergie par token et par GPU : (ALPHA·exp(BETA·B)·P_actif + GAMMA) / 1000 kWh/token, B = taille de lot, P en milliards.
ALPHA = 1.1665273170451914e-06
BETA = -0.011205921025579175
GAMMA = 4.052928146734005e-05
LOT = 64
PUE = (1.09, 1.14)                 # centre de données Anthropic : (min, max)
MIX_KGCO2E_PAR_KWH = 0.3844        # États-Unis (Our World in Data, repris par EcoLogits)
OCTETS_PAR_PARAMETRE = 2           # 16 bits
SURCHARGE_MEMOIRE = 1.2
MEMOIRE_GPU_GO = 80
CHARGE_SERVEUR_KW = 1.2
GPU_PAR_SERVEUR = 8
FABRICATION_SERVEUR_KG = 5700      # hors GPU
FABRICATION_GPU_KG = 273
DUREE_VIE_S = 3 * 365 * 86400

# id : (famille, version, (total, actif_min, actif_max) en milliards de paramètres, tokens/s, délai du premier token en s).
# `total` None : modèle dense (la taille active la plus grande sert de taille totale). Vitesse None : non estimée.
_TABLE = [
    ("claude-haiku-4-5", "haiku", (4, 5), None, (10, 35), 79, 0.5),
    ("claude-haiku-5-5", "haiku", (5, 5), None, (10, 35), 147, 1.75),
    ("claude-sonnet-4-5", "sonnet", (4, 5), 440, (44, 132), 42, 1.15),
    ("claude-sonnet-4-6", "sonnet", (4, 6), 440, (44, 132), 40, 1.15),
    ("claude-sonnet-5", "sonnet", (5, 0), 293, (29, 88), 79.5, 1.76),
    ("claude-sonnet-5-5", "sonnet", (5, 5), 293, (29, 88), 102, 2.21),
    ("claude-opus-4-5", "opus", (4, 5), 670, (67, 200), 30.5, 5.03),
    ("claude-opus-4-6", "opus", (4, 6), 670, (67, 200), 35, 1.95),
    ("claude-opus-4-7", "opus", (4, 7), 670, (67, 200), 42, 1.75),
    ("claude-opus-4-8", "opus", (4, 8), 670, (67, 200), 110.8, 0.87),
    ("claude-opus-5", "opus", (5, 0), 670, (67, 200), 89.5, 1.84),
    ("claude-opus-5-5", "opus", (5, 5), 670, (70, 200), 102.8, 2.68),
    ("claude-fable-5", "fable", (5, 0), 1340, (134, 400), None, None),
    ("claude-fable-5-1", "fable", (5, 1), 1340, (134, 400), None, None),
]
MODELES = {i: {"famille": f, "version": v, "total": t, "actif": a, "tps": tps, "ttft": ttft}
           for i, f, v, t, a, tps, ttft in _TABLE}
FAMILLES = ("haiku", "sonnet", "opus", "fable")

_DATE = re.compile(r"-\d{8}$")
_APRES = re.compile(r"(haiku|sonnet|opus|fable)(?:-(\d+)(?:-(\d+))?)?(?![a-z])")
_AVANT = re.compile(r"(\d+)(?:-(\d+))?-(haiku|sonnet|opus|fable)")


def _lecture(modele):
    """(famille, version | None) d'un nom de modèle, ou None."""
    if not isinstance(modele, str):
        return None
    nom = _DATE.sub("", re.sub(r"[\s._]+", "-", modele.strip().lower()))
    m = _AVANT.search(nom)
    if m:
        return m.group(3), (int(m.group(1)), int(m.group(2) or 0))
    m = _APRES.search(nom)
    if not m:
        return None
    return m.group(1), ((int(m.group(2)), int(m.group(3) or 0)) if m.group(2) else None)


def _reel(v):
    return v[0] + v[1] / 10


def resoudre(modele):
    """(id du modèle de la table, assimilé) ; (None, False) si la famille est inconnue. Un nom de famille seul prend la
    version la plus récente sans être « assimilé » ; une version absente de la table prend la plus proche de la famille
    (la plus récente à égalité) et l'est."""
    lu = _lecture(modele)
    if lu is None:
        return None, False
    famille, version = lu
    membres = [(i, m["version"]) for i, m in MODELES.items() if m["famille"] == famille]
    if version is None:
        return max(membres, key=lambda x: x[1])[0], False
    exact = [i for i, v in membres if v == version]
    if exact:
        return exact[0], False
    return min(membres, key=lambda x: (abs(_reel(x[1]) - _reel(version)), -_reel(x[1])))[0], True


def _calcul(m, tokens, actif, pue):
    """(énergie en Wh, usage en gCO2e, fabrication en gCO2e) d'une requête de `tokens` tokens de sortie."""
    total = m["total"] if m["total"] is not None else m["actif"][1]
    memoire = SURCHARGE_MEMOIRE * total * 16 / 8
    gpus = 2 ** math.ceil(math.log2(max(1, math.ceil(memoire / MEMOIRE_GPU_GO))))
    duree = tokens / m["tps"] + m["ttft"]
    e_token = (ALPHA * math.exp(BETA * LOT) * actif + GAMMA) / 1000          # kWh par token et par GPU
    e_serveur = duree / 3600 * CHARGE_SERVEUR_KW * (gpus / GPU_PAR_SERVEUR) / LOT
    kwh = pue * (e_serveur + gpus * tokens * e_token)
    fabrication_kg = duree * ((gpus / GPU_PAR_SERVEUR) * FABRICATION_SERVEUR_KG + gpus * FABRICATION_GPU_KG) \
        / (DUREE_VIE_S * LOT)
    return kwh * 1000, kwh * MIX_KGCO2E_PAR_KWH * 1000, fabrication_kg * 1000


def _nombre(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def estimer(modele, tokens_sortie):
    """L'empreinte de `tokens_sortie` tokens de sortie du `modele` : {min, max (gCO2e, usage + fabrication), wh_min,
    wh_max, usage_min, usage_max, fabrication (gCO2e), modele (l'entrée de la table utilisée), assimile (si le modèle
    n'est pas dans la table)} ; `None` si la famille est inconnue ou sans donnée, ou si le nombre est invalide."""
    if not _nombre(tokens_sortie) or tokens_sortie < 0:
        return None
    identifiant, assimile = resoudre(modele)
    if identifiant is None:
        return None
    m = MODELES[identifiant]
    if m["tps"] is None or m["ttft"] is None:
        return None
    if tokens_sortie == 0:
        zero = {"min": 0.0, "max": 0.0, "wh_min": 0.0, "wh_max": 0.0, "usage_min": 0.0, "usage_max": 0.0,
                "fabrication": 0.0, "modele": identifiant}
        return dict(zero, assimile=True) if assimile else zero
    wh_min, usage_min, fab = _calcul(m, tokens_sortie, m["actif"][0], PUE[0])
    wh_max, usage_max, _ = _calcul(m, tokens_sortie, m["actif"][1], PUE[1])
    r = {"min": usage_min + fab, "max": usage_max + fab, "wh_min": wh_min, "wh_max": wh_max,
         "usage_min": usage_min, "usage_max": usage_max, "fabrication": fab, "modele": identifiant}
    if assimile:
        r["assimile"] = True
    return r


_CHAMPS = ("min", "max", "wh_min", "wh_max")


class Cumul:
    """La somme d'empreintes. `incomplet` : au moins un usage chargé en tokens n'a pu être estimé (famille inconnue)."""

    def __init__(self):
        self.v = dict.fromkeys(_CHAMPS, 0.0)
        self.n = 0
        self.assimile = False
        self.incomplet = False

    def ajouter(self, quoi, tokens_sortie=None):
        """Ajoute un usage (`modele`, tokens de sortie) ou un autre cumul."""
        if isinstance(quoi, Cumul):
            for c in _CHAMPS:
                self.v[c] += quoi.v[c]
            self.n += quoi.n
            self.assimile = self.assimile or quoi.assimile
            self.incomplet = self.incomplet or quoi.incomplet
            return
        r = estimer(quoi, tokens_sortie)
        if r is None:
            if _nombre(tokens_sortie) and tokens_sortie > 0:
                self.incomplet = True
            return
        for c in _CHAMPS:
            self.v[c] += r[c]
        self.n += 1
        self.assimile = self.assimile or bool(r.get("assimile"))

    def vue(self):
        """{min, max (gCO2e), wh_min, wh_max, assimile?, incomplet?}, ou None quand rien n'a pu être estimé."""
        if self.n == 0:
            return None
        sortie = {c: round(self.v[c], 6) for c in _CHAMPS}
        if self.assimile:
            sortie["assimile"] = True
        if self.incomplet:
            sortie["incomplet"] = True
        return sortie


def plage(tokens, modeles, part_sortie=0.2):
    """La fourchette {min, max, wh_min, wh_max} d'une estimation sans détail : `tokens` = [bas, haut] au total, répartis
    à parts égales entre les `modeles` (un par étape), dont la part `part_sortie` est en sortie. `None` si un modèle n'a
    pas de valeur ou s'il n'y en a aucun."""
    if not modeles or not isinstance(tokens, (list, tuple)) or len(tokens) != 2 or not all(_nombre(t) for t in tokens):
        return None
    bas, haut = Cumul(), Cumul()
    for modele in modeles:
        for cumul, t in ((bas, tokens[0]), (haut, tokens[1])):
            cumul.ajouter(modele, t * part_sortie / len(modeles))
    if bas.incomplet or haut.incomplet or bas.n != len(modeles) or haut.n != len(modeles):
        return None
    b, h = bas.vue(), haut.vue()
    sortie = {"min": b["min"], "max": h["max"], "wh_min": b["wh_min"], "wh_max": h["wh_max"]}
    if b.get("assimile") or h.get("assimile"):
        sortie["assimile"] = True
    return sortie


def _grammes(g, kg):
    v = g / 1000 if kg else g
    if not kg and v < 0.01:
        return "< 0,01"
    if v < 1 and not kg:
        texte = f"{v:.2f}"
    else:
        texte = f"{v:.1f}" if v < 10 else f"{v:.0f}"
    return texte.replace(".", ",")


def texte(co2):
    """« ≈ 0,46 à 0,72 g CO₂e » (en kg au-delà de 1000 g) ; vide sans valeur. Le miroir de `etiquetteCO2` de la page."""
    if not isinstance(co2, dict) or not _nombre(co2.get("min")) or not _nombre(co2.get("max")) or co2["max"] <= 0:
        return ""
    kg = co2["max"] >= 1000
    a, b = _grammes(co2["min"], kg), _grammes(co2["max"], kg)
    unite = "kg" if kg else "g"
    if a == b:
        return f"{'' if a.startswith('<') else '≈ '}{a} {unite} CO₂e"
    return f"≈ {a} à {b} {unite} CO₂e"
