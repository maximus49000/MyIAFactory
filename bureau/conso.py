"""La consommation du forfait Claude Code : ce qu'il reste sur la fenêtre de 5 h, sur la semaine, par modèle.

Source : le point d'usage du compte (`/api/oauth/usage`), lu avec le jeton que Claude Code garde dans
`~/.claude/.credentials.json`. Le jeton n'est que lu, jamais rafraîchi ni écrit (Claude Code le renouvelle quand il
tourne) et ne sort jamais du serveur : le navigateur ne reçoit que des pourcentages et des heures de remise à zéro.
Un jeton absent ou périmé, ou un réseau en panne : `{"disponible": false, "raison": …}`, sans faire tomber le bureau.
"""
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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


class Conso:
    """La consommation, mise en cache `DUREE_CACHE` secondes (le navigateur interroge souvent)."""

    def __init__(self, identifiants=IDENTIFIANTS, telecharger=_telecharger, horloge=time.monotonic):
        self.identifiants, self._telecharger, self._horloge = identifiants, telecharger, horloge
        self._verrou, self._cache, self._a = threading.Lock(), None, 0.0

    def lire(self):
        with self._verrou:
            if self._cache is not None and self._horloge() - self._a < DUREE_CACHE:
                return self._cache
            jeton, raison = _jeton(self.identifiants)
            if jeton is None:
                resultat = {"disponible": False, "raison": raison}
            else:
                try:
                    resultat = mettre_en_forme(self._telecharger(jeton))
                except urllib.error.HTTPError as e:
                    resultat = {"disponible": False, "raison": "Connexion à renouveler : utilisez Claude Code un instant."
                                if e.code in (401, 403) else f"Consommation indisponible (code {e.code})."}
                except (OSError, ValueError):
                    resultat = {"disponible": False, "raison": "Consommation indisponible (réseau)."}
            self._cache, self._a = resultat, self._horloge()
            return resultat
