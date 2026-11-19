"""Machine à états de la plateforme (`outils/plateforme.py`). Client OVH et SSH factices : aucun réseau, aucun ssh réel."""
import io
import json
import os
import sys
import tempfile
import time
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
    def __init__(self, os_="none_64", statut_tache="done", script=None, echec_start=None, sans_tache=False, au_start=None,
                 lecture_echoue=None, modeles_echoue_au=None):
        self.os, self.statut_tache, self.appels, self.corps_reinstall = os_, statut_tache, [], None
        self.lecture_echoue, self.modeles_echoue_au, self.lectures_modeles = lecture_echoue, modeles_echoue_au, 0
        self.script, self.echec_start, self.sans_tache, self.au_start = list(script or []), echec_start, sans_tache, au_start

    def appeler(self, methode, chemin, corps=None):
        self.appels.append((methode, chemin))
        if chemin.endswith("/reinstall"):
            self.corps_reinstall = corps
            if self.echec_start:
                raise self.echec_start
            if self.au_start:
                self.au_start()
            if not self.sans_tache:
                self.os = "ubuntu2404-server_64"
            return {} if self.sans_tache else {"taskId": 7}
        if "/task/" in chemin and self.script:
            v = self.script.pop(0)
            if isinstance(v, Exception):
                raise v
            return {"status": v}
        if chemin == "/dedicated/server/ns1":
            if self.lecture_echoue:
                raise self.lecture_echoue
            return {"os": self.os, "ip": IP, "state": "ok", "commercialRange": "x"}
        if chemin.endswith("/install/compatibleTemplates"):
            self.lectures_modeles += 1
            if self.modeles_echoue_au == self.lectures_modeles:
                raise ErreurOvh(503, "indisponible")
            return {"ovh": ["ubuntu2204-server_64", "ubuntu2404-server_64", "debian12_64"], "personal": []}
        if "/task/" in chemin:
            return {"status": self.statut_tache}
        raise ErreurOvh(404, "inconnu")

    def reinstallations(self):
        return [a for a in self.appels if a[1].endswith("/reinstall")]

    def ecritures(self):
        return [a for a in self.appels if a[0] != "GET"]


class SshFactice:
    def __init__(self, erreur_cle_hote=False, attente=None):
        self.commandes, self.oublies, self.erreur_cle_hote = [], [], erreur_cle_hote
        self.attente, self.attentes, self.cles_generees = attente, 0, 0

    def generer_cle(self, dossier):
        self.cles_generees += 1
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
        self.attentes += 1
        return self.attente(self) if self.attente else True

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
        envois = [c for c, _ in ssh.commandes if 'cat > "$HOME/myiafactory/mise_en_place.sh.$$.tmp"' in c]
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

    def test_cle_hote_changee_sans_reinstallation_bloque_meme_avec_accord(self):
        client = ClientFactice(os_="ubuntu2404-server_64")
        ssh = SshFactice(erreur_cle_hote=True)
        etat = self.lancer(client, ssh, accord=True)
        ssh_ = [e for e in etat["etapes"] if e["id"] == "ssh"][0]
        self.assertEqual(ssh_["statut"], "bloque")
        self.assertEqual(ssh.oublies, [])
        self.assertIn("empreinte", ssh_["detail"])
        self.assertIn("ssh-keygen -R", ssh_["geste"])

    def test_cle_hote_changee_apres_la_reinstallation_de_cette_execution_est_oubliee(self):
        ssh = SshFactice(erreur_cle_hote=True)
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        self.assertEqual(ssh.oublies, [(IP, True)])
        self.assertEqual(self.statuts(etat)["ssh"], "fait")

    def test_cle_hote_changee_apres_une_tache_en_cache_terminee_est_oubliee(self):
        rapports = {"lecture": {"statut": "fait"}, "os": {"statut": "en_cours", "detail": "tâche 7"}}
        (self.dossier / "plateforme.json").write_text(json.dumps({"rapports": rapports, "ip": IP, "tache": 7}), encoding="utf-8")
        ssh = SshFactice(erreur_cle_hote=True)
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), ssh)
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


def _cache(dossier):
    return json.loads((Path(dossier) / "plateforme.json").read_text(encoding="utf-8"))


