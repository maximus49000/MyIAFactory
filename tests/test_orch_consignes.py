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

    def test_reprendre_une_methode_existante(self):
        # Essai réel : une fonctionnalité qui ressemble à une méthode validée propose d'industrialiser d'emblée.
        texte = lire(ORCH / "consignes.md")
        self.assertIn("`reprendre_methode`", texte)
        ligne = next(l for l in texte.splitlines() if l.startswith("| `methode` |"))
        for mot in ("`reprendre`", "`adapter`", "`revoir`"):
            self.assertIn(mot, ligne, mot)

    def test_toute_demande_du_bureau_est_prise_par_l_outil(self):
        # Essai réel : « Actualiser » et « Mettre à jour les offres » des partenaires étaient acceptés par le bureau
        # puis refusés par l'outil (« Demande inconnue ») : le bouton ne faisait rien.
        from bureau import demandes
        self.assertEqual(sorted(set(demandes.CHAMPS) - set(outil.TYPES_DEMANDE)), [])

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

    def test_choix_toujours_en_questions(self):
        # Un message qui offre un choix le donne en boutons (questions à choix), jamais seulement en phrases.
        texte = lire(ORCH / "consignes.md")
        self.assertIn("soit… soit…", texte)
        self.assertIn("`questions`", texte)
        self.assertIn("Les choix en boutons", texte)

    def test_cadrage_mixte(self):
        # La compréhension se joue à la première réponse et au cahier : sur un cran au-dessus d'une fiche Haiku ;
        # les questions intermédiaires restent sur le modèle léger.
        texte = lire(ORCH / "consignes.md")
        self.assertIn("première analyse du besoin", texte)
        self.assertIn("écrire le cahier des charges", texte)

    def test_correction_du_cahier_rouvre_le_cadrage(self):
        # Essai réel : « corriger » rouvre la discussion (étape cadrage), l'ancien cahier n'est plus montré comme
        # valable, et le nouveau le remplace (l'ancien reste dans les versions précédentes).
        texte = lire(ORCH / "consignes.md")
        ligne = next(l for l in texte.splitlines() if l.startswith("| `cahier` |"))
        for mot in ("`corriger`", "`action: lever`", "`etape: cadrage`", "cahiers_precedents", "`valider_cahier`"):
            self.assertIn(mot, ligne, mot)

    def test_serie_en_parallele(self):
        # En série, la factory n'attend pas la relecture pour lancer le dev suivant ; les corrections passent d'abord.
        texte = lire(ORCH / "consignes.md")
        for mot in ("En parallèle", "les corrections passent avant", "deux éléments en cours", "jamais pendant le prototype"):
            self.assertIn(mot, texte, mot)

    def test_section_partenaires(self):
        texte = lire(ORCH / "consignes.md")
        self.assertIn("## Les partenaires", texte)
        section = texte.split("## Les partenaires", 1)[1].split("\n## ", 1)[0]
        for action in outil.ACTIONS_PARTENAIRES:
            if action != "usage":   # l'agent la note ; elle est citée par son nom dans la section
                self.assertIn(f"`{action}`", section, action)
        for mot in ("facultatifs", "Aucune valeur de", "`meilleur_non_connecte`", "ne bloque pas", "`gratuit`",
                    "`inclus`", "`usage` ou `inconnu`", "toujours son accord", "mode manuel", "mode navigateur",
                    "`partenaire_regle`", "`partenaires_actualiser`", "`partenaires_maj`", "Sonnet", "mots interdits",
                    "commit et push", "`verifie_le`", "`force: true`", "une fois par heure", "`partenaires`"):
            self.assertIn(mot, section, mot)

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
