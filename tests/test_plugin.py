"""Le plugin Claude Code : ses fichiers JSON et les consignes de la discussion d'installation."""
import json
import re
import unittest
from pathlib import Path

from installation import outil

RACINE = Path(__file__).resolve().parent.parent
SKILL = RACINE / "skills" / "installer" / "SKILL.md"


def lire_json(chemin):
    return json.loads(chemin.read_text(encoding="utf-8"))


def commandes_de_l_outil():
    sous = next(a for a in outil._analyseur()._actions if a.dest == "commande")
    return set(sous.choices)


class TestPlugin(unittest.TestCase):
    def test_json_du_plugin(self):
        p = lire_json(RACINE / ".claude-plugin" / "plugin.json")
        self.assertEqual((p["name"], p["version"]), ("myiafactory", "0.4.0"))
        self.assertTrue(p["description"].strip())
        m = lire_json(RACINE / ".claude-plugin" / "marketplace.json")
        self.assertEqual(m["name"], "myiafactory")
        self.assertTrue(m["owner"]["name"].strip())
        self.assertEqual(len(m["plugins"]), 1)
        self.assertEqual((m["plugins"][0]["name"], m["plugins"][0]["source"]), ("myiafactory", "./"))

    def test_frontmatter(self):
        texte = SKILL.read_text(encoding="utf-8")
        entete = re.match(r"---\n(.*?)\n---\n", texte, re.S)
        self.assertIsNotNone(entete)
        champs = dict(l.split(":", 1) for l in entete.group(1).splitlines() if ":" in l)
        self.assertEqual(champs["name"].strip(), "installer")
        self.assertGreater(len(champs["description"].strip()), 40)

    def test_commandes_citees_existent(self):
        citees = set(re.findall(r"outil\.py\"? ([a-z]+)", SKILL.read_text(encoding="utf-8")))
        connues = commandes_de_l_outil()
        self.assertEqual(sorted(citees - connues), [])
        self.assertEqual(sorted(connues - citees), [], "chaque commande de l'outil sert dans la discussion")

    def test_longueur_consignes(self):
        mots = len(SKILL.read_text(encoding="utf-8").split())
        self.assertLessEqual(mots, 2000, f"{mots} mots")

    def test_aucun_fable_choisi(self):
        for ligne in SKILL.read_text(encoding="utf-8").splitlines():
            if "fable" in ligne.lower():
                self.assertIn("jamais", ligne.lower(), ligne)


if __name__ == "__main__":
    unittest.main()
