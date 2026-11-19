"""Client d'API OVH signé (`outils/ovh_api.py`). Le transport HTTP est simulé."""
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import ovh_api  # noqa: E402

POINT = "https://eu.api.ovh.com/1.0"


class HttpFactice:
    def __init__(self, reponses):
        self.reponses = reponses
        self.appels = []

    def __call__(self, methode, url, entetes, corps):
        self.appels.append((methode, url, dict(entetes), corps))
        return self.reponses.pop(0)


def client(reponses):
    http = HttpFactice(reponses)
    return ovh_api.ClientOvh(POINT, "app", "secret", "consommateur", http=http), http


class TestOvhApi(unittest.TestCase):
    def test_signature_connue(self):
        c, _ = client([])
        url = POINT + "/me"
        attendu = "$1$" + hashlib.sha1(("secret+consommateur+GET+" + url + "++1700000000").encode()).hexdigest()
        self.assertEqual(c.signer("GET", url, "", 1700000000), attendu)

    def test_heure_prise_sur_auth_time(self):
        c, http = client([(200, "1700000123"), (200, '{"ok": true}')])
        self.assertEqual(c.appeler("GET", "/me"), {"ok": True})
        self.assertEqual(http.appels[0][0:2], ("GET", POINT + "/auth/time"))
        self.assertNotIn("X-Ovh-Signature", http.appels[0][2])
        entetes = http.appels[1][2]
        self.assertEqual(entetes["X-Ovh-Timestamp"], "1700000123")
        self.assertEqual(entetes["X-Ovh-Application"], "app")
        self.assertEqual(entetes["X-Ovh-Consumer"], "consommateur")
        self.assertEqual(entetes["X-Ovh-Signature"], c.signer("GET", POINT + "/me", "", 1700000123))

    def test_401_donne_erreur_claire(self):
        c, _ = client([(200, "1700000000"), (401, '{"message": "Invalid credentials"}')])
        with self.assertRaises(ovh_api.ErreurOvh) as ctx:
            c.appeler("GET", "/me")
        self.assertEqual(ctx.exception.code, 401)
        self.assertNotIn("secret", str(ctx.exception))
        self.assertNotIn("consommateur", str(ctx.exception))

    def test_corps_json_signe_tel_quel(self):
        c, http = client([(200, "1700000000"), (200, "{}")])
        c.appeler("POST", "/dedicated/server/x/reboot", {"a": 1, "b": "é"})
        _, url, entetes, corps = http.appels[1]
        texte = corps.decode("utf-8")
        self.assertEqual(entetes["X-Ovh-Signature"], c.signer("POST", url, texte, 1700000000))
        self.assertEqual(entetes["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
