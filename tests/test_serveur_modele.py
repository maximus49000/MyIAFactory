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


if __name__ == "__main__":
    unittest.main()
