"""Service permanent côté poste (`outils/serveur_service.py`) et sa commande (`lancer.py service`, `deporter service`).

Un faux SSH conduit le VRAI script hôte (`serveur_ovh/services/service.py`) importé, avec le faux docker/ufw de
`test_serveur_service_hote` : bout en bout simulé, aucun serveur, aucun pare-feu, aucun jeton réel."""
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import serveur_service as ss  # noqa: E402
from tests.test_serveur_service_hote import DECLARATION, FauxHote, S  # noqa: E402

CLE_PRIVEE = "C:/cles-factices/cle-de-test-SECRET-CHEMIN"
SECRET = "cle-api-football-tres-secrete-123"


class FauxSsh:
    """`executer_octets` : le dépôt du script (reconnu par son en-tête) ou `python3 <script> <commande> ...` conduit en
    mémoire sur le script hôte, avec `FauxHote` et un ~/services jetable."""

    def __init__(self, racine):
        self.racine = racine
        self.hote = FauxHote()
        self.commandes = []
        self.entrees = []
        self.injoignable = False

    def executer_octets(self, cible, commande, cle, entree=None, delai=60):
        self.commandes.append(commande)
        self.entrees.append(entree or b"")
        if self.injoignable:
            return 255, b"", "ssh: connect to host: Connection refused"
        if commande.startswith("# service:deposer"):
            return 0, b"", ""
        argv = shlex.split(commande)
        assert argv[:2] == ["python3", ss.SCRIPT_DISTANT.replace('"', "")] or argv[0] == "python3", argv
        sortie = io.StringIO()
        code = S.main(argv[2:], entree=io.BytesIO(entree or b""), sortie=sortie, hote=self.hote, racine=self.racine,
                      uid=1000, gid=1000)
        return code, sortie.getvalue().encode("utf-8"), ""

    executer_octets_silencieux = executer_octets


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        t = Path(self._t.name)
        self.dossier = t / "MyIAFactory"
        self.dossier.mkdir()
        self.projet = t / "FM_Stats"
        (self.projet / ".factory").mkdir(parents=True)
        (self.projet / ".factory" / "service.json").write_text(json.dumps(DECLARATION), "utf-8")
        (self.projet / "serveur").mkdir()
        (self.projet / "serveur" / "Dockerfile").write_text("FROM python:3.12-slim\n", "utf-8")
        self.reglages = self.projet / ".factory" / "reglages.json"
        self.regler("serveur")
        self.bureau = self.dossier / "bureau.json"
        self.bureau.write_text(json.dumps({"projets": [{"chemin": str(self.reglages)}]}), "utf-8")
        (self.dossier / "serveurs.json").write_text(json.dumps(
            [{"id": "srv1", "nom": "srv1", "hote": "serveur.exemple.test", "utilisateur": "ubuntu", "cle": CLE_PRIVEE}]),
            "utf-8")
        (self.dossier / "serveurs-etat.json").write_text(json.dumps(
            {"srv1": {"capacites": {"base": {"statut": "presente"}}, "installation": {"en_cours": False}}}), "utf-8")
        _git("init", "-q", "-b", "main", cwd=self.projet)
        _git("-c", "user.email=test@exemple.test", "-c", "user.name=t", "add", "-A", cwd=self.projet)
        _git("-c", "user.email=test@exemple.test", "-c", "user.name=t", "commit", "-q", "-m", "init", cwd=self.projet)
        self.commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.projet, capture_output=True,
                                     text=True).stdout.strip()
        self.ssh = FauxSsh(t / "services-serveur")

    def tearDown(self):
        self._t.cleanup()

    def regler(self, lieu, variables=None):
        d = {"deport": {"lieux": {"service": lieu}}}
        if variables is not None:
            d["service"] = {"variables": variables}
        self.reglages.write_text(json.dumps(d), "utf-8")

    def k(self):
        return {"dossier": self.dossier, "ssh": self.ssh, "bureau": self.bureau}

    def secrets(self):
        return ss.poser_secrets(self.projet, {"CLE_API": SECRET}, **self.k())

    def deployer(self):
        self.secrets()
        return ss.deployer(self.projet, **self.k())


