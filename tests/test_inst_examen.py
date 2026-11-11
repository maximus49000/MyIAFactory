"""L'examen d'un dossier : borné, sans réseau, sans rien écrire."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from installation import examen


def ecrire(base, rel, texte=""):
    p = Path(base) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texte, encoding="utf-8")
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name) / "projet"
        self.d.mkdir()


class TestExamen(Base):
    def test_dossier_vide(self):
        r = examen.examiner(self.d)
        self.assertEqual(r["cas"], "vide")
        self.assertEqual(r["environnement"], [])
        self.assertEqual(r["inventaire"]["git"], {"depot": False, "distant": None})

    def test_vide_avec_readme_et_git(self):
        (self.d / ".git").mkdir()
        ecrire(self.d / ".git", "config", '[remote "origin"]\n\turl = https://exemple.test/x.git\n')
        ecrire(self.d, "README.md", "# x")
        ecrire(self.d, ".gitignore", "x")
        ecrire(self.d, "LICENSE", "x")
        r = examen.examiner(self.d)
        self.assertEqual(r["cas"], "vide")
        self.assertEqual(r["inventaire"]["git"], {"depot": True, "distant": "https://exemple.test/x.git"})

    def test_existant_python(self):
        ecrire(self.d, "pyproject.toml", "[project]")
        ecrire(self.d, "src/a.py", "x")
        ecrire(self.d, "src/b.py", "x")
        r = examen.examiner(self.d)
        self.assertEqual(r["cas"], "existant")
        self.assertEqual(r["environnement"], ["Python"])
        self.assertIn("pyproject.toml", r["inventaire"]["fichiers_cles"])
        self.assertEqual(r["inventaire"]["extensions"][0], [".py", 2])
        self.assertEqual(r["inventaire"]["nb_fichiers"], 3)

    def test_moteur_de_jeu_version_lue(self):
        ecrire(self.d, "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 2022.3.1f1\nautre\n")
        r = examen.examiner(self.d)
        self.assertEqual(r["environnement"], ["moteur de jeu, version m_EditorVersion: 2022.3.1f1"])

    def test_installe(self):
        ecrire(self.d, ".factory/factory.json", "{}")
        self.assertEqual(examen.examiner(self.d)["cas"], "installe")

    def test_factory_propre(self):
        ecrire(self.d, ".factory/reglages.json", json.dumps({"images": {}}))
        self.assertEqual(examen.examiner(self.d)["cas"], "factory_propre")

    def test_reglages_avec_orchestrateur_pas_propre(self):
        ecrire(self.d, ".factory/reglages.json", json.dumps({"orchestrateur": "factory.json"}))
        ecrire(self.d, "main.py", "x")
        self.assertEqual(examen.examiner(self.d)["cas"], "existant")

    def test_node_modules_saute(self):
        ecrire(self.d, "package.json", "{}")
        for i in range(50):
            ecrire(self.d, f"node_modules/m{i}/index.js", "x")
        r = examen.examiner(self.d)
        self.assertEqual(r["environnement"], ["Node.js"])
        self.assertEqual(r["inventaire"]["nb_fichiers"], 1)
        self.assertFalse(any("node_modules" in e for e in r["inventaire"]["arbre"]))

    def test_gros_dossier(self):
        for a in range(10):
            for b in range(10):
                os.makedirs(self.d / f"a{a}" / f"b{b}")
                for i in range(50):
                    (self.d / f"a{a}" / f"b{b}" / f"f{i}.txt").write_text("", encoding="utf-8")
        t = time.monotonic()
        r = examen.examiner(self.d)
        self.assertLess(time.monotonic() - t, 2.5)
        self.assertLessEqual(len(r["inventaire"]["arbre"]), 200)
        self.assertEqual(r["inventaire"]["nb_fichiers"], 5000)

    def test_lien_sortant_ignore(self):
        dehors = Path(self._tmp.name) / "dehors"
        ecrire(dehors, "secret/s.txt", "x")
        ecrire(self.d, "a.py", "x")
        try:
            os.symlink(dehors, self.d / "lien", target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != "nt" or subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(self.d / "lien"), str(dehors)],
                    capture_output=True).returncode != 0:
                self.skipTest("aucun lien possible")
        r = examen.examiner(self.d)
        self.assertEqual(r["inventaire"]["nb_fichiers"], 1)
        self.assertFalse(any("secret" in e for e in r["inventaire"]["arbre"]))

    def test_rien_n_est_ecrit(self):
        ecrire(self.d, "package.json", "{}")
        ecrire(self.d, "src/x.js", "x")
        avant = sorted((str(p.relative_to(self.d)), p.stat().st_mtime_ns) for p in self.d.rglob("*"))
        examen.examiner(self.d)
        apres = sorted((str(p.relative_to(self.d)), p.stat().st_mtime_ns) for p in self.d.rglob("*"))
        self.assertEqual(avant, apres)


if __name__ == "__main__":
    unittest.main()
