"""Mandataire HTTPS côté poste (`outils/serveur_service.py`, `lancer.py service mandataire`) : le nom gratuit sslip.io se déduit de
l'adresse IPv4 du serveur ; le Directeur seul peut mettre un service en HTTPS. Faux SSH conduisant le vrai script hôte."""
import io
import json
import unittest
from unittest import mock

from tests.test_serveur_mandataire_hote import HoteHttps
from tests.test_serveur_service_poste import Base, S, ss


class Poste(Base):
    def setUp(self):
        super().setUp()
        self.ssh.hote = HoteHttps()
        self.assertEqual(self.deployer()[0], 0)

    def main(self, *argv, env=None):
        sortie, erreur = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", sortie), mock.patch("sys.stderr", erreur):
            code = ss.main(list(argv) + ["--dossier", str(self.projet)], environ=dict(env or {}), **self.k())
        return code, sortie.getvalue(), erreur.getvalue()

    def test_nom_gratuit_deduit_de_l_adresse_ipv4(self):
        self.assertEqual(ss.domaine_sslip("203.0.113.10"), "203-0-113-10.sslip.io")
        for h in ("serveur.exemple.test", "999.1.1.1", "::1", ""):
            with self.assertRaises(ValueError):
                ss.domaine_sslip(h)

    def test_domaine_donne_mis_en_https_et_note_au_cache(self):
        code, rep = ss.https(self.projet, "mandataire", domaine="stats.exemple.test", **self.k())
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["adresse"], "https://stats.exemple.test")
        cache = json.loads((self.dossier / "services.json").read_text("utf-8"))
        self.assertEqual(cache["fm-stats"]["adresse_https"], "https://stats.exemple.test")

    def test_sans_domaine_et_sans_ipv4_le_poste_refuse_sans_toucher_au_serveur(self):
        n = len(self.ssh.commandes)
        code, rep = ss.https(self.projet, "mandataire", **self.k())          # hôte de test : un nom, pas une IPv4
        self.assertEqual(code, 2, rep)
        self.assertEqual(len(self.ssh.commandes), n)

    def test_domaine_invalide_refuse_avant_tout_appel(self):
        n = len(self.ssh.commandes)
        code, rep = ss.https(self.projet, "mandataire", domaine="203.0.113.10", **self.k())
        self.assertEqual(code, 2, rep)
        self.assertEqual(len(self.ssh.commandes), n)

    def test_retrait_du_relais(self):
        ss.https(self.projet, "mandataire", domaine="stats.exemple.test", **self.k())
        code, rep = ss.https(self.projet, "mandataire-supprimer", **self.k())
        self.assertEqual(code, 0, rep)
        cache = json.loads((self.dossier / "services.json").read_text("utf-8"))
        self.assertIsNone(cache["fm-stats"]["adresse_https"])
        self.assertNotIn(S.MANDATAIRE_NOM, self.ssh.hote.conteneurs)

    def test_la_commande_est_au_directeur_seul(self):
        for commande in ("mandataire", "mandataire-supprimer"):
            code, _o, e = self.main(commande, env={"MYIAFACTORY_AGENT": "dev-1"})
            self.assertEqual(code, 2)
            self.assertIn("Directeur", e)

    def test_la_commande_lancer_service_mandataire(self):
        code, sortie, erreur = self.main("mandataire", "--domaine", "stats.exemple.test")
        self.assertEqual(code, 0, erreur)
        self.assertEqual(json.loads(sortie)["adresse"], "https://stats.exemple.test")


if __name__ == "__main__":
    unittest.main()