class TestIdentifiant(unittest.TestCase):
    def test_identifiant(self):
        self.assertEqual(ss.identifiant(Path("C:/x/FM_Stats")), "fm-stats")
        self.assertEqual(ss.identifiant(Path("/x/123 Projet")), "p-123-projet")
        self.assertTrue(S.MOTIF_PROJET.fullmatch(ss.identifiant(Path("/x/" + "é" * 80))))


class TestDeploiement(Base):
    def test_bout_en_bout(self):
        code, rep = self.deployer()
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["statut"], "ok")
        self.assertRegex(rep["adresse"], r"^http://serveur\.exemple\.test:18\d{3}$")
        jeton = ss.lire_jeton("fm-stats", self.dossier)
        self.assertGreaterEqual(len(jeton), 40)
        cache = json.loads((self.dossier / "services.json").read_text("utf-8"))
        texte = json.dumps(cache)
        self.assertNotIn(jeton, texte)
        self.assertNotIn(SECRET, texte)
        self.assertEqual(cache["fm-stats"]["etat"]["secrets"], {"CLE_API": True})
        # le secret n'a voyagé que par l'entrée standard, jamais dans une ligne de commande
        self.assertFalse(any(SECRET in c for c in self.ssh.commandes))
        self.assertTrue(any(SECRET.encode() in e for e in self.ssh.entrees))
        # l'archive envoyée est celle du commit
        self.assertTrue(any(c.split()[2:4] == ["recevoir", "fm-stats"] and self.commit in c for c in self.ssh.commandes))

    def test_sans_accord_rien_ne_part(self):
        self.regler("poste")
        code, rep = ss.deployer(self.projet, **self.k())
        self.assertEqual(code, 2, rep)
        self.assertEqual(self.ssh.commandes, [])

    def test_projet_non_enregistre(self):
        self.bureau.write_text(json.dumps({"projets": []}), "utf-8")
        code, _rep = ss.deployer(self.projet, **self.k())
        self.assertEqual(code, 2)
        self.assertEqual(self.ssh.commandes, [])

    def test_declaration_hostile_refusee_au_poste(self):
        (self.projet / ".factory" / "service.json").write_text(json.dumps(dict(DECLARATION, port_interne=22)), "utf-8")
        code, rep = ss.deployer(self.projet, **self.k())
        self.assertEqual(code, 2, rep)
        self.assertEqual(self.ssh.commandes, [])

    def test_variables_du_reglage(self):
        self.regler("serveur", variables={"NIVEAU_JOURNAL": "debug"})
        code, rep = self.deployer()
        self.assertEqual(code, 0, rep)
        env = (self.ssh.racine / "fm-stats" / "env").read_text("utf-8")
        self.assertIn("NIVEAU_JOURNAL=debug", env)

    def test_retour_arriere_rapporte(self):
        self.deployer()
        (self.projet / "x.txt").write_text("x", "utf-8")
        _git("-c", "user.email=test@exemple.test", "-c", "user.name=t", "add", "-A", cwd=self.projet)
        _git("-c", "user.email=test@exemple.test", "-c", "user.name=t", "commit", "-q", "-m", "b", cwd=self.projet)
        nouveau = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.projet, capture_output=True,
                                 text=True).stdout.strip()
        self.ssh.hote.images_malades.add(S.nom_image("fm-stats", nouveau))
        code, rep = ss.deployer(self.projet, **self.k())
        self.assertEqual(code, 1)
        self.assertEqual(rep["statut"], "retour_arriere")

    def test_serveur_injoignable(self):
        self.secrets()
        self.ssh.injoignable = True
        code, rep = ss.deployer(self.projet, **self.k())
        self.assertEqual(code, 1)
        self.assertNotIn(CLE_PRIVEE, json.dumps(rep))

    def test_aucun_serveur_pret(self):
        (self.dossier / "serveurs-etat.json").write_text("{}", "utf-8")
        code, rep = ss.deployer(self.projet, **self.k())
        self.assertEqual(code, 1, rep)
        self.assertEqual(self.ssh.commandes, [])


