"""Le moniteur de l'orchestrateur (`lancer guetter`) : il annonce les demandes et note sa présence (essai réel)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from orchestrateur import guetteur


class Horloge:
    def __init__(self):
        self.t = datetime(2026, 11, 11, 18, 0, 0).astimezone()

    def __call__(self):
        return self.t


class TestGuetteur(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        d = Path(self._t.name)
        self.journal, self.presence = d / "demandes.jsonl", d / "presence.json"
        self.horloge = Horloge()
        self.lignes = []

    def tour(self, n=1, apres=None):
        def dormir(s):
            self.horloge.t += timedelta(seconds=s)
            if apres:
                apres()
        guetteur.guetter(self.journal, self.presence, dormir=dormir, horloge=self.horloge, tours=n,
                         sortie=self.lignes.append)

    def test_annonce_seulement_les_nouvelles_demandes(self):
        self.journal.write_text(json.dumps({"id": "r1", "type": "message"}) + "\n", encoding="utf-8")
        ajout = lambda: self.journal.open("a", encoding="utf-8").write(json.dumps({"id": "r2", "type": "cahier"}) + "\n")
        self.tour(2, apres=ajout)
        self.assertTrue(any("r2" in l and "cahier" in l for l in self.lignes), self.lignes)
        self.assertFalse(any("r1" in l for l in self.lignes), "une demande d'avant le moniteur n'est pas réannoncée")

    def test_note_sa_presence(self):
        self.tour(1)
        p = json.loads(self.presence.read_text(encoding="utf-8"))
        self.assertEqual(datetime.fromisoformat(p["maj"]), self.horloge.t.replace(microsecond=0)
                         - timedelta(seconds=guetteur.PAS_S))

    def test_present(self):
        self.assertFalse(guetteur.present(self.presence, self.horloge()))   # jamais lancé
        self.tour(1)
        self.assertTrue(guetteur.present(self.presence, self.horloge()))
        self.assertFalse(guetteur.present(self.presence, self.horloge() + timedelta(seconds=guetteur.FRAICHEUR_S + 5)))
        self.presence.write_text("illisible", encoding="utf-8")
        self.assertFalse(guetteur.present(self.presence, self.horloge()))

    def test_journal_absent_puis_cree(self):
        self.tour(2, apres=lambda: self.journal.write_text(json.dumps({"id": "r1", "type": "fonctionnalite"}) + "\n",
                                                          encoding="utf-8"))
        self.assertTrue(any("r1" in l for l in self.lignes), self.lignes)


if __name__ == "__main__":
    unittest.main()