class TestRobustesse(Base):
    def starts(self, client):
        return len(client.reinstallations())

    def taches(self, client):
        return [a[1] for a in client.appels if "/task/" in a[1]]

    def test_cle_publique_dans_la_reinstallation_et_aucune_autre_ecriture(self):
        client = ClientFactice()
        self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(client.ecritures(), [("POST", "/dedicated/server/ns1/reinstall")])
        self.assertEqual(client.corps_reinstall, {"operatingSystem": "ubuntu2404-server_64", "customizations": {"sshKey": PUB}})
        self.assertFalse([a for a in client.appels if "/me/sshKey" in a[1] or "/install/start" in a[1]])

    def test_sans_accord_aucune_ecriture_chez_ovh_ni_cle_generee(self):
        client, ssh = ClientFactice(), SshFactice()
        self.lancer(client, ssh)
        self.assertEqual(client.ecritures(), [])
        self.assertEqual(ssh.cles_generees, 0)
        self.assertEqual(ssh.commandes, [])

    def test_os_cible_absent_de_la_liste_ovh_ne_reinstalle_pas(self):
        class SansCible(ClientFactice):
            def appeler(self, methode, chemin, corps=None):
                if chemin.endswith("/install/compatibleTemplates"):
                    self.appels.append((methode, chemin))
                    return {"ovh": ["debian12_64", "ubuntu2204-server_64"], "personal": []}
                return super().appeler(methode, chemin, corps)
        client = SansCible()
        etat = self.lancer(client, SshFactice(), accord=True)
        os_ = [e for e in etat["etapes"] if e["id"] == "os"][0]
        self.assertEqual(os_["statut"], "bloque")
        self.assertIn("ubuntu2404-server_64", os_["detail"])
        self.assertEqual(client.ecritures(), [])
        self.assertFalse(_cache(self.dossier).get("demande"))

    def test_tache_non_terminee_bloque_puis_la_relance_reprend_sans_reinstaller(self):
        client = ClientFactice(statut_tache="init")
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.statuts(etat)["os"], "bloque")
        self.assertEqual(_cache(self.dossier)["tache"], 7)
        client.statut_tache = "done"
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.starts(client), 1)
        self.assertEqual(set(self.taches(client)), {"/dedicated/server/ns1/task/7"})
        self.assertTrue(etat["pret"])

    def test_deuxieme_session_en_echec_empeche_le_durcissement(self):
        class Seconde(SshFactice):
            n = 0

            def executer(self, hote, commande, cle, stdin=None, delai=60):
                if commande == "true":
                    Seconde.n += 1
                    if Seconde.n >= 2:
                        return 255, "", "refus"
                return super().executer(hote, commande, cle, stdin, delai)
        ssh = Seconde()
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), ssh)
        self.assertEqual(self.statuts(etat)["durcissement"], "bloque")
        self.assertEqual(ssh.etapes_lancees(), [])

    def test_accord_non_booleen_ne_reinstalle_jamais(self):
        for accord in ("yes", 1, "true"):
            client = ClientFactice()
            etat = plateforme.installer(self.dossier, accord, client=client, ssh=SshFactice(), dormir=lambda s: None)
            self.assertEqual(self.starts(client), 0)
            self.assertEqual(self.statuts(etat)["os"], "bloque")

    def test_verifier_ne_modifie_rien_et_rapporte_l_etat_distant(self):
        client, ssh = ClientFactice(os_="ubuntu2404-server_64"), SshFactice()
        etat = plateforme.verifier(self.dossier, client=client, ssh=ssh, dormir=lambda s: None)
        self.assertEqual(etat["serveur"]["statut"], "fait")
        self.assertEqual(ssh.etapes_lancees(), ["etat"])
        self.assertFalse((self.dossier / "plateforme.json").exists())
        self.assertEqual(self.starts(client), 0)

    def test_verifier_ne_perd_pas_la_tache_et_ne_ouvre_pas_de_seconde_reinstallation(self):
        client = ClientFactice(statut_tache="init")
        self.lancer(client, SshFactice(), accord=True)
        avant = (self.dossier / "plateforme.json").read_bytes()
        plateforme.verifier(self.dossier, client=client, ssh=SshFactice(), dormir=lambda s: None)
        self.assertEqual((self.dossier / "plateforme.json").read_bytes(), avant)
        client.statut_tache = "done"
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.starts(client), 1)
        self.assertEqual(set(self.taches(client)), {"/dedicated/server/ns1/task/7"})
        self.assertTrue(etat["pret"])

    def test_ecriture_du_cache_impossible_apres_la_demande_bloque(self):
        def casser():
            fichier = self.dossier / "plateforme.json"
            fichier.unlink()
            fichier.mkdir()
        client = ClientFactice(au_start=casser)
        etat = self.lancer(client, SshFactice(), accord=True)
        os_ = [e for e in etat["etapes"] if e["id"] == "os"][0]
        self.assertEqual(os_["statut"], "bloque")
        self.assertIn("plateforme.json", os_["detail"])
        self.assertEqual(self.starts(client), 1)
        self.assertEqual(self.statuts(etat)["ssh"], "a_faire")

    def test_ecriture_impossible_avant_la_demande_ne_reinstalle_pas(self):
        (self.dossier / "plateforme.json").mkdir()
        client = ClientFactice()
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.starts(client), 0)
        self.assertEqual(self.statuts(etat)["os"], "bloque")

    def test_identifiant_de_tache_inconnu_bloque_et_la_relance_ne_reinstalle_pas(self):
        client = ClientFactice(sans_tache=True)
        etat = self.lancer(client, SshFactice(), accord=True)
        os_ = [e for e in etat["etapes"] if e["id"] == "os"][0]
        self.assertEqual(os_["statut"], "bloque")
        self.assertIn("espace client OVH", os_["geste"])
        self.assertTrue(_cache(self.dossier)["demande"])
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.starts(client), 1)
        self.assertEqual(self.statuts(etat)["os"], "bloque")

    def test_refus_net_avant_la_requete_efface_la_marque(self):
        for erreur in (ErreurOvh(400, "refusé"), ValueError("modèle incompatible")):
            client = ClientFactice(echec_start=erreur)
            etat = self.lancer(client, SshFactice(), accord=True)
            self.assertEqual(self.statuts(etat)["os"], "bloque")
            self.assertFalse(_cache(self.dossier).get("demande"))

    def test_deux_installations_simultanees_la_seconde_est_refusee(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        client = ClientFactice(os_="ubuntu2404-server_64")
        etat = plateforme.installer(self.dossier, False, client=client, ssh=SshFactice(), vivant=lambda p: True)
        self.assertEqual(self.statuts(etat)["lecture"], "bloque")
        self.assertIn("déjà en cours", etat["etapes"][0]["detail"])
        self.assertEqual(client.appels, [])

    def test_refuse_pendant_une_installation_des_serveurs_de_travail(self):
        (self.dossier / "serveurs-installation.lock").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        client, ssh = ClientFactice(os_="ubuntu2404-server_64"), SshFactice()
        etat = plateforme.installer(self.dossier, False, client=client, ssh=ssh, vivant=lambda p: p == 4242)
        self.assertEqual(self.statuts(etat)["lecture"], "bloque")
        self.assertIn("serveurs", etat["etapes"][0]["detail"].lower())
        self.assertEqual((client.appels, ssh.commandes), ([], []))
        self.assertTrue((self.dossier / "serveurs-installation.lock").exists())     # celui de l'autre reste
        self.assertFalse((self.dossier / "plateforme.lock").exists())               # le nôtre est rendu

    def test_verrou_d_un_processus_mort_repris_et_libere_a_la_fin(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        etat = plateforme.installer(self.dossier, False, client=ClientFactice(os_="ubuntu2404-server_64"),
                                    ssh=SshFactice(), vivant=lambda p: False)
        self.assertTrue(etat["pret"])
        self.assertFalse((self.dossier / "plateforme.lock").exists())

    def test_erreur_ovh_passagere_pendant_l_attente_est_reessayee_et_l_etat_est_en_cours(self):
        client = ClientFactice(script=[ErreurOvh(503, "indisponible"), ErreurOvh(0, "délai"), "init", "doing", "done"])
        vus, pauses = [], []

        def dormir(s):
            pauses.append(s)
            vus.append(self.statuts(_cache(self.dossier)["etat"])["os"] if (self.dossier / "plateforme.json").exists() else None)
        etat = plateforme.installer(self.dossier, True, client=client, ssh=SshFactice(), dormir=dormir)
        self.assertEqual(len(pauses), 4)
        self.assertEqual(vus[0], "en_cours")
        self.assertEqual(self.starts(client), 1)
        self.assertTrue(etat["pret"])

    def test_detail_en_cours_ecrit_avant_l_attente(self):
        details = []

        def dormir(s):
            details.append(_cache(self.dossier)["rapports"]["os"])
        plateforme.installer(self.dossier, True, client=ClientFactice(script=["init", "done"]), ssh=SshFactice(), dormir=dormir)
        self.assertEqual(details[0]["statut"], "en_cours")
        self.assertIn("tâche 7", details[0]["detail"])

    def test_ssh_refuse_pendant_le_redemarrage_se_lit_en_cours(self):
        vus = []

        class Redemarre(SshFactice):
            def executer(self, hote, commande, cle, stdin=None, delai=60):
                if commande == "true" and not vus:
                    return 255, "", "Connection refused"
                return super().executer(hote, commande, cle, stdin, delai)

            def attendre_ssh(inner, hote, cle, delai_total):
                vus.append(_cache(self.dossier)["rapports"]["ssh"]["statut"])
                inner.commandes.append(("true", None))
                vus.append("ok")
                return True
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), Redemarre())
        self.assertEqual(vus[0], "en_cours")
        self.assertEqual(self.statuts(etat)["ssh"], "fait")

    def test_script_envoye_en_octets_identiques_au_fichier_du_depot_sans_retour_chariot(self):
        import functools
        import subprocess
        recus = []

        def runner(args, **kw):
            recus.append((args[-1], kw.get("input")))
            sortie = b""
            if "--etape" in args[-1]:
                etape = args[-1].split("--etape ")[1].split()[0]
                sortie = json.dumps({"etape": etape, "statut": "fait", "detail": "ok"}).encode()
            return subprocess.CompletedProcess(args, 0, stdout=sortie, stderr=b"")

        class Reel(SshFactice):
            executer = staticmethod(lambda hote, commande, cle, stdin=None, delai=60:
                                    plateforme.plateforme_ssh.executer(hote, commande, cle, stdin=stdin, delai=delai, runner=runner))
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), Reel())
        self.assertTrue(etat["pret"])
        envoi = [i for c, i in recus if 'cat > "$HOME/myiafactory/mise_en_place.sh.$$.tmp"' in c][0]
        depot = (Path(plateforme.RACINE_SERVEUR) / "mise_en_place.sh").read_bytes()
        self.assertEqual(envoi, depot.replace(b"\r\n", b"\n"))
        for _, entree in recus:
            if entree is not None:
                self.assertNotIn(b"\r", entree)


