"""Demande de tâche et index du poste (`outils/serveur_tache.py`). Dossier temporaire : jamais le vrai ~/MyIAFactory."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_tache as st  # noqa: E402


def brut(**plus):
    return {"type": "emulation", "projet": "demo", "mode": "scenario", "scenario": "demarrage", **plus}


class TestDemande(unittest.TestCase):
    def test_demande_valide_par_defaut(self):
        d = st.valider_demande(brut())
        self.assertEqual(d.limites, st.LIMITES_DEFAUT)
        self.assertRegex(d.id, r"^t\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual((d.type, d.mode, d.scenario), ("emulation", "scenario", "demarrage"))

    def test_limites_ne_depassent_jamais_le_defaut(self):
        d = st.valider_demande(brut(limites={"duree_s": 60, "captures": 5}))
        self.assertEqual(d.limites["duree_s"], 60)
        self.assertEqual(d.limites["captures"], 5)
        self.assertEqual(d.limites["octets"], st.LIMITES_DEFAUT["octets"])
        for cle in st.LIMITES_DEFAUT:
            with self.assertRaises(ValueError):
                st.valider_demande(brut(limites={cle: st.LIMITES_DEFAUT[cle] + 1}))
            with self.assertRaises(ValueError):
                st.valider_demande(brut(limites={cle: 0}))
            with self.assertRaises(ValueError):
                st.valider_demande(brut(limites={cle: "10"}))
        with self.assertRaises(ValueError):
            st.valider_demande(brut(limites={"inconnue": 1}))

    def test_mode_scenario_exige_un_scenario(self):
        sans = brut()
        del sans["scenario"]
        with self.assertRaises(ValueError):
            st.valider_demande(sans)
        with self.assertRaises(ValueError):
            st.valider_demande(brut(scenario="../x"))
        with self.assertRaises(ValueError):
            st.valider_demande(brut(mode="autre"))
        self.assertEqual(st.valider_demande(brut(mode="pilote", scenario=None)).mode, "pilote")

    def test_id_hostile_refuse(self):
        for mauvais in ("../x", "a b", "", "t" * 200):
            with self.assertRaises(ValueError):
                st.valider_demande(brut(id=mauvais))
        self.assertEqual(st.valider_demande(brut(id="t20261119-101500-ab12")).id, "t20261119-101500-ab12")

    def test_type_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            st.valider_demande(brut(type="shell"))

    def test_nouvel_id_deterministe(self):
        self.assertEqual(st.nouvel_id(lambda: 0, lambda n: "ab12"), "t19700101-000000-ab12")


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.index = st.Index(Path(self.tmp.name))

    def test_index_ecriture_atomique_et_lecture(self):
        self.assertEqual(self.index.lire(), {})
        self.index.enregistrer("a", {"etat": "en_attente"})
        self.index.enregistrer("b", {"etat": "en_cours"})
        self.index.enregistrer("a", {"etat": "terminee"})
        self.assertEqual(self.index.lire(), {"a": {"etat": "terminee"}, "b": {"etat": "en_cours"}})
        self.index.retirer("a")
        self.index.retirer("absent")
        self.assertEqual(list(self.index.lire()), ["b"])
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], ["taches.json"])

    def test_index_abime_lu_comme_vide(self):
        for contenu in ("{pas du json", "[1, 2]", ""):
            (Path(self.tmp.name) / "taches.json").write_text(contenu, encoding="utf-8")
            self.assertEqual(self.index.lire(), {})
        self.index.enregistrer("a", {"etat": "en_attente"})
        self.assertEqual(self.index.lire(), {"a": {"etat": "en_attente"}})

    def test_deux_ecritures_simultanees_sans_perte(self):
        erreurs = []

        def ecrire(prefixe):
            try:
                for i in range(20):
                    self.index.enregistrer(f"{prefixe}{i}", {"etat": "en_attente"})
            except Exception as e:  # noqa: BLE001
                erreurs.append(e)

        fils = [threading.Thread(target=ecrire, args=(p,)) for p in "xy"]
        [f.start() for f in fils]
        [f.join() for f in fils]
        self.assertEqual(erreurs, [])
        self.assertEqual(len(self.index.lire()), 40)


if __name__ == "__main__":
    unittest.main()
