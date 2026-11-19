"""Client de l'API OVH, signé, sans dépendance (urllib seulement, pas de SDK OVH).

Signature OVH : "$1$" + sha1("+".join([secret, consommateur, METHODE, url, corps, horodatage])) en hexadécimal. L'horodatage
vient de `GET {point}/auth/time` (non signé), jamais de l'horloge locale : un poste en avance ou en retard ferait refuser
toutes les requêtes. Le corps signé est exactement le texte envoyé. Aucun secret ni consommateur dans les messages d'erreur.
"""
import hashlib
import http.client
import json
import urllib.error
import urllib.request

POINTS = {
    "ovh-eu": "https://eu.api.ovh.com/1.0",
    "ovh-ca": "https://ca.api.ovh.com/1.0",
    "ovh-us": "https://api.us.ovhcloud.com/1.0",
}
DELAI_S = 30


class ErreurOvh(Exception):
    def __init__(self, code, message):
        super().__init__(f"OVH {code} : {message}")
        self.code = code
        self.message = message


def _http_urllib(methode, url, entetes, corps):
    requete = urllib.request.Request(url, data=corps, headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_S) as reponse:
            return reponse.status, reponse.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        raise ErreurOvh(0, f"API OVH injoignable ({type(e).__name__})") from None


class ClientOvh:
    def __init__(self, point, cle_app, secret, consommateur, http=None):
        if point in POINTS:
            point = POINTS[point]
        elif not str(point).startswith("http"):
            raise ValueError(f"Point d'accès OVH inconnu : « {point} ». Noms valides : {', '.join(sorted(POINTS))}, ou une URL http(s).")
        self.point = point.rstrip("/")
        self.cle_app = cle_app
        self.secret = secret
        self.consommateur = consommateur
        self.http = http or _http_urllib

    def signer(self, methode, url, corps_texte, horodatage):
        brut = "+".join([self.secret, self.consommateur, methode.upper(), url, corps_texte, str(horodatage)])
        return "$1$" + hashlib.sha1(brut.encode("utf-8")).hexdigest()

    def _heure(self):
        statut, texte = self.http("GET", self.point + "/auth/time", {}, None)
        if statut != 200:
            raise ErreurOvh(statut, "heure du serveur OVH indisponible")
        try:
            return int(texte.strip())
        except ValueError:
            raise ErreurOvh(statut, "heure du serveur OVH illisible") from None

    @staticmethod
    def _message(texte):
        try:
            donnees = json.loads(texte)
            if isinstance(donnees, dict) and donnees.get("message"):
                return str(donnees["message"])
        except ValueError:
            pass
        return (texte or "").strip()[:200] or "réponse vide"

    def appeler(self, methode, chemin, corps=None):
        methode = methode.upper()
        url = self.point + chemin
        corps_texte = "" if corps is None else json.dumps(corps, ensure_ascii=False)
        horodatage = self._heure()
        entetes = {
            "X-Ovh-Application": self.cle_app,
            "X-Ovh-Consumer": self.consommateur,
            "X-Ovh-Timestamp": str(horodatage),
            "X-Ovh-Signature": self.signer(methode, url, corps_texte, horodatage),
        }
        octets = None
        if corps is not None:
            entetes["Content-Type"] = "application/json"
            octets = corps_texte.encode("utf-8")
        statut, texte = self.http(methode, url, entetes, octets)
        if statut == 401 or statut == 403:
            raise ErreurOvh(statut, "identifiants OVH refusés ou droits insuffisants : " + self._message(texte))
        if statut >= 400:
            raise ErreurOvh(statut, self._message(texte))
        if not texte.strip():
            return None
        try:
            return json.loads(texte)
        except ValueError:
            return texte
