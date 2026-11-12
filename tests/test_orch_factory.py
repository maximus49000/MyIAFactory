import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_factory_flux_vide_ou_absent_valide(self):
        # Un projet créé sans workflow est valide : sa première demande en propose un.
        self.assertEqual(factory.lire(self.ecrire(flux=[]))["flux"], [])
        chemin = self.ecrire()
        brut = json.loads(chemin.read_text(encoding="utf-8"))
        del brut["flux"]
        chemin.write_text(json.dumps(brut), encoding="utf-8")
        self.assertEqual(factory.lire(chemin)["flux"], [])
        with self.assertRaises(factory.FactoryInvalide) as c:
            factory.lire(self.ecrire(flux="dev"))
        self.assertIn("flux", str(c.exception))

    def test_etape_de_validation_lue(self):
        flux = [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"},
                {"id": "val", "nom": "Validation du Directeur", "validation": True},
                {"id": "livre", "nom": "Livraison", "role": "dev", "service": "dev"}]
        f = factory.lire(self.ecrire(flux=flux))
        self.assertEqual(f["flux"][1], {"id": "val", "nom": "Validation du Directeur", "validation": True})

    def test_validation_premiere_derniere_ou_double_refusee(self):
        dev = {"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}
        v1 = {"id": "v1", "nom": "V1", "validation": True}
        v2 = {"id": "v2", "nom": "V2", "validation": True}
        fin = {"id": "fin", "nom": "Fin", "role": "dev", "service": "dev"}
        for flux, mot in (([v1, dev], "première"), ([dev, v1], "dernière"), ([dev, v1, v2, fin], "de suite")):
            with self.assertRaises(factory.FactoryInvalide, msg=str(flux)) as c:
                factory.lire(self.ecrire(flux=flux))
            self.assertIn(mot, str(c.exception))
        with self.assertRaises(factory.FactoryInvalide):   # une validation n'a ni rôle ni service
            factory.lire(self.ecrire(flux=[dev, {**v1, "role": "dev"}, fin]))

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

    def _home(self, nom="home"):
        home = self.dossier / nom
        home.mkdir()
        env = mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)})
        env.start()
        self.addCleanup(env.stop)
        return home

    def test_tilde_dans_skill(self):
        home = self._home()
        f = factory.lire(self.ecrire(skill="~/MyIAFactory/skill"))
        self.assertEqual(f["skill"], (home / "MyIAFactory" / "skill").resolve())
        self.assertEqual(f["memoire"], (home / "MyIAFactory" / "skill" / "orchestrateur" / "memoire").resolve())

    def test_tilde_au_milieu_inchange(self):
        self._home()
        for texte in ("a~b", "~x"):
            f = factory.lire(self.ecrire(skill=texte))
            self.assertEqual(f["skill"], (self.dossier / texte).resolve())

    def test_tilde_espaces_accents(self):
        home = self._home("Zoé Martin")
        f = factory.lire(self.ecrire(skill="~/MyIAFactory/skill"))
        self.assertEqual(f["skill"], (home / "MyIAFactory" / "skill").resolve())

    def test_agents_locaux_max_defaut_et_valide(self):
        self.assertEqual(factory.lire(self.ecrire())["agents_locaux_max"], 2)
        for bon in (1, 4, 16):
            self.assertEqual(factory.lire(self.ecrire(agents_locaux_max=bon))["agents_locaux_max"], bon)

    def test_agents_locaux_max_invalide(self):
        for mauvais in (0, 17, True, "2", 1.5, [], -1):
            with self.assertRaises(factory.FactoryInvalide, msg=repr(mauvais)) as c:
                factory.lire(self.ecrire(agents_locaux_max=mauvais))
            self.assertIn("agents_locaux_max", str(c.exception))


if __name__ == "__main__":
    unittest.main()
