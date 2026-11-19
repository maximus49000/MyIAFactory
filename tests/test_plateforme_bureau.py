"""Étape facultative 8 de la plateforme (session graphique) et mot de passe de session."""
import io
import json
import subprocess
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

    def installer(self, ssh, bureau=False, client=None):
        return plateforme.installer(self.dossier, True, client=client or ClientFactice(), ssh=ssh, dormir=lambda s: None,
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
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("refusé")):
            r = plateforme_bureau.etape_bureau_distant(plateforme._Contexte(self.dossier, False, None, ssh, None), lambda *a, **k: self.fail("envoi"))
        self.assertEqual(r["statut"], "bloque")
        self.assertEqual(chemin.read_text(encoding="utf-8"), "x" * 30 + "\n")

    def test_fichier_non_utf8_bloque_sans_ecraser_ni_envoyer(self):
        chemin = self.dossier / plateforme_bureau.FICHIER_MDP
        for nom, octets in (("utf16le", b"\xff\xfe" + "motdepasse-tres-long-123".encode("utf-16-le")),
                            ("utf16be", b"\xfe\xff" + "motdepasse-tres-long-123".encode("utf-16-be")),
                            ("invalide", b"abcdefghijklmnopqrst\xe9\xff\n")):
            with self.subTest(nom):
                chemin.write_bytes(octets)
                ssh = SshBureau()
                etat = self.installer(ssh, bureau=True)
                e = self.etape8(etat)
                self.assertEqual(e["statut"], "bloque")
                self.assertIn("UTF-8", e["detail"])
                self.assertIn("UTF-8", e["geste"])
                self.assertEqual(chemin.read_bytes(), octets)
                self.assertEqual(ssh.recus, [])
                self.assertNotIn("motdepasse", json.dumps(etat))
                (self.dossier / "plateforme.json").unlink(missing_ok=True)

    def test_fichier_absent_genere_et_temporaire_perime_supprime(self):
        vieux = self.dossier / f".{plateforme_bureau.FICHIER_MDP}.99999.tmp"
        vieux.write_text("ancien-secret", encoding="utf-8")
        autre = self.dossier / "autre.tmp"
        autre.write_text("x", encoding="utf-8")
        mdp = plateforme_bureau.mot_de_passe(self.dossier)
        self.assertGreaterEqual(len(mdp), 24)
        self.assertFalse(vieux.exists())
        self.assertTrue(autre.exists())

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

    def test_rejouer_avec_drapeau_relance_l_etape_8_deja_faite_et_renvoie_le_mot_de_passe_modifie(self):
        ssh, client = SshBureau(), ClientFactice()
        self.installer(ssh, bureau=True, client=client)
        chemin = self.dossier / plateforme_bureau.FICHIER_MDP
        chemin.write_text("Mon-Propre-Mot-De-Passe-77\n", encoding="utf-8")
        ssh2 = SshBureau()
        etat = self.installer(ssh2, bureau=True, client=client)
        self.assertEqual(ssh2.etapes_lancees(), ["bureau_distant"])      # ni étapes 1 à 6, ni réinstallation
        self.assertEqual(ssh2.recus[0][1], "Mon-Propre-Mot-De-Passe-77\n")
        self.assertEqual(self.etape8(etat)["statut"], "fait")
        self.assertEqual(len([c for c, _ in ssh2.commandes if "reinstall" in c]), 0)

    def test_rejouer_sans_drapeau_ne_relance_pas_l_etape_8_deja_faite(self):
        client = ClientFactice()
        self.installer(SshBureau(), bureau=True, client=client)
        ssh2 = SshBureau()
        etat = self.installer(ssh2, client=client)
        self.assertEqual(ssh2.recus, [])
        self.assertEqual(ssh2.etapes_lancees(), [])
        self.assertEqual(self.etape8(etat)["statut"], "fait")

    def test_sans_drapeau_et_etape_precedente_bloquee_le_detail_reste_non_demandee(self):
        class ImagesBloquees(SshFactice):
            def executer(self, hote, commande, cle, stdin=None, delai=60):
                if "--etape images" in commande:
                    self.commandes.append((commande, stdin))
                    return 0, json.dumps({"etape": "images", "statut": "bloque", "detail": "non"}) + "\n", ""
                return super().executer(hote, commande, cle, stdin, delai)
        for bureau, attendu in ((False, plateforme.NON_DEMANDEE), (True, "En attente de l'étape précédente.")):
            with self.subTest(bureau=bureau):
                etat = self.installer(ImagesBloquees(), bureau=bureau)
                self.assertEqual(self.etape8(etat)["detail"], attendu)

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


