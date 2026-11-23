"""La publication des livrables en releases GitHub privées (`installation.publication`, `lancer publier`). git et gh sont
simulés : rien n'est envoyé."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from installation import publication
from tests.test_recrutement import Base, Executeur

URL = "https://github.com/moi/projet/releases/tag/v7"
GITHUB = {"remote get-url": (0, "https://github.com/moi/projet.git")}
PUBLIE = {"auth status": (0, "ok"), "release view": (1, "release not found"), "release create": (0, URL)}


class Outils(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)

    def apk(self, nom="Jeu_7.apk", octets=10):
        f = self.tmp / nom
        f.write_bytes(b"x" * octets)
        return f

    def test_tag_d_apres_le_numero_du_fichier_sinon_la_date(self):
        self.assertEqual(publication.tag_de("Livrables/FM_Stats_121.apk"), "v121")
        self.assertEqual(publication.tag_de("jeu_007.zip"), "v7")
        self.assertEqual(publication.tag_de("jeu.apk", datetime(2026, 11, 23, 15, 4)), "v20261123-1504")

    def test_seuls_les_fichiers_telechargeables_sont_publiables(self):
        self.assertTrue(publication.publiable("a/b.APK"))
        self.assertTrue(publication.publiable("x.zip"))
        self.assertFalse(publication.publiable("capture.png"))
        self.assertFalse(publication.publiable(None))

    def test_publier_un_fichier_cree_la_release_et_rend_son_lien(self):
        gh = Executeur(PUBLIE)
        r = publication.publier_fichier(self.tmp, self.apk(), "Jeu", Executeur(GITHUB), gh)
        self.assertTrue(r["fait"])
        self.assertEqual((r["tag"], r["url"]), ("v7", URL))
        creer = [a for a in gh.appels if a[:2] == ["release", "create"]]
        self.assertEqual(len(creer), 1)
        self.assertEqual(creer[0][2], "v7")
        self.assertIn("Jeu_7.apk", creer[0][3])

    def test_une_release_qui_existe_deja_n_est_pas_refaite(self):
        gh = Executeur({**PUBLIE, "release view": (0, URL)})
        r = publication.publier_fichier(self.tmp, self.apk(), "Jeu", Executeur(GITHUB), gh)
        self.assertTrue(r["fait"])
        self.assertEqual(r["url"], URL)
        self.assertEqual([a for a in gh.appels if a[:2] == ["release", "create"]], [])

    def test_fichier_introuvable_ou_trop_gros(self):
        gh = Executeur(PUBLIE)
        r = publication.publier_fichier(self.tmp, self.tmp / "absent.apk", "x", Executeur(GITHUB), gh)
        self.assertFalse(r["fait"])
        self.assertIn("introuvable", r["texte"])
        with mock.patch.object(publication, "TAILLE_MAX", 5):
            r = publication.publier_fichier(self.tmp, self.apk(octets=10), "x", Executeur(GITHUB), gh)
        self.assertFalse(r["fait"])
        self.assertIn("2 Go", r["texte"])
        self.assertEqual([a for a in gh.appels if a[:2] == ["release", "create"]], [])

    def test_echec_de_gh_dit_pourquoi(self):
        gh = Executeur({**PUBLIE, "release create": (1, "HTTP 422")})
        r = publication.publier_fichier(self.tmp, self.apk(), "Jeu", Executeur(GITHUB), gh)
        self.assertFalse(r["fait"])
        self.assertIn("HTTP 422", r["texte"])

    def livrables(self):
        return [{"chemin": "Jeu_7.apk", "titre": "Jeu"}, {"chemin": "capture.png", "titre": "Capture"}]

    def test_livrables_projet_pas_sur_github(self):
        r = publication.publier_livrables(self.tmp, self.livrables(), lambda c: self.tmp / c, Executeur(),
                                          Executeur(PUBLIE))
        self.assertFalse(r["fait"])
        self.assertIn("Créer le dépôt Git", r["texte"])

    def test_livrables_gh_non_connecte(self):
        r = publication.publier_livrables(self.tmp, self.livrables(), lambda c: self.tmp / c, Executeur(GITHUB),
                                          Executeur({"auth status": (1, "not logged in")}))
        self.assertFalse(r["fait"])
        self.assertIn("gh auth login", r["texte"])

    def test_livrables_seul_l_apk_est_publie(self):
        self.apk()
        gh = Executeur(PUBLIE)
        r = publication.publier_livrables(self.tmp, self.livrables(), lambda c: self.tmp / c, Executeur(GITHUB), gh)
        self.assertTrue(r["fait"])
        self.assertEqual([x["tag"] for x in r["releases"]], ["v7"])

    def test_rien_de_telechargeable_rien_a_faire(self):
        gh = Executeur(PUBLIE)
        r = publication.publier_livrables(self.tmp, [{"chemin": "a.png", "titre": "A"}], lambda c: self.tmp / c,
                                          Executeur(GITHUB), gh)
        self.assertTrue(r["fait"])
        self.assertEqual(gh.appels, [])


class CommandePublier(Base):
    """`lancer publier` : la fin d'une fonctionnalité garde le résultat et le lien de la release."""

    def terminer(self, livrables):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Un jeu"})
        self.ok("fonctionnalite", entree={"id": "f1", "fin": {"livrables": livrables}})

    def publier(self, git, gh, **entree):
        with mock.patch("orchestrateur.outil.GIT", git), mock.patch("orchestrateur.outil.GH", gh):
            return self.outil("publier", entree=entree)

    def fin(self):
        return next(f for f in self.releve()["fonctionnalites"] if f["id"] == "f1")["fin"]

    def test_publie_et_garde_le_lien_dans_le_livrable(self):
        (self.dossier / "Jeu_7.apk").write_bytes(b"x" * 10)
        self.terminer([{"chemin": "Jeu_7.apk", "titre": "Jeu"}])
        gh = Executeur(PUBLIE)
        code, r = self.publier(Executeur(GITHUB), gh)
        self.assertEqual(code, 0, r)
        self.assertTrue(r["fonctionnalites"][0]["fait"])
        fin = self.fin()
        self.assertTrue(fin["publication"]["fait"])
        self.assertEqual(fin["livrables"][0]["lien"], URL)

    def test_deja_publie_n_est_pas_refait_sans_relancer(self):
        (self.dossier / "Jeu_7.apk").write_bytes(b"x" * 10)
        self.terminer([{"chemin": "Jeu_7.apk", "titre": "Jeu"}])
        self.publier(Executeur(GITHUB), Executeur(PUBLIE))
        gh = Executeur(PUBLIE)
        code, r = self.publier(Executeur(GITHUB), gh)
        self.assertEqual((code, r["fonctionnalites"]), (0, []))
        self.assertEqual(gh.appels, [])

    def test_un_echec_est_garde_puis_relance_a_la_demande(self):
        (self.dossier / "Jeu_7.apk").write_bytes(b"x" * 10)
        self.terminer([{"chemin": "Jeu_7.apk", "titre": "Jeu"}])
        code, r = self.publier(Executeur(), Executeur(PUBLIE))          # pas encore sur GitHub
        self.assertEqual(code, 0, r)
        self.assertFalse(self.fin()["publication"]["fait"])
        code, r = self.publier(Executeur(), Executeur(PUBLIE))          # pas relancé tout seul
        self.assertEqual(r["fonctionnalites"], [])
        code, r = self.publier(Executeur(GITHUB), Executeur(PUBLIE), relancer=True)
        self.assertTrue(r["fonctionnalites"][0]["fait"])
        self.assertEqual(self.fin()["livrables"][0]["lien"], URL)

    def test_une_fin_sans_livrable_telechargeable_ne_publie_rien(self):
        self.terminer([{"chemin": "capture.png", "titre": "Capture"}])
        gh = Executeur(PUBLIE)
        code, r = self.publier(Executeur(GITHUB), gh)
        self.assertEqual((code, r["fonctionnalites"]), (0, []))
        self.assertEqual(gh.appels, [])


