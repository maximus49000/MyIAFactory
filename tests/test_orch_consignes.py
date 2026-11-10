"""Les consignes génériques, l'interface et les modèles se tiennent entre eux."""
import re
import unittest
from pathlib import Path

from bureau import releve
from orchestrateur import factory, outil

RACINE = Path(__file__).resolve().parent.parent
ORCH = RACINE / "orchestrateur"


def lire(chemin):
    return chemin.read_text(encoding="utf-8")


class TestConsignes(unittest.TestCase):
    def test_chaque_commande_documentee(self):
        titres = set(re.findall(r"^### `([a-z-]+)`", lire(ORCH / "interface.md"), re.M))
        self.assertEqual(titres, set(outil.COMMANDES))

    def test_consignes_n_appellent_que_des_commandes_connues(self):
        texte = lire(ORCH / "consignes.md")
        appels = re.findall(r"\blancer ([a-z-]+)", texte)
        self.assertGreater(len(appels), 20)
        inconnues = sorted(set(appels) - set(outil.COMMANDES))
        self.assertEqual(inconnues, [], f"commandes inconnues dans consignes.md : {inconnues}")
        # Chaque commande de l'interface sert au moins une fois, sauf `actions` (c'est le bureau qui l'appelle)
        # et `releve` (c'est le bureau qui le lit).
        manquantes = sorted(set(outil.COMMANDES) - set(appels) - {"actions", "releve"})
        self.assertEqual(manquantes, [], f"commandes jamais appelées par les consignes : {manquantes}")
        # L'orchestrateur ne passe jamais à côté de `lancer` (l'adaptateur du projet serait contourné).
        for ligne in texte.splitlines():
            for m in re.finditer(r"outil\.py(?: --factory \S+)? ([a-z-]+)", ligne):
                self.assertEqual(m.group(1), "lancer", f"appel direct sans `lancer` : {ligne.strip()}")

    def test_consignes_couvrent_le_parcours(self):
        texte = lire(ORCH / "consignes.md")
        for etape in releve.ETAPES:
            self.assertIn(f"`{etape}`", texte, f"étape non nommée : {etape}")
        for genre in releve.DECISIONS_FONCTIONNALITE + releve.DECISIONS_PROJET:
            self.assertIn(f"`{genre}`", texte, f"décision non nommée : {genre}")
        from bureau import demandes
        for genre in demandes.CHAMPS:
            self.assertIn(f"`{genre}`", texte, f"demande du bureau non traitée : {genre}")
        for mot in ("Fable", "contexte neuf", "En attente de", "les outils d'abord", "l'emportent",
                    "git pull --rebase", "mots interdits", "commit"):
            self.assertIn(mot.lower(), texte.lower(), f"règle absente : {mot}")

    def test_modele_factory_lisible(self):
        f = factory.lire(ORCH / "modeles" / "factory.json")
        self.assertGreaterEqual(len(f["flux"]), 1)
        self.assertIsNone(f["genre"])
        for nom in ("brief-role.md", "registre-controles.md", "fiche-agent.md"):
            self.assertTrue((ORCH / "modeles" / nom).is_file(), nom)

    def test_guide_de_passage(self):
        texte = lire(RACINE / "docs" / "orchestrateur.md")
        for mot in ("verifier_interface.py", "consignes propres", "liste de compatibilité", "adaptateur",
                    "orchestrateur/consignes.md", "commandes"):
            self.assertIn(mot, texte, mot)


if __name__ == "__main__":
    unittest.main()