class ProcFactice:
    def __init__(self, args):
        self.args, self.termine, self.tue, self.stderr = args, False, False, None

    def poll(self):
        return None

    def terminate(self):
        self.termine = True

    def kill(self):
        self.tue = True

    def wait(self, timeout=None):
        return 0


class ProcVivant:
    def __init__(self, sorties):
        self.sorties = list(sorties)      # valeurs successives de poll()

    def poll(self):
        return self.sorties.pop(0) if len(self.sorties) > 1 else self.sorties[0]


class TestAttendrePort(unittest.TestCase):
    def attendre(self, proc, connecter, delai=15):
        t = [0.0]

        def dormir(s):
            t[0] += s
        return plateforme_bureau._attendre_port(1234, proc, delai, connecter=connecter, dormir=dormir,
                                                horloge=lambda: t[0]), t[0]

    def test_port_ouvert_et_ssh_vivant(self):
        ok, _ = self.attendre(ProcVivant([None]), lambda *a, **k: mock.MagicMock())
        self.assertTrue(ok)

    def test_ssh_sorti_aussitot(self):
        def connecter(*a, **k):
            self.fail("pas de sonde")
        ok, t = self.attendre(ProcVivant([1]), connecter)
        self.assertFalse(ok)
        self.assertLess(t, 1)

    def test_connexion_etrangere_ssh_sorti_apres(self):
        ok, _ = self.attendre(ProcVivant([None, 255]), lambda *a, **k: mock.MagicMock())
        self.assertFalse(ok)

    def test_delai_depasse(self):
        def refuse(*a, **k):
            raise OSError
        ok, t = self.attendre(ProcVivant([None]), refuse, delai=3)
        self.assertFalse(ok)
        self.assertGreaterEqual(t, 3)