if __name__ == "__main__":
    unittest.main()


class Reglage(unittest.TestCase):
    """Le réglage `livraison_github` : décoché par défaut, écrit par le bureau, booléen seulement."""

    def setUp(self):
        from bureau import reglages
        self.reglages = reglages
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.fichier = self.tmp / "reglages.json"
        self.fichier.write_text('{"orchestrateur": "factory.json"}', encoding="utf-8")

    def test_decoche_par_defaut_puis_ecrit(self):
        self.assertIs(self.reglages.charger(self.fichier)["livraison_github"], False)
        self.reglages.fixer_livraison_github(self.fichier, True)
        self.assertIs(self.reglages.charger(self.fichier)["livraison_github"], True)

    def test_un_booleen_seulement(self):
        with self.assertRaises(ValueError):
            self.reglages.fixer_livraison_github(self.fichier, "oui")


class Declencheur(unittest.TestCase):
    """Le moteur ne publie que si le réglage est coché."""

    def test_sans_reglage_rien(self):
        from moteur import regles
        projet = mock.Mock(fichier_reglages=None, livraison_github=False)
        with mock.patch.object(regles, "lancer") as lancer:
            regles._publier_les_livrables(projet)
        lancer.assert_not_called()

    def test_avec_reglage_lance_publier_sans_jamais_bloquer(self):
        from moteur import regles
        projet = mock.Mock(fichier_reglages=None, livraison_github=True)
        with mock.patch.object(regles, "lancer", side_effect=regles.Refus("publier : boom")) as lancer:
            regles._publier_les_livrables(projet)
        lancer.assert_called_once_with(projet, "publier", {})

    def test_pose_au_global_ou_au_type_le_reglage_n_agit_pas(self):
        """`livraison_github` est propre au projet : écrit à la main au global ou au type, rien n'est publié ; seule
        la valeur du projet compte."""
        from moteur import regles
        from tests.test_reglages_effectif import ANDROID, bureau_avec
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, ignore_errors=True)
        (tmp / "factory.json").write_text(json.dumps({"genre": ANDROID}), encoding="utf-8")
        regl = tmp / "reglages.json"
        b = bureau_avec(regl, reglages={"livraison_github": True},
                        types={ANDROID: {"reglages": {"livraison_github": True}}})
        projet = mock.Mock(fichier_reglages=regl, fichier_bureau=b, livraison_github=False)
        with mock.patch.object(regles, "lancer") as lancer:
            regles._publier_les_livrables(projet)
        lancer.assert_not_called()
        regl.write_text(json.dumps({"livraison_github": True}), encoding="utf-8")
        with mock.patch.object(regles, "lancer") as lancer:
            regles._publier_les_livrables(projet)
        lancer.assert_called_once_with(projet, "publier", {})
