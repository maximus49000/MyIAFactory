"""La sélection des tests touchés par des fichiers modifiés (`outils/impact_tests.py`), sur un petit dépôt fictif."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import impact_tests  # noqa: E402

FICHIERS = {
    "paquet/__init__.py": "",
    "paquet/a.py": "X = 1\n",
    "paquet/b.py": "from paquet import a\n",
    "paquet/serveur.py": "DOSSIER = 'web'\n",
    "outil/__init__.py": "",
    "outil/prog.py": "from paquet import a\nif __name__ == '__main__':\n    pass\n",
    "autre/prog.py": "if __name__ == '__main__':\n    pass\n",
    "autre/chemins.py": "P = RACINE / 'outil' / 'autre.py'\n",
    "web/ui/vue.js": "// rien\n",
    "tests/__init__.py": "",
    "tests/test_b.py": "from paquet import b\n",
    "tests/test_c.py": "X = 2\n",
    "tests/test_prog.py": "PROG = RACINE / 'outil' / 'prog.py'\n",
    "tests/test_serveur.py": "from paquet import serveur\n",
    "docs/note.md": "texte\n",
}


class TestImpact(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.r = Path(self._t.name)
        for nom, texte in FICHIERS.items():
            (self.r / nom).parent.mkdir(parents=True, exist_ok=True)
            (self.r / nom).write_text(texte, encoding="utf-8")
        self.g = impact_tests.Graphe(self.r)

    def touches(self, *modifies):
        return self.g.touches(list(modifies))[0]

    def test_par_imports_de_proche_en_proche(self):
        self.assertEqual(self.touches("paquet/a.py"), ["test_b", "test_prog"])   # b importe a ; prog importe a

    def test_un_programme_lance_par_son_chemin(self):
        self.assertEqual(self.touches("outil/prog.py"), ["test_prog"])

    def test_un_nom_partage_ne_relie_que_par_son_chemin(self):
        self.assertEqual(self.touches("autre/prog.py"), [])   # « prog.py » cité ailleurs, mais pour outil/prog.py

    def test_un_fichier_web_par_son_dossier(self):
        self.assertEqual(self.touches("web/ui/vue.js"), ["test_serveur"])

    def test_les_documents_ne_demandent_rien(self):
        self.assertEqual(self.touches("docs/note.md", "README.md"), [])

    def test_un_test_modifie_se_relance(self):
        self.assertEqual(self.touches("tests/test_c.py"), ["test_c"])

    def test_un_fichier_que_rien_ne_cite_donne_toute_la_suite(self):
        tests, raison = self.g.touches(["inconnu/donnees.bin"])
        self.assertIsNone(tests)
        self.assertIn("toute la suite", raison)


if __name__ == "__main__":
    unittest.main()
