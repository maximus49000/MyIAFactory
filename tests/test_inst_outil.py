"""La ligne de commande de l'installation, en sous-processus. HOME et USERPROFILE sont temporaires ; la skill du
dossier stable est un clone d'un dépôt local (aucun accès réseau)."""
import json
import os
import subprocess
import sys
from pathlib import Path

from installation import dossier
from tests.inst_aide import AvecMaison, proposition_valide

OUTIL = Path(__file__).resolve().parent.parent / "installation" / "outil.py"
RACINE = Path(__file__).resolve().parent.parent


class TestOutil(AvecMaison):
    def lancer(self, *args, entree=None):
        env = {**os.environ, "HOME": str(self.maison), "USERPROFILE": str(self.maison),
               "GIT_TERMINAL_PROMPT": "0"}
        corps = None if entree is None else json.dumps(entree, ensure_ascii=False).encode("utf-8")
        p = subprocess.run([sys.executable, str(OUTIL), *args], input=corps,
                           stdin=None if corps is not None else subprocess.DEVNULL, capture_output=True, env=env,
                           timeout=300)
        sortie = p.stdout.decode("utf-8")
        return p.returncode, (json.loads(sortie) if sortie.strip() else None)

    def git(self, *args, cwd):
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})

    def skill_clonee(self):
        """Un dépôt « origine » local et sa copie dans le dossier stable : `git pull` marche sans réseau."""
        origine = self.base / "origine"
        origine.mkdir()
        self.git("init", "-q", cwd=origine)
        (origine / "LISEZMOI.md").write_text("skill\n", encoding="utf-8")
        self.git("add", ".", cwd=origine)
        self.git("-c", "user.name=t", "-c", "user.email=t@exemple.invalid", "commit", "-q", "-m", "départ", cwd=origine)
        dossier.racine().mkdir(parents=True)
        self.git("clone", "-q", str(origine), str(dossier.skill()), cwd=dossier.racine())
        # le code de la skill, par des jonctions vers ce dépôt : le bureau peut lancer la commande du relevé
        for nom in ("orchestrateur", "bureau"):
            lien = dossier.skill() / nom
            dossier.creer_lien(RACINE / nom, lien)
            self.addCleanup(os.rmdir, lien)   # retire la jonction seule

    def test_parcours_vide_bout_en_bout(self):
        self.skill_clonee()
        code, r = self.lancer("preparer")
        self.assertEqual((code, r["action"]), (0, "mise_a_jour"), r)
        self.assertEqual(r["message"], "La skill est à jour.")
        code, r = self.lancer("examiner", str(self.projet))
        self.assertEqual((code, r["cas"]), (0, "vide"))
        code, cal = self.lancer("calibrer")
        self.assertEqual(code, 0)
        self.assertTrue(1 <= cal["agents_locaux_max"] <= 6)
        p = proposition_valide(self.projet)
        code, est = self.lancer("estimer", entree={"flux": p["flux"], "agents": p["agents"], "genre": None})
        self.assertEqual((code, est["source"]), (0, "defauts"))
        self.assertIsNone(est["euros"])
        code, r = self.lancer("proposer", entree=p)
        self.assertEqual(code, 0, r)
        enregistree = Path(r["proposition"])
        self.assertTrue(enregistree.is_file())
        self.assertEqual(enregistree.parent, dossier.propositions())
        self.assertEqual(r["estimation"]["tokens"], est["tokens"])
        self.assertFalse((self.projet / ".factory").exists())
        code, r = self.lancer("appliquer", str(self.projet))
        self.assertEqual(code, 0, r)
        self.assertTrue(r["pret"], r["verification"])
        self.assertFalse(enregistree.exists())
        self.assertTrue((self.projet / ".factory" / "factory.json").is_file())
        code, r = self.lancer("examiner", str(self.projet))
        self.assertEqual(r["cas"], "installe")
        code, r = self.lancer("reparer", str(self.projet))
        self.assertEqual(code, 0, r)
        self.assertEqual(r["corrections"], [])
        self.assertTrue(r["pret"], r["verification"])
        self.assertIn("agents_locaux_max", r["calibrage"])

    def test_partenaires_detecte_sans_rien_ecrire_dans_le_projet(self):
        (self.projet / ".mcp.json").write_text(json.dumps({"mcpServers": {"stripe": {"url": "https://mcp.stripe.com",
                                                          "headers": {"Authorization": "Bearer CLE-SECRETE-9"}}}}),
                                               encoding="utf-8")
        avant = sorted(x.name for x in self.projet.iterdir())
        code, r = self.lancer("partenaires", str(self.projet))
        self.assertEqual(code, 0, r)
        self.assertEqual(r["connexions"]["stripe"]["etat"], "declare")
        self.assertIn("synthese-vocale", r["besoins"]["voix-audio"])
        self.assertNotIn("CLE-SECRETE-9", json.dumps(r))
        self.assertEqual(sorted(x.name for x in self.projet.iterdir()), avant)
        self.assertTrue((self.maison / "MyIAFactory" / "partenaires.json").is_file())
        code, r = self.lancer("partenaires", str(self.projet), "--besoins", "synthese-vocale,3d")
        self.assertEqual(code, 0, r)
        self.assertEqual(len(r["suggestions"]["synthese-vocale"]), 5)
        self.assertEqual(r["suggestions"]["synthese-vocale"][0]["id"], "elevenlabs")
        self.assertTrue(all(x["description"] and x["inscription"] is None or x["inscription"].startswith("https://")
                            for x in r["suggestions"]["3d"]))

    def test_appliquer_sans_proposition(self):
        code, r = self.lancer("appliquer", str(self.projet))
        self.assertEqual(code, 1)
        self.assertIn("proposer", r["erreur"])
        self.assertFalse((self.projet / ".factory").exists())

    def test_proposer_invalide_code_1(self):
        code, r = self.lancer("proposer", entree=proposition_valide(self.projet, modele_orchestrateur="Fable"))
        self.assertEqual(code, 1)
        self.assertTrue(any("Fable" in e for e in r["erreurs"]))
        self.assertFalse(dossier.propositions().exists() and any(dossier.propositions().iterdir()))

    def test_entree_illisible_code_2(self):
        env = {**os.environ, "HOME": str(self.maison), "USERPROFILE": str(self.maison)}
        p = subprocess.run([sys.executable, str(OUTIL), "proposer"], input=b"{pas du json", capture_output=True,
                           env=env, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("erreur", json.loads(p.stdout.decode("utf-8")))

    def test_commande_inconnue_code_2(self):
        code, _ = self.lancer("inconnue")
        self.assertEqual(code, 2)
        code, _ = self.lancer("examiner")
        self.assertEqual(code, 2)

    def test_reparer_sans_installation_code_1(self):
        code, r = self.lancer("reparer", str(self.projet))
        self.assertEqual(code, 1)
        self.assertIn("erreur", r)


class TestAccesEnProcessus(AvecMaison):
    """Les accès du téléphone, sans lancer Tailscale ni toucher au réseau : l'outil est appelé en processus."""

    def test_commande_acces(self):
        from unittest import mock
        from installation import outil
        with mock.patch.object(outil.acces, "adresses", return_value={"tailscale": None, "reseau_local": "10.0.0.2"}):
            self.assertEqual(outil.cmd_acces(outil._analyseur().parse_args(["acces"])),
                             {"tailscale": None, "reseau_local": "10.0.0.2"})

    def test_reparer_avec_acces(self):
        from installation import outil
        a = outil._analyseur().parse_args(["reparer", "x", "--tailscale"])
        self.assertEqual(outil._acces_demandes(a), {"tailscale": True, "reseau_local": False})
        a = outil._analyseur().parse_args(["reparer", "x"])
        self.assertIsNone(outil._acces_demandes(a))


if __name__ == "__main__":
    import unittest
    unittest.main()
