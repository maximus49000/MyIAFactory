"""La consommation du forfait Claude Code : ce qu'il reste sur la fenêtre de 5 h, sur la semaine, par modèle.

Source : le point d'usage du compte (`/api/oauth/usage`), lu avec le jeton que Claude Code garde dans
`~/.claude/.credentials.json`. Le jeton n'est que lu, jamais rafraîchi ni écrit (Claude Code le renouvelle quand il
tourne) et ne sort jamais du serveur : le navigateur ne reçoit que des pourcentages et des heures de remise à zéro.
Un jeton absent ou périmé, ou un réseau en panne : `{"disponible": false, "raison": …}`, sans faire tomber le bureau.

Dans le bureau (`memoire=True`), le rond est la source unique des jauges : une lecture réussie porte `source: "compte"`
et est versée à l'historique d'abonnement ; sinon, on se rabat sur le dernier instantané des appels du moteur
(`source: "moteur"`, avec la `raison` de l'échec et `mesure`, l'instant de cet instantané) plutôt que d'afficher
« indisponible ». Ici les pourcentages sont en « utilisé » (`utilise`) et en « reste » (`reste`).
"""
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import abonnement

URL = "https://api.anthropic.com/api/oauth/usage"
IDENTIFIANTS = Path.home() / ".claude" / ".credentials.json"
DUREE_CACHE = 60.0
LIBELLES = {"five_hour": "5 heures", "seven_day": "Semaine"}
ORDRE = ("five_hour", "seven_day")
PREFIXE_SEMAINE = "seven_day_"
IGNOREES = ("extra_usage",)   # les crédits supplémentaires ne sont pas une fenêtre du forfait


def _jeton(chemin):
    """(jeton, raison) : le jeton d'accès valide, ou la raison de son absence."""
    try:
        d = json.loads(Path(chemin).read_text(encoding="utf-8"))["claudeAiOauth"]
        jeton, expire = d["accessToken"], d.get("expiresAt")
    except (OSError, ValueError, KeyError, TypeError):
        return None, "Connexion Claude Code introuvable."
    if not isinstance(jeton, str) or not jeton:
        return None, "Connexion Claude Code introuvable."
    if isinstance(expire, (int, float)) and expire / 1000 < time.time():
        return None, "Connexion à renouveler : utilisez Claude Code un instant."
    return jeton, None


