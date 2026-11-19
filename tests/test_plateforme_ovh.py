"""Opérations OVH sur le serveur dédié (`outils/plateforme_ovh.py`). Le client OVH est simulé."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import ovh_api  # noqa: E402
import plateforme_ovh  # noqa: E402

NOM = "ns1234.ip-1-2-3.eu"
MODELES = {"ovh": ["debian12_64", "ubuntu2204-server_64", "ubuntu2404-server_64", "ubuntu2404-desktop_64",
                   "ubuntu2410-server_64"], "personal": []}


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

    def ecritures(self):
        return [a for a in self.appels if a[0] != "GET"]


class TestPlateformeOvh(unittest.TestCase):
    def test_lire_serveur(self):
        c = ClientFactice({("GET", "/dedicated/server/" + NOM): {
            "os": "ubuntu2204-server_64", "ip": "1.2.3.4", "state": "ok", "commercialRange": "rise"}})
        self.assertEqual(plateforme_ovh.lire_serveur(c, NOM),
                         {"os": "ubuntu2204-server_64", "ip": "1.2.3.4", "etat": "ok", "modele": "rise"})

    def test_modeles_os_aplatit_la_reponse(self):
        c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
        self.assertIn("ubuntu2404-server_64", plateforme_ovh.modeles_os(c, NOM))

    def test_reinstaller_sans_accord_ne_touche_a_rien(self):
        c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
        with self.assertRaises(plateforme_ovh.ErreurAccord):
            plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", "cle", False)
        self.assertEqual(c.appels, [])

    def test_reinstaller_accord_non_booleen_refuse(self):
        for accord in ("False", "0", 0, None, 1, "", "true"):
            c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
            with self.assertRaises(plateforme_ovh.ErreurAccord, msg=repr(accord)):
                plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", "cle", accord)
            self.assertEqual(c.appels, [], repr(accord))

    def test_reinstaller_sans_id_de_tache_message_lisible(self):
        for reponse in (None, {}, {"taskId": "x"}):
            c = ClientFactice({
                ("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES,
                ("POST", f"/dedicated/server/{NOM}/install/start"): reponse,
            })
            with self.assertRaises(ovh_api.ErreurOvh) as e:
                plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", "cle", True)
            self.assertIn("lancée", str(e.exception))

    def test_reinstaller_avec_accord_demande_ubuntu_lts_et_cle(self):
        c = ClientFactice({
            ("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES,
            ("POST", f"/dedicated/server/{NOM}/install/start"): {"taskId": 42},
        })
        modele = plateforme_ovh.choisir_ubuntu_lts(plateforme_ovh.modeles_os(c, NOM))
        self.assertEqual(modele, "ubuntu2404-server_64")
        self.assertEqual(plateforme_ovh.reinstaller(c, NOM, modele, "cle", True), 42)
        methode, chemin, corps = c.ecritures()[0]
        self.assertEqual(chemin, f"/dedicated/server/{NOM}/install/start")
        self.assertEqual(corps["templateName"], "ubuntu2404-server_64")
        self.assertEqual(corps["details"]["sshKeyName"], "cle")

    def test_reinstaller_refuse_un_modele_non_compatible(self):
        c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
        with self.assertRaises(ValueError):
            plateforme_ovh.reinstaller(c, NOM, "windows", "cle", True)
        self.assertEqual(c.ecritures(), [])

    def test_aucun_ubuntu_lts_message_lisible(self):
        with self.assertRaises(ValueError) as e:
            plateforme_ovh.choisir_ubuntu_lts(["debian12_64", "ubuntu2410-server_64"])
        self.assertIn("Ubuntu", str(e.exception))

    def test_cle_enregistree(self):
        c = ClientFactice()
        plateforme_ovh.enregistrer_cle_ssh(c, "cle", "ssh-ed25519 AAA")
        self.assertEqual(c.appels, [("POST", "/me/sshKey", {"keyName": "cle", "key": "ssh-ed25519 AAA"})])

    def test_cle_existante_identique_tolérée(self):
        c = ClientFactice({("POST", "/me/sshKey"): ovh_api.ErreurOvh(409, "existe déjà"),
                           ("GET", "/me/sshKey/cle"): {"keyName": "cle", "key": "ssh-ed25519 AAA"}})
        plateforme_ovh.enregistrer_cle_ssh(c, "cle", "ssh-ed25519 AAA ")

    def test_cle_existante_differente_refusee(self):
        c = ClientFactice({("POST", "/me/sshKey"): ovh_api.ErreurOvh(409, "existe déjà"),
                           ("GET", "/me/sshKey/cle"): {"keyName": "cle", "key": "ssh-ed25519 BBB"}})
        with self.assertRaises(plateforme_ovh.ErreurCleSsh):
            plateforme_ovh.enregistrer_cle_ssh(c, "cle", "ssh-ed25519 AAA")

    def test_etat_tache_traduit_les_statuts_ovh(self):
        for statut, attendu in [("doing", "en_cours"), ("todo", "en_cours"), ("init", "en_cours"),
                                ("done", "fini"), ("error", "echec"), ("cancelled", "echec"),
                                ("customerError", "echec"), ("ovhError", "echec")]:
            c = ClientFactice({("GET", f"/dedicated/server/{NOM}/task/7"): {"status": statut}})
            self.assertEqual(plateforme_ovh.etat_tache(c, NOM, 7), attendu, statut)


if __name__ == "__main__":
    unittest.main()
