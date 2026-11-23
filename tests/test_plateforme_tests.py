"""Marqueurs de plateforme (`tests/plateforme_tests.py`) et lecture des ignorés du lanceur."""
import ast
import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import tests_paralleles  # noqa: E402
from tests import plateforme_tests  # noqa: E402


def _classe(decorateur):
    @decorateur
    class Cible(unittest.TestCase):
        def test_x(self):
            pass
    return Cible


class TestMarqueurs(unittest.TestCase):
    def test_raisons_prefixees(self):
        with mock.patch.object(plateforme_tests, "WINDOWS", False), mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(_classe(plateforme_tests.windows_seulement("registre")).__unittest_skip_why__,
                             "Windows seulement : registre")
            self.assertEqual(_classe(plateforme_tests.pas_encore_linux("chemin C:/")).__unittest_skip_why__,
                             "À rendre hermétique : chemin C:/")
            self.assertFalse(getattr(_classe(plateforme_tests.linux_seulement("bash")), "__unittest_skip__", False))
        with mock.patch.object(plateforme_tests, "WINDOWS", True), mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(_classe(plateforme_tests.linux_seulement("bash")).__unittest_skip_why__,
                             "Linux seulement : bash")
            self.assertFalse(getattr(_classe(plateforme_tests.windows_seulement("registre")), "__unittest_skip__", False))
            self.assertFalse(getattr(_classe(plateforme_tests.pas_encore_linux("x")), "__unittest_skip__", False))

    def test_raison_vide_refusee(self):
        for f in (plateforme_tests.windows_seulement, plateforme_tests.linux_seulement,
                  plateforme_tests.pas_encore_linux, plateforme_tests.module_pas_encore_linux):
            with self.assertRaises(ValueError):
                f("  ")

    def test_module_pas_encore_linux(self):
        with mock.patch.object(plateforme_tests, "WINDOWS", False):
            with self.assertRaises(unittest.SkipTest) as c:
                plateforme_tests.module_pas_encore_linux("bash")
            self.assertEqual(str(c.exception), "À rendre hermétique : bash")
        with mock.patch.object(plateforme_tests, "WINDOWS", True):
            plateforme_tests.module_pas_encore_linux("bash")

    def test_ignores_lus(self):
        self.assertEqual(tests_paralleles._ignores("Ran 4 tests in 0.1s\n\nOK (skipped=3)\n"), 3)
        self.assertEqual(tests_paralleles._ignores("Ran 4 tests in 0.1s\n\nFAILED (failures=1, skipped=2)\n"), 2)
        self.assertEqual(tests_paralleles._ignores("Ran 4 tests in 0.1s\n\nOK\n"), 0)

    def test_compatible_py39(self):
        source = (RACINE / "tests" / "plateforme_tests.py").read_text(encoding="utf-8")
        ast.parse(source, feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
