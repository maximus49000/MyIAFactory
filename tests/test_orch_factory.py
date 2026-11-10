import json
import tempfile
import unittest
from pathlib import Path

from orchestrateur import factory
from tests.orch_aide import RACINE, factory_minimale


class TestFactory(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)

    def ecrire(self, **champs):
        base = {"skill": str(RACINE), "services": [{"id": "dev", "nom": "Dev"}],
                "flux": [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}]}
        base.update(champs)
        chemin = self.dossier / "factory.json"
        chemin.write_text(json.dumps(base), encoding="utf-8")
        return chemin

    def test_factory_minimale(self):
        f = factory.lire(self.ecrire())
        self.assertEqual(f["skill"], RACINE.resolve())
        self.assertEqual(f["suivi"], (self.dossier / "suivi.json").resolve())
        self.assertEqual(f["pieces"], (self.dossier / "pieces").resolve())
        self.assertEqual(f["seuil_methode"], 3)
        self.assertIsNone(f["genre"])
        self.assertEqual(f["mots_interdits"], [])
        self.assertEqual(f["memoire"], RACINE.resolve() / "orchestrateur" / "memoire")
        self.assertIsNone(f["consignes"])

    def test_chemins_relatifs_au_fichier(self):
        sous = self.dossier / ".factory"
        sous.mkdir()
        (sous / "factory.json").write_text(json.dumps({
            "skill": "../skill", "services": [{"id": "dev", "nom": "Dev"}], "fiches": "equipe",
            "flux": [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}]}), encoding="utf-8")
        f = factory.lire(sous / "factory.json")
        self.assertEqual(f["fiches"], (sous / "equipe").resolve())
        self.assertEqual(f["skill"], (self.dossier / "skill").resolve())
        self.assertEqual(f["nom"], self.dossier.name)   # le dossier du projet, pas « .factory »

    def test_factory_genre_invalide(self):
        for mauvais in ("../x", "A", "", 3, "a" * 41):
            with self.assertRaises(factory.FactoryInvalide, msg=repr(mauvais)):
                factory.lire(self.ecrire(genre=mauvais))
        self.assertEqual(factory.lire(self.ecrire(genre="vitrine"))["genre"], "vitrine")

    def test_factory_flux_vide(self):
        with self.assertRaises(factory.FactoryInvalide) as c:
            factory.lire(self.ecrire(flux=[]))
        self.assertIn("flux", str(c.exception))

    def test_flux_refuse_les_colonnes_reservees_et_les_doublons(self):
        etape = {"nom": "X", "role": "dev", "service": "dev"}
        for flux in ([{"id": "cadrage", **etape}], [{"id": "fait", **etape}],
                     [{"id": "a", **etape}, {"id": "a", **etape}], [{"id": "a", **etape, "service": "autre"}]):
            with self.assertRaises(factory.FactoryInvalide, msg=str(flux)):
                factory.lire(self.ecrire(flux=flux))

    def test_fichier_illisible_ou_incomplet(self):
        for contenu in ("pas du json", "[]", "{}"):
            chemin = self.dossier / "mauvais.json"
            chemin.write_text(contenu, encoding="utf-8")
            with self.assertRaises(factory.FactoryInvalide):
                factory.lire(chemin)
        with self.assertRaises(factory.FactoryInvalide):
            factory.lire(self.dossier / "absent.json")

    def test_commandes_et_seuil(self):
        f = factory.lire(self.ecrire(commandes={"etat": ["py", "x.py"]}, seuil_methode=5))
        self.assertEqual(f["commandes"], {"etat": ["py", "x.py"]})
        self.assertEqual(f["seuil_methode"], 5)
        for mauvais in ({"commandes": {"etat": []}}, {"commandes": {"etat": "x"}}, {"seuil_methode": 0},
                        {"mots_interdits": [3]}):
            with self.assertRaises(factory.FactoryInvalide, msg=str(mauvais)):
                factory.lire(self.ecrire(**mauvais))

    def test_ecrire_genre_garde_le_reste(self):
        chemin = factory_minimale(self.dossier)
        factory.ecrire_genre(chemin, "vitrine")
        d = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(d["genre"], "vitrine")
        self.assertEqual(d["reglages"], "reglages.json")


if __name__ == "__main__":
    unittest.main()
