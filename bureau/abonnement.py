"""L'abonnement Claude vu par les appels `claude -p` : les deux jauges (fenêtre de 5 h, semaine) et la part estimée.

`claude -p --output-format stream-json --verbose` émet une ligne `rate_limit_event` avant la réponse : le taux d'usage du
compte (`unifiedWindows`, ou à défaut `rateLimitType` + `utilization`, de 0 à 1) et l'heure de remise à zéro (secondes
epoch). On en tire un instantané `{"five_hour": {"pourcent", "remise"}, "seven_day": {...}, "t"}` ; une valeur absente ou
illisible n'est jamais remplacée par un chiffre inventé.

Ces pourcentages sont ceux du **compte** : ils comptent aussi les autres sessions Claude de l'utilisateur.

Gardé dans le dossier commun (`~/MyIAFactory`) :
- `abonnement.json` : le dernier instantané (écriture atomique) ;
- `abonnement-historique.jsonl` : un instantané par appel, avec son coût en dollars (équivalent tarif API), pour étalonner ;
  plus, quand elle a changé, chaque lecture directe du compte faite par le rond (`"source": "compte"`, sans coût).
  Unités : ici tout est en « utilisé » (0 à 100) ; le rond de `conso.py` travaille en « reste » (100 − utilisé).
- `abonnement-semaines/` : chaque semaine du forfait, archivée pour toujours hors du fichier rogné (voir `semaines.py`).

Étalonnage : sur une même fenêtre (même heure de remise à zéro), on suit les instantanés successifs, rangés par date, et
le coût de nos appels datés entre deux (une lecture du compte compte pour 0 $) ; dès que le compteur a monté d'au moins `ECART_MIN` points, une mesure « points par dollar » est
prise. Les autres sessions font aussi monter le compteur : chaque mesure est un majorant. L'estimation est donc la
médiane de la moitié la plus basse des mesures, et il en faut au moins `MIN_MESURES`.
"""
import json
import math
import os
import statistics
import threading
import time
from pathlib import Path

from . import semaines

FENETRES = ("five_hour", "seven_day")
LIBELLES = {"five_hour": "5 h", "seven_day": "Semaine"}
MIN_MESURES = 3
ECART_MIN = 2.0       # points de pourcentage au moins pour qu'une mesure compte (le compteur monte par paliers)
COUT_MIN_USD = 0.01   # et au moins ce coût de nos appels (sinon le bruit des autres sessions domine)
TOLERANCE_REMISE = 120   # secondes : deux remises à zéro si proches sont la même fenêtre
SOURCE_COMPTE = "compte"
MAX_HISTORIQUE = 3000
TAILLE_MAX = 600_000   # au-delà, l'historique est ramené à ses `MAX_HISTORIQUE` dernières lignes
NOM_INSTANTANE = "abonnement.json"
NOM_HISTORIQUE = "abonnement-historique.jsonl"

DOSSIER = None   # remplacé par les tests (jamais le vrai dossier commun) : un Path
_VERROU = threading.Lock()


def racine(dossier=None):
    d = dossier if dossier is not None else DOSSIER
    return Path(d) if d is not None else Path("~/MyIAFactory").expanduser()


