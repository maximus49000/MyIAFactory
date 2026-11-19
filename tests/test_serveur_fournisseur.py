"""Interface fournisseur et fournisseur OVH (`outils/serveur_fournisseur.py`). Le client OVH est simulé."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

OUTILS = Path(__file__).resolve().parent.parent / "outils"
sys.path.insert(0, str(OUTILS))
import plateforme_acces  # noqa: E402
import plateforme_ovh  # noqa: E402
import serveur_fournisseur  # noqa: E402
from serveur_modele import Serveur  # noqa: E402

NOM = "ns1234.ip-1-2-3.eu"
CLE = "ssh-ed25519 AAAAFAKEKEY myiafactory"
MODELES = {"ovh": ["debian12_64", "ubuntu2404-server_64"], "personal": []}
SERVEUR = Serveur("s1", "Mon serveur", "1.2.3.4", "deploy", "cle", "ovh", {"serveur": NOM})
SECRET = "SECRET-TRES-PRIVE-123"


class ClientFactice:
    def __init__(self, reponses=None):
        self.reponses = reponses or {}
        self.appels = []

    def appeler(self, methode, chemin, corps=None):
        self.appels.append((methode, chemin, corps))
        r = self.reponses.get((methode, chemin))
        if isinstance(r, Exception):
            raise r
        return r


def _client_complet():
    return ClientFactice({
        ("GET", f"/dedicated/server/{NOM}"): {"os": "ubuntu2404-server_64", "ip": "1.2.3.4", "state": "ok"},
        ("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES,
        ("POST", f"/dedicated/server/{NOM}/reinstall"): {"taskId": 7},
        ("GET", f"/dedicated/server/{NOM}/task/7"): {"status": "done"},
    })


class TestObtenir(unittest.TestCase):
    def test_obtenir_sans_fournisseur_renvoie_none(self):
        self.assertIsNone(serveur_fournisseur.obtenir(None))

    def test_obtenir_inconnu_leve_valueerror(self):
        with self.assertRaises(ValueError) as e:
            serveur_fournisseur.obtenir("inconnu")
        self.assertIn("inconnu", str(e.exception).lower())

    def test_obtenir_ovh(self):
        f = serveur_fournisseur.obtenir("ovh", client=ClientFactice())
        self.assertIsInstance(f, serveur_fournisseur.FournisseurOvh)
        self.assertEqual(f.nom, "ovh")

    def test_client_construit_paresseusement(self):
        with mock.patch.object(plateforme_acces, "charger_ovh") as charger:
            serveur_fournisseur.obtenir("ovh", dossier="/inexistant")
            serveur_fournisseur.FournisseurOvh("/inexistant")
            charger.assert_not_called()


class TestFournisseurOvh(unittest.TestCase):
    def test_ovh_delegue_lecture_et_etat_de_tache(self):
        c = _client_complet()
        f = serveur_fournisseur.obtenir("ovh", client=c)
        self.assertEqual(f.lire(SERVEUR), {"os": "ubuntu2404-server_64", "etat": "ok", "ip": "1.2.3.4"})
        self.assertEqual(f.etat_tache(SERVEUR, 7), "fini")

    def test_lire_est_en_lecture_seule(self):
        c = _client_complet()
        serveur_fournisseur.obtenir("ovh", client=c).lire(SERVEUR)
        self.assertTrue(c.appels)
        self.assertEqual([a for a in c.appels if a[0] != "GET"], [])

    def test_ovh_reinstaller_sans_accord_strict_n_ecrit_rien(self):
        for accord in ("True", 1, None, False):
            c = _client_complet()
            with mock.patch.object(plateforme_acces, "charger_ovh") as charger:
                f = serveur_fournisseur.obtenir("ovh", client=c)
                with self.assertRaises(plateforme_ovh.ErreurAccord, msg=repr(accord)):
                    f.reinstaller(SERVEUR, CLE, accord)
                charger.assert_not_called()
            self.assertEqual(c.appels, [], repr(accord))

    def test_reinstaller_avec_accord_poste_le_meme_corps_que_le_code_existant(self):
        c = _client_complet()
        self.assertEqual(serveur_fournisseur.obtenir("ovh", client=c).reinstaller(SERVEUR, CLE, True), 7)
        self.assertEqual([a for a in c.appels if a[0] != "GET"],
                         [("POST", f"/dedicated/server/{NOM}/reinstall",
                           {"operatingSystem": "ubuntu2404-server_64", "customizations": {"sshKey": CLE}})])

    def test_nom_du_service_repris_de_ovh_json_sans_reglage(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ovh.json").write_text(json.dumps({
                "point": "ovh-eu", "cle_app": "a", "secret": SECRET, "consommateur": "c", "serveur": NOM}), encoding="utf-8")
            c = _client_complet()
            sans_reglage = Serveur("s2", "x", "1.2.3.4", "deploy", "cle", "ovh", {})
            serveur_fournisseur.obtenir("ovh", dossier=d, client=c).lire(sans_reglage)
        self.assertEqual(c.appels[0][1], f"/dedicated/server/{NOM}")

    def test_secret_jamais_dans_les_messages(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ovh.json").write_text(json.dumps({
                "point": "ovh-eu", "cle_app": "a", "secret": SECRET, "consommateur": "c"}), encoding="utf-8")
            f = serveur_fournisseur.obtenir("ovh", dossier=d)
            sans_reglage = Serveur("s2", "x", "1.2.3.4", "deploy", "cle", "ovh", {})
            messages = []
            for appel in (lambda: f.lire(sans_reglage), lambda: f.reinstaller(sans_reglage, CLE, "True")):
                try:
                    appel()
                except Exception as e:
                    messages.append(str(e))
            try:
                serveur_fournisseur.obtenir("x" + SECRET)
            except ValueError as e:
                messages.append(str(e))
        self.assertEqual(len(messages), 3)
        for m in messages:
            self.assertNotIn(SECRET, m)


class TestSeparation(unittest.TestCase):
    def test_aucun_nom_ovh_hors_du_fournisseur(self):
        autorises = ("`ovh.json`", "« ovh »", '"ovh"')      # nom de fournisseur et fichier d'accès cités, rien d'autre
        for module in ("serveur_modele", "serveur_capacites", "serveur_etat"):
            texte = (OUTILS / f"{module}.py").read_text(encoding="utf-8")
            for a in autorises:
                texte = texte.replace(a, "")
            self.assertIsNone(re.search("ovh", texte, re.I), module)


if __name__ == "__main__":
    unittest.main()
