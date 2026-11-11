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

    def test_la_discussion_lance_le_bureau(self):
        """Essai réel : à la fin, c'est la discussion qui lance (ou relance) le bureau, pas l'utilisateur."""
        texte = SKILL.read_text(encoding="utf-8")
        fin = texte.split("## 7. La fin", 1)[1]
        self.assertIn("outil.py bureau", fin)
        self.assertIn("--relancer", fin)
        self.assertNotIn('lancer.py" serveur', texte)
        installe = texte.split("- `installe`", 1)[1].split("\n- ", 1)[0]
        self.assertIn("--relancer", installe)

    def test_la_fin_lance_l_orchestrateur(self):
        """Essai réel : la discussion ouvre elle-même la conversation orchestratrice (session de l'app, sinon
        `outil.py orchestrateur`), et ne donne le message à coller qu'en dernier recours."""
        fin = SKILL.read_text(encoding="utf-8").split("## 7. La fin", 1)[1]
        self.assertIn('outil.py orchestrateur "<dossier>"', fin)
        self.assertIn("message_orchestrateur", fin)
        self.assertIn("session", fin)

    def test_questions_fermees_sans_reponse_devinee(self):
        """Essai réel : « les deux, locaux, facturation, non » a été lu « facturation : non ». Les questions groupées
        sont numérotées avec leurs choix, chaque réponse est redite, une réponse ambiguë est reposée."""
        section = SKILL.read_text(encoding="utf-8").split("## 4. Les questions communes", 1)[1].split("\n## ", 1)[0]
        for mot in ("numérotées", "oui ou non", "Redis", "ambiguë"):
            self.assertIn(mot, section, mot)

    def test_skill_cite_partenaires_detecter(self):
        texte = SKILL.read_text(encoding="utf-8")
        section = texte.split("### Les partenaires (facultatifs)", 1)[1].split("\n## ", 1)[0]
        for mot in ('outil.py partenaires "<dossier>"', "`detecter`", "partenaires_declares", "--besoins",
                    "Rien n'est obligatoire", "partenaires_conseilles"):
            self.assertIn(mot, section, mot)
        self.assertLess(texte.index("### Les partenaires"), texte.index("## 3a."))   # au début, après l'examen

    def test_aucun_fable_choisi(self):
        for ligne in SKILL.read_text(encoding="utf-8").splitlines():
            if "fable" in ligne.lower():
                self.assertIn("jamais", ligne.lower(), ligne)


class TestGuides(unittest.TestCase):
    """Les guides d'accord avec le plugin et la règle de versionnement (tâche 11)."""

    def test_installation_commence_par_le_plugin(self):
        texte = (RACINE / "docs" / "installation.md").read_text(encoding="utf-8")
        debut = texte[:texte.index("## Essayer avec la démo")]
        for mot in ("/plugin marketplace add maximus49000/MyIAFactory", "/plugin install myiafactory@myiafactory",
                    "/myiafactory:installer"):
            self.assertIn(mot, debut, mot)
        self.assertNotIn("arrivera avec le projet 4", texte)

    def test_regle_de_versionnement(self):
        # Plus personne ne conseille de mettre `.factory/` entier hors de git.
        for nom in ("installation.md", "orchestrateur.md"):
            texte = (RACINE / "docs" / nom).read_text(encoding="utf-8")
            self.assertNotRegex(texte, r"ajoutez `\.factory/` au `\.gitignore`", nom)
        texte = (RACINE / "docs" / "installation.md").read_text(encoding="utf-8")
        for regle in (".factory/equipe.json\n", ".factory/*-historique.jsonl\n"):
            self.assertIn(regle, texte, regle)

    def test_bureau_sur_le_telephone(self):
        texte = (RACINE / "docs" / "installation.md").read_text(encoding="utf-8")
        self.assertIn("## Le bureau sur le téléphone", texte)
        section = texte.split("## Le bureau sur le téléphone", 1)[1].split("\n## ", 1)[0]
        for mot in ("Tailscale", "Wi-Fi", "QR code", "Révoquer les téléphones", "pas chiffré", "--tailscale"):
            self.assertIn(mot, section, mot)

    def test_projet_neuf_renvoie_a_la_commande(self):
        texte = (RACINE / "docs" / "orchestrateur.md").read_text(encoding="utf-8")
        section = texte.split("## Démarrer un projet neuf", 1)[1]
        self.assertIn("/myiafactory:installer", section)

    def test_bureau_partenaire(self):
        texte = (RACINE / "docs" / "installation.md").read_text(encoding="utf-8")
        self.assertIn("## Le bureau partenaire", texte)
        section = texte.split("## Le bureau partenaire", 1)[1].split("\n## ", 1)[0]
        for mot in ("facultatif", "~/MyIAFactory/partenaires.json", ".factory/partenaires.json", "Mettre à jour les offres",
                    ".env", "jamais", "Règles"):
            self.assertIn(mot, section, mot)

    def test_readme_projet_4(self):
        texte = (RACINE / "README.md").read_text(encoding="utf-8")
        self.assertIn("/myiafactory:installer", texte)
        self.assertRegex(texte, r"- \[x\] 11\. Les guides d'accord")
        for n in ("18", "19", "20", "21"):
            self.assertRegex(texte, rf"- \[x\] {n}\. ")


if __name__ == "__main__":
    unittest.main()