class TestGestion(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.deployer()[0], 0)
        self.jeton = ss.lire_jeton("fm-stats", self.dossier)

    def test_journal_masque(self):
        self.ssh.hote.journaux["svc-fm-stats"] = f"démarré\nclé {SECRET}\njeton {self.jeton}\n"
        code, rep = ss.gerer(self.projet, "journal", **self.k())
        self.assertEqual(code, 0, rep)
        texte = json.dumps(rep)
        self.assertNotIn(SECRET, texte)
        self.assertNotIn(self.jeton, texte)
        cache = json.loads((self.dossier / "services.json").read_text("utf-8"))
        self.assertNotIn(SECRET, json.dumps(cache))

    def test_arreter_puis_etat(self):
        self.assertEqual(ss.gerer(self.projet, "arreter", **self.k())[0], 0)
        _c, rep = ss.gerer(self.projet, "etat", **self.k())
        self.assertEqual(rep["etat"], "arrete")
        self.assertEqual(self.ssh.hote.regles, [])

    def test_supprimer_retire_le_jeton_du_coffre(self):
        self.assertEqual(ss.gerer(self.projet, "supprimer", **self.k())[0], 0)
        self.assertEqual(ss.lire_jeton("fm-stats", self.dossier), "")

    def test_commande_inconnue(self):
        n = len(self.ssh.commandes)
        code, _rep = ss.gerer(self.projet, "rm -rf", **self.k())
        self.assertEqual(code, 2)
        self.assertEqual(len(self.ssh.commandes), n)


class TestCommande(Base):
    def main(self, *argv, env=None, saisir=None, tty=True):
        sortie, erreur = io.StringIO(), io.StringIO()
        environ = dict(env or {})
        with mock.patch("sys.stdout", sortie), mock.patch("sys.stderr", erreur):
            code = ss.main(list(argv) + ["--dossier", str(self.projet)], environ=environ,
                           saisir=saisir or (lambda invite: SECRET), est_tty=lambda: tty, **self.k())
        return code, sortie.getvalue(), erreur.getvalue()

    def test_agent_limite_a_etat_et_journal(self):
        for commande in ("deployer", "redemarrer", "arreter", "supprimer", "secrets", "jeton", "mettre-a-jour"):
            with self.subTest(commande=commande):
                code, _o, e = self.main(commande, env={"MYIAFACTORY_AGENT": "dev-1"})
                self.assertEqual(code, 2)
                self.assertIn("Directeur", e)
        self.assertEqual(self.ssh.commandes, [])

    def test_agent_lit_l_etat(self):
        self.deployer()
        code, sortie, _e = self.main("etat", env={"MYIAFACTORY_AGENT": "dev-1"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(sortie)["etat"], "actif")

    def test_secrets_saisis_sans_echo_jamais_affiches(self):
        self.ssh.commandes.clear()
        code, sortie, erreur = self.main("secrets", "CLE_API")
        self.assertEqual(code, 0, erreur)
        self.assertNotIn(SECRET, sortie + erreur)

    def test_secrets_refuses_sans_terminal(self):
        code, _o, e = self.main("secrets", "CLE_API", tty=False)
        self.assertEqual(code, 2)
        self.assertEqual(self.ssh.commandes, [])

    def test_jeton_pour_le_directeur(self):
        self.deployer()
        code, sortie, _e = self.main("jeton")
        self.assertEqual(code, 0)
        self.assertEqual(sortie.strip(), ss.lire_jeton("fm-stats", self.dossier))


class TestDeporterService(Base):
    def test_deporter_service_etat_et_refus(self):
        import deporter
        appels = []
        code = deporter.main(["service", "etat", "--dossier", str(self.projet)], bureau=self.bureau,
                             service=lambda argv: appels.append(argv) or 0)
        self.assertEqual(code, 0)
        self.assertEqual(appels, [["service", "etat", "--dossier", str(self.projet)]])
        for sous in ("deployer", "arreter", "secrets", "jeton", None):
            with self.subTest(sous=sous):
                argv = ["service"] + ([sous] if sous else []) + ["--dossier", str(self.projet)]
                self.assertEqual(deporter.main(argv, bureau=self.bureau, service=lambda a: 0), 2)


if __name__ == "__main__":
    unittest.main()
