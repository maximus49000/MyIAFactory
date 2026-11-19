"""Machine à états de la plateforme (`outils/plateforme.py`). Client OVH et SSH factices : aucun réseau, aucun ssh réel."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import plateforme  # noqa: E402
from ovh_api import ErreurOvh  # noqa: E402

IP = "203.0.113.7"
SECRET = "SECRET-OVH-XYZ"
CONSO = "CONSO-OVH-XYZ"
CLE_APP = "APP-OVH-XYZ"
LICENCE = "LICENCE-UNITY-XYZ"
PUB = "ssh-ed25519 AAAAKEYDEDIEE myiafactory"


class ClientFactice:
    def __init__(self, os_="none_64", statut_tache="done"):
        self.os, self.statut_tache, self.appels = os_, statut_tache, []

    def appeler(self, methode, chemin, corps=None):
        self.appels.append((methode, chemin))
        if chemin == "/dedicated/server/ns1":
            return {"os": self.os, "ip": IP, "state": "ok", "commercialRange": "x"}
        if chemin.endswith("/install/compatibleTemplates"):
            return {"ovh": ["ubuntu2204-server_64", "ubuntu2404-server_64", "debian12_64"], "personal": []}
        if chemin == "/me/sshKey":
            return {}
        if chemin.endswith("/install/start"):
            self.os = "ubuntu2404-server_64"
            return {"taskId": 7}
        if "/task/" in chemin:
            return {"status": self.statut_tache}
        raise ErreurOvh(404, "inconnu")

    def reinstallations(self):
        return [a for a in self.appels if a[1].endswith("/install/start")]


class SshFactice:
    def __init__(self, erreur_cle_hote=False):
        self.commandes, self.oublies, self.erreur_cle_hote = [], [], erreur_cle_hote

    def generer_cle(self, dossier):
        return Path(dossier) / "cle", PUB

    def executer(self, hote, commande, cle, stdin=None, delai=60):
        self.commandes.append((commande, stdin))
        if commande == "true":
            if self.erreur_cle_hote and not self.oublies:
                return 255, "", "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!"
            return 0, "", ""
        if "--etape" in commande:
            etape = commande.split("--etape ")[1].split()[0]
            detail = f"ok {SECRET}" if etape == "docker" else "ok"
            return 0, json.dumps({"etape": etape, "statut": "fait", "detail": detail, "versions": {}, "disque_libre_go": 90}) + "\n", ""
        return 0, "", ""

    def attendre_ssh(self, hote, cle, delai_total):
        return True

    def oublier_hote(self, hote, accord):
        self.oublies.append((hote, accord))

    def etapes_lancees(self):
        return [c.split("--etape ")[1].split()[0] for c, _ in self.commandes if "--etape" in c]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        (self.dossier / "ovh.json").write_text(json.dumps({
            "point": "ovh-eu", "cle_app": CLE_APP, "secret": SECRET, "consommateur": CONSO, "serveur": "ns1"}), encoding="utf-8")

    def lancer(self, client, ssh, accord=False):
        return plateforme.installer(self.dossier, accord, client=client, ssh=ssh, dormir=lambda s: None)

    @staticmethod
    def statuts(etat):
        return {e["id"]: e["statut"] for e in etat["etapes"]}


class TestEtat(Base):
    def test_serveur_vierge_sans_accord_bloque_a_l_etape_os_sans_effacer(self):
        client, ssh = ClientFactice(), SshFactice()
        etat = self.lancer(client, ssh)
        s = self.statuts(etat)
        self.assertEqual((s["lecture"], s["os"], s["ssh"]), ("fait", "bloque", "a_faire"))
        self.assertEqual(client.reinstallations(), [])
        self.assertEqual(ssh.commandes, [])
        self.assertIn("accord-reinstallation", [e for e in etat["etapes"] if e["id"] == "os"][0]["geste"])
        self.assertFalse(etat["pret"])

    def test_avec_accord_enchaine_les_etapes_dans_l_ordre(self):
        client, ssh = ClientFactice(), SshFactice()
        etat = self.lancer(client, ssh, accord=True)
        self.assertEqual(len(client.reinstallations()), 1)
        self.assertEqual(self.statuts(etat)["images"], "fait")
        self.assertEqual(ssh.etapes_lancees(), ["durcissement", "docker", "images"])
        self.assertTrue(etat["pret"])
        envois = [c for c, _ in ssh.commandes if c.startswith("cat > /tmp")]
        self.assertEqual(len(envois), 1)
        self.assertTrue(any("android/Dockerfile" in c for c, _ in ssh.commandes))

    def test_relance_reprend_sans_refaire_les_etapes_faites(self):
        client, ssh = ClientFactice(), SshFactice()
        self.lancer(client, ssh, accord=True)
        ssh2 = SshFactice()
        etat = self.lancer(client, ssh2, accord=True)
        self.assertEqual(len(client.reinstallations()), 1)
        self.assertEqual(ssh2.etapes_lancees(), [])
        self.assertTrue(etat["pret"])

    def test_pret_vaut_etapes_1_a_6_et_licence_facultative(self):
        etat = plateforme.calculer_etat({i: {"statut": "fait"} for i in plateforme.ETAPES[:6]})
        self.assertEqual(self.statuts(etat)["licence"], "a_faire")
        self.assertTrue(etat["pret"])
        self.assertTrue(etat["pret_sans_unity"])
        etat = plateforme.calculer_etat({i: {"statut": "fait"} for i in plateforme.ETAPES[:5]})
        self.assertFalse(etat["pret"])

    def test_licence_absente_donne_un_geste(self):
        etat = self.lancer(ClientFactice(), SshFactice(), accord=True)
        licence = [e for e in etat["etapes"] if e["id"] == "licence"][0]
        self.assertEqual(licence["statut"], "a_faire")
        self.assertIn("unity.ulf", licence["geste"])

    def test_os_present_non_ubuntu_bloque_avec_raison(self):
        client, ssh = ClientFactice(os_="debian12_64"), SshFactice()
        etat = self.lancer(client, ssh)
        os_ = [e for e in etat["etapes"] if e["id"] == "os"][0]
        self.assertEqual(os_["statut"], "bloque")
        self.assertIn("debian12_64", os_["detail"])
        self.assertIn("Rien n'a été effacé", os_["detail"])
        self.assertEqual(client.reinstallations(), [])

    def test_ubuntu_present_sans_accord_ne_reinstalle_jamais(self):
        client, ssh = ClientFactice(os_="ubuntu2404-server_64"), SshFactice()
        etat = self.lancer(client, ssh)
        self.assertEqual(self.statuts(etat)["os"], "fait")
        self.assertEqual(client.reinstallations(), [])
        self.assertTrue(etat["pret"])

    def test_echec_de_tache_ovh_donne_geste_et_pas_de_trace_de_pile(self):
        client, ssh = ClientFactice(statut_tache="error"), SshFactice()
        etat = self.lancer(client, ssh, accord=True)
        os_ = [e for e in etat["etapes"] if e["id"] == "os"][0]
        self.assertEqual(os_["statut"], "bloque")
        self.assertIn("espace client OVH", os_["geste"])
        self.assertNotIn("Traceback", json.dumps(etat))
        self.assertEqual(self.statuts(etat)["ssh"], "a_faire")

    def test_erreur_ssh_et_hote_invalide_sans_trace(self):
        class Casse(SshFactice):
            def executer(self, *a, **k):
                raise plateforme.ErreurSsh("client OpenSSH introuvable")
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), Casse())
        self.assertEqual(self.statuts(etat)["ssh"], "bloque")
        self.assertNotIn("Traceback", json.dumps(etat))

    def test_cle_hote_changee_exige_accord(self):
        client = ClientFactice(os_="ubuntu2404-server_64")
        ssh = SshFactice(erreur_cle_hote=True)
        etat = self.lancer(client, ssh)
        self.assertEqual(self.statuts(etat)["ssh"], "bloque")
        self.assertEqual(ssh.oublies, [])
        ssh = SshFactice(erreur_cle_hote=True)
        etat = self.lancer(client, ssh, accord=True)
        self.assertEqual(ssh.oublies, [(IP, True)])
        self.assertEqual(self.statuts(etat)["ssh"], "fait")

    def test_durcissement_refuse_si_cle_absente_d_authorized_keys(self):
        class SansCle(SshFactice):
            def executer(self, hote, commande, cle, stdin=None, delai=60):
                if commande.startswith("grep -qF"):
                    return 1, "", ""
                return super().executer(hote, commande, cle, stdin, delai)
        ssh = SansCle()
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), ssh)
        self.assertEqual(self.statuts(etat)["durcissement"], "bloque")
        self.assertNotIn("durcissement", ssh.etapes_lancees())

    def test_licence_en_stdin_seulement_pour_la_licence(self):
        ssh = SshFactice()
        self.lancer(ClientFactice(), ssh, accord=True)
        for commande, stdin in ssh.commandes:
            if "--etape" in commande:
                self.assertIsNone(stdin)

    def test_aucun_secret_dans_etat_ni_cache(self):
        (self.dossier / "unity.ulf").write_text(LICENCE, encoding="utf-8")
        etat = self.lancer(ClientFactice(), SshFactice(), accord=True)
        cache = (self.dossier / "plateforme.json").read_text(encoding="utf-8")
        for secret in (SECRET, CONSO, CLE_APP, LICENCE):
            self.assertNotIn(secret, json.dumps(etat))
            self.assertNotIn(secret, cache)
        self.assertIn("***", cache)


class TestMain(Base):
    def test_etat_lit_le_cache_et_n_expose_aucun_secret(self):
        self.lancer(ClientFactice(), SshFactice(), accord=True)
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = plateforme.main(["etat", "--dossier", str(self.dossier)])
        self.assertEqual(code, 0)
        self.assertNotIn(SECRET, sortie.getvalue())
        self.assertTrue(json.loads(sortie.getvalue())["pret"])

    def test_usage_incorrect(self):
        self.assertEqual(plateforme.main(["n_importe_quoi"]), 2)

    def test_ovh_json_absent_donne_un_geste_sans_trace(self):
        with tempfile.TemporaryDirectory() as vide:
            etat = plateforme.installer(vide, False, client=ClientFactice(), ssh=SshFactice())
        self.assertEqual(self.statuts(etat)["lecture"], "bloque")


if __name__ == "__main__":
    unittest.main()
