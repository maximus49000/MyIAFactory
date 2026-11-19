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
        chemin = self.dossier / plateforme_bureau.FICHIER_MDP
        chemin.write_text("abcde\n", encoding="utf-8")
        ssh = SshBureau()
        etat = self.installer(ssh, bureau=True)
        mdp = chemin.read_text(encoding="utf-8").splitlines()[0]
        self.assertGreaterEqual(len(mdp), 24)
        self.assertEqual(ssh.recus[0][1], mdp + "\n")
        e = self.etape8(etat)
        self.assertIn("Mot de passe trop court dans bureau-distant.txt : remplacé par un mot de passe généré.", e["detail"])
        self.assertNotIn(mdp, json.dumps(etat))

    def test_fichier_illisible_donne_bloque_sans_ecraser(self):
        chemin = self.dossier / plateforme_bureau.FICHIER_MDP
        chemin.write_text("x" * 30 + "\n", encoding="utf-8")
        ssh = SshBureau()
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("refusé")):
            r = plateforme_bureau.etape_bureau_distant(plateforme._Contexte(self.dossier, False, None, ssh, None), lambda *a, **k: self.fail("envoi"))
        self.assertEqual(r["statut"], "bloque")
        self.assertEqual(chemin.read_text(encoding="utf-8"), "x" * 30 + "\n")

    def test_bom_crlf_et_plusieurs_lignes_seule_la_premiere_sert(self):
        chemin = self.dossier / plateforme_bureau.FICHIER_MDP
        chemin.write_bytes(b"\xef\xbb\xbfabcdefghijklmnop\r\nsecondeligne\r\n")
        self.assertEqual(plateforme_bureau.mot_de_passe(self.dossier), "abcdefghijklmnop")
        chemin.write_bytes(b"\xef\xbb\xbfabcdefghijkl\r\n")      # 12 caractères + BOM : trop court
        self.assertGreaterEqual(len(plateforme_bureau.mot_de_passe(self.dossier)), 24)

    def test_echec_d_ecriture_laisse_le_fichier_intact_et_sans_temporaire(self):
        chemin = self.dossier / plateforme_bureau.FICHIER_MDP
        chemin.write_text("abc\n", encoding="utf-8")
        with mock.patch.object(plateforme_bureau.os, "fsync", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                plateforme_bureau.mot_de_passe(self.dossier)
        self.assertEqual(chemin.read_text(encoding="utf-8"), "abc\n")
        self.assertEqual([p.name for p in self.dossier.glob("*.tmp")], [])

    def test_ecriture_reussie_sans_temporaire_et_permission_0600(self):
        plateforme_bureau.mot_de_passe(self.dossier)
        self.assertEqual([p.name for p in self.dossier.glob("*.tmp")] + [p.name for p in self.dossier.glob(".*.tmp")], [])
        if sys.platform != "win32":
            self.assertEqual((self.dossier / plateforme_bureau.FICHIER_MDP).stat().st_mode & 0o777, 0o600)

    def test_licence_bloquee_ou_a_faire_ne_bloque_pas_l_etape_8(self):
        for licence in ("bloque", "a_faire"):
            with self.subTest(licence=licence):
                (self.dossier / "unity.ulf").write_text("<License>" + "A" * 40 + "</License>\n", encoding="utf-8")
                def rep(c, s):
                    return _json("fait")
                class Ssh(SshBureau):
                    def executer(s, hote, commande, cle, stdin=None, delai=60):
                        if "--etape licence" in commande:
                            return 0, json.dumps({"etape": "licence", "statut": licence, "detail": "non"}) + "\n", ""
                        return super().executer(hote, commande, cle, stdin, delai)
                ssh = Ssh()
                (self.dossier / "plateforme.json").unlink(missing_ok=True)
                etat = self.installer(ssh, bureau=True)
                self.assertEqual(self.statuts(etat)["licence"], licence)
                self.assertEqual(self.etape8(etat)["statut"], "fait")
                self.assertTrue(etat["pret"])
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
        self.assertTrue(ssh.recus)
        self.rien_ne_contient_le_mot_de_passe(etat)

    def test_reponse_illisible_qui_repete_le_mot_de_passe_est_masquee(self):
        ssh = SshBureau(lambda c, s: (1, "", f"boum {s.strip()}"))
        etat = self.installer(ssh, bureau=True)
        self.assertTrue(ssh.recus)                      # la réponse factice a bien été reçue
        e = self.etape8(etat)
        self.assertEqual(e["statut"], "bloque")
        self.assertIn("boum ***", e["detail"])
        self.rien_ne_contient_le_mot_de_passe(etat)

    def rien_ne_contient_le_mot_de_passe(self, etat):
        mdp = plateforme_bureau.mot_de_passe(self.dossier)
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            plateforme.main(["etat", "--dossier", str(self.dossier)])
        for texte in (json.dumps(etat), json.dumps(etat, ensure_ascii=False), (self.dossier / "plateforme.json").read_text(encoding="utf-8"),
                      sortie.getvalue()):
            self.assertNotIn(mdp, texte)
            self.assertNotIn(json.dumps(mdp)[1:-1], texte)

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
