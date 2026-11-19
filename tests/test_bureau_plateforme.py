"""Essai réel : le bureau expose l'état de la plateforme (cache seulement) et lance l'installation en arrière-plan."""
import json
import threading
import unittest
from unittest import mock

from bureau import plateforme as bplateforme
from tests.test_serveur import AvecServeur

SECRET = "SECRET-OVH-XYZ-123456"


class TestPlateformeBureau(AvecServeur):
    def setUp(self):
        super().setUp()
        self.dossier = self.tmp / "secrets"
        self.dossier.mkdir()
        p = mock.patch.object(bplateforme, "DOSSIER", self.dossier)
        p.start()
        self.addCleanup(p.stop)
        self.appels = []
        self.libre = threading.Event()
        self.srv.travail_plateforme = bplateforme.Travail(self.installer_factice)

    def installer_factice(self, dossier, accord_reinstallation=False):
        self.appels.append((dossier, accord_reinstallation))
        self.libre.wait(5)

    def ecrire_cache(self, rapports):
        (self.dossier / "plateforme.json").write_text(json.dumps({"rapports": rapports}), encoding="utf-8")

    def poster(self, corps, entetes=None):
        return self.req("POST", "/api/plateforme/installer", json.dumps(corps), self.ENT if entetes is None else entetes)

    def test_get_sans_cache_donne_etat_a_faire_sans_erreur(self):
        e = self.json("/api/plateforme")
        self.assertEqual(len(e["etapes"]), 8)
        self.assertEqual({x["statut"] for x in e["etapes"]}, {"a_faire"})
        self.assertIs(e["pret"], False)
        self.assertIs(e["pret_sans_unity"], False)
        self.assertEqual(e["derniere_lecture"], "")
        self.assertNotIn("erreur", e)

    def test_get_ne_bloque_pas_si_ovh_injoignable(self):
        # aucun ovh.json, aucun client : la lecture ne touche ni OVH ni ssh
        bplateforme._modules()
        import ovh_api
        with mock.patch("subprocess.run", side_effect=AssertionError("ssh")), \
                mock.patch.object(ovh_api.ClientOvh, "appeler", side_effect=AssertionError("ovh")):
            r, _ = self.req("GET", "/api/plateforme")
        self.assertEqual(r.status, 200)

    def test_get_relit_le_cache(self):
        self.ecrire_cache({e: {"statut": "fait"} for e in ("lecture", "os", "ssh", "durcissement", "docker", "images")})
        e = self.json("/api/plateforme")
        self.assertIs(e["pret"], True)
        self.assertNotEqual(e["derniere_lecture"], "")

    def test_post_refuse_409_pendant_une_installation_des_serveurs(self):
        (self.dossier / "serveurs-installation.lock").write_text("", encoding="utf-8")    # verrou récent d'une installation générique
        r, data = self.poster({"accord_reinstallation": False})
        self.assertEqual(r.status, 409)
        self.assertIn("serveurs", json.loads(data)["erreur"].lower())
        self.srv.travail_plateforme.attendre()
        self.assertEqual(self.appels, [])

    def test_post_sans_en_tete_bureau_refuse(self):
        r, _ = self.poster({"accord_reinstallation": True}, {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.appels, [])

    def test_post_deuxieme_lancement_renvoie_409(self):
        r, data = self.poster({})
        self.assertEqual((r.status, json.loads(data)), (202, {"demarre": True}))
        r2, _ = self.poster({})
        self.assertEqual(r2.status, 409)
        self.libre.set()
        self.srv.travail_plateforme.attendre()
        r3, _ = self.poster({})
        self.assertEqual(r3.status, 202)
        self.srv.travail_plateforme.attendre()

    def test_post_sans_accord_ne_reinstalle_pas(self):
        self.libre.set()
        for corps in ({}, {"accord_reinstallation": "true"}, {"accord_reinstallation": 1}, {"accord_reinstallation": False}):
            with self.subTest(corps=corps):
                self.poster(corps)
                self.srv.travail_plateforme.attendre()
        self.assertEqual([a[1] for a in self.appels], [False] * 4)
        self.poster({"accord_reinstallation": True})
        self.srv.travail_plateforme.attendre()
        self.assertIs(self.appels[-1][1], True)

    def test_exception_du_fil_ne_tue_pas_le_serveur(self):
        def casse(dossier, accord_reinstallation=False):
            raise RuntimeError(SECRET)
        self.srv.travail_plateforme = bplateforme.Travail(casse)
        self.poster({})
        self.srv.travail_plateforme.attendre()
        self.assertNotIn(SECRET, self.srv.travail_plateforme.erreur)
        self.assertEqual(self.req("GET", "/api/plateforme")[0].status, 200)

    def test_serveur_disponible_vrai_seulement_si_pret(self):
        self.assertIs(self.json("/api/etat")["deport"]["serveur_disponible"], False)
        self.ecrire_cache({e: {"statut": "fait"} for e in ("lecture", "os", "ssh", "durcissement", "docker")})
        self.srv.projets["projet"]._cache_etat = (0.0, None)
        self.assertIs(self.json("/api/etat")["deport"]["serveur_disponible"], False)
        self.ecrire_cache({e: {"statut": "fait"} for e in ("lecture", "os", "ssh", "durcissement", "docker", "images")})
        self.srv.projets["projet"]._cache_etat = (0.0, None)
        self.assertIs(self.json("/api/etat")["deport"]["serveur_disponible"], True)

    def test_reponses_sans_secret(self):
        (self.dossier / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-XYZ-123456", "secret": SECRET,
                                                            "consommateur": "CONSO-XYZ-123456", "serveur": "ns1"}), encoding="utf-8")
        self.ecrire_cache({"lecture": {"statut": "bloque", "detail": f"échec avec {SECRET}"}})
        r, data = self.req("GET", "/api/plateforme")
        self.assertNotIn(SECRET.encode(), data)
        self.assertIn("***", data.decode("utf-8"))
        _, data = self.poster({})
        self.assertNotIn(SECRET.encode(), data)
        self.libre.set()
        self.srv.travail_plateforme.attendre()

    def en_cours_au_cache(self):
        self.ecrire_cache({"lecture": {"statut": "fait"}, "os": {"statut": "fait"}, "ssh": {"statut": "fait"},
                           "durcissement": {"statut": "fait"}, "docker": {"statut": "en_cours", "detail": "Docker en cours"}})

    def statut(self, etat, id_):
        return [e for e in etat["etapes"] if e["id"] == id_][0]

    def test_etape_en_cours_sans_fil_ni_verrou_est_interrompue_a_reprendre(self):
        self.en_cours_au_cache()
        e = self.json("/api/plateforme")
        docker = self.statut(e, "docker")
        self.assertEqual(docker["statut"], "a_faire")
        self.assertIn("Interrompu : à reprendre", docker["detail"])
        self.assertIs(e["en_cours"], False)

    def test_etape_en_cours_avec_fil_vivant_reste_en_cours(self):
        self.en_cours_au_cache()
        self.poster({})
        e = self.json("/api/plateforme")
        self.assertEqual(self.statut(e, "docker")["statut"], "en_cours")
        self.assertIs(e["en_cours"], True)
        self.libre.set()
        self.srv.travail_plateforme.attendre()

    def test_etape_en_cours_avec_verrou_d_un_processus_vivant_reste_en_cours(self):
        self.en_cours_au_cache()
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        vivant = bplateforme.lire(self.dossier, vivant=lambda p: True)
        self.assertEqual(self.statut(vivant, "docker")["statut"], "en_cours")
        mort = bplateforme.lire(self.dossier, vivant=lambda p: False)
        self.assertEqual(self.statut(mort, "docker")["statut"], "a_faire")

    def test_attente_os_interrompue_reste_reprenable(self):
        self.ecrire_cache({"lecture": {"statut": "fait"}, "os": {"statut": "en_cours", "detail": "tâche 7"}})
        os_ = self.statut(self.json("/api/plateforme"), "os")
        self.assertEqual(os_["statut"], "a_faire")
        self.assertIn("reprendre", os_["detail"])

    def test_erreur_du_fil_exposee_et_masquee(self):
        def casse(dossier, accord_reinstallation=False):
            raise RuntimeError(SECRET)
        self.srv.travail_plateforme = bplateforme.Travail(casse)
        self.poster({})
        self.srv.travail_plateforme.attendre()
        e = self.json("/api/plateforme")
        self.assertIn("Installation interrompue", e["erreur"])
        self.assertNotIn(SECRET, json.dumps(e))
        self.srv.travail_plateforme.attendre()
        self.srv.travail_plateforme._installer = lambda dossier, accord_reinstallation=False: None
        self.poster({})
        self.srv.travail_plateforme.attendre()
        self.assertNotIn("erreur", self.json("/api/plateforme"))

    def test_erreur_precedente_effacee_des_le_debut_de_la_nouvelle_execution(self):
        def casse(dossier, accord_reinstallation=False):
            raise RuntimeError("panne")
        travail = bplateforme.Travail(casse)
        self.srv.travail_plateforme = travail
        self.poster({})
        travail.attendre()
        self.assertIn("Installation interrompue", travail.erreur)
        self.assertIn("erreur", self.json("/api/plateforme"))
        travail._installer = self.installer_factice      # la nouvelle exécution reste en cours
        self.poster({})
        self.assertIsNone(travail.erreur)
        e = self.json("/api/plateforme")
        self.assertIs(e["en_cours"], True)
        self.assertNotIn("erreur", e)
        self.libre.set()
        travail.attendre()


