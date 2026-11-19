"""Essai réel : le bureau expose les serveurs distants et leurs capacités (fichiers seulement) et lance la sonde ou
l'installation en arrière-plan. Jamais de vrai `ssh` ni de vrai `ssh-keygen` : un faux ssh et un faux moteur sont injectés."""
import json
import os
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bureau import serveurs as bserveurs
from tests.test_acces import AvecBureauOuvert
from tests.test_serveur import AvecServeur

SECRET = "SECRET-SERVEUR-XYZ-123456"
IDS = ["base", "durcissement", "android-build", "android-emulateur", "unity-cli", "unity-editeur", "session-graphique", "agent"]


class FauxSsh:
    """Un `ssh` de poche : répond à l'accès (`sudo`) et aux sondes (`CAPACITES` : id -> 0 présente, 1 absente)."""
    CHANGEMENT_CLE = "REMOTE HOST IDENTIFICATION HAS CHANGED"

    CHARGE_SORTIE = "load=1.00\ncpu=4\nmemtotal=8000000\nmemlibre=6000000\nconteneurs=2\n"

    def __init__(self, presentes=("base",), accessible=True):
        self.presentes, self.accessible, self.appels = set(presentes), accessible, []

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        self.appels.append((hote, commande))
        if not self.accessible:
            return 255, "", "injoignable"
        if "/proc/loadavg" in (stdin or ""):
            return 0, self.CHARGE_SORTIE, ""
        if "sudo -n" in (stdin or ""):
            return 0, "user=bob\nsudo=0\n", ""
        if "echo" in (stdin or "") and "=0" in (stdin or ""):
            return 0, "".join(f"{i}={'0' if i in self.presentes else '1'}\n" for i in IDS), ""
        return 0, '{"statut": "fait", "detail": "ok"}\n', ""