def _telecharger(jeton):
    requete = urllib.request.Request(URL, headers={"Authorization": "Bearer " + jeton,
                                                   "anthropic-beta": "oauth-2025-04-20"})
    with urllib.request.urlopen(requete, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def _libelle(cle):
    if cle in LIBELLES:
        return LIBELLES[cle]
    if cle.startswith(PREFIXE_SEMAINE):
        return "Semaine · " + cle[len(PREFIXE_SEMAINE):].replace("_", " ").capitalize()
    return cle.replace("_", " ").capitalize()


def mettre_en_forme(brut):
    """Les fenêtres du forfait : `[{"cle", "libelle", "utilise", "reste", "remise"}]`, la plus serrée d'abord
    dans le rond (`pire`). Une fenêtre sans pourcentage lisible est ignorée."""
    fenetres = []
    if isinstance(brut, dict):
        for cle, v in brut.items():
            if cle in IGNOREES or not isinstance(v, dict) or isinstance(v.get("utilization"), bool):
                continue
            utilise = v.get("utilization")
            if not isinstance(utilise, (int, float)) or utilise != utilise:
                continue
            utilise = max(0.0, min(100.0, float(utilise)))
            remise = v.get("resets_at")
            fenetres.append({"cle": cle, "libelle": _libelle(cle), "utilise": round(utilise, 1),
                             "reste": round(100.0 - utilise, 1), "remise": remise if isinstance(remise, str) else None})
    fenetres.sort(key=lambda f: (ORDRE.index(f["cle"]) if f["cle"] in ORDRE else len(ORDRE), f["cle"]))
    if not fenetres:
        return {"disponible": False, "raison": "Aucune consommation reçue."}
    pire = min(fenetres, key=lambda f: f["reste"])
    return {"disponible": True, "fenetres": fenetres, "pire": pire["cle"], "reste": pire["reste"],
            "t": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _epoch(iso):
    """Les secondes epoch d'une date ISO 8601 du compte, ou None."""
    try:
        return round(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except (AttributeError, ValueError, OverflowError):
        return None


def instantane_du_compte(forme, maintenant):
    """L'instantané d'abonnement (pourcentages **utilisés**, remise en epoch) d'une lecture réussie du compte : les deux
    fenêtres du forfait seulement, et seulement celles dont la remise à zéro est lisible. None sans fenêtre."""
    sortie = {}
    for f in forme.get("fenetres") or []:
        if f["cle"] in abonnement.FENETRES and (r := _epoch(f["remise"])):
            sortie[f["cle"]] = {"pourcent": f["utilise"], "remise": r}
    return {**sortie, "t": int(maintenant)} if sortie else None


def depuis_le_moteur(instantane, raison, maintenant):
    """La même forme qu'une lecture du compte, tirée du dernier instantané des appels du moteur (`source: "moteur"`) :
    les fenêtres déjà remises à zéro depuis sont écartées (leur pourcentage ne dit plus rien). `raison` : pourquoi la
    lecture directe a manqué. Sans rien de lisible, `{"disponible": False, "raison"}`."""
    fenetres = []
    for cle in abonnement.FENETRES:
        f = (instantane or {}).get(cle)
        if f and f["remise"] > maintenant:
            fenetres.append({"cle": cle, "libelle": LIBELLES[cle], "utilise": f["pourcent"],
                             "reste": round(100.0 - f["pourcent"], 1),
                             "remise": datetime.fromtimestamp(f["remise"], timezone.utc).isoformat(timespec="seconds")})
    if not fenetres:
        return {"disponible": False, "raison": raison}
    pire = min(fenetres, key=lambda f: f["reste"])
    return {"disponible": True, "fenetres": fenetres, "pire": pire["cle"], "reste": pire["reste"], "source": "moteur",
            "mesure": instantane["t"], "raison": raison,
            "t": datetime.fromtimestamp(instantane["t"], timezone.utc).isoformat(timespec="seconds")}


class Conso:
    """La consommation, mise en cache `DUREE_CACHE` secondes (le navigateur interroge souvent).

    `memoire=True` (le bureau) : chaque lecture réussie est versée comme instantané à l'historique d'abonnement (sans
    coût) et, quand elle échoue, on se rabat sur le dernier instantané des appels du moteur. `part` : une fonction qui
    rend ce que `abonnement.pour_la_page` rend (ou None) pour y lire la part estimée des coûts."""

    def __init__(self, identifiants=IDENTIFIANTS, telecharger=_telecharger, horloge=time.monotonic,
                 memoire=False, part=None, maintenant=time.time):
        self.identifiants, self._telecharger, self._horloge = identifiants, telecharger, horloge
        self.memoire, self._part, self._maintenant = memoire, part, maintenant
        self._verrou, self._cache, self._a = threading.Lock(), None, 0.0

    def _lecture(self):
        jeton, raison = _jeton(self.identifiants)
        if jeton is None:
            return {"disponible": False, "raison": raison}
        try:
            return mettre_en_forme(self._telecharger(jeton))
        except urllib.error.HTTPError as e:
            return {"disponible": False, "raison": "Connexion à renouveler : utilisez Claude Code un instant."
                    if e.code in (401, 403) else f"Consommation indisponible (code {e.code})."}
        except (OSError, ValueError):
            return {"disponible": False, "raison": "Consommation indisponible (réseau)."}

    def lire(self):
        with self._verrou:
            if self._cache is not None and self._horloge() - self._a < DUREE_CACHE:
                return self._cache
            resultat, maintenant = self._lecture(), self._maintenant()
            if self.memoire:
                if resultat["disponible"]:
                    resultat["source"], resultat["mesure"] = "compte", int(maintenant)
                    snap = instantane_du_compte(resultat, maintenant)
                    if snap:
                        abonnement.noter(snap, source=abonnement.SOURCE_COMPTE)
                else:   # le jeton manque, est périmé ou le réseau coupe : le dernier instantané du moteur, dit comme tel
                    resultat = depuis_le_moteur(abonnement.lire(), resultat["raison"], maintenant)
                resultat["part"] = self._lire_part()
            self._cache, self._a = resultat, self._horloge()
            return resultat

    def _lire_part(self):
        """{"pourcent_par_euro" (semaine, ou None), "mesures", "minimum"} ; None sans état d'abonnement (couche API)."""
        try:
            page = self._part() if self._part else None
            if not page:
                return None
            return {"pourcent_par_euro": page["pourcent_par_euro"]["seven_day"], "mesures": page["mesures"]["seven_day"],
                    "minimum": page["minimum"]}
        except Exception:   # la part ne fait jamais tomber le rond
            return None
