"""Le moteur et la mise à jour de la skill : vérification à intervalle, relance au premier passage libre. Rien de réel :
la vérification et la relance du bureau sont simulées."""
import unittest

from moteur import boucle, regles


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.verifs, self.relances = [], []
        self.reponse = {"etat": "a_jour", "message": "La skill est à jour (abc1234).", "commits": []}
        self.horloge = Horloge()

        def verifier():
            self.verifs.append(self.horloge.t)
            return dict(self.reponse)

        self.moteur = boucle.Moteur([], horloge=self.horloge, synchrone=True, mise_a_jour=verifier,
                                    relancer_bureau=lambda: self.relances.append(self.horloge.t) or "relancé")


class TestMiseAJour(Base):
    def test_sans_mise_a_jour_branchee_rien_n_est_verifie(self):
        m = boucle.Moteur([], synchrone=True)
        m.tour()
        self.assertFalse(m.relance_demandee)

    def test_premiere_verification_au_demarrage_puis_a_intervalle(self):
        self.moteur.tour()
        self.moteur.tour()
        self.assertEqual(len(self.verifs), 1)
        self.horloge.t += boucle.INTERVALLE_MAJ_S - 1
        self.moteur.tour()
        self.assertEqual(len(self.verifs), 1)
        self.horloge.t += 2
        self.moteur.tour()
        self.assertEqual(len(self.verifs), 2)
        self.assertFalse(self.moteur.relance_demandee)

    def test_mise_a_jour_faite_relance_au_passage_libre(self):
        self.reponse = {"etat": "mise_a_jour", "message": "Skill mise à jour : a → b (1 commit(s)).", "commits": ["b x"]}
        self.moteur.tour()
        self.assertTrue(self.moteur.relance_demandee)
        self.assertEqual(len(self.relances), 1)
        self.assertTrue(any("Skill mise à jour" in ligne for ligne in self.moteur.journal))

    def test_pas_de_relance_tant_qu_un_agent_travaille(self):
        self.reponse = {"etat": "mise_a_jour", "message": "Skill mise à jour.", "commits": ["b x"]}
        etat = regles.nouvel_etat()
        etat["en_cours"].add("t1")
        self.moteur.etats["projet"] = etat
        self.moteur.tour()
        self.moteur.tour()
        self.assertFalse(self.moteur.relance_demandee)
        self.assertEqual(self.relances, [])
        self.assertEqual(len(self.verifs), 1)        # mise à jour faite une fois : on attend, sans revérifier
        etat["en_cours"].discard("t1")
        self.moteur.tour()
        self.assertTrue(self.moteur.relance_demandee)
        self.assertEqual(len(self.relances), 1)

    def test_une_installation_ou_un_retour_non_lu_n_est_pas_libre(self):
        self.assertTrue(self.moteur._libre())
        self.moteur.file_installations.append(("projet", "t2"))
        self.assertFalse(self.moteur._libre())
        self.moteur.file_installations.clear()
        self.moteur.pause_installation = {"texte": "installation"}
        self.assertFalse(self.moteur._libre())
        self.moteur.pause_installation = None
        self.moteur.retours.put("retour d'agent")
        self.assertFalse(self.moteur._libre())

    def test_bloquee_est_dite_une_fois_sans_relance(self):
        self.reponse = {"etat": "bloquee", "message": "Mise à jour en attente : fichiers modifiés.", "commits": ["b x"]}
        self.moteur.tour()
        self.horloge.t += boucle.INTERVALLE_MAJ_S + 1
        self.moteur.tour()
        self.assertFalse(self.moteur.relance_demandee)
        self.assertEqual(sum("fichiers modifiés" in x for x in self.moteur.journal), 1)   # pas répété à chaque essai

    def test_une_erreur_de_verification_n_arrete_pas_le_moteur(self):
        def casse():
            raise OSError("disque")
        m = boucle.Moteur([], synchrone=True, mise_a_jour=casse)
        m.tour()
        self.assertFalse(m.relance_demandee)
        self.assertTrue(any("disque" in x for x in m.journal))


class TestRelanceDuMoteur(unittest.TestCase):
    def test_le_moteur_libere_son_verrou_et_lance_le_suivant(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from moteur import __main__ as principal, verrou

        class FauxMoteur:
            def __init__(self, projets, **k):
                self.k, self.journal, self.relance_demandee = k, [], False

            def tour(self):
                self.relance_demandee = True

            def attendre(self, arret):
                raise AssertionError("pas d'attente : il se relance")

        with tempfile.TemporaryDirectory() as d:
            bureau, chemin_verrou = Path(d) / "bureau.json", Path(d) / "moteur.pid"
            bureau.write_text("{}", encoding="utf-8")
            lances = []
            vus = {}

            def lancer(argv, dossier):
                vus["verrou_libre"] = verrou.lire(chemin_verrou) is None
                lances.append(argv)

            argv = ["--bureau", str(bureau), "--verrou", str(chemin_verrou)]
            with mock.patch.object(principal.boucle, "Moteur", FauxMoteur):
                self.assertEqual(principal.main(argv, lancer=lancer), 0)
            self.assertEqual(len(lances), 1)
            self.assertEqual(lances[0][1:], ["-m", "moteur", *argv])
            self.assertTrue(vus["verrou_libre"])       # libéré avant que le suivant démarre

    def test_sans_mise_a_jour_rien_n_est_branche(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from moteur import __main__ as principal

        recus = {}

        class FauxMoteur:
            def __init__(self, projets, **k):
                recus.update(k)
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as d:
            bureau = Path(d) / "bureau.json"
            bureau.write_text("{}", encoding="utf-8")
            with mock.patch.object(principal.boucle, "Moteur", FauxMoteur):
                with self.assertRaises(KeyboardInterrupt):
                    principal.main(["--bureau", str(bureau), "--verrou", str(Path(d) / "v.pid"), "--sans-mise-a-jour"])
        self.assertNotIn("mise_a_jour", recus)


if __name__ == "__main__":
    unittest.main()