class TestScriptDistant(Base):
    def test_script_depose_sous_le_dossier_prive_pas_dans_tmp(self):
        ssh = SshFactice()
        self.lancer(ClientFactice(), ssh, accord=True)
        depot = [c for c, _ in ssh.commandes if 'cat > "$HOME/myiafactory/mise_en_place.sh.$$.tmp"' in c][0]
        self.assertNotIn("/tmp", depot)
        self.assertIn('install -d -m 700 "$HOME/myiafactory"', depot)
        self.assertIn("umask 077", depot)
        self.assertIn('chmod 700 "$HOME/myiafactory/mise_en_place.sh.$$.tmp"', depot)
        self.assertIn('mv -f "$HOME/myiafactory/mise_en_place.sh.$$.tmp" "$HOME/myiafactory/mise_en_place.sh"', depot)
        for c, _ in ssh.commandes:
            if "--etape" in c:
                self.assertIn('bash "$HOME/myiafactory/mise_en_place.sh"', c)
                self.assertNotIn("/tmp", c)


class TestVerrou(Base):
    def verrou(self, vivant=lambda p: False):
        return plateforme._prendre_verrou(self.dossier, vivant)

    def test_verrou_vide_et_recent_est_tenu(self):
        (self.dossier / "plateforme.lock").write_text("", encoding="utf-8")
        self.assertIsNone(self.verrou())
        self.assertTrue((self.dossier / "plateforme.lock").exists())

    def test_verrou_illisible_et_recent_est_tenu(self):
        (self.dossier / "plateforme.lock").write_text("{pas du json", encoding="utf-8")
        self.assertIsNone(self.verrou())

    def test_verrou_vide_et_ancien_est_repris(self):
        f = self.dossier / "plateforme.lock"
        f.write_text("", encoding="utf-8")
        ancien = time.time() - 120
        os.utime(f, (ancien, ancien))
        self.assertEqual(self.verrou(), f)

    def test_verrou_d_un_pid_mort_est_repris_meme_recent(self):
        f = self.dossier / "plateforme.lock"
        f.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        self.assertEqual(self.verrou(lambda p: False), f)

    def test_verrou_d_un_pid_vivant_est_tenu(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        self.assertIsNone(self.verrou(lambda p: True))


class TestProgression(Base):
    def test_etape_distante_ecrite_en_cours_dans_le_cache_avant_son_lancement(self):
        vus = {}

        class Observe(SshFactice):
            def executer(inner, hote, commande, cle, stdin=None, delai=60):
                if "--etape" in commande:
                    etape = commande.split("--etape ")[1].split()[0]
                    r = _cache(self.dossier)["rapports"][etape]
                    vus[etape] = (r["statut"], r["detail"])
                return super().executer(hote, commande, cle, stdin, delai)
        etat = self.lancer(ClientFactice(), Observe(), accord=True)
        self.assertTrue(etat["pret"])
        for etape in ("durcissement", "docker", "images"):
            self.assertEqual(vus[etape][0], "en_cours", etape)
            self.assertTrue(vus[etape][1], etape)
        self.assertEqual(self.statuts(_cache(self.dossier)["etat"])["docker"], "fait")


class TestEmpreinteApresAttente(Base):
    """R-1 : empreinte SSH changée découverte pendant l'attente du redémarrage."""

    class Refuse(SshFactice):
        """Sondes `true` refusées (serveur en train de redémarrer) tant que l'empreinte n'a pas été oubliée."""
        def executer(self, hote, commande, cle, stdin=None, delai=60):
            if commande == "true" and not self.oublies:
                self.commandes.append((commande, stdin))
                return 255, "", "Connection refused"
            return super().executer(hote, commande, cle, stdin, delai)

    @staticmethod
    def attente_empreinte(ssh):
        return True if ssh.oublies else plateforme.plateforme_ssh.CLE_CHANGEE

    def test_reinstallation_de_cette_execution_empreinte_oubliee_une_fois_puis_ssh_fait(self):
        ssh = self.Refuse(attente=self.attente_empreinte)
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        self.assertEqual(ssh.oublies, [(IP, True)])
        self.assertEqual(ssh.attentes, 2)
        self.assertEqual(self.statuts(etat)["ssh"], "fait")
        self.assertTrue(etat["pret"])

    def test_sans_reinstallation_empreinte_changee_bloque_avec_le_bon_message(self):
        ssh = self.Refuse(attente=self.attente_empreinte)
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), ssh, accord=True)
        ssh_ = [e for e in etat["etapes"] if e["id"] == "ssh"][0]
        self.assertEqual(ssh_["statut"], "bloque")
        self.assertEqual(ssh.oublies, [])
        self.assertIn("empreinte", ssh_["detail"])
        self.assertIn("ssh-keygen -R " + IP, ssh_["geste"])
        self.assertNotIn("authorized_keys", ssh_["geste"])

    def test_delai_simple_garde_l_ancien_message(self):
        ssh = self.Refuse(attente=lambda s: False)
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), ssh)
        ssh_ = [e for e in etat["etapes"] if e["id"] == "ssh"][0]
        self.assertEqual(ssh_["statut"], "bloque")
        self.assertIn("ne répond pas en SSH", ssh_["detail"])
        self.assertIn("authorized_keys", ssh_["geste"])
        self.assertEqual(ssh.oublies, [])

    def test_empreinte_encore_changee_apres_l_oubli_ne_boucle_pas(self):
        class Tetue(self.Refuse):
            def executer(inner, hote, commande, cle, stdin=None, delai=60):
                if commande == "true":
                    inner.commandes.append((commande, stdin))
                    return 255, "", "Connection refused"
                return SshFactice.executer(inner, hote, commande, cle, stdin, delai)
        ssh = Tetue(attente=lambda s: plateforme.plateforme_ssh.CLE_CHANGEE)
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        self.assertEqual(self.statuts(etat)["ssh"], "bloque")
        self.assertEqual(len(ssh.oublies), 1)
        self.assertEqual(ssh.attentes, 2)