def _nombre(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# --- Lecture d'un instantané.

def _fenetre_brute(v):
    """{"pourcent", "remise"} d'une fenêtre `{utilization (0..1), resetsAt (epoch s)}`, ou None si illisible."""
    if not isinstance(v, dict):
        return None
    u, r = v.get("utilization"), v.get("resetsAt")
    if not _nombre(u) or not _nombre(r) or not 0 <= u <= 1 or r <= 0:
        return None
    return {"pourcent": round(u * 100, 1), "remise": int(r)}


def instantane_depuis(evenements, t=None):
    """L'instantané lu dans les lignes `rate_limit_event` d'un appel (dictionnaires), ou None sans aucune valeur
    lisible. `unifiedWindows` l'emporte sur `rateLimitType` + `utilization` ; le dernier événement l'emporte."""
    fenetres = {}
    for ev in evenements or []:
        info = ev.get("rate_limit_info") if isinstance(ev, dict) else None
        if not isinstance(info, dict):
            continue
        unifiees = info.get("unifiedWindows")
        unifiees = unifiees if isinstance(unifiees, dict) else {}
        for nom in FENETRES:
            f = _fenetre_brute(unifiees.get(nom))
            if f is None and info.get("rateLimitType") == nom:
                f = _fenetre_brute(info)
            if f is not None:
                fenetres[nom] = f
    if not fenetres:
        return None
    return {**fenetres, "t": int(t if t is not None else time.time())}


def valider(ab):
    """L'instantané nettoyé (ses seuls champs connus, bien formés), ou None. Sert à ce qui vient d'un fichier."""
    if not isinstance(ab, dict):
        return None
    sortie = {}
    for nom in FENETRES:
        f = ab.get(nom)
        if (isinstance(f, dict) and _nombre(f.get("pourcent")) and 0 <= f["pourcent"] <= 100
                and _nombre(f.get("remise")) and f["remise"] > 0):
            sortie[nom] = {"pourcent": round(float(f["pourcent"]), 1), "remise": int(f["remise"])}
    if not sortie or not _nombre(ab.get("t")) or ab["t"] <= 0:
        return None
    sortie["t"] = int(ab["t"])
    return sortie


# --- Le dossier commun.

def lire(dossier=None):
    """Le dernier instantané gardé, ou None."""
    try:
        return valider(json.loads((racine(dossier) / NOM_INSTANTANE).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def _ecrire_atomique(chemin, texte):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(texte, encoding="utf-8")
    os.replace(tmp, chemin)


def _meme_mesure(a, b):
    """Deux instantanés disent-ils la même chose (mêmes fenêtres, mêmes pourcentages, mêmes remises à `TOLERANCE_REMISE`) ?"""
    for nom in FENETRES:
        fa, fb = a.get(nom), b.get(nom)
        if (fa is None) != (fb is None):
            return False
        if fa is not None and (fa["pourcent"] != fb["pourcent"] or abs(fa["remise"] - fb["remise"]) > TOLERANCE_REMISE):
            return False
    return True


def noter(instantane, cout_usd=None, dossier=None, source=None):
    """Garde `instantane` comme le plus récent et l'ajoute à l'historique avec le coût de l'appel. Sans instantané lisible,
    rien n'est écrit. Ne lève jamais (le disque ne doit pas faire échouer un appel).

    `source="compte"` : lecture directe du compte (le rond du bandeau), sans coût ; la ligne d'historique n'est ajoutée
    que si la mesure a changé depuis la dernière ligne (sinon une lecture par minute noierait les lignes des appels)."""
    ab = valider(instantane)
    if ab is None:
        return
    d = racine(dossier)
    semaines.noter(ab, "compte" if source == SOURCE_COMPTE else "moteur", d)   # l'archive des semaines, pour toujours
    ligne = dict(ab)
    if source == SOURCE_COMPTE:
        ligne["source"] = SOURCE_COMPTE
    elif _nombre(cout_usd) and cout_usd >= 0:
        ligne["cout_usd"] = float(cout_usd)
    try:
        with _VERROU:
            _ecrire_atomique(d / NOM_INSTANTANE, json.dumps(ab, ensure_ascii=False))
            h = d / NOM_HISTORIQUE
            if source == SOURCE_COMPTE:
                avant = lire_historique(dossier)
                if avant and _meme_mesure(avant[-1], ab):
                    return
            with h.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            if h.stat().st_size > TAILLE_MAX:
                lignes = h.read_text(encoding="utf-8").splitlines()[-MAX_HISTORIQUE:]
                _ecrire_atomique(h, "".join(x + "\n" for x in lignes))
    except OSError:
        pass


def lire_historique(dossier=None):
    """Les lignes valides de l'historique, dans l'ordre du fichier."""
    try:
        texte = (racine(dossier) / NOM_HISTORIQUE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    sortie = []
    for brut in texte.splitlines():
        try:
            d = json.loads(brut)
        except ValueError:
            continue
        ab = valider(d)
        if ab is None:
            continue
        c = d.get("cout_usd")
        ab["cout_usd"] = float(c) if _nombre(c) and c >= 0 else None
        if d.get("source") == SOURCE_COMPTE:
            ab["source"] = SOURCE_COMPTE   # une lecture du compte : aucun appel de nous derrière, donc un coût nul
        sortie.append(ab)
    return sortie


# --- L'étalonnage.

def mesures(historique, fenetre):
    """Les mesures « points de pourcentage par dollar » d'une fenêtre, à partir des instantanés successifs."""
    sortie = []
    suite = []   # les lignes de la même fenêtre de remise à zéro, qui se suivent
    # Rangées par date (une ligne d'appel est écrite à sa fin mais datée de son début) : le coût entre deux instantanés
    # est alors la somme des appels datés entre eux. Une lecture du compte n'a pas de coût propre : 0.
    historique = sorted(historique, key=lambda x: x.get("t") or 0)

    def parcourir(suite):
        debut, cout = 0, 0.0
        for k in range(1, len(suite)):
            c = suite[k - 1]["cout_usd"]
            if c is None and suite[k - 1].get("source") == SOURCE_COMPTE:
                c = 0.0
            if c is None:
                debut, cout = k, 0.0
                continue
            cout += c
            ecart = suite[k][fenetre]["pourcent"] - suite[debut][fenetre]["pourcent"]
            if ecart < 0:
                debut, cout = k, 0.0
            elif ecart >= ECART_MIN and cout >= COUT_MIN_USD:
                sortie.append(ecart / cout)
                debut, cout = k, 0.0

    cle = None
    for ligne in historique:
        f = ligne.get(fenetre)
        if f is None:
            parcourir(suite)
            suite, cle = [], None
            continue
        # même fenêtre : même remise à zéro, à quelques secondes près (le compte la donne à la fraction de seconde)
        if suite and abs(f["remise"] - cle) > TOLERANCE_REMISE:
            parcourir(suite)
            suite = []
        suite.append(ligne)
        cle = f["remise"]
    parcourir(suite)
    return sortie


def points_par_dollar(historique, fenetre):
    """(estimation prudente | None, nombre de mesures) : la médiane de la moitié la plus basse des mesures (elles sont
    des majorants), `None` sous `MIN_MESURES` mesures."""
    m = sorted(mesures(historique, fenetre))
    if len(m) < MIN_MESURES:
        return None, len(m)
    return statistics.median(m[:(len(m) + 1) // 2]), len(m)


def pour_la_page(dossier=None, euros_par_dollar=None, couche="claude", maintenant=None):
    """Ce que le bureau sert à la page : l'instantané, et pour chaque fenêtre les points par euro (None : en cours
    d'étalonnage). Rien (`None`) quand la couche est l'API : les appels n'usent pas l'abonnement."""
    if couche == "api":
        return None
    historique = lire_historique(dossier)
    ratio, mesure = {}, {}
    for nom in FENETRES:
        p, n = points_par_dollar(historique, nom)
        ok = p is not None and _nombre(euros_par_dollar) and euros_par_dollar > 0
        ratio[nom] = p / euros_par_dollar if ok else None
        mesure[nom] = n
    return {"instantane": lire(dossier), "pourcent_par_euro": ratio, "mesures": mesure, "minimum": MIN_MESURES,
            "maintenant": int(maintenant if maintenant is not None else time.time())}
