"""Étape facultative 8 de la plateforme (session graphique) et mot de passe de session."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plateforme  # noqa: E402
import plateforme_bureau  # noqa: E402
from test_plateforme import Base, ClientFactice, SshFactice  # noqa: E402

AMBIGUS = set("0Oo1lI")


class SshBureau(SshFactice):
    def __init__(self, reponse=None):
        super().__init__()
        self.reponse, self.recus = reponse, []

    def executer(self, hote, commande, cle, stdin=None, delai=60):
        if "--etape bureau_distant" in commande:
            self.recus.append((commande, stdin))
            if self.reponse:
                return self.reponse(commande, stdin)
        return super().executer(hote, commande, cle, stdin, delai)


def _json(statut, detail="ok", stderr=""):
    return 0, json.dumps({"etape": "bureau_distant", "statut": statut, "detail": detail}) + "\n", stderr


class TestBureau(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(plateforme_bureau, "_restreindre_windows", lambda chemin: None)
        p.start()
        self.addCleanup(p.stop)

    def etape8(self, etat):
        return [e for e in etat["etapes"] if e["id"] == "bureau_distant"][0]

    def installer(self, ssh, bureau=False):
        return plateforme.installer(self.dossier, True, client=ClientFactice(), ssh=ssh, dormir=lambda s: None,
                                    bureau_distant=bureau)

    def test_mot_de_passe_genere_puis_relu(self):
        a = plateforme_bureau.mot_de_passe(self.dossier)
        b = plateforme_bureau.mot_de_passe(self.dossier)
        self.assertEqual(a, b)
        self.assertGreaterEqual(len(a), 24)
        self.assertFalse(AMBIGUS & set(a))
        self.assertTrue((self.dossier / plateforme_bureau.FICHIER_MDP).is_file())

    def test_mot_de_passe_trop_court_dans_le_fichier_est_regenere_avec_prevenance(self):
        (self.dossier / plateforme_bureau.FICHIER_MDP).write_text("abcde\n", encoding="utf-8")
        mdp = plateforme_bureau.mot_de_passe(self.dossier)
        self.assertGreaterEqual(len(mdp), 24)
        self.assertEqual((self.dossier / plateforme_bureau.FICHIER_MDP).read_text(encoding="utf-8").splitlines()[0], mdp)

    def test_etape_envoie_le_mot_de_passe_par_stdin_seulement(self):
        ssh = SshBureau()
        self.installer(ssh, bureau=True)
        mdp = plateforme_bureau.mot_de_passe(self.dossier)
        self.assertEqual(len(ssh.recus), 1)
        commande, stdin = ssh.recus[0]
        self.assertEqual(stdin, mdp + "\n")
        for cmd, _ in ssh.commandes:
            self.assertNotIn(mdp, cmd)

    def test_mot_de_passe_absent_de_l_etat_du_cache_et_de_la_sortie(self):
        ssh = SshBureau(lambda c, s: _json("fait", f"mdp {s.strip()}", stderr=f"err {s.strip()}"))
        etat = self.installer(ssh, bureau=True)
        mdp = plateforme_bureau.mot_de_passe(self.dossier)
        self.assertNotIn(mdp, json.dumps(etat))
        self.assertNotIn(mdp, (self.dossier / "plateforme.json").read_text(encoding="utf-8"))
        # illisible : le stderr répété est masqué aussi
        ssh = SshBureau(lambda c, s: (1, "", f"boum {s.strip()}"))
        etat = self.installer(ssh, bureau=True)
        self.assertNotIn(mdp, json.dumps(etat))
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            plateforme.main(["etat", "--dossier", str(self.dossier)])
        self.assertNotIn(mdp, sortie.getvalue())

    def test_geste_donne_le_chemin_pas_le_mot_de_passe(self):
        etat = self.installer(SshBureau(), bureau=True)
        e = self.etape8(etat)
        self.assertEqual(e["statut"], "fait")
        self.assertIn(str(self.dossier / plateforme_bureau.FICHIER_MDP), e["geste"])
        self.assertIn("lancer.py plateforme bureau-distant", e["geste"])

    def test_installer_sans_drapeau_ne_lance_pas_l_etape_8(self):
        ssh = SshBureau()
        etat = self.installer(ssh)
        self.assertEqual(ssh.recus, [])
        self.assertNotIn("bureau_distant", ssh.etapes_lancees())
        e = self.etape8(etat)
        self.assertEqual(e["statut"], "a_faire")
        self.assertEqual(e["detail"], "Facultative : non demandée (installer --bureau-distant).")
        self.assertTrue(etat["pret"])
        self.assertFalse((self.dossier / plateforme_bureau.FICHIER_MDP).exists())

    def test_installer_avec_drapeau_lance_l_etape_8_apres_les_images(self):
        ssh = SshBureau()
        etat = self.installer(ssh, bureau=True)
        lancees = ssh.etapes_lancees()
        self.assertLess(lancees.index("images"), lancees.index("bureau_distant"))
        self.assertEqual(lancees[-1], "bureau_distant")
        self.assertEqual(self.etape8(etat)["statut"], "fait")
        self.assertTrue(etat["pret"])

    def test_etape_8_bloquee_ne_change_pas_pret(self):
        ssh = SshBureau(lambda c, s: _json("bloque", "xrdp indisponible"))
        etat = self.installer(ssh, bureau=True)
        self.assertEqual(self.etape8(etat)["statut"], "bloque")
        self.assertTrue(etat["pret"] and etat["pret_sans_unity"])

    def test_calculer_etat_a_huit_etapes_dans_l_ordre(self):
        etat = plateforme.calculer_etat({})
        self.assertEqual([e["id"] for e in etat["etapes"]],
                         ["lecture", "os", "ssh", "durcissement", "docker", "images", "licence", "bureau_distant"])
        self.assertEqual(self.etape8(etat)["detail"], "Facultative : non demandée (installer --bureau-distant).")
        etat = plateforme.calculer_etat({i: {"statut": "fait"} for i in plateforme.ETAPES[:6]})
        self.assertTrue(etat["pret"])

    def test_cli_accepte_le_drapeau_et_l_usage_le_liste(self):
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(plateforme.main([]), 2)
        self.assertIn("--bureau-distant", err.getvalue())
        with mock.patch.object(plateforme, "installer", return_value=plateforme.calculer_etat({})) as inst:
            with redirect_stdout(io.StringIO()):
                plateforme.main(["installer", "--bureau-distant", "--dossier", str(self.dossier)])
        self.assertIs(inst.call_args.kwargs.get("bureau_distant"), True)


if __name__ == "__main__":
    unittest.main()