class FauxKeygen:
    def __init__(self):
        self.appels = []

    def __call__(self, args, **kw):
        self.appels.append(args)
        prive = Path(args[args.index("-f") + 1])
        prive.write_text("PRIVEE", encoding="utf-8")
        Path(str(prive) + ".pub").write_text("ssh-ed25519 AAAAFAUX myiafactory\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class AvecServeurs(AvecServeur):
    def setUp(self):
        super().setUp()
        self.dossier = self.tmp / "secrets"
        self.dossier.mkdir()
        p = mock.patch.object(bserveurs, "DOSSIER", self.dossier)
        p.start()
        self.addCleanup(p.stop)
        self.ssh = FauxSsh()
        self.keygen = FauxKeygen()
        self.appels = []
        self.libre = threading.Event()
        self.srv.travaux_serveurs = bserveurs.Travaux(ssh=self.ssh, installer=self.installer_factice, runner=self.keygen)

    def installer_factice(self, serveur, actions, accord, dossier=None, ssh=None):
        self.appels.append((serveur.id, list(actions), accord))
        self.libre.wait(5)
        return {"capacites": {}, "ok": True, "erreur": None}

    @property
    def travaux(self):
        return self.srv.travaux_serveurs

    def declarer(self, **plus):
        corps = {"nom": "Mon serveur", "hote": "srv.exemple.fr", "utilisateur": "bob", "fournisseur": None, **plus}
        return self.poster("/api/serveurs", corps)

    def poster(self, chemin, corps, entetes=None):
        return self.req("POST", chemin, json.dumps(corps), self.ENT if entetes is None else entetes)

    def ecrire_etat(self, serveur_id="mon-serveur", **statuts):
        (self.dossier / "serveurs-etat.json").write_text(json.dumps({serveur_id: {
            "capacites": {i: {"statut": s, "detail": "", "geste": "", "maj": "x"} for i, s in statuts.items()},
            "installation": {"en_cours": False, "debut": ""}}}), encoding="utf-8")

    def instantane(self):
        return {str(p.relative_to(self.dossier)): p.read_bytes() for p in self.dossier.rglob("*") if p.is_file()}


class TestLecture(AvecServeurs):
    def test_get_serveurs_ne_se_connecte_a_rien(self):
        self.declarer()
        self.ssh.appels.clear()
        with mock.patch("subprocess.run", side_effect=AssertionError("subprocess")):
            r, data = self.req("GET", "/api/serveurs")
        self.assertEqual(r.status, 200)
        self.assertEqual(self.ssh.appels, [])
        s = json.loads(data)["serveurs"][0]
        self.assertEqual((s["id"], s["hote"], s["utilisateur"], s["installation_en_cours"]), ("mon-serveur", "srv.exemple.fr", "bob", False))
        self.assertEqual(set(s["capacites"]), set(IDS))

    def test_get_ne_genere_pas_de_cle(self):
        (self.dossier / "serveurs.json").write_text(json.dumps([{
            "id": "mon-serveur", "nom": "Mon serveur", "hote": "srv.exemple.fr", "utilisateur": "bob",
            "cle": str(self.dossier / "id_ed25519_mon-serveur"), "fournisseur": None}]), encoding="utf-8")
        s = self.json("/api/serveurs")["serveurs"][0]
        self.assertIsNone(s["ligne_cle_publique"])
        self.assertEqual(self.keygen.appels, [])
        self.assertFalse((self.dossier / "id_ed25519_mon-serveur").exists())

    def test_get_serveurs_rejets_visibles(self):
        (self.dossier / "serveurs.json").write_text(json.dumps([
            {"nom": "ok", "hote": "ok.exemple.fr", "utilisateur": "bob", "cle": "k", "fournisseur": None},
            {"nom": "mauvais", "hote": "x.exemple.fr", "utilisateur": "root", "cle": "k", "fournisseur": None}]), encoding="utf-8")
        e = self.json("/api/serveurs")
        self.assertEqual([s["id"] for s in e["serveurs"]], ["ok"])
        self.assertEqual(len(e["rejets"]), 1)
        self.assertIn("entrée 2", e["rejets"][0])

    def test_get_serveurs_etat_degrade_sans_installation_vivante(self):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "en_cours"})
        c = self.json("/api/serveurs")["serveurs"][0]["capacites"]
        self.assertEqual((c["base"]["statut"], c["android-build"]["statut"], c["agent"]["statut"]), ("presente", "inconnue", "inconnue"))

    def test_get_donne_statut_detail_et_geste_de_chaque_capacite(self):
        (self.dossier / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-XYZ-123456", "secret": SECRET,
                                                            "consommateur": "CONSO-XYZ-123456", "serveur": "ns1"}), encoding="utf-8")
        self.declarer()
        (self.dossier / "serveurs-etat.json").write_text(json.dumps({"mon-serveur": {"capacites": {
            "base": {"statut": "presente", "detail": "Constatée par la sonde.", "geste": "", "maj": "x"},
            "android-build": {"statut": "bloque", "detail": "Disque plein " + SECRET, "geste": "Libérez de la place.", "maj": "x"},
            "android-emulateur": {"statut": "a_faire", "detail": "En attente de android-build.", "geste": "", "maj": "x"}},
            "installation": {"en_cours": False, "debut": ""}}}), encoding="utf-8")
        brut = self.req("GET", "/api/serveurs")[1]
        c = json.loads(brut)["serveurs"][0]["capacites"]
        self.assertEqual(set(c), set(IDS))
        self.assertEqual(c["android-build"]["statut"], "bloque")
        self.assertIn("Disque plein", c["android-build"]["detail"])
        self.assertEqual(c["android-build"]["geste"], "Libérez de la place.")
        self.assertEqual(c["android-emulateur"]["statut"], "a_faire")
        self.assertEqual(c["unity-cli"], {"statut": "inconnue", "detail": "", "geste": ""})
        self.assertNotIn(SECRET.encode(), brut)

    def test_get_etat_abime_a_la_main_ne_leve_pas(self):
        self.declarer()
        (self.dossier / "serveurs-etat.json").write_text(json.dumps({"mon-serveur": {"capacites": {
            "base": "presente", "agent": 12, "android-build": {"statut": "en_cours"}, "unity-cli": None}}}), encoding="utf-8")
        r, data = self.req("GET", "/api/serveurs")
        self.assertEqual(r.status, 200)
        c = json.loads(data)["serveurs"][0]["capacites"]
        self.assertEqual((c["base"]["statut"], c["agent"]["statut"], c["android-build"]["statut"]), ("inconnue", "inconnue", "inconnue"))
        self.assertEqual(self.req("GET", "/api/serveurs/lieux?actions=apk")[0].status, 200)

    def test_lieux_serveur_non_permis_si_capacite_bloquee(self):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "bloque"})
        e = self.json("/api/serveurs/lieux?actions=apk,charge")
        self.assertEqual(e["apk"]["serveur"]["permis"], False)
        self.assertEqual(e["apk"]["serveur"]["manque"], ["android-build"])
        self.assertIn("android-build", e["apk"]["serveur"]["raison"])
        self.assertEqual(e["charge"]["serveur"]["permis"], True)

    def test_lieux_permis_quand_tout_est_present(self):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "presente"})
        self.assertEqual(self.json("/api/serveurs/lieux?actions=apk")["apk"]["serveur"]["permis"], True)

    def test_lieux_jamais_permis_si_capacite_bloquee_ou_inconnue(self):
        self.declarer()
        for statut in ("bloque", "inconnue", "absente", "a_faire", "en_cours", "texte-bizarre"):
            with self.subTest(statut=statut):
                self.ecrire_etat(base="presente", **{"android-build": statut, "android-emulateur": statut})
                e = self.json("/api/serveurs/lieux?actions=apk,emulateur")
                self.assertFalse(e["apk"]["serveur"]["permis"])
                self.assertFalse(e["emulateur"]["serveur"]["permis"])
        self.ecrire_etat(base="presente", **{"android-build": "presente", "android-emulateur": "inconnue"})
        e = self.json("/api/serveurs/lieux?actions=emulateur")
        self.assertEqual(e["emulateur"]["serveur"]["manque"], ["android-emulateur"])

    def test_lieux_sans_serveur_ou_sans_etat_ou_action_inconnue(self):
        e = self.json("/api/serveurs/lieux?actions=apk,nimporte")
        self.assertFalse(e["apk"]["serveur"]["permis"])
        self.assertFalse(e["nimporte"]["serveur"]["permis"])
        self.declarer()
        e = self.json("/api/serveurs/lieux?actions=apk")        # jamais sondé : tout est inconnu
        self.assertFalse(e["apk"]["serveur"]["permis"])
        self.assertEqual(self.req("GET", "/api/serveurs/lieux")[0].status, 400)

    def test_lieux_charge_ferme_par_defaut_sans_sonde_reussie(self):
        self.declarer()
        e = self.json("/api/serveurs/lieux?actions=charge")["charge"]["serveur"]      # jamais sondé
        self.assertFalse(e["permis"])
        self.assertEqual(e["manque"], [])
        self.assertIn("jamais sondé", e["raison"])
        self.ssh.accessible = False
        self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.travaux.attendre()
        self.assertFalse(self.json("/api/serveurs/lieux?actions=charge")["charge"]["serveur"]["permis"])   # injoignable
        self.ssh.accessible = True
        self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.travaux.attendre()
        self.assertTrue(self.json("/api/serveurs/lieux?actions=charge")["charge"]["serveur"]["permis"])    # bonne sonde

    def test_lieux_donnent_niveau_et_raison_pour_chaque_lieu(self):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "presente"})
        e = self.json("/api/serveurs/lieux?actions=apk")["apk"]
        self.assertEqual(set(e), {"poste", "github", "serveur"})
        for lieu in e.values():
            self.assertIn(lieu["niveau"], ("recommande", "possible", "deconseille", "indisponible"))
            self.assertTrue(lieu["raison"] or lieu["niveau"] == "recommande")
            self.assertEqual(lieu["fondee_sur"], "regles")        # aucune durée mesurée ici
        self.assertTrue(e["serveur"]["permis"])
        self.assertNotEqual(e["serveur"]["niveau"], "recommande")   # charge du serveur inconnue

    def test_lieux_serveur_non_permis_ou_jamais_sonde_est_indisponible(self):
        self.declarer()
        e = self.json("/api/serveurs/lieux?actions=apk")["apk"]      # jamais sondé
        self.assertFalse(e["serveur"]["permis"])
        self.assertEqual(e["serveur"]["niveau"], "indisponible")
        self.assertTrue(e["serveur"]["raison"])
        self.assertIn(e["poste"]["niveau"], ("possible", "recommande"))
        self.ecrire_etat(base="presente", **{"android-build": "bloque"})
        self.assertEqual(self.json("/api/serveurs/lieux?actions=apk")["apk"]["serveur"]["niveau"], "indisponible")

    def _charge(self, charge):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "presente"})
        tout = json.loads((self.dossier / "serveurs-etat.json").read_text(encoding="utf-8"))
        tout["mon-serveur"]["charge"] = {"maj": time.time(), **charge}
        (self.dossier / "serveurs-etat.json").write_text(json.dumps(tout), encoding="utf-8")
        return self.json("/api/serveurs/lieux?actions=apk")["apk"]["serveur"]

    def test_lieux_serveur_charge_haute_sans_autres_mesures_n_est_que_possible(self):
        e = self._charge({"charge_par_coeur": 0.8, "memoire_libre_ratio": 0.9})
        self.assertEqual((e["niveau"], e["fondee_sur"]), ("possible", "regles"))
        self.assertIn("inconnues", e["raison"])

    def test_lieux_serveur_charge_basse_est_recommande(self):
        e = self._charge({"charge_par_coeur": 0.3, "memoire_libre_ratio": 0.9})
        self.assertEqual((e["niveau"], e["fondee_sur"]), ("recommande", "regles"))

    def test_lieux_charge_illisible_ne_donne_jamais_recommande(self):
        for bad in (float("nan"), float("inf"), -float("inf"), True, "0.1", None, 1e400):
            with self.subTest(bad=bad):
                e = self._charge({"charge_par_coeur": bad, "memoire_libre_ratio": bad})
                self.assertNotEqual(e["niveau"], "recommande")

    def test_nombre_01(self):
        f = bserveurs._nombre_01
        self.assertEqual((f(-3), f(0.4), f(7), f(float("nan")), f(float("inf")), f(True), f("0.2")), (0.0, 0.4, 1.0, None, None, None, None))

    def _ecrire_charge(self, charge):
        tout = json.loads((self.dossier / "serveurs-etat.json").read_text(encoding="utf-8"))
        tout["mon-serveur"]["charge"] = charge
        (self.dossier / "serveurs-etat.json").write_text(json.dumps(tout), encoding="utf-8")

    def test_charge_trop_vieille_ou_sans_date_est_ignoree(self):
        self.declarer()
        for maj in (time.time() - 901, None, "hier", time.time() + 3600):
            with self.subTest(maj=maj):
                self.ecrire_etat(base="presente", **{"android-build": "presente"})
                self._ecrire_charge({"charge_par_coeur": 0.1, "memoire_libre_ratio": 0.9, "maj": maj})
                e = self.json("/api/serveurs/lieux?actions=apk")["apk"]["serveur"]
                self.assertNotEqual(e["niveau"], "recommande")

    def test_charge_recente_avec_horloge_injectee(self):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "presente"})
        self._ecrire_charge({"charge_par_coeur": 0.1, "memoire_libre_ratio": 0.9, "maj": 1000.0})
        for maintenant, attendu in ((1000 + 899, "recommande"), (1000 + 901, "possible")):
            with mock.patch.object(bserveurs, "HORLOGE", lambda m=maintenant: m):
                self.assertEqual(self.json("/api/serveurs/lieux?actions=apk")["apk"]["serveur"]["niveau"], attendu)

    def test_sonder_range_la_charge_lue_par_ssh(self):
        self.declarer()
        self.ssh.appels.clear()
        self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.travaux.attendre()
        charge = json.loads((self.dossier / "serveurs-etat.json").read_text(encoding="utf-8"))["mon-serveur"]["charge"]
        self.assertEqual((charge["charge_par_coeur"], charge["memoire_libre_ratio"], charge["conteneurs_outils"]), (0.25, 0.75, 2))
        self.assertLess(abs(charge["maj"] - time.time()), 60)
        self.assertEqual(len(self.ssh.appels), 2)     # sondes puis charge : l'option ssh injectée atteint la charge

    def test_sonder_serveur_injoignable_ne_garde_aucune_charge_perimee(self):
        self.declarer()
        self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.travaux.attendre()
        self.ssh.accessible = False
        self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.travaux.attendre()
        self.assertNotIn("charge", json.loads((self.dossier / "serveurs-etat.json").read_text(encoding="utf-8"))["mon-serveur"])

    def test_lieux_serveur_recommande_avec_charge_lue_dans_l_etat(self):
        self.declarer()
        self.ecrire_etat(base="presente", **{"android-build": "presente"})
        tout = json.loads((self.dossier / "serveurs-etat.json").read_text(encoding="utf-8"))
        tout["mon-serveur"]["charge"] = {"charge_par_coeur": 0.1, "memoire_libre_ratio": 0.8, "conteneurs_outils": 0, "maj": time.time()}
        (self.dossier / "serveurs-etat.json").write_text(json.dumps(tout), encoding="utf-8")
        e = self.json("/api/serveurs/lieux?actions=apk")["apk"]
        self.assertEqual((e["serveur"]["niveau"], e["serveur"]["fondee_sur"]), ("recommande", "regles"))   # seule charge connue, basse
        tout["mon-serveur"]["charge"] = {"charge_par_coeur": 0.99, "memoire_libre_ratio": 0.8, "maj": time.time()}
        (self.dossier / "serveurs-etat.json").write_text(json.dumps(tout), encoding="utf-8")
        self.assertEqual(self.json("/api/serveurs/lieux?actions=apk")["apk"]["serveur"]["niveau"], "deconseille")

    def test_lieux_action_inconnue_indisponible_partout(self):
        self.declarer()
        e = self.json("/api/serveurs/lieux?actions=nimporte")["nimporte"]
        self.assertEqual({v["niveau"] for v in e.values()}, {"indisponible"})

    def test_lieux_ne_se_connecte_a_rien(self):
        self.declarer()
        self.ssh.appels.clear()
        self.json("/api/serveurs/lieux?actions=apk")
        self.assertEqual(self.ssh.appels, [])