class TestDemandeAvantEcriture(Base):
    """R-4 : seule une panne prouvée avant le POST efface la marque de demande."""

    def test_get_de_validation_en_panne_efface_la_marque_sans_post(self):
        client = ClientFactice(modeles_echoue_au=2)   # 1re lecture (choix du modèle) ok, 2e (dans reinstaller) en 503
        etat = self.lancer(client, SshFactice(), accord=True)
        os_ = [e for e in etat["etapes"] if e["id"] == "os"][0]
        self.assertEqual(os_["statut"], "bloque")
        self.assertIn("relancez", os_["geste"].lower())
        self.assertEqual(client.reinstallations(), [])
        self.assertFalse(_cache(self.dossier).get("demande"))
        self.assertEqual(self.statuts(etat)["ssh"], "a_faire")

    def test_post_en_echec_incertain_garde_la_marque(self):
        for erreur in (ErreurOvh(0, "délai"), ErreurOvh(502, "passerelle")):
            (self.dossier / "plateforme.json").unlink(missing_ok=True)    # repart d'un cache vierge à chaque cas
            client = ClientFactice(echec_start=erreur)
            etat = self.lancer(client, SshFactice(), accord=True)
            self.assertEqual(self.statuts(etat)["os"], "bloque")
            self.assertTrue(_cache(self.dossier)["demande"], repr(erreur))
            self.assertEqual(len(client.reinstallations()), 1)

    def test_post_refuse_en_4xx_efface_la_marque(self):
        client = ClientFactice(echec_start=ErreurOvh(403, "refusé"))
        self.lancer(client, SshFactice(), accord=True)
        self.assertFalse(_cache(self.dossier).get("demande"))


