"""Le bureau commun lancé par l'installation (outil.py bureau) : en arrière-plan, relancé si besoin."""
import json
import subprocess
import sys
import unittest

from tests.inst_aide import AvecMaison
from installation import dossier, lanceur
from installation.dossier import Echec


class Faux:
    """Un bureau simulé : `en_marche` dit si le port répond ; démarrer et arrêter le changent."""

    def __init__(self, en_marche=False, demarre_vraiment=True, annonces=("Le bureau est ouvert sur http://127.0.0.1:8770/",)):
        self.en_marche = en_marche
        self.demarre_vraiment = demarre_vraiment
        self.annonces = annonces
        self.demarres, self.arretes = [], []

    def sonde(self, port):
        return self.en_marche

    def demarrer(self, bureau_json, journal):
        self.demarres.append(bureau_json)
        journal.write_text("\n".join(self.annonces) + "\n", encoding="utf-8")
        self.en_marche = self.demarre_vraiment
        return 4242

    def arreter(self, pid):
        self.arretes.append(pid)
        self.en_marche = False

    def lancer(self, **kw):
        return lanceur.lancer(demarrer=self.demarrer, arreter=self.arreter, sonde=self.sonde,
                              attendre=lambda s: None, delai=0.05, **kw)


class TestLanceur(AvecMaison):

    def setUp(self):
        super().setUp()
        dossier.racine().mkdir()
        (self.projet / "reglages.json").write_text("{}", encoding="utf-8")   # le lanceur ne lit que le port
        dossier.bureau().write_text(json.dumps({"port": 8770, "projets": [str(self.projet / "reglages.json")]}),
                                    encoding="utf-8")

    def test_bureau_lance_en_arriere_plan(self):
        f = Faux()
        r = f.lancer()
        self.assertEqual(r["action"], "lance")
        self.assertEqual(r["url"], "http://127.0.0.1:8770/")
        self.assertEqual(f.demarres, [dossier.bureau()])
        self.assertEqual(lanceur.fichier_pid().read_text(encoding="utf-8").strip(), "4242")
        self.assertIn("Le bureau est ouvert sur http://127.0.0.1:8770/", r["annonces"])

    def test_bureau_deja_lance_rien_ne_bouge(self):
        f = Faux(en_marche=True)
        r = f.lancer()
        self.assertEqual(r["action"], "deja_lance")
        self.assertEqual((f.demarres, f.arretes), ([], []))

    def test_relancer_arrete_puis_relance(self):
        f = Faux()
        f.lancer()
        r = f.lancer(relancer=True)
        self.assertEqual(r["action"], "relance")
        self.assertEqual(f.arretes, [4242])
        self.assertEqual(len(f.demarres), 2)

    def test_relancer_un_bureau_lance_a_la_main_refuse(self):
        f = Faux(en_marche=True)   # aucun fichier de PID : ce n'est pas l'installation qui l'a lancé
        with self.assertRaises(Echec) as e:
            f.lancer(relancer=True)
        self.assertIn("arrêtez-le", str(e.exception))
        self.assertEqual((f.demarres, f.arretes), ([], []))

    def test_relancer_sans_bureau_en_marche_le_lance(self):
        f = Faux()
        self.assertEqual(f.lancer(relancer=True)["action"], "lance")

    def test_bureau_qui_ne_repond_pas_cite_son_journal(self):
        f = Faux(demarre_vraiment=False, annonces=("Impossible de démarrer le serveur : port pris",))
        with self.assertRaises(Echec) as e:
            f.lancer()
        self.assertIn("port pris", str(e.exception))
        self.assertFalse(lanceur.fichier_pid().exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows seulement")
    def test_aucune_fenetre_noire(self):
        """Essai réel : lancé sans console, le bureau faisait surgir une fenêtre à chaque commande qu'il lance."""
        d = lanceur.drapeaux_windows()
        self.assertTrue(d & subprocess.CREATE_NO_WINDOW)
        self.assertFalse(d & subprocess.DETACHED_PROCESS)

    def test_bureau_absent_refuse(self):
        dossier.bureau().unlink()
        with self.assertRaises(Echec):
            Faux().lancer()


if __name__ == "__main__":
    unittest.main()
