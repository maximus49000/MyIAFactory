"""Opérations OVH sur le serveur dédié (`outils/plateforme_ovh.py`). Le client OVH est simulé."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import ovh_api  # noqa: E402
import plateforme_ovh  # noqa: E402

NOM = "ns1234.ip-1-2-3.eu"
CLE = "ssh-ed25519 AAAAFAKEKEY myiafactory"
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
            plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", CLE, False)
        self.assertEqual(c.appels, [])

    def test_reinstaller_accord_non_booleen_refuse(self):
        for accord in ("False", "0", 0, None, 1, "", "true"):
            c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
            with self.assertRaises(plateforme_ovh.ErreurAccord, msg=repr(accord)):
                plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", CLE, accord)
            self.assertEqual(c.appels, [], repr(accord))

    def test_reinstaller_sans_id_de_tache_message_lisible(self):
        for reponse in (None, {}, {"taskId": "x"}):
            c = ClientFactice({
                ("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES,
                ("POST", f"/dedicated/server/{NOM}/reinstall"): reponse,
            })
            with self.assertRaises(ovh_api.ErreurOvh) as e:
                plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", CLE, True)
            self.assertIn("lancée", str(e.exception))

    def test_reinstaller_avec_accord_poste_sur_reinstall_avec_la_cle_publique(self):
        c = ClientFactice({
            ("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES,
            ("POST", f"/dedicated/server/{NOM}/reinstall"): {"taskId": 42},
        })
        modele = plateforme_ovh.choisir_os_cible(plateforme_ovh.modeles_os(c, NOM))
        self.assertEqual(modele, "ubuntu2404-server_64")
        self.assertEqual(plateforme_ovh.reinstaller(c, NOM, modele, CLE + " ", True), 42)
        ecritures = c.ecritures()
        self.assertEqual(len(ecritures), 1)
        methode, chemin, corps = ecritures[0]
        self.assertEqual((methode, chemin), ("POST", f"/dedicated/server/{NOM}/reinstall"))
        self.assertEqual(corps, {"operatingSystem": "ubuntu2404-server_64", "customizations": {"sshKey": CLE}})
        self.assertFalse([a for a in c.appels if "/install/start" in a[1] or "/me/sshKey" in a[1]])

    def test_reinstaller_refuse_un_modele_non_compatible(self):
        c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
        with self.assertRaises(ValueError):
            plateforme_ovh.reinstaller(c, NOM, "windows", CLE, True)
        self.assertEqual(c.ecritures(), [])

    def test_reinstaller_refuse_une_cle_publique_vide(self):
        for cle in ("", "  ", None):
            c = ClientFactice({("GET", f"/dedicated/server/{NOM}/install/compatibleTemplates"): MODELES})
            with self.assertRaises(ValueError, msg=repr(cle)):
                plateforme_ovh.reinstaller(c, NOM, "ubuntu2404-server_64", cle, True)
            self.assertEqual(c.ecritures(), [])

    def test_os_cible_est_ubuntu_2404(self):
        self.assertEqual(plateforme_ovh.OS_CIBLE, "ubuntu2404-server_64")

    def test_os_cible_present_dans_ovh_ou_personal(self):
        self.assertEqual(plateforme_ovh.choisir_os_cible(["debian12_64", "ubuntu2404-server_64", "ubuntu2604-server_64"]),
                         "ubuntu2404-server_64")

    def test_os_cible_absent_message_lisible_sans_reinstaller(self):
        with self.assertRaises(ValueError) as e:
            plateforme_ovh.choisir_os_cible(["debian12_64", "ubuntu2204-server_64", "ubuntu2604-server_64"])
        self.assertIn("ubuntu2404-server_64", str(e.exception))
        self.assertIn("pas tentée", str(e.exception))

    def test_ubuntu_lts_reconnu_22_24_26_seulement(self):
        for os_ in ("ubuntu2204-server_64", "ubuntu2404-server_64", "ubuntu2604-server_64", "Ubuntu2404-Server_64"):
            self.assertTrue(plateforme_ovh.est_ubuntu_lts(os_), os_)
        for os_ in ("ubuntu2410-server_64", "ubuntu2610-server_64", "ubuntu2304-server_64", "debian12_64", "none_64", "", None):
            self.assertFalse(plateforme_ovh.est_ubuntu_lts(os_), repr(os_))

    def test_plus_aucune_trace_de_l_enregistrement_de_cle_chez_ovh(self):
        self.assertFalse(hasattr(plateforme_ovh, "enregistrer_cle_ssh"))
        self.assertFalse(hasattr(plateforme_ovh, "ErreurCleSsh"))

    def test_etat_tache_traduit_les_statuts_ovh(self):
        for statut, attendu in [("doing", "en_cours"), ("todo", "en_cours"), ("init", "en_cours"),
                                ("done", "fini"), ("error", "echec"), ("cancelled", "echec"),
                                ("customerError", "echec"), ("ovhError", "echec")]:
            c = ClientFactice({("GET", f"/dedicated/server/{NOM}/task/7"): {"status": statut}})
            self.assertEqual(plateforme_ovh.etat_tache(c, NOM, 7), attendu, statut)


if __name__ == "__main__":
    unittest.main()