class TestDeclaration(AvecServeurs):
    def test_declarer_cree_le_serveur_et_la_cle(self):
        r, data = self.declarer()
        self.assertEqual(r.status, 201)
        s = json.loads(data)["serveur"]
        self.assertEqual(s["id"], "mon-serveur")
        self.assertTrue(s["ligne_cle_publique"].startswith("ssh-ed25519 "))
        self.assertEqual([x["id"] for x in self.json("/api/serveurs")["serveurs"]], ["mon-serveur"])
        self.assertNotIn(str(self.dossier).encode(), data)      # le chemin de la clé privée n'est pas rendu

    def test_declarer_refuse_root_et_hote_piege_avec_400(self):
        for plus in ({"utilisateur": "root"}, {"hote": "-oProxyCommand=x"}, {"hote": "a b"}, {"hote": "a@b"},
                     {"hote": ""}, {"fournisseur": "inconnu"}):
            with self.subTest(plus=plus):
                r, data = self.declarer(**plus)
                self.assertEqual(r.status, 400)
                self.assertIn("erreur", json.loads(data))
        self.assertFalse((self.dossier / "serveurs.json").exists())
        self.assertEqual(self.keygen.appels, [])

    def test_declarer_ignore_les_champs_en_trop(self):
        r, _ = self.declarer(cle="/etc/passwd", id="autre", reglages_fournisseur={"secret": "x"})
        self.assertEqual(r.status, 201)
        enregistre = json.loads((self.dossier / "serveurs.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(enregistre["id"], "mon-serveur")
        self.assertNotIn("passwd", enregistre["cle"])

    def test_declarer_en_double_400(self):
        self.declarer()
        self.assertEqual(self.declarer()[0].status, 400)

    def test_declarer_refuse_409_pendant_une_operation(self):
        self.declarer()
        self.poster("/api/serveurs/mon-serveur/installer", {"actions": ["apk"], "accord": True})
        try:
            r, data = self.declarer(nom="Autre", hote="autre.exemple.fr")
            self.assertEqual(r.status, 409)
            self.assertIn("erreur", json.loads(data))
        finally:
            self.libre.set()
            self.travaux.attendre()
        self.assertEqual([x["id"] for x in self.json("/api/serveurs")["serveurs"]], ["mon-serveur"])
        self.assertEqual(self.declarer(nom="Autre", hote="autre.exemple.fr")[0].status, 201)

    def test_declarer_refuse_409_pendant_une_migration(self):
        with mock.patch.object(bserveurs.Travaux, "en_cours", return_value=True):
            r, _ = self.declarer()
        self.assertEqual(r.status, 409)
        self.assertFalse((self.dossier / "serveurs.json").exists())

    def test_declarer_corps_trop_gros_ou_sans_en_tete(self):
        gros = {"nom": "x" * 3000, "hote": "a.fr", "utilisateur": "bob"}
        self.assertEqual(self.poster("/api/serveurs", gros)[0].status, 400)
        self.assertEqual(self.poster("/api/serveurs", {}, {"Content-Type": "application/json"})[0].status, 403)
        self.assertEqual(self.poster("/api/serveurs", {}, {"X-Bureau": "1", "Content-Type": "text/plain"})[0].status, 403)


class TestInstallation(AvecServeurs):
    def setUp(self):
        super().setUp()
        self.declarer()
        self.chemin = "/api/serveurs/mon-serveur/installer"

    def test_installer_sans_en_tete_bureau_refuse(self):
        r, _ = self.poster(self.chemin, {"actions": ["apk"], "accord": True}, {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.appels, [])

    def test_installer_refuse_409_pendant_l_installation_de_la_plateforme(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        r, data = self.poster(self.chemin, {"actions": ["apk"], "accord": True})
        self.assertEqual(r.status, 409)
        self.assertIn("plateforme", json.loads(data)["erreur"].lower())
        self.travaux.attendre()
        self.assertEqual(self.appels, [])

    def test_installer_accord_non_booleen_ne_lance_rien(self):
        for corps in ({"actions": ["apk"]}, {"actions": ["apk"], "accord": "true"}, {"actions": ["apk"], "accord": 1},
                      {"actions": ["apk"], "accord": False}, {"actions": ["apk"], "accord": None},
                      {"actions": ["apk"], "accord": [True]}):
            with self.subTest(corps=corps):
                r, _ = self.poster(self.chemin, corps)
                self.assertEqual(r.status, 400)
        self.travaux.attendre()
        self.assertEqual(self.appels, [])

    def test_installer_accord_verifie_avant_de_demarrer_le_fil(self):
        with mock.patch.object(bserveurs.Travaux, "lancer") as lancer, \
                mock.patch.object(bserveurs.Travaux, "installer") as installer:
            r, _ = self.poster(self.chemin, {"actions": ["apk"], "accord": "oui"})
        self.assertEqual(r.status, 400)
        lancer.assert_not_called()
        installer.assert_not_called()
        self.assertFalse(self.travaux.en_cours())

    def test_cles_dupliquees_refusees_sans_appel_moteur(self):
        brut = '{"actions": ["apk"], "accord": false, "accord": true}'
        for chemin in (self.chemin, "/api/serveurs/mon-serveur/apercu", "/api/serveurs/mon-serveur/sonder", "/api/serveurs"):
            with self.subTest(chemin=chemin):
                r, _ = self.req("POST", chemin, brut, self.ENT)
                self.assertEqual(r.status, 400)
        r, _ = self.req("POST", self.chemin, '{"actions": [{"a": 1, "a": 2}], "accord": true}', self.ENT)
        self.assertEqual(r.status, 400)
        self.travaux.attendre()
        self.assertEqual(self.appels, [])
        self.assertEqual(self.ssh.appels, [])

    def test_erreur_d_un_serveur_disparu_n_est_plus_listee(self):
        self.travaux.erreurs["fantome"] = "vieille erreur"
        self.json("/api/serveurs")
        self.assertNotIn("fantome", self.travaux.erreurs)

    def test_installer_actions_invalides_400(self):
        for corps in ({"accord": True}, {"actions": [], "accord": True}, {"actions": "apk", "accord": True},
                      {"actions": [1], "accord": True}, {"actions": ["nimporte"], "accord": True}):
            with self.subTest(corps=corps):
                self.assertEqual(self.poster(self.chemin, corps)[0].status, 400)
        self.assertEqual(self.appels, [])

    def test_installer_lance_le_moteur_avec_accord(self):
        r, data = self.poster(self.chemin, {"actions": ["apk"], "accord": True})
        self.assertEqual((r.status, json.loads(data)), (202, {"demarre": True}))
        self.assertTrue(self.json("/api/serveurs")["serveurs"][0]["installation_en_cours"])
        self.libre.set()
        self.travaux.attendre()
        self.assertEqual(self.appels, [("mon-serveur", ["apk"], True)])
        self.assertFalse(self.json("/api/serveurs")["serveurs"][0]["installation_en_cours"])

    def test_sonde_en_cours_est_exposee_pendant_la_sonde_seulement(self):
        import threading
        from types import SimpleNamespace
        libre = threading.Event()
        self.assertFalse(self.json("/api/serveurs")["serveurs"][0]["sonde_en_cours"])
        self.assertTrue(self.travaux.lancer("sonder", SimpleNamespace(id="mon-serveur"), lambda: libre.wait(10) and None))
        e = self.json("/api/serveurs")["serveurs"][0]
        self.assertTrue(e["sonde_en_cours"])
        self.assertFalse(e["installation_en_cours"])
        libre.set()
        self.travaux.attendre()
        self.assertFalse(self.json("/api/serveurs")["serveurs"][0]["sonde_en_cours"])

    def test_installer_deuxieme_lancement_409(self):
        self.assertEqual(self.poster(self.chemin, {"actions": ["apk"], "accord": True})[0].status, 202)
        self.assertEqual(self.poster(self.chemin, {"actions": ["apk"], "accord": True})[0].status, 409)
        self.assertEqual(self.poster("/api/serveurs/mon-serveur/sonder", {})[0].status, 409)
        self.libre.set()
        self.travaux.attendre()
        self.assertEqual(self.poster(self.chemin, {"actions": ["apk"], "accord": True})[0].status, 202)
        self.travaux.attendre()
        self.assertEqual(len(self.appels), 2)

    def test_installer_409_si_une_installation_d_un_autre_processus_tourne(self):
        (self.dossier / "serveurs-installation.lock").write_text("", encoding="utf-8")     # verrou tout juste créé : tenu
        r, _ = self.poster(self.chemin, {"actions": ["apk"], "accord": True})
        self.assertEqual(r.status, 409)
        self.assertEqual(self.appels, [])

    def test_erreur_installation_du_fil_est_exposee_masquee(self):
        import serveur_installation

        def refuse(serveur, actions, accord, dossier=None, ssh=None):
            raise serveur_installation.ErreurInstallation(f"Accès refusé avec {SECRET}", "Corrigez l'accès.")
        self.srv.travaux_serveurs = bserveurs.Travaux(ssh=self.ssh, installer=refuse, runner=self.keygen)
        (self.dossier / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-XYZ-123456", "secret": SECRET,
                                                            "consommateur": "CONSO-XYZ-123456", "serveur": "ns1"}), encoding="utf-8")
        self.assertEqual(self.poster(self.chemin, {"actions": ["apk"], "accord": True})[0].status, 202)
        self.travaux.attendre()
        r, data = self.req("GET", "/api/serveurs")
        e = json.loads(data)["serveurs"][0]
        self.assertIn("Accès refusé", e["erreur"])
        self.assertIn("Corrigez l'accès.", e["erreur"])
        self.assertNotIn(SECRET.encode(), data)

    def test_exception_du_fil_masquee_puis_effacee_au_run_suivant(self):
        def casse(serveur, actions, accord, dossier=None, ssh=None):
            raise RuntimeError(SECRET)
        self.srv.travaux_serveurs = bserveurs.Travaux(ssh=self.ssh, installer=casse, runner=self.keygen)
        self.poster(self.chemin, {"actions": ["apk"], "accord": True})
        self.travaux.attendre()
        r, data = self.req("GET", "/api/serveurs")
        self.assertNotIn(SECRET.encode(), data)
        self.assertIn("interrompue", json.loads(data)["serveurs"][0]["erreur"])
        self.travaux._installer = self.installer_factice
        self.poster(self.chemin, {"actions": ["apk"], "accord": True})
        self.assertNotIn("erreur", self.json("/api/serveurs")["serveurs"][0])
        self.libre.set()
        self.travaux.attendre()

    def test_erreur_rendue_par_le_moteur_est_exposee(self):
        self.travaux._installer = lambda *a, **k: {"capacites": {}, "ok": False, "erreur": "Serveur injoignable : rien n'a été installé."}
        self.poster(self.chemin, {"actions": ["apk"], "accord": True})
        self.travaux.attendre()
        self.assertIn("injoignable", self.json("/api/serveurs")["serveurs"][0]["erreur"])


class TestIdentifiants(AvecServeurs):
    def setUp(self):
        super().setUp()
        self.declarer()

    def test_id_inconnu_donne_404(self):
        for action, corps in (("sonder", {}), ("apercu", {"actions": ["apk"]}), ("installer", {"actions": ["apk"], "accord": True})):
            with self.subTest(action=action):
                self.assertEqual(self.poster(f"/api/serveurs/inconnu/{action}", corps)[0].status, 404)
        self.assertEqual(self.ssh.appels, [])
        self.assertEqual(self.appels, [])

    def test_id_avec_chemin_est_refuse(self):
        for ident in ("..%2Fetc", "%2e%2e", "mon-serveur%2F..%2Fx", "a%00b", "..", "mon-serveur%20", "MON-SERVEUR"):
            with self.subTest(ident=ident):
                r, _ = self.poster(f"/api/serveurs/{ident}/sonder", {})
                self.assertEqual(r.status, 404)
        self.assertEqual(self.poster("/api/serveurs/a/b/sonder", {})[0].status, 404)
        self.assertEqual(self.ssh.appels, [])
        self.assertEqual(sorted(self.instantane()), ["id_ed25519_mon-serveur", "id_ed25519_mon-serveur.pub", "serveurs.json"])


class TestSondeEtApercu(AvecServeurs):
    def setUp(self):
        super().setUp()
        self.declarer()

    def test_sonde_ecrit_l_etat(self):
        self.ssh.presentes = {"base", "android-build"}
        r, data = self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.assertEqual((r.status, json.loads(data)), (202, {"demarre": True}))
        self.travaux.attendre()
        c = self.json("/api/serveurs")["serveurs"][0]["capacites"]
        self.assertEqual((c["base"]["statut"], c["android-build"]["statut"], c["agent"]["statut"]), ("presente", "presente", "absente"))
        self.assertNotIn("erreur", self.json("/api/serveurs")["serveurs"][0])

    def test_sonde_serveur_injoignable_inconnue_et_erreur(self):
        self.ssh.accessible = False
        self.poster("/api/serveurs/mon-serveur/sonder", {})
        self.travaux.attendre()
        e = self.json("/api/serveurs")["serveurs"][0]
        self.assertEqual({v["statut"] for v in e["capacites"].values()}, {"inconnue"})
        self.assertIn("injoignable", e["erreur"])

    def test_apercu_ne_modifie_rien(self):
        self.ssh.presentes = {"base"}
        avant = self.instantane()
        r, data = self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["apk"]})
        self.assertEqual(r.status, 200)
        a = json.loads(data)
        self.assertEqual(a["manquantes"], ["android-build"])
        self.assertEqual(self.instantane(), avant)
        self.assertEqual(self.appels, [])
        self.assertFalse(any("mise_en_place" in c for _, c in self.ssh.appels))

    def test_apercu_action_inconnue_400_et_serveur_injoignable_sans_secret(self):
        self.assertEqual(self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["nimporte"]})[0].status, 400)
        self.ssh.accessible = False
        r, data = self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["apk"]})
        self.assertEqual(r.status, 200)
        self.assertIn("erreur", json.loads(data))
        self.assertNotIn(str(self.dossier / "id_ed25519_mon-serveur").encode(), data)

    def test_sonde_avec_verrou_tenu_n_ecrit_rien_et_erreur_masquee(self):
        import serveur_installation
        avant = self.instantane()
        self.assertTrue(serveur_installation._VERROU_PROCESSUS.acquire(blocking=False))
        try:
            self.poster("/api/serveurs/mon-serveur/sonder", {})
            self.travaux.attendre()
        finally:
            serveur_installation._VERROU_PROCESSUS.release()
        self.assertEqual(self.instantane(), avant)
        self.assertIn("déjà en cours", self.json("/api/serveurs")["serveurs"][0]["erreur"])

    def test_enregistrer_sonde_refuse_si_verrou_tenu(self):
        import serveur_installation as si
        serveur = bserveurs._modules()[4].lire_avec_rejets(self.dossier)[0][0]
        self.assertTrue(si._VERROU_PROCESSUS.acquire(blocking=False))
        try:
            with self.assertRaises(si.ErreurInstallation) as c:
                si.enregistrer_sonde(self.dossier, serveur, {"base": "presente"})
        finally:
            si._VERROU_PROCESSUS.release()
        self.assertIn("déjà en cours", str(c.exception))
        (self.dossier / si.VERROU).write_text("", encoding="utf-8")        # verrou fichier tout jeune
        with self.assertRaises(si.ErreurInstallation):
            si.enregistrer_sonde(self.dossier, serveur, {"base": "presente"})
        (self.dossier / si.VERROU).unlink()
        si.enregistrer_sonde(self.dossier, serveur, {"base": "presente"})
        self.assertFalse((self.dossier / si.VERROU).exists())               # verrou rendu
        self.assertEqual(si.lire_etat(self.dossier)["mon-serveur"]["capacites"]["base"]["statut"], "presente")

    def test_sonde_garde_la_raison_d_une_capacite_non_installable_bloquee(self):
        import serveur_capacites as sc
        import serveur_installation as si
        serveur = bserveurs._modules()[4].lire_avec_rejets(self.dossier)[0][0]
        ni = next(i for i, c in sc.CATALOGUE.items() if not c.installable)
        (self.dossier / si.ETAT).write_text(json.dumps({"mon-serveur": {"capacites": {
            ni: {"statut": "bloque", "detail": "Licence à accepter à la main.", "geste": "g", "maj": "x"}},
            "installation": {"en_cours": False, "debut": ""}}}), encoding="utf-8")
        si.enregistrer_sonde(self.dossier, serveur, {ni: "absente", "base": "presente"})
        e = si.lire_etat(self.dossier)["mon-serveur"]["capacites"]
        self.assertEqual((e[ni]["statut"], e[ni]["detail"]), ("bloque", "Licence à accepter à la main."))
        self.assertEqual(e["base"]["statut"], "presente")

    def test_apercu_limite_de_concurrence_409(self):
        bloque = threading.Event()
        self.addCleanup(bloque.set)
        self.travaux._ssh = SimpleNamespace(executer=lambda *a, **k: (bloque.wait(5), (0, "", ""))[1], CHANGEMENT_CLE="x")
        serveur = bserveurs._modules()[4].lire_avec_rejets(self.dossier)[0][0]
        for _ in range(2):
            self.assertIsNone(self.travaux.apercu(serveur, ["apk"], self.dossier, delai=0.05))
        r, data = self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["apk"]})
        self.assertEqual(r.status, 409)
        self.assertIn("erreur", json.loads(data))
        bloque.set()
        for _ in range(100):
            if self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["apk"]})[0].status != 409:
                break
            threading.Event().wait(0.05)
        else:
            self.fail("la limite n'a pas été relâchée")

    def test_apercu_delai_depasse_504_http(self):
        bloque = threading.Event()
        self.addCleanup(bloque.set)
        self.travaux._ssh = SimpleNamespace(executer=lambda *a, **k: (bloque.wait(5), (0, "", ""))[1], CHANGEMENT_CLE="x")
        with mock.patch.object(bserveurs, "DELAI_APERCU_S", 0.05):
            r, data = self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["apk"]})
        self.assertEqual(r.status, 504)
        self.assertIn("erreur", json.loads(data))

    def test_apercu_exception_inattendue_500_masque(self):
        with mock.patch.object(bserveurs.Travaux, "apercu", side_effect=RuntimeError(SECRET)):
            r, data = self.poster("/api/serveurs/mon-serveur/apercu", {"actions": ["apk"]})
        self.assertEqual(r.status, 500)
        self.assertNotIn(SECRET.encode(), data)
        self.assertNotIn(b"RuntimeError", data)
        self.assertIn("erreur", json.loads(data))

    def test_apercu_borne_dans_le_temps(self):
        bloque = threading.Event()
        self.addCleanup(bloque.set)
        self.travaux._ssh = SimpleNamespace(executer=lambda *a, **k: (bloque.wait(5), (0, "", ""))[1], CHANGEMENT_CLE="x")
        self.assertIsNone(self.travaux.apercu(next(iter(bserveurs._modules()[4].lire(self.dossier))), ["apk"], self.dossier, delai=0.05))


