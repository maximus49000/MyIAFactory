"""Le code d'accès du bureau ouvert au téléphone.

La clé vit dans `~/MyIAFactory/acces.json` (`{"cle": secret}`), hors de tout dépôt. Un téléphone est associé une fois :
la page de l'ordinateur montre un code d'association (usage unique, 10 minutes) dans un QR code ; le téléphone
l'échange contre la clé, posée en cookie. « Révoquer les téléphones » crée une nouvelle clé : les anciens cookies ne
valent plus rien.
"""
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # ni 0, O, 1, I, L
LONGUEUR_CODE = 8
DUREE_CODE_S = 600
CODES_MAX = 20       # codes en attente au plus (les plus anciens sont oubliés)
ESSAIS_MAX = 20      # échanges ratés avant d'annuler tous les codes en attente


class Cles:
    def __init__(self, chemin, horloge=time.time):
        self.chemin = Path(chemin)
        self.horloge = horloge
        self._verrou = threading.Lock()
        self._cle = None
        self._codes = {}      # code -> instant d'expiration
        self._rates = 0

    def _ecrire(self, cle):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.chemin.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"cle": cle}, f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.chemin)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _charger(self):
        if self._cle is None:
            try:
                cle = json.loads(self.chemin.read_text(encoding="utf-8")).get("cle")
            except (OSError, ValueError, AttributeError):
                cle = None
            if not (isinstance(cle, str) and len(cle) >= 32):
                cle = secrets.token_urlsafe(32)
                self._ecrire(cle)
            self._cle = cle
        return self._cle

    def cle(self):
        with self._verrou:
            return self._charger()

    def revoquer(self):
        """Une nouvelle clé : les cookies déjà posés et les codes en attente ne valent plus."""
        with self._verrou:
            cle = secrets.token_urlsafe(32)
            self._ecrire(cle)
            self._cle = cle
            self._codes.clear()
            return cle

    def code_association(self):
        with self._verrou:
            self._charger()
            maintenant = self.horloge()
            self._codes = {c: e for c, e in self._codes.items() if e > maintenant}
            while len(self._codes) >= CODES_MAX:
                self._codes.pop(next(iter(self._codes)))
            code = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_CODE))
            self._codes[code] = maintenant + DUREE_CODE_S
            return code

    def expiration(self, code):
        with self._verrou:
            return self._codes.get(code)

    def _trouver(self, code):
        trouve = None
        if isinstance(code, str):
            for c in list(self._codes):
                if hmac.compare_digest(c.encode(), code.upper().encode()):
                    trouve = c
        return trouve

    def _rate(self):
        self._rates += 1
        if self._rates >= ESSAIS_MAX:
            self._codes.clear()
            self._rates = 0

    def en_attente(self, code):
        """Vrai si le code vaut encore (rien n'est consommé) ; un faux compte comme un essai raté."""
        with self._verrou:
            trouve = self._trouver(code)
            if trouve is not None and self._codes[trouve] > self.horloge():
                return True
            self._rate()
            return False

    def echanger(self, code):
        """La clé contre un code valide (qui est alors consommé) ; sinon None."""
        with self._verrou:
            maintenant = self.horloge()
            trouve = self._trouver(code)
            if trouve is not None and self._codes.pop(trouve) > maintenant:
                self._rates = 0
                return self._charger()
            self._rate()
            return None

    def valide(self, cookie):
        if not isinstance(cookie, str) or not cookie:
            return False
        return hmac.compare_digest(cookie.encode(), self.cle().encode())