class TestIsolationEtCacheAbime(unittest.TestCase):
    def test_dossier_par_defaut_des_essais_n_est_pas_le_vrai_dossier_personnel(self):
        import os
        from pathlib import Path
        self.assertEqual(bplateforme.dossier(), Path(os.environ["MYIAFACTORY_PLATEFORME"]))
        self.assertNotEqual(bplateforme.dossier(), Path("~/MyIAFactory").expanduser())
        self.assertIs(bplateforme.pret(), False)   # dossier vide : jamais prête

    def test_cache_abime_donne_l_etat_a_faire(self):
        import tempfile
        from pathlib import Path
        formes = ['{"rapports": ["x"]}', '{"rapports": {"lecture": "x"}}', '{"rapports": {"lecture": null, "os": 3}}',
                  '{"rapports": 5}', '{"rapports": {"lecture": {"statut": 3, "detail": null}}}',
                  '{"rapports": {}, "demande": [1], "tache": "x"}', '[]', '"texte"', '', '{pas du json', 'null']
        for texte in formes:
            with self.subTest(texte=texte), tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
                (Path(t) / "plateforme.json").write_text(texte, encoding="utf-8")
                e = bplateforme.lire(t)
                self.assertEqual(len(e["etapes"]), 8)
                self.assertIs(e["pret"], False)
                self.assertIs(bplateforme.pret(t), False)


if __name__ == "__main__":
    unittest.main()
