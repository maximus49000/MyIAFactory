"""Modèle de serveur générique (`outils/serveur_modele.py`). Dossiers temporaires, aucun vrai ssh-keygen."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import plateforme_ssh  # noqa: E402
import serveur_modele  # noqa: E402

BON = {"nom": "Mon Serveur Été", "hote": "203.0.113.5", "utilisateur": "ubuntu", "cle": "/k/id", "fournisseur": "ovh",
       "reglages_fournisseur": {"serveur": "ns1.ovh.net"}}


class FauxKeygen:
    def __init__(self):
        self.appels = 0

    def __call__(self, args, **kw):
        self.appels += 1
        prive = Path(args[args.index("-f") + 1])
        prive.write_text("PRIVEE", encoding="utf-8")
        Path(str(prive) + ".pub").write_text("ssh-ed25519 AAAA myiafactory\n", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, b"", b"")


class ModeleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def test_valider_refuse_root_et_hote_piege(self):
        for champ, valeur in (("utilisateur", "root"), ("utilisateur", ""), ("hote", "-oProxyCommand=x"),
                              ("hote", "a b"), ("hote", "u@x"), ("hote", ""), ("fournisseur", "aws"), ("cle", ""),
                              ("cle", 5)):
            with self.subTest(champ=champ, valeur=valeur):
                with self.assertRaises(ValueError):
                    serveur_modele.valider({**BON, champ: valeur})
        with self.assertRaises(ValueError):
            serveur_modele.valider({**BON, "reglages_fournisseur": {"secret": "x"}})

    def test_valider_id_deterministe_depuis_le_nom(self):
        s = serveur_modele.valider(BON)
        self.assertEqual(s.id, "mon-serveur-ete")
        self.assertEqual(serveur_modele.valider({**BON, "fournisseur": None}).fournisseur, None)
        with self.assertRaises(Exception):
            s.id = "x"      # dataclass figée

    def test_lire_fichier_abime_donne_liste_vide(self):
        chemin = self.dossier / serveur_modele.FICHIER
        self.assertEqual(serveur_modele.lire(self.dossier), [])
        for contenu in ("{pas du json", "[[1], [2]]", '{"a": 1}', json.dumps([{"nom": "x", "utilisateur": "u", "cle": "k"}])):
            chemin.write_text(contenu, encoding="utf-8")
            self.assertEqual(serveur_modele.lire(self.dossier), [], contenu)
        chemin.write_bytes(b"\xff\xfe\x00")
        self.assertEqual(serveur_modele.lire(self.dossier), [])

    def test_lire_tolere_bom_et_ignore_les_entrees_invalides(self):
        (self.dossier / serveur_modele.FICHIER).write_text(json.dumps([BON, {"nom": "sans hote"}, 3]), encoding="utf-8-sig")
        self.assertEqual([s.hote for s in serveur_modele.lire(self.dossier)], ["203.0.113.5"])

    def test_ecrire_puis_lire_aller_retour_sans_secret(self):
        s = serveur_modele.valider(BON)
        serveur_modele.ecrire([s], self.dossier)
        self.assertEqual(serveur_modele.lire(self.dossier), [s])
        texte = (self.dossier / serveur_modele.FICHIER).read_text(encoding="utf-8")
        for mot in ("secret", "cle_app", "consommateur"):
            self.assertNotIn(mot, texte)
        with self.assertRaises(ValueError):
            serveur_modele.ecrire([{**BON, "reglages_fournisseur": {"cle_app": "z"}}], self.dossier)

    def test_ajouter_refuse_doublon(self):
        serveur_modele.ajouter(BON, self.dossier)
        with self.assertRaises(ValueError):
            serveur_modele.ajouter({**BON, "hote": "198.51.100.1"}, self.dossier)
        self.assertEqual(len(serveur_modele.lire(self.dossier)), 1)
        autre = serveur_modele.ajouter({**BON, "id": "b"}, self.dossier)
        self.assertEqual(autre.id, "b")
        self.assertEqual(len(serveur_modele.lire(self.dossier)), 2)

    def test_ligne_cle_publique_genere_une_seule_fois(self):
        s = serveur_modele.valider({**BON, "cle": str(self.dossier / plateforme_ssh.NOM_CLE)})
        faux = FauxKeygen()
        a = serveur_modele.ligne_cle_publique(self.dossier, s, runner=faux)
        (self.dossier / plateforme_ssh.NOM_CLE).write_text("MA CLE", encoding="utf-8")
        b = serveur_modele.ligne_cle_publique(self.dossier, s, runner=faux)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("ssh-ed25519 "))
        self.assertEqual(faux.appels, 1)
        self.assertEqual((self.dossier / plateforme_ssh.NOM_CLE).read_text(encoding="utf-8"), "MA CLE")

    def test_ecriture_atomique_ne_laisse_pas_de_temporaire(self):
        serveur_modele.ecrire([serveur_modele.valider(BON)], self.dossier)
        serveur_modele.ecrire([], self.dossier)
        self.assertEqual([p.name for p in self.dossier.iterdir()], [serveur_modele.FICHIER])
        (self.dossier / ".serveurs.json.1.tmp").write_text("vieux", encoding="utf-8")
        serveur_modele.ecrire([serveur_modele.valider(BON)], self.dossier)
        self.assertEqual([p.name for p in self.dossier.iterdir()], [serveur_modele.FICHIER])

    # --- I1 : une clé par serveur ---
    def test_cle_au_chemin_exact_du_serveur(self):
        chemin = self.dossier / "cles" / "id_ed25519_autre"
        s = serveur_modele.valider({**BON, "cle": str(chemin)})
        ligne = serveur_modele.ligne_cle_publique(self.dossier, s, runner=FauxKeygen())
        self.assertTrue(chemin.is_file())
        self.assertTrue(ligne.startswith("ssh-ed25519 "))
        self.assertFalse((self.dossier / plateforme_ssh.NOM_CLE).exists())

    def test_deux_serveurs_deux_cles_sans_ecrasement(self):
        a = serveur_modele.valider({**BON, "cle": str(self.dossier / "cle_a")})
        b = serveur_modele.valider({**BON, "id": "b", "cle": str(self.dossier / "cle_b")})
        faux = FauxKeygen()
        (self.dossier / "cle_a").write_text("A-EXISTANTE", encoding="utf-8")
        Path(str(self.dossier / "cle_a") + ".pub").write_text("ssh-ed25519 PUBA\n", encoding="utf-8")
        la = serveur_modele.ligne_cle_publique(self.dossier, a, runner=faux)
        lb = serveur_modele.ligne_cle_publique(self.dossier, b, runner=faux)
        self.assertEqual(la, "ssh-ed25519 PUBA")
        self.assertEqual(faux.appels, 1)
        self.assertNotEqual(la, lb)
        self.assertEqual((self.dossier / "cle_a").read_text(encoding="utf-8"), "A-EXISTANTE")
        self.assertEqual((self.dossier / "cle_b").read_text(encoding="utf-8"), "PRIVEE")

    def test_cle_par_defaut_a_l_ajout(self):
        s = serveur_modele.ajouter({k: v for k, v in BON.items() if k != "cle"}, self.dossier)
        self.assertEqual(Path(s.cle), self.dossier / "id_ed25519_mon-serveur-ete")
        with self.assertRaises(ValueError):
            serveur_modele.valider({k: v for k, v in BON.items() if k != "cle"})

    # --- I2 : aucune perte silencieuse ---
    def test_lire_avec_rejets_signale_les_entrees_refusees(self):
        chemin = self.dossier / serveur_modele.FICHIER
        chemin.write_text(json.dumps([BON, {**BON, "id": "r", "utilisateur": "root"}, {"nom": "sans hote"}]), encoding="utf-8")
        ok, rejets = serveur_modele.lire_avec_rejets(self.dossier)
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(rejets), 2)
        self.assertIn("2", rejets[0])
        chemin.write_text("{abime", encoding="utf-8")
        ok, rejets = serveur_modele.lire_avec_rejets(self.dossier)
        self.assertEqual((ok, len(rejets)), ([], 1))
        chemin.unlink()
        self.assertEqual(serveur_modele.lire_avec_rejets(self.dossier), ([], []))

    def test_ajouter_refuse_de_reecrire_un_fichier_abime_ou_avec_rejets(self):
        chemin = self.dossier / serveur_modele.FICHIER
        for contenu in (b"{abime", json.dumps([BON, {**BON, "id": "r", "utilisateur": "root"}]).encode()):
            chemin.write_bytes(contenu)
            with self.assertRaises(ValueError) as ctx:
                serveur_modele.ajouter({**BON, "id": "nouveau"}, self.dossier)
            self.assertIn("refusée(s) ou est abîmé", str(ctx.exception))
            self.assertEqual(chemin.read_bytes(), contenu)
            self.assertEqual([p.name for p in self.dossier.iterdir()], [serveur_modele.FICHIER])

    def test_ajouter_sur_fichier_sain_fonctionne(self):
        serveur_modele.ajouter(BON, self.dossier)
        serveur_modele.ajouter({**BON, "id": "b"}, self.dossier)
        self.assertEqual(len(serveur_modele.lire(self.dossier)), 2)

    # --- cheap items ---
    def test_id_normalise_et_doublon_insensible_a_la_casse(self):
        self.assertEqual(serveur_modele.valider({**BON, "id": "A B"}).id, "a-b")
        self.assertEqual(serveur_modele.valider({**BON, "id": "../x"}).id, "x")
        with self.assertRaises(ValueError):
            serveur_modele.valider({**BON, "id": "../"})
        serveur_modele.ajouter({**BON, "id": "A"}, self.dossier)
        with self.assertRaises(ValueError):
            serveur_modele.ajouter({**BON, "id": "a"}, self.dossier)

    def test_hote_et_longueurs_refuses(self):
        for champ, valeur in (("hote", "a/b"), ("hote", "a:b"), ("hote", "[::1]"), ("hote", "a,b"), ("hote", "a\x00b"),
                              ("hote", "a\x1bb"), ("hote", "a\nb"), ("hote", "h" * 254), ("utilisateur", "u" * 65),
                              ("utilisateur", "u\x00"), ("id", "i" * 65), ("nom", "n" * 101)):
            with self.subTest(champ=champ, valeur=valeur[:12]):
                with self.assertRaises(ValueError):
                    serveur_modele.valider({**BON, champ: valeur})
        serveur_modele.valider({**BON, "hote": "h" * 253, "utilisateur": "u" * 64, "id": "i" * 64, "nom": "n" * 100})

    def test_hote_et_utilisateur_suivent_la_regle_stricte_de_la_connexion(self):
        for champ, valeur in (("hote", "a$b"), ("hote", "a;b"), ("hote", "a`b"), ("hote", "a'b"), ("hote", "h~x"),
                              ("hote", "a|b"), ("hote", "h\nx"), ("utilisateur", "u$b"), ("utilisateur", "u;x"),
                              ("utilisateur", "u\nx")):
            with self.subTest(champ=champ, valeur=valeur):
                with self.assertRaises(ValueError):
                    serveur_modele.valider({**BON, champ: valeur})
        self.assertEqual(serveur_modele.valider({**BON, "hote": "h\n"}).hote, "h")     # jamais rangé avec un retour à la ligne
        for hote in ("srv.exemple.fr", "203.0.113.5", "a-b.c_d"):
            serveur_modele.valider({**BON, "hote": hote})

    def test_identifiant_migration_reste_reserve(self):
        for ident in ("migration", "Migration", " migration "):
            with self.assertRaises(ValueError):
                serveur_modele.valider({**BON, "id": ident})

    def test_cle_par_defaut_toujours_absolue_meme_avec_un_dossier_relatif(self):
        import os
        ancien = os.getcwd()
        os.chdir(self.dossier)
        self.addCleanup(os.chdir, ancien)
        sans_cle = {k: v for k, v in BON.items() if k != "cle"}
        s = serveur_modele.ajouter(sans_cle, Path("relatif"))
        self.assertTrue(Path(s.cle).is_absolute(), s.cle)
        self.assertEqual(Path(s.cle), (self.dossier / "relatif").resolve() / "id_ed25519_mon-serveur-ete")
        stocke = serveur_modele.lire(Path("relatif"))[0]
        self.assertEqual(stocke.cle, s.cle)
        os.chdir(ancien)                                    # la clé ne dépend plus du dossier courant
        fausse = FauxKeygen()
        serveur_modele.ligne_cle_publique(Path("autre-dossier"), stocke, runner=fausse)
        self.assertTrue(Path(s.cle).exists())
        self.assertFalse((Path("autre-dossier")).exists())

    def test_filtre_secrets_imbrique_et_par_mots(self):
        for cles in ({"password": 1}, {"db_passwd": 1}, {"a": {"b": {"api_key": 1}}}, {"mot_de_passe": 1},
                     {"cle_api": 1}, {"x": [{"Token": 1}]}, {"secret": 1}, {"client-secret": 1}):
            with self.subTest(cles=cles):
                with self.assertRaises(ValueError):
                    serveur_modele.valider({**BON, "reglages_fournisseur": cles})
        serveur_modele.valider({**BON, "reglages_fournisseur": {"passerelle": "x", "bypass": 1, "n": {"tokenizer": 1}}})


if __name__ == "__main__":
    unittest.main()