class TestReponsesSansSecret(AvecServeurs):
    def test_reponses_sans_secret(self):
        (self.dossier / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-XYZ-123456", "secret": SECRET,
                                                            "consommateur": "CONSO-XYZ-123456", "serveur": "ns1"}), encoding="utf-8")
        r, data = self.declarer(nom=f"serveur {SECRET}")
        self.assertEqual(r.status, 201)
        self.assertNotIn(SECRET.encode(), data)
        for chemin in ("/api/serveurs", "/api/serveurs/lieux?actions=apk"):
            self.assertNotIn(SECRET.encode(), self.req("GET", chemin)[1])
        self.assertNotIn(str(self.dossier / "id_ed25519").encode(), self.req("GET", "/api/serveurs")[1])
        ident = json.loads(self.req("GET", "/api/serveurs")[1])["serveurs"][0]["id"]
        self.ssh.accessible = False
        r, data = self.poster(f"/api/serveurs/{ident}/apercu", {"actions": ["apk"]})
        self.assertEqual(r.status, 200)
        self.assertNotIn(SECRET.encode(), data)


def installer_ovh(dossier, ip="203.0.113.9"):
    """Les anciens fichiers du flux OVH (valeurs factices)."""
    (dossier / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": SECRET, "secret": SECRET + "2",
                                                  "consommateur": SECRET + "3", "serveur": "ns000.ip-1-2-3.eu"}), encoding="utf-8")
    (dossier / "plateforme.json").write_text(json.dumps({"ip": ip}), encoding="utf-8")
    (dossier / "id_ed25519_myiafactory").write_text("PRIVATE-KEY-CONTENT-ABCDEF", encoding="utf-8")


