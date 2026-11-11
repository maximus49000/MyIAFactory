"""Essai réel : sans orchestrateur en cours, le bureau bloque les gestes et propose de le lancer."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import demarrage, serveur
from tests import copie_demo
from tests.test_serveur import SourceSimulee


class AvecDemo(unittest.TestCase):
    PRESENT = False
    ENT = {"X-Bureau": "1", "Content-Type": "application/json"}

    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        copie_demo(self.tmp / "demo")
        rel = self.tmp / "demo" / "releve.json"
        r = json.loads(rel.read_text(encoding="utf-8"))
        r["orchestrateur_present"] = self.PRESENT
        rel.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        self.lances = []
        self.srv = serveur.creer(self.tmp / "demo" / "reglages.json", port=0, ouvrir=SourceSimulee(),
                                 demarrer=lambda regl: self.lances.append(regl) or {"ok": True, "message": "Démarre."})
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def req(self, methode, chemin, corps=None, ent=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request(methode, chemin, body=None if corps is None else json.dumps(corps).encode(),
                  headers=ent if ent is not None else self.ENT)
        r = c.getresponse()
        d = r.read()
        c.close()
        return r.status, json.loads(d or b"{}")


class TestAbsent(AvecDemo):
    def test_etat_bloque_les_gestes(self):
        _, e = self.req("GET", "/api/etat", ent={})
        self.assertIs(e["orchestrateur_absent"], True)
        self.assertIs(e["agir"], False)

    def test_demande_refusee(self):
        code, r = self.req("POST", "/api/demande", {"type": "fonctionnalite", "texte": "Une idée"})
        self.assertEqual(code, 409)
        self.assertIn("orchestrateur", r["erreur"])

    def test_lancer_l_orchestrateur(self):
        code, r = self.req("POST", "/api/orchestrateur/lancer", {})
        self.assertEqual((code, r["ok"]), (200, True))
        self.assertEqual(len(self.lances), 1)
        code, r = self.req("POST", "/api/orchestrateur/lancer", {})   # un second clic pendant le démarrage
        self.assertEqual(len(self.lances), 1)
        self.assertIn("démarre", r["message"])

    def test_lancer_exige_l_en_tete(self):
        code, _ = self.req("POST", "/api/orchestrateur/lancer", {}, ent={"Content-Type": "application/json"})
        self.assertEqual(code, 403)
        self.assertEqual(self.lances, [])


class TestPresent(AvecDemo):
    PRESENT = True

    def test_rien_n_est_bloque(self):
        _, e = self.req("GET", "/api/etat", ent={})
        self.assertFalse(e.get("orchestrateur_absent"))
        self.assertIs(e["agir"], True)

    def test_lancer_refuse_s_il_tourne_deja(self):
        code, r = self.req("POST", "/api/orchestrateur/lancer", {})
        self.assertEqual(code, 409)
        self.assertEqual(self.lances, [])


class TestToutValider(AvecDemo):
    """Essai réel : « Tout valider » est une seule requête ; le serveur envoie chaque verdict lui-même (la page peut
    être fermée aussitôt)."""
    PRESENT = True

    def test_un_lot_de_verdicts(self):
        envoyees = []
        self.srv.projets["projet"].envoyer = lambda regl, d: envoyees.append(d) or (True, "")
        code, r = self.req("POST", "/api/demande", {"type": "lecons", "verdict": "valider",
                                                     "lecons": [{"id": "dev:1:L1"}]})
        self.assertEqual((code, r["envoyees"], r["refusees"]), (200, 1, []))
        self.assertEqual(envoyees, [{"type": "lecon", "id": "dev:1:L1", "verdict": "valider"}])

    def test_lot_refuse_les_inconnues_sans_bloquer_les_autres(self):
        envoyees = []
        self.srv.projets["projet"].envoyer = lambda regl, d: envoyees.append(d) or (True, "")
        code, r = self.req("POST", "/api/demande", {"type": "lecons", "verdict": "valider",
                                                     "lecons": [{"id": "inconnue"}, {"id": "dev:1:L1"}]})
        self.assertEqual(code, 200)
        self.assertEqual(r["envoyees"], 1)
        self.assertEqual([x["id"] for x in r["refusees"]], ["inconnue"])

    def test_lot_mal_forme(self):
        for corps in ({"type": "lecons", "verdict": "peut-etre", "lecons": [{"id": "dev:1:L1"}]},
                      {"type": "lecons", "verdict": "valider", "lecons": []},
                      {"type": "lecons", "verdict": "valider", "lecons": "dev:1:L1"}):
            self.assertEqual(self.req("POST", "/api/demande", corps)[0], 400, corps)


class TestDemarrage(unittest.TestCase):
    """Le lancement lui-même : jamais de vraie fenêtre ni de vrai `claude` dans les tests."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.projet = Path(self._t.name) / "Mon projet"
        (self.projet / ".factory").mkdir(parents=True)
        self.regl = self.projet / ".factory" / "reglages.json"
        self.regl.write_text("{}", encoding="utf-8")
        (self.projet / ".factory" / "factory.json").write_text(json.dumps({"modele_orchestrateur": "Opus"}),
                                                               encoding="utf-8")
        self.ouverts = []

    def demarrer(self, trouve="C:/outils/claude.exe"):
        return demarrage.demarrer(self.regl, trouver=lambda nom: trouve, windows=True,
                                  ouvrir=lambda *a: self.ouverts.append(a))

    def test_ouvre_claude_dans_le_projet_sur_le_modele_de_l_orchestrateur(self):
        r = self.demarrer()
        self.assertTrue(r["ok"])
        claude, modele, message, dossier = self.ouverts[0]
        self.assertEqual((claude, modele, Path(dossier)), ("C:/outils/claude.exe", "opus", self.projet))
        self.assertIn("factory.json", message)
        self.assertIn("orchestrateur", message)

    def test_sans_claude_le_message_a_copier(self):
        r = self.demarrer(trouve=None)
        self.assertFalse(r["ok"])
        self.assertEqual(self.ouverts, [])
        self.assertIn("factory.json", r["a_copier"])
        self.assertIn("claude", r["message"])

    def test_sans_fichier_de_factory(self):
        (self.projet / ".factory" / "factory.json").unlink()
        r = self.demarrer()
        self.assertFalse(r["ok"])
        self.assertEqual(self.ouverts, [])


if __name__ == "__main__":
    unittest.main()
