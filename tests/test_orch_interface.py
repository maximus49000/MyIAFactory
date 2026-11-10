import json
import subprocess
import sys
import textwrap
from pathlib import Path

from tests.orch_aide import AvecProjet, RACINE

VERIFIER = RACINE / "orchestrateur" / "verifier_interface.py"


class TestVerificateur(AvecProjet):
    def setUp(self):
        super().setUp()
        # une « skill » factice : la mesure de charge réelle prendrait cinq secondes
        skill = self.dossier / "skill"
        skill.mkdir()
        (skill / "lancer.py").write_text("print('ok : charge 5 % (max 75 %)')\n", encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["skill"] = "skill"
        self.factory.write_text(json.dumps(d), encoding="utf-8")

    def verifier(self, *args, factory=None):
        p = subprocess.run([sys.executable, str(VERIFIER), "--factory", str(factory or self.factory), *args],
                           capture_output=True, timeout=180, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout.decode("utf-8", "replace")

    def marquer(self):
        (self.dossier / ".copie-de-verification").write_text("", encoding="utf-8")

    def declarer(self, commande, source):
        (self.dossier / f"adaptateur-{commande}.py").write_text(textwrap.dedent(source), encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d.setdefault("commandes", {})[commande] = [sys.executable, f"adaptateur-{commande}.py"]
        self.factory.write_text(json.dumps(d), encoding="utf-8")

    def test_verificateur_outils_generiques_ok(self):
        self.marquer()
        code, sortie = self.verifier("--complet")
        self.assertEqual(code, 0, sortie)
        lignes = sortie.strip().splitlines()
        self.assertTrue(all(l.startswith("ok") or l.startswith("ignoré") for l in lignes), sortie)
        for commande in ("releve", "etat", "demandes", "memoire", "genre", "agent-libre", "depart", "catalogue", "actions",
                         "charge", "reveil", "demande-traitee", "fonctionnalite", "message", "decision", "tache", "file",
                         "file-prendre", "session", "lecon", "controle"):
            self.assertTrue(any(f" {commande}" in l for l in lignes), (commande, sortie))

    def test_sans_complet_ne_change_rien(self):
        self.ok("tache", entree={"titre": "A", "colonne": "dev"})
        avant = (self.dossier / "suivi.json").read_text(encoding="utf-8")
        code, sortie = self.verifier()   # pas de marque, pas de --complet
        self.assertEqual(code, 0, sortie)
        self.assertEqual((self.dossier / "suivi.json").read_text(encoding="utf-8"), avant)
        self.assertNotIn(" actions", sortie)
        self.assertIn(" releve", sortie)
        self.assertFalse((self.dossier / "demandes.jsonl").exists())

    def test_verificateur_signale_un_ecart(self):
        # un adaptateur d'`etat` qui oublie des champs du contrat
        self.declarer("etat", """
            import json
            print(json.dumps({"genre": None}))
        """)
        code, sortie = self.verifier()
        self.assertEqual(code, 1, sortie)
        ligne = next(l for l in sortie.splitlines() if " etat" in l)
        self.assertFalse(ligne.startswith("ok"))
        self.assertIn("fonctionnalites", ligne)
        self.assertTrue(any(l.startswith("ok") and " releve" in l for l in sortie.splitlines()))   # les autres sont vérifiées

    def test_verificateur_signale_un_mauvais_code(self):
        # un adaptateur qui accepte une décision inconnue au lieu de la refuser (code 1 attendu)
        self.declarer("demande-traitee", """
            import json, sys
            sys.stdin.read()
            print(json.dumps({"ok": True}))
        """)
        self.marquer()
        code, sortie = self.verifier("--complet")
        self.assertEqual(code, 1, sortie)
        ligne = next(l for l in sortie.splitlines() if " demande-traitee" in l)
        self.assertIn("code", ligne)

    def test_verificateur_signale_une_commande_qui_plante(self):
        self.declarer("releve", """
            raise SystemExit(7)
        """)
        code, sortie = self.verifier()
        self.assertEqual(code, 1)
        self.assertIn("code 7", next(l for l in sortie.splitlines() if " releve" in l))

    def test_complet_refuse_hors_copie(self):
        subprocess.run(["git", "init", "-q"], cwd=str(self.dossier), check=True)
        code, sortie = self.verifier("--complet")
        self.assertEqual(code, 2)
        self.assertIn("copie", sortie)
        self.assertFalse((self.dossier / "suivi.json").exists())   # rien n'a été lancé
        code, sortie = self.verifier()   # sans --complet, un dépôt git est bien accepté
        self.assertEqual(code, 0, sortie)
        self.marquer()
        code, sortie = self.verifier("--complet")
        self.assertEqual(code, 0, sortie)

    def test_factory_illisible(self):
        code, sortie = self.verifier(factory=self.dossier / "absent.json")
        self.assertEqual(code, 2)