class TestMigration(AvecServeurs):
    def setUp(self):
        super().setUp()
        installer_ovh(self.dossier)

    def test_get_migration_sans_fichiers_donne_null(self):
        for p in self.dossier.iterdir():
            p.unlink()
        r, data = self.req("GET", "/api/serveurs/migration")
        self.assertEqual((r.status, json.loads(data)), (200, {"proposition": None}))

    def test_get_migration_propose_sans_secret_ni_connexion_ni_ecriture(self):
        avant = self.instantane()
        r, data = self.req("GET", "/api/serveurs/migration")
        self.assertEqual(r.status, 200)
        p = json.loads(data)["proposition"]
        self.assertEqual((p["serveur"]["hote"], p["serveur"]["utilisateur"], p["serveur"]["fournisseur"]),
                         ("203.0.113.9", "ubuntu", "ovh"))
        self.assertEqual(sorted(p["source"]), ["id_ed25519_myiafactory", "ovh.json", "plateforme.json"])
        for secret in (SECRET.encode(), b"PRIVATE-KEY-CONTENT"):
            self.assertNotIn(secret, data)
        self.assertEqual(self.ssh.appels, [])
        self.assertEqual(self.instantane(), avant)

    def test_get_migration_null_si_un_serveur_est_deja_declare(self):
        self.declarer()
        self.assertEqual(json.loads(self.req("GET", "/api/serveurs/migration")[1]), {"proposition": None})

    def test_apercu_migration_lit_sans_rien_ecrire(self):
        self.ssh.presentes = {"base", "android-build"}
        avant = self.instantane()
        r, data = self.poster("/api/serveurs/migration/apercu", {})
        self.assertEqual(r.status, 200)
        a = json.loads(data)
        self.assertEqual(a["capacites"]["android-build"], "presente")
        self.assertEqual(a["capacites"]["android-emulateur"], "absente")
        self.assertTrue(self.ssh.appels)
        self.assertEqual(self.instantane(), avant)
        self.assertNotIn(SECRET.encode(), data)

    def test_apercu_migration_injoignable_donne_inconnue(self):
        self.ssh.accessible = False
        r, data = self.poster("/api/serveurs/migration/apercu", {})
        self.assertEqual(r.status, 200)
        self.assertEqual(set(json.loads(data)["capacites"].values()), {"inconnue"})

    def test_apercu_migration_rien_a_migrer_404(self):
        self.declarer()
        self.assertEqual(self.poster("/api/serveurs/migration/apercu", {})[0].status, 404)

    def test_apercu_migration_limite_de_concurrence_409(self):
        for _ in range(bserveurs.MAX_APERCUS):
            self.assertTrue(self.travaux._places_apercu.acquire(blocking=False))
        r, data = self.poster("/api/serveurs/migration/apercu", {})
        self.assertEqual(r.status, 409)
        self.assertIn("erreur", json.loads(data))

    def test_apercu_migration_delai_depasse_504(self):
        bloque = threading.Event()
        self.addCleanup(bloque.set)
        self.travaux._ssh = SimpleNamespace(executer=lambda *a, **k: (bloque.wait(5), (0, "", ""))[1], CHANGEMENT_CLE="x")
        with mock.patch.object(bserveurs, "DELAI_APERCU_S", 0.05):
            self.assertEqual(self.poster("/api/serveurs/migration/apercu", {})[0].status, 504)

    def test_apercu_migration_exception_500_masquee(self):
        with mock.patch("serveur_migration.apercu", side_effect=RuntimeError(SECRET)):
            r, data = self.poster("/api/serveurs/migration/apercu", {})
        self.assertEqual(r.status, 500)
        self.assertNotIn(SECRET.encode(), data)
        self.assertNotIn(b"RuntimeError", data)

    def test_confirmer_sans_accord_exact_n_ecrit_rien(self):
        avant = self.instantane()
        for corps in ({}, {"accord": False}, {"accord": "true"}, {"accord": 1}, {"accord": [True]}, {"accord": None}):
            with self.subTest(corps=corps):
                r, data = self.poster("/api/serveurs/migration/confirmer", corps)
                self.assertEqual(r.status, 400)
                self.assertIn("erreur", json.loads(data))
                self.assertEqual(self.instantane(), avant)
        self.assertEqual(self.ssh.appels, [])

    def test_confirmer_cles_dupliquees_refusees(self):
        avant = self.instantane()
        r, _ = self.req("POST", "/api/serveurs/migration/confirmer", '{"accord": false, "accord": true}', self.ENT)
        self.assertEqual(r.status, 400)
        self.assertEqual(self.instantane(), avant)

    def test_confirmer_en_tetes_manquants_refuse(self):
        self.assertEqual(self.poster("/api/serveurs/migration/confirmer", {"accord": True}, {"Content-Type": "application/json"})[0].status, 403)
        self.assertEqual(self.poster("/api/serveurs/migration/confirmer", {"accord": True}, {"X-Bureau": "1"})[0].status, 403)
        self.assertFalse((self.dossier / "serveurs.json").exists())

    def test_confirmer_declare_le_serveur_puis_refuse_409(self):
        self.ssh.presentes = {"base"}
        ovh_avant = (self.dossier / "ovh.json").read_bytes()
        r, data = self.poster("/api/serveurs/migration/confirmer", {"accord": True})
        self.assertEqual(r.status, 200)
        fiche = json.loads(data)["serveur"]
        self.assertEqual((fiche["hote"], fiche["fournisseur"], fiche["capacites"]["base"]["statut"]), ("203.0.113.9", "ovh", "presente"))
        self.assertNotIn(b"PRIVATE-KEY-CONTENT", data)
        serveurs = bserveurs._modules()[4].lire(self.dossier)
        self.assertEqual([s.hote for s in serveurs], ["203.0.113.9"])
        self.assertEqual((self.dossier / "ovh.json").read_bytes(), ovh_avant)     # intact
        r, data = self.poster("/api/serveurs/migration/confirmer", {"accord": True})
        self.assertEqual(r.status, 409)
        self.assertIn("déjà déclaré", json.loads(data)["erreur"])
        self.assertEqual(len(bserveurs._modules()[4].lire(self.dossier)), 1)

    def test_confirmer_installation_en_cours_409_sans_ecriture(self):
        with mock.patch.object(bserveurs._modules()[3], "installation_en_cours", return_value=True):
            r, _ = self.poster("/api/serveurs/migration/confirmer", {"accord": True})
        self.assertEqual(r.status, 409)
        self.assertFalse((self.dossier / "serveurs.json").exists())

    def test_confirmer_exception_500_masquee(self):
        with mock.patch("serveur_migration.confirmer", side_effect=RuntimeError(SECRET)):
            r, data = self.poster("/api/serveurs/migration/confirmer", {"accord": True})
        self.assertEqual(r.status, 500)
        self.assertNotIn(SECRET.encode(), data)

    def test_confirmer_rejoue_pendant_un_premier_lent_est_refuse(self):
        bloque = threading.Event()
        self.addCleanup(bloque.set)
        self.travaux._ssh = SimpleNamespace(executer=lambda *a, **k: (bloque.wait(5), (0, "", ""))[1], CHANGEMENT_CLE="x")
        with mock.patch.object(bserveurs, "DELAI_APERCU_S", 0.05):
            self.assertEqual(self.poster("/api/serveurs/migration/confirmer", {"accord": True})[0].status, 504)
        self.assertTrue(self.travaux.en_cours())               # la migration en fond compte
        self.assertEqual(self.poster("/api/serveurs/migration/confirmer", {"accord": True})[0].status, 409)
        bloque.set()
        self.travaux.attendre_migration(5)
        self.assertFalse(self.travaux.en_cours())
        self.assertEqual(len(bserveurs._modules()[4].lire(self.dossier)), 1)       # exactement une inscription

    def test_une_migration_en_cours_bloque_sonder_et_installer(self):
        (self.dossier / "serveurs.json").unlink(missing_ok=True)
        self.declarer()
        bloque = threading.Event()
        self.addCleanup(bloque.set)
        fil = threading.Thread(target=lambda: self.travaux.migration(lambda: bloque.wait(5), delai=0.01))
        fil.start()
        fil.join(5)
        self.assertTrue(self.travaux.en_cours())
        self.assertEqual(self.poster("/api/serveurs/mon-serveur/sonder", {})[0].status, 409)
        self.assertEqual(self.poster("/api/serveurs/mon-serveur/installer", {"actions": ["apk"], "accord": True})[0].status, 409)
        bloque.set()

    def test_proposition_illisible_donne_400_et_pas_409(self):
        with mock.patch("serveur_migration.detecter", return_value={"serveur": 12, "source": []}):
            r, _ = self.poster("/api/serveurs/migration/confirmer", {"accord": True})
        self.assertEqual(r.status, 400)

    def test_migration_ne_prend_jamais_la_place_d_un_serveur_nomme_migration(self):
        # « migration » n'est pas un identifiant de serveur utilisable pour les routes /api/serveurs/<id>/...
        r, data = self.declarer(nom="Migration")
        self.assertEqual(r.status, 400)