class TestOuvrir(Base):
    def setUp(self):
        super().setUp()
        self.procs = []
        self.rdp = []
        self.windows = mock.patch.object(plateforme_bureau, "_windows", lambda: True)
        self.windows.start()
        self.addCleanup(self.windows.stop)

    def cache(self, statut="fait", ip="203.0.113.7"):
        etat = plateforme.calculer_etat({"bureau_distant": {"statut": statut}})
        (self.dossier / "plateforme.json").write_text(json.dumps({"ip": ip, "etat": etat}), encoding="utf-8")

    def popen(self, args, **kw):
        p = ProcFactice(args)
        self.procs.append(p)
        return p

    def rdp_ok(self, args, **kw):
        self.rdp.append(args)
        return mock.Mock(returncode=0)

    def ouvrir(self, **kw):
        options = dict(popen=self.popen, lancer_rdp=self.rdp_ok, port_libre=lambda: 33890,
                       attendre_port=lambda port, proc, delai=25: True)
        options.update(kw)
        sortie = io.StringIO()
        with redirect_stdout(sortie), mock.patch("sys.stderr", sortie):
            code = plateforme_bureau.ouvrir(self.dossier, **options)
        return code, sortie.getvalue()

    def test_ouvrir_refuse_si_l_etape_8_n_est_pas_faite(self):
        for statut in ("a_faire", "bloque"):
            self.cache(statut)
            code, sortie = self.ouvrir()
            self.assertEqual(code, 1)
            self.assertIn("installer --bureau-distant", sortie)
        self.assertEqual(self.procs, [])

    def test_ouvrir_refuse_sans_cache(self):
        code, _ = self.ouvrir()
        self.assertEqual(code, 1)
        self.assertEqual(self.procs, [])

    def test_ouvrir_lance_le_tunnel_en_loopback_puis_mstsc(self):
        self.cache()
        code, _ = self.ouvrir(port_libre=lambda: 41234)
        self.assertEqual(code, 0)
        args = self.procs[0].args
        self.assertEqual(args[0], "ssh")
        self.assertIn("-N", args)
        self.assertEqual(args[args.index("-L") + 1], "127.0.0.1:41234:127.0.0.1:3389")
        self.assertIn("-i", args)
        self.assertEqual(args[args.index("-i") + 1], str(self.dossier / "id_ed25519_myiafactory"))
        self.assertIn("StrictHostKeyChecking=accept-new", args)
        self.assertFalse([a for a in args if a.endswith("=no") and "StrictHostKeyChecking" in a])
        self.assertEqual(args[-2:], ["--", "ubuntu@203.0.113.7"])
        fichier = self.dossier / "bureau-distant.rdp"
        texte = fichier.read_text(encoding="utf-8")
        self.assertIn("full address:s:127.0.0.1:41234", texte)
        self.assertIn("username:s:ubuntu", texte)
        self.assertNotIn("password", texte.lower())
        self.assertEqual(self.rdp, [["mstsc", str(fichier)]])
        self.assertTrue(self.procs[0].termine)

    def test_ouvrir_arrete_le_tunnel_meme_si_mstsc_echoue(self):
        self.cache()

        def casse(args, **kw):
            raise OSError("mstsc a planté")
        code, sortie = self.ouvrir(lancer_rdp=casse)
        self.assertNotEqual(code, 0)
        self.assertTrue(self.procs[0].termine)
        self.assertNotIn("Traceback", sortie)

    def test_ouvrir_arrete_le_tunnel_si_le_port_ne_s_ouvre_pas(self):
        self.cache()
        code, sortie = self.ouvrir(attendre_port=lambda port, proc, delai=15: False)
        self.assertEqual(code, 1)
        self.assertTrue(self.procs[0].termine)
        self.assertEqual(self.rdp, [])
        self.assertNotIn("Traceback", sortie)

    def test_ouvrir_choisit_un_autre_port_si_33890_est_pris(self):
        import socket
        with socket.socket() as occupe:
            occupe.bind(("127.0.0.1", 0))
            pris = occupe.getsockname()[1]
            autre = plateforme_bureau._port_libre(pris)
            self.assertNotEqual(autre, pris)
            self.assertGreater(autre, 0)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            libre = s.getsockname()[1]
        self.assertEqual(plateforme_bureau._port_libre(libre), libre)

    def test_ouvrir_n_affiche_jamais_le_mot_de_passe(self):
        self.cache()
        mdp = plateforme_bureau.mot_de_passe(self.dossier)
        code, sortie = self.ouvrir()
        self.assertEqual(code, 0)
        self.assertNotIn(mdp, sortie)
        self.assertIn(str(self.dossier / plateforme_bureau.FICHIER_MDP), sortie)
        self.assertNotIn(mdp, (self.dossier / "bureau-distant.rdp").read_text(encoding="utf-8"))
        self.assertFalse([a for a in self.procs[0].args if mdp in a])

    def test_ouvrir_hors_windows_dit_que_mstsc_est_absent(self):
        self.cache()
        with mock.patch.object(plateforme_bureau, "_windows", lambda: False):
            code, sortie = self.ouvrir()
        self.assertEqual(code, 2)
        self.assertIn("mstsc", sortie)
        self.assertEqual(self.procs, [])

    def test_popen_sans_tube_et_fichier_d_erreurs_supprime(self):
        self.cache()
        vus = []

        def popen(args, **kw):
            vus.append(kw)
            return self.popen(args, **kw)
        self.assertEqual(self.ouvrir(popen=popen)[0], 0)
        kw = vus[0]
        for nom in ("stdin", "stdout", "stderr"):
            self.assertNotEqual(kw.get(nom), subprocess.PIPE, nom)
            self.assertIsNotNone(kw.get(nom), nom)
        self.assertEqual([p.name for p in self.dossier.glob(".*.err")], [])
        # échec du port : fichier supprimé aussi
        self.ouvrir(attendre_port=lambda port, proc, delai=15: False)
        self.assertEqual([p.name for p in self.dossier.glob(".*.err")], [])

    def test_cle_changee_message_precis_sans_oublier(self):
        self.cache()

        def popen(args, **kw):
            kw["stderr"].write(b"@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@\n")
            kw["stderr"].flush()
            return self.popen(args, **kw)
        code, sortie = self.ouvrir(popen=popen, attendre_port=lambda port, proc, delai=15: False)
        self.assertEqual(code, 1)
        self.assertIn("ssh-keygen -R 203.0.113.7", sortie)
        self.assertNotIn("@@@", sortie)
        self.assertEqual([p.name for p in self.dossier.glob(".*.err")], [])

    def test_ip_invalide_rien_lance(self):
        for ip in ("-oProxyCommand=x", "a b", "u@x", "", None):
            self.cache(ip=ip)
            code, sortie = self.ouvrir()
            self.assertEqual(code, 1, ip)
            self.assertIn("Adresse" if ip else "Installez", sortie)
        self.assertEqual(self.procs, [])

    def test_ctrl_c_arrete_le_tunnel_sans_trace(self):
        self.cache()

        def interrompu(args, **kw):
            raise KeyboardInterrupt
        code, sortie = self.ouvrir(lancer_rdp=interrompu)
        self.assertEqual(code, 1)
        self.assertTrue(self.procs[0].termine)
        self.assertNotIn("Traceback", sortie)

    def test_mstsc_introuvable(self):
        self.cache()

        def absent(args, **kw):
            raise FileNotFoundError("mstsc")
        code, sortie = self.ouvrir(lancer_rdp=absent)
        self.assertEqual(code, 2)
        self.assertIn("mstsc introuvable (Bureau à distance de Windows)", sortie)
        self.assertTrue(self.procs[0].termine)

    def test_filenotfound_de_l_ecriture_du_rdp_ne_dit_pas_mstsc_introuvable(self):
        self.cache()
        with mock.patch.object(plateforme_bureau, "_ecrire_rdp", side_effect=FileNotFoundError("dossier")):
            code, sortie = self.ouvrir()
        self.assertEqual(code, 1)
        self.assertNotIn("mstsc introuvable", sortie)
        self.assertTrue(self.procs[0].termine)

    def test_tunnel_avec_keepalive(self):
        self.cache()
        self.ouvrir()
        args = self.procs[0].args
        self.assertIn("ServerAliveInterval=30", args)
        self.assertIn("ServerAliveCountMax=3", args)

    def test_l_attente_du_port_depasse_le_delai_de_connexion_ssh(self):
        self.cache()
        self.ouvrir()
        delai_connexion = int(next(a for a in self.procs[0].args if a.startswith("ConnectTimeout=")).split("=")[1])
        self.assertGreater(plateforme_bureau.ATTENTE_TUNNEL_S, delai_connexion)
        self.assertEqual(plateforme_bureau._attendre_port.__defaults__[0], plateforme_bureau.ATTENTE_TUNNEL_S)

    def test_main_delegue_bureau_distant(self):
        with mock.patch.object(plateforme_bureau, "ouvrir", return_value=0) as o:
            self.assertEqual(plateforme.main(["bureau-distant", "--dossier", str(self.dossier)]), 0)
        self.assertEqual(o.call_args.args[0], self.dossier)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            plateforme.main([])
        self.assertIn("bureau-distant", err.getvalue())


if __name__ == "__main__":
    unittest.main()
