"""La détection des partenaires déclarés : noms et adresses seulement, jamais une valeur de clé."""
import json
import tempfile
import unittest
from pathlib import Path

from partenaires import detection

CLE = "CLE-SECRETE-RECONNAISSABLE-1234"


def catalogue():
    def p(i, nom, **c):
        return {"id": i, "nom": nom, "categorie": "voix-audio", "sous_categorie": "synthese-vocale", "statut": "actif",
                "connexions": [c] if c else [], "plans": []}
    return {"version": 1, "partenaires": [
        p("vox", "Vox", type="api", variables=["VOX_API_KEY"]),
        p("echo", "Echo Labs", type="mcp", url="https://mcp.echo.example/sse",
          commande="claude mcp add --transport sse echo-officiel https://mcp.echo.example/sse"),
        p("rien", "Rien", type="api", variables=["RIEN_API_KEY"]),
    ]}


class TestDetection(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.dossier = Path(t.name)
        self.projet = self.dossier / "projet"
        self.projet.mkdir()
        self.config = self.dossier / ".claude.json"

    def test_env_noms_seulement(self):
        (self.projet / ".env").write_text(
            "# commentaire\nexport VOX_API_KEY=\"" + CLE + "\"\nAUTRE='a b'\n  # RIEN_API_KEY=x\n"
            "MULTI=\"debut\nFAUX_NOM=pas une variable\nfin\"\nSIMPLE=valeur # note\n=sans nom\n", encoding="utf-8")
        noms = detection.noms_env(self.projet / ".env")
        self.assertEqual(noms, {"VOX_API_KEY", "AUTRE", "MULTI", "SIMPLE"})
        self.assertNotIn(CLE, repr(noms))
        d = detection.declares(self.projet, environ={}, config_utilisateur=self.config, catalogue=catalogue())
        self.assertEqual(d, {"vox": "variable VOX_API_KEY présente (.env du projet)"})
        self.assertNotIn(CLE, json.dumps(d))

    def test_cle_environnement_puis_env(self):
        (self.projet / ".env").write_text(f"VOX_API_KEY='{CLE}'\n", encoding="utf-8")
        self.assertEqual(detection.cle("vox", self.projet, environ={}, catalogue=catalogue()), CLE)
        self.assertEqual(detection.cle("vox", self.projet, environ={"VOX_API_KEY": "machine"}, catalogue=catalogue()),
                         "machine")
        self.assertIsNone(detection.cle("rien", self.projet, environ={}, catalogue=catalogue()))
        self.assertIsNone(detection.cle("inconnu", self.projet, environ={}, catalogue=catalogue()))

    def test_mcp_headers_jamais_lus(self):
        secret = {"headers": {"Authorization": f"Bearer {CLE}"}, "env": {"X": CLE}, "args": ["--token", CLE]}
        self.config.write_text(json.dumps({
            "mcpServers": {"echo-officiel": {"type": "stdio", "command": "x", **secret}},
            "projects": {str(self.projet.resolve()): {"mcpServers": {"autre": {"url": "https://mcp.echo.example/sse/", **secret}}}},
            "oauthAccount": {"jeton": CLE}}), encoding="utf-8")
        (self.projet / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {"x": {"url": "https://ailleurs.example", **secret}}}), encoding="utf-8")
        serveurs = detection.serveurs_mcp(self.projet, self.config)
        self.assertNotIn(CLE, repr(serveurs))
        self.assertEqual({s[0] for s in serveurs}, {"echo-officiel", "autre", "x"})
        d = detection.declares(self.projet, environ={}, config_utilisateur=self.config, catalogue=catalogue())
        self.assertIn("echo", d)
        self.assertNotIn(CLE, json.dumps(d))
        # le hook de lecture jette les champs sensibles avant tout usage
        lu = detection._lire_json(self.config)
        self.assertNotIn("headers", json.dumps(lu))
        self.assertNotIn("Bearer", json.dumps(lu))

    def test_adresse_reconnue(self):
        (self.projet / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {"nom-libre": {"type": "sse", "url": "HTTPS://MCP.ECHO.EXAMPLE/sse/"}}}), encoding="utf-8")
        d = detection.declares(self.projet, environ={}, config_utilisateur=self.config, catalogue=catalogue())
        self.assertEqual(list(d), ["echo"])
        self.assertIn(".mcp.json", d["echo"])

    def test_variable_machine(self):
        d = detection.declares(self.projet, environ={"RIEN_API_KEY": CLE}, config_utilisateur=self.config,
                               catalogue=catalogue())
        self.assertEqual(d, {"rien": "variable RIEN_API_KEY présente (environnement)"})

    def test_fichiers_absents_ou_illisibles(self):
        self.config.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(detection.declares(self.projet, environ={}, config_utilisateur=self.config,
                                            catalogue=catalogue()), {})


if __name__ == "__main__":
    unittest.main()
