import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bureau import demandes, releve

R = releve.normaliser({
    "version": 2, "projet": "P", "factory": {"etat": "en marche"},
    "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}, {"id": "b", "nom": "B"}],
    "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
    "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
    "file": {"visibles": [{"id": "q1", "titre": "Q"}], "reste": 0},
    "actions": [{"id": "pause", "libelle": "Pause"},
                {"id": "doc", "libelle": "Doc", "lien": "https://exemple.org"},
                {"id": "gris", "libelle": "G", "actif": False}],
    "lecons": [{"id": "d1:L1", "agent": "d1", "texte": "t"}]})


class TestVerifier(unittest.TestCase):
    def ok(self, d):
        self.assertIsNone(demandes.verifier(d, R), d)

    def refus(self, d):
        m = demandes.verifier(d, R)
        self.assertTrue(m, d)
        return m

    def test_acceptees(self):
        self.ok({"type": "bouton", "id": "pause"})
        self.ok({"type": "deplacer", "tache": "t1", "colonne": "b"})
        self.ok({"type": "deplacer", "tache": "q1", "colonne": "a"})
        self.ok({"type": "retour", "tache": "t1", "texte": "bien"})
        self.ok({"type": "retour", "tache": "t1", "texte": "x" * 3500})
        self.ok({"type": "lecon", "id": "d1:L1", "verdict": "valider"})
        self.ok({"type": "lecon", "id": "d1:L1", "verdict": "invalider"})

    def test_refusees(self):
        for d in (None, [], "x", {}, {"type": "autre"},
                  {"type": "bouton", "id": "inconnu"}, {"type": "bouton"},
                  {"type": "bouton", "id": "doc"},  # un lien n'est pas une demande
                  {"type": "bouton", "id": "gris"},  # grisé
                  {"type": "bouton", "id": 3},
                  {"type": "deplacer", "tache": "zz", "colonne": "a"},
                  {"type": "deplacer", "tache": "t1", "colonne": "zz"},
                  {"type": "deplacer", "tache": "t1"},
                  {"type": "retour", "tache": "zz", "texte": "x"},
                  {"type": "retour", "tache": "t1", "texte": "   \n"},
                  {"type": "retour", "tache": "t1", "texte": 3},
                  {"type": "retour", "tache": "t1", "texte": "x" * 3501},
                  {"type": "lecon", "id": "inconnue", "verdict": "valider"},
                  {"type": "lecon", "id": "d1:L1", "verdict": "peut-être"},
                  {"type": "lecon", "id": "d1:L1"}):
            self.refus(d)

    def test_version_1_sans_actions(self):
        r1 = releve.normaliser({k: v for k, v in R.items() if k not in ("actions", "lecons")} | {"version": 1})
        self.assertTrue(demandes.verifier({"type": "bouton", "id": "pause"}, r1))

    def test_nettoyer_ne_garde_que_les_champs_connus(self):
        d = demandes.nettoyer({"type": "retour", "tache": "t1", "texte": "x", "t": "faux", "autre": 1})
        self.assertEqual(d, {"type": "retour", "tache": "t1", "texte": "x"})


class TestEnvoyer(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.sortie = self.tmp / "sortie.jsonl"

    def regl(self, code, extra=None):
        return {"dossier": str(self.tmp), "actions": {"commande": [sys.executable, "-c", code] + (extra or []),
                                                      "dossier": "."}}

    def test_recopie_la_demande_en_json_utf8(self):
        code = ("import sys; open(sys.argv[1],'ab').write(sys.stdin.buffer.read()+b'\\n')")
        regl = self.regl(code, [str(self.sortie)])
        self.assertEqual(demandes.envoyer(regl, {"type": "retour", "tache": "t1", "texte": "é — ü"}), (True, ""))
        ligne = json.loads(self.sortie.read_bytes().decode("utf-8"))
        self.assertEqual((ligne["type"], ligne["texte"]), ("retour", "é — ü"))
        self.assertRegex(ligne["t"], r"^\d{4}-\d\d-\d\dT")

    def test_echec_avec_message(self):
        regl = self.regl("import sys; sys.stdin.read(); print('non'); sys.exit(3)")
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}), (False, "non"))

    def test_echec_message_des_erreurs(self):
        regl = self.regl("import sys; sys.stderr.write('oups\\nsuite'); sys.exit(1)")
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}), (False, "oups"))

    def test_echec_sans_message(self):
        regl = self.regl("import sys; sys.exit(2)")
        ok, m = demandes.envoyer(regl, {"type": "bouton", "id": "x"})
        self.assertFalse(ok)
        self.assertIn("2", m)

    def test_depassement(self):
        ancien = releve.DELAI_COMMANDE_S
        releve.DELAI_COMMANDE_S = 1
        self.addCleanup(setattr, releve, "DELAI_COMMANDE_S", ancien)
        regl = self.regl("import time; time.sleep(15)")
        debut = time.monotonic()
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}),
                         (False, "La commande d'actions a dépassé 1 s."))
        self.assertLess(time.monotonic() - debut, 10)

    def test_sans_commande(self):
        for regl in ({"dossier": str(self.tmp)}, {"dossier": str(self.tmp), "actions": {}},
                     {"dossier": str(self.tmp), "actions": {"commande": "python x.py"}}):
            self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}),
                             (False, "Aucune commande d'actions dans les réglages."))

    def test_commande_introuvable(self):
        regl = {"dossier": str(self.tmp), "actions": {"commande": ["commande-qui-n-existe-pas"]}}
        ok, m = demandes.envoyer(regl, {"type": "bouton", "id": "x"})
        self.assertFalse(ok)
        self.assertTrue(m)

    def test_commande_qui_ferme_son_entree(self):
        # n'écrit pas dans le tube (ne lit pas l'entrée) : pas d'erreur côté bureau
        regl = self.regl("pass")
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}), (True, ""))


if __name__ == "__main__":
    unittest.main()
