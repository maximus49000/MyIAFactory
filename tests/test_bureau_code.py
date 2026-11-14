import tempfile
import unittest
from pathlib import Path

from bureau import serveur


class EmpreinteDuCode(unittest.TestCase):
    def test_change_avec_le_code_de_la_page_pas_avec_les_tests(self):
        d = Path(tempfile.mkdtemp())
        (d / "a.js").write_text("1")
        (d / "tests").mkdir()
        (d / "tests" / "x.js").write_text("1")
        e1 = serveur.empreinte_du_code(d)
        (d / "tests" / "x.js").write_text("22")
        self.assertEqual(serveur.empreinte_du_code(d), e1)
        (d / "a.js").write_text("22")
        self.assertNotEqual(serveur.empreinte_du_code(d), e1)

    def test_empreinte_du_bureau(self):
        self.assertRegex(serveur.empreinte_du_code(), r"^[0-9a-f]{12}$")


class LeconsAuto(unittest.TestCase):
    def test_lecons_auto_hors_du_compteur(self):
        e = {"lecons_auto": True, "directeur": {"lecons": 3, "bloquees": 1, "total": 4}}
        self.assertEqual(serveur.sans_lecons_au_compteur(e)["directeur"], {"lecons": 0, "bloquees": 1, "total": 1})
        e = {"lecons_auto": False, "directeur": {"lecons": 3, "bloquees": 1, "total": 4}}
        self.assertEqual(serveur.sans_lecons_au_compteur(e)["directeur"]["total"], 4)


if __name__ == "__main__":
    unittest.main()
