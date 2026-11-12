"""Le faux terminal (pseudo-console Windows) : une commande qui exige un terminal y tourne sans fenêtre."""
import sys
import time
import unittest
from unittest import mock

from moteur import pseudo_terminal as pt

WINDOWS = pt.disponible()


class Nettoyage(unittest.TestCase):
    def test_retire_couleurs_et_titres(self):
        brut = "\x1b[?25l\x1b[1;32mSession\x1b[0m prête\x1b]0;claude\x07\r\n"
        self.assertEqual(pt.nettoyer(brut), "Session prête\n")

    def test_deplacements_vers_la_droite_deviennent_des_espaces(self):
        self.assertEqual(pt.nettoyer("a\x1b[3Cb"), "a   b")

    def test_lien_hypertexte_garde_le_texte_et_l_adresse(self):
        brut = "\x1b]8;;https://claude.ai/code/session_abc\x1b\\voir\x1b]8;;\x1b\\"
        self.assertEqual(pt.nettoyer(brut), "voir <https://claude.ai/code/session_abc>")

    def test_retour_en_debut_de_ligne_et_positionnement(self):
        self.assertEqual(pt.nettoyer("un\x1b[2;1Hdeux\x1b[K"), "un\ndeux")


class Environnement(unittest.TestCase):
    def test_sans_la_cle(self):
        env = pt.environnement_sans("ANTHROPIC_API_KEY", {"ANTHROPIC_API_KEY": "x", "PATH": "p", "CLAUDE_X": "1"})
        self.assertEqual(env, {"PATH": "p", "CLAUDE_X": "1"})

    def test_session_hote_retiree(self):
        env = pt.environnement_sans("ANTHROPIC_API_KEY", {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "s",
                                                          "ANTHROPIC_BASE_URL": "u", "PATH": "p"})
        self.assertEqual(env, {"PATH": "p"})


class Indisponible(unittest.TestCase):
    def test_hors_windows(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(pt.disponible())
            with self.assertRaises(pt.PseudoTerminalIndisponible):
                pt.lancer(["echo", "x"], cwd=".", delai_s=5)


@unittest.skipUnless(WINDOWS, "pseudo-console Windows seulement")
class SurWindows(unittest.TestCase):
    def test_sortie_et_code(self):
        r = pt.lancer(["cmd", "/c", "echo bonjour"], cwd=".", delai_s=20)
        self.assertTrue(r.fini)
        self.assertEqual(r.code, 0)
        self.assertIn("bonjour", r.texte)

    def test_code_de_sortie_non_nul(self):
        r = pt.lancer(["cmd", "/c", "exit 3"], cwd=".", delai_s=20)
        self.assertEqual(r.code, 3)

    def test_la_commande_voit_un_terminal(self):
        r = pt.lancer([sys.executable, "-c", "import sys; print('tty', sys.stdout.isatty())"], cwd=".", delai_s=30)
        self.assertIn("tty True", r.texte)

    def test_entree(self):
        r = pt.lancer([sys.executable, "-c", "print('lu:' + input()[::-1])"], cwd=".", delai_s=30, entree="abc\r")
        self.assertIn("lu:cba", r.texte)

    def test_reponse_a_ce_qui_s_affiche(self):
        code = "print('Votre nom ?', flush=True); print('nom:' + input())"
        dit = []

        def repondre(texte):
            if "Votre nom ?" in texte and not dit:
                dit.append(1)
                return "Lucas\r"
            return None

        r = pt.lancer([sys.executable, "-c", code], cwd=".", delai_s=30, repondre=repondre)
        self.assertTrue(r.fini)
        self.assertIn("nom:Lucas", r.texte)

    def test_delai_arrete_le_processus(self):
        debut = time.monotonic()
        r = pt.lancer([sys.executable, "-c", "import time; print('debut', flush=True); time.sleep(60)"], cwd=".",
                      delai_s=3)
        self.assertFalse(r.fini)
        self.assertIsNone(r.code)
        self.assertLess(time.monotonic() - debut, 20)
        self.assertIn("debut", r.texte)

    def test_arret_des_que_la_sortie_suffit(self):
        debut = time.monotonic()
        r = pt.lancer([sys.executable, "-c", "import time; print('PRET', flush=True); time.sleep(60)"], cwd=".",
                      delai_s=60, arret=lambda texte: "PRET" in texte)
        self.assertFalse(r.fini)
        self.assertTrue(r.arrete)
        self.assertLess(time.monotonic() - debut, 20)

    def test_environnement(self):
        r = pt.lancer([sys.executable, "-c", "import os; print('V=' + os.environ.get('ESSAI_PT', '?'))"], cwd=".",
                      delai_s=30, env={"ESSAI_PT": "oui", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
        self.assertIn("V=oui", r.texte)


if __name__ == "__main__":
    unittest.main()