class TestRepliHorsLigne(Base):
    def semer(self, **extra):
        rapports = {i: {"statut": "fait", "detail": "ancien", "geste": ""} for i in plateforme.ETAPES[:6]}
        (self.dossier / "plateforme.json").write_text(
            json.dumps({"rapports": rapports, "ip": IP, "tache": None, **extra}), encoding="utf-8")

    def test_panne_ovh_ne_degrade_pas_un_serveur_deja_pret(self):
        for erreur in (ErreurOvh(0, "API OVH injoignable"), ErreurOvh(403, "jeton révoqué"), ErreurOvh(500, "panne")):
            self.semer()
            client, ssh = ClientFactice(os_="ubuntu2404-server_64", lecture_echoue=erreur), SshFactice()
            etat = self.lancer(client, ssh, accord=True)
            self.assertTrue(etat["pret"], repr(erreur))
            lecture = [e for e in etat["etapes"] if e["id"] == "lecture"][0]
            self.assertEqual(lecture["statut"], "fait")
            self.assertIn("adresse en cache", lecture["detail"])
            self.assertIn(IP, lecture["detail"])
            self.assertEqual(client.reinstallations(), [])
            self.assertEqual(self.statuts(etat)["os"], "fait")

    def test_detail_du_repli_dit_la_vraie_cause(self):
        attendus = {0: "OVH injoignable", 500: "OVH injoignable", 429: "OVH injoignable",
                    401: "refusé l'accès (jeton/droits)", 403: "refusé l'accès (jeton/droits)",
                    404: "ne connaît pas ce serveur (nom à vérifier)"}
        for code, texte in attendus.items():
            self.semer()
            client = ClientFactice(os_="ubuntu2404-server_64", lecture_echoue=ErreurOvh(code, "x"))
            etat = self.lancer(client, SshFactice())
            self.assertTrue(etat["pret"], code)
            detail = [e for e in etat["etapes"] if e["id"] == "lecture"][0]["detail"]
            self.assertIn(texte, detail, code)
            self.assertIn("adresse en cache", detail, code)
            self.assertIn(IP, detail, code)
        self.semer()
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64", lecture_echoue=ErreurOvh(403, "x")), SshFactice())
        self.assertNotIn("injoignable", [e for e in etat["etapes"] if e["id"] == "lecture"][0]["detail"])

    def test_ovh_json_disparu_ne_degrade_pas_non_plus(self):
        self.semer()
        (self.dossier / "ovh.json").unlink()
        etat = plateforme.installer(self.dossier, False, client=ClientFactice(), ssh=SshFactice(), dormir=lambda s: None)
        self.assertTrue(etat["pret"])

    def test_serveur_neuf_sans_cache_bloque_toujours_sur_la_lecture(self):
        etat = self.lancer(ClientFactice(lecture_echoue=ErreurOvh(403, "refusé")), SshFactice(), accord=True)
        self.assertEqual(self.statuts(etat)["lecture"], "bloque")
        self.assertFalse(etat["pret"])

    def test_pas_de_repli_si_une_etape_n_est_pas_faite_ou_une_tache_est_en_cours(self):
        cas = [{"tache": 7}, {"demande": True}]
        for extra in cas:
            self.semer(**extra)
            etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64", lecture_echoue=ErreurOvh(0, "x")), SshFactice(), accord=True)
            self.assertEqual(self.statuts(etat)["lecture"], "bloque", extra)
        rapports = {i: {"statut": "fait"} for i in plateforme.ETAPES[:4]}
        (self.dossier / "plateforme.json").write_text(json.dumps({"rapports": rapports, "ip": IP}), encoding="utf-8")
        etat = self.lancer(ClientFactice(lecture_echoue=ErreurOvh(0, "x")), SshFactice(), accord=True)
        self.assertEqual(self.statuts(etat)["lecture"], "bloque")

    def test_pas_de_repli_sans_adresse_en_cache(self):
        self.semer()
        cache = _cache(self.dossier)
        cache["ip"] = None
        (self.dossier / "plateforme.json").write_text(json.dumps(cache), encoding="utf-8")
        etat = self.lancer(ClientFactice(lecture_echoue=ErreurOvh(0, "x")), SshFactice())
        self.assertEqual(self.statuts(etat)["lecture"], "bloque")