class TestMigrationDistante(AvecBureauOuvert):
    def test_routes_migration_distantes_404_et_aucune_ecriture(self):
        cookie = self.associer()
        ent = {"Cookie": cookie, "Origin": f"http://127.0.0.1:{self.distant}", "X-Bureau": "1",
               "Content-Type": "application/json"}
        d = self.tmp / "secrets-distant"
        d.mkdir()
        installer_ovh(d)
        p = mock.patch.object(bserveurs, "DOSSIER", d)
        p.start()
        self.addCleanup(p.stop)
        avant = sorted(x.name for x in d.iterdir())
        for chemin in ("/api/serveurs/migration/apercu", "/api/serveurs/migration/confirmer"):
            r, _ = self.req("POST", chemin, json.dumps({"accord": True}), ent)
            self.assertEqual(r.status, 404)
        self.assertEqual(sorted(x.name for x in d.iterdir()), avant)


class TestEcouteurDistant(AvecBureauOuvert):
    def test_route_distante_404(self):
        cookie = self.associer()
        ent = {"Cookie": cookie, "Origin": f"http://127.0.0.1:{self.distant}", "X-Bureau": "1",
               "Content-Type": "application/json"}
        appels = []
        self.srv.travaux_serveurs = bserveurs.Travaux(installer=lambda *a, **k: appels.append(a))
        d = self.tmp / "secrets-distant"
        d.mkdir()
        (d / "serveurs.json").write_text(json.dumps([{
            "id": "x", "nom": "X", "hote": "srv.exemple.fr", "utilisateur": "bob",
            "cle": str(d / "id_ed25519_x"), "fournisseur": None}]), encoding="utf-8")
        p = mock.patch.object(bserveurs, "DOSSIER", d)
        p.start()
        self.addCleanup(p.stop)
        self.assertEqual([s.id for s in bserveurs._modules()[4].lire_avec_rejets(d)[0]], ["x"])   # le serveur existe bien
        for chemin, corps in (("/api/serveurs", {"nom": "n", "hote": "a.fr", "utilisateur": "bob"}),
                              ("/api/serveurs/x/sonder", {}), ("/api/serveurs/x/apercu", {"actions": ["apk"]}),
                              ("/api/serveurs/x/installer", {"actions": ["apk"], "accord": True})):
            with self.subTest(chemin=chemin):
                r, _ = self.req("POST", chemin, json.dumps(corps), ent)
                self.assertEqual(r.status, 404)
        self.assertEqual(appels, [])
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["serveurs.json"])        # rien écrit
        r, data = self.req("GET", "/api/serveurs", entetes={"Cookie": cookie})      # lecture seule : permise, masquée
        self.assertEqual(r.status, 200)
        self.assertEqual([x["id"] for x in json.loads(data)["serveurs"]], ["x"])
        self.assertEqual(self.req("GET", "/api/serveurs")[0].status, 401)


if __name__ == "__main__":
    unittest.main()