class TestChangementDeSysteme(Base):
    def semer(self, **extra):
        rapports = {i: {"statut": "fait", "detail": "ancien", "geste": ""} for i in plateforme.ETAPES[:6]}
        (self.dossier / "plateforme.json").write_text(
            json.dumps({"rapports": rapports, "ip": IP, "tache": None, **extra}), encoding="utf-8")

    def apres(self, etat):
        return [self.statuts(etat)[i] for i in ("ssh", "durcissement", "docker", "images")]

    def test_reinstallation_expiree_remet_la_suite_a_faire_puis_tout_est_refait(self):
        self.semer()
        client = ClientFactice(os_="debian12_64", statut_tache="init")
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.statuts(etat)["os"], "bloque")
        self.assertEqual(self.apres(etat), ["a_faire"] * 4)
        cache = self.statuts_cache()
        self.assertEqual([cache[i] for i in ("ssh", "durcissement", "docker", "images")], ["a_faire"] * 4)
        self.assertFalse(etat["pret"])
        client.statut_tache = "done"
        ssh = SshFactice()
        etat = self.lancer(client, ssh, accord=True)
        self.assertEqual(ssh.etapes_lancees(), ["durcissement", "docker", "images"])
        self.assertIn("true", [c for c, _ in ssh.commandes])
        self.assertEqual(len(client.reinstallations()), 1)
        self.assertTrue(etat["pret"])

    def statuts_cache(self):
        return {r: v["statut"] for r, v in json.loads((self.dossier / "plateforme.json").read_text(encoding="utf-8"))["rapports"].items()}

    def test_reprise_normale_saute_les_etapes_faites(self):
        self.semer()
        ssh = SshFactice()
        etat = self.lancer(ClientFactice(os_="ubuntu2404-server_64"), ssh)
        self.assertEqual(ssh.etapes_lancees(), [])
        self.assertTrue(etat["pret"])

    def test_marque_incertaine_remet_la_suite_a_faire(self):
        self.semer(demande=True)
        client = ClientFactice()
        etat = self.lancer(client, SshFactice(), accord=True)
        self.assertEqual(self.statuts(etat)["os"], "bloque")
        self.assertEqual(self.apres(etat), ["a_faire"] * 4)
        self.assertEqual(len(client.reinstallations()), 0)

    def test_blocage_faute_d_accord_remet_la_suite_a_faire(self):
        self.semer()
        etat = self.lancer(ClientFactice(os_="debian12_64"), SshFactice())
        self.assertEqual(self.statuts(etat)["os"], "bloque")
        self.assertEqual(self.apres(etat), ["a_faire"] * 4)


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
