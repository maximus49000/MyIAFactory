"""Installation à la demande (`outils/serveur_installation.py`). SSH et script factices : aucune connexion réelle,
jamais le vrai ~/MyIAFactory."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import plateforme_ssh  # noqa: E402
import serveur_installation as inst  # noqa: E402
from serveur_capacites import CATALOGUE  # noqa: E402
from serveur_modele import Serveur  # noqa: E402

SERVEUR = Serveur("srv", "Serveur", "203.0.113.7", "factory", "C:/cles/id_secret_ed25519")
SCRIPT = RACINE / "serveur_ovh" / "mise_en_place.sh"


class FauxSsh:
    """Serveur factice : sondes, droits, dépôt du script et étapes distantes programmables."""
    ErreurSsh = plateforme_ssh.ErreurSsh
    CHANGEMENT_CLE = plateforme_ssh.CHANGEMENT_CLE
    _verifier_hote = staticmethod(plateforme_ssh._verifier_hote)

    def __init__(self, presentes=(), etapes=None, acces=True, injoignable=False, tomber_a=None):
        self.presentes = set(presentes)
        self.etapes = etapes or {}          # etape -> (statut, detail) ; absent : "fait" et la capacité devient présente
        self.acces, self.injoignable, self.tomber_a = acces, injoignable, tomber_a
        self.appels, self.lancees, self.nb_sondes = [], [], 0

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        self.appels.append({"hote": hote, "commande": commande, "stdin": stdin, "delai": delai})
        if self.injoignable:
            return 255, "", "ssh: connect to host: Connection timed out"
        if commande == "bash -s" and "sudo=" in (stdin or ""):
            return 0, "user=factory\nsudo=" + ("0" if self.acces else "1") + "\n", ""
        if commande == "bash -s":
            self.nb_sondes += 1
            return 0, "\n".join(f"{i}={0 if i in self.presentes else 1}" for i in CATALOGUE) + "\n", ""
        if "cat >" in commande:
            return 0, "", ""
        etape = commande.rsplit("--etape ", 1)[1].strip()
        if self.tomber_a == etape:
            return 255, "", "Connection reset"
        self.lancees.append(etape)
        statut, detail = self.etapes.get(etape, ("fait", f"{etape} ok"))
        if statut == "fait":
            self.presentes |= {c.id for c in CATALOGUE.values() if c.etape == etape and c.installable}
        return 0, "log\n" + json.dumps({"etape": etape, "statut": statut, "detail": detail}) + "\n", ""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def installer(self, ssh, actions=("apk",), accord=True, **kw):
        return inst.installer(SERVEUR, list(actions), accord, dossier=self.dossier, ssh=ssh, dormir=lambda s: None,
                              vivant=kw.pop("vivant", lambda p: False), **kw)


class TestApercu(Base):
    def test_apercu_ne_modifie_rien_et_donne_l_ordre(self):
        ssh = FauxSsh(presentes=())
        r = inst.apercu(SERVEUR, ["emulateur"], ssh=ssh, dossier=self.dossier)
        self.assertEqual(r["manquantes"], ["base", "android-build", "android-emulateur"])
        self.assertAlmostEqual(r["taille_go"], 0.5 + 5.4 + 2.0)
        self.assertEqual(r["duree_min"], 5 + 10 + 8)
        self.assertEqual(r["bloquees"], [])
        self.assertEqual(r["etat"]["base"], "absente")
        self.assertEqual(list(self.dossier.iterdir()), [])
        self.assertFalse([a for a in ssh.appels if "cat >" in a["commande"] or "--etape" in a["commande"]])

    def test_apercu_serveur_injoignable_ne_calcule_rien(self):
        r = inst.apercu(SERVEUR, ["apk"], ssh=FauxSsh(injoignable=True), dossier=self.dossier)
        self.assertIn("erreur", r)
        self.assertNotIn("manquantes", r)
        self.assertEqual(set(r["etat"].values()), {"inconnue"})

    def test_apercu_sans_rien_a_faire(self):
        r = inst.apercu(SERVEUR, ["apk"], ssh=FauxSsh(presentes={"base", "android-build"}), dossier=self.dossier)
        self.assertEqual(r["manquantes"], [])
        self.assertEqual(r["duree_min"], 0)


class TestAccordEtVerrou(Base):
    def test_installer_sans_accord_strict_n_appelle_rien(self):
        for accord in ("oui", "True", 1, None, False):
            ssh = FauxSsh()
            with self.assertRaises(inst.ErreurInstallation) as c:
                self.installer(ssh, accord=accord)
            self.assertTrue(c.exception.geste)
            self.assertEqual(ssh.appels, [])
            self.assertEqual(list(self.dossier.iterdir()), [])

    def test_acces_refuse_n_installe_rien(self):
        ssh = FauxSsh(acces=False)
        with self.assertRaises(inst.ErreurInstallation):
            self.installer(ssh)
        self.assertEqual(ssh.lancees, [])
        self.assertFalse((self.dossier / inst.VERROU).exists())

    def test_deuxieme_installation_simultanee_refusee(self):
        (self.dossier / inst.VERROU).write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        ssh = FauxSsh()
        with self.assertRaises(inst.ErreurInstallation) as c:
            self.installer(ssh, vivant=lambda p: p == 4242)
        self.assertIn("déjà en cours", str(c.exception))
        self.assertEqual(ssh.lancees, [])
        self.assertTrue((self.dossier / inst.VERROU).exists())      # le verrou d'un autre n'est pas retiré

    def test_verrou_vide_recent_est_tenu_et_verrou_mort_est_repris(self):
        verrou = self.dossier / inst.VERROU
        verrou.write_text("", encoding="utf-8")
        with self.assertRaises(inst.ErreurInstallation):
            self.installer(FauxSsh())
        vieux = time.time() - 120
        os.utime(verrou, (vieux, vieux))                            # vide mais ancien : abandonné
        self.assertTrue(self.installer(FauxSsh())["ok"])
        verrou.write_text(json.dumps({"pid": 999999}), encoding="utf-8")   # pid mort
        self.assertTrue(self.installer(FauxSsh())["ok"])
        self.assertFalse(verrou.exists())

    def test_verrou_libere_meme_en_cas_d_erreur(self):
        class Casse(FauxSsh):
            def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
                if "--etape" in commande:
                    raise RuntimeError("boum")
                return super().executer(hote, commande, cle, stdin, delai, runner)
        r = self.installer(Casse())
        self.assertFalse(r["ok"])
        self.assertFalse((self.dossier / inst.VERROU).exists())
        self.assertFalse(inst.lire_etat(self.dossier)["srv"]["installation"]["en_cours"])


class TestInstallation(Base):
    def test_installer_dans_l_ordre_des_dependances(self):
        ssh = FauxSsh()
        r = self.installer(ssh, actions=["emulateur"])
        self.assertEqual(ssh.lancees, ["docker", "android_build", "android_emulateur"])
        self.assertTrue(r["ok"])
        self.assertEqual({i: c["statut"] for i, c in r["capacites"].items()},
                         {"base": "fait", "android-build": "fait", "android-emulateur": "fait"})

    def test_relance_reprend_sans_refaire_ce_qui_est_fait(self):
        ssh = FauxSsh(presentes={"base"}, etapes={"android_build": ("bloque", "SDK indisponible")})
        r = self.installer(ssh)
        self.assertEqual(ssh.lancees, ["android_build"])
        self.assertEqual(r["capacites"]["base"]["statut"], "presente")
        ssh2 = FauxSsh(presentes={"base"})
        self.installer(ssh2)
        self.assertEqual(ssh2.lancees, ["android_build"])

    def test_capacite_bloquee_arrete_la_suite_et_garde_la_raison(self):
        ssh = FauxSsh(etapes={"android_build": ("bloque", "Disque plein")})
        r = self.installer(ssh, actions=["emulateur"])
        self.assertEqual(ssh.lancees, ["docker", "android_build"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["capacites"]["android-build"]["statut"], "bloque")
        self.assertIn("Disque plein", r["capacites"]["android-build"]["detail"])
        self.assertTrue(r["capacites"]["android-build"]["geste"])
        self.assertEqual(r["capacites"]["android-emulateur"]["statut"], "a_faire")
        self.assertIn("En attente de android-build", r["capacites"]["android-emulateur"]["detail"])

    def test_etape_a_faire_arrete_aussi_la_suite(self):
        ssh = FauxSsh(etapes={"docker": ("a_faire", "geste humain")})
        r = self.installer(ssh)
        self.assertEqual(ssh.lancees, ["docker"])
        self.assertEqual(r["capacites"]["base"]["statut"], "a_faire")
        self.assertEqual(r["capacites"]["android-build"]["statut"], "a_faire")

    def test_serveur_injoignable_donne_inconnue_et_n_installe_rien(self):
        ssh = FauxSsh(injoignable=True)
        with self.assertRaises(inst.ErreurInstallation):          # l'accès est vérifié avant tout
            self.installer(ssh)
        self.assertEqual(ssh.lancees, [])

    def test_sondes_illisibles_donnent_inconnue(self):
        class SondeMuette(FauxSsh):
            def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
                if commande == "bash -s" and "sudo=" not in (stdin or ""):
                    return 255, "", "reset"
                return super().executer(hote, commande, cle, stdin, delai, runner)
        ssh = SondeMuette()
        r = self.installer(ssh)
        self.assertEqual(ssh.lancees, [])
        self.assertEqual({c["statut"] for c in r["capacites"].values()}, {"inconnue"})
        self.assertFalse(r["ok"])

    def test_connexion_perdue_en_cours_donne_inconnue_et_rien_d_autre(self):
        ssh = FauxSsh(tomber_a="android_build")
        r = self.installer(ssh, actions=["emulateur"])
        self.assertEqual(ssh.lancees, ["docker"])
        self.assertEqual(r["capacites"]["android-build"]["statut"], "inconnue")
        self.assertEqual(r["capacites"]["android-emulateur"]["statut"], "a_faire")
        self.assertIn("injoignable", r["erreur"])

    def test_agent_refuse_avec_sa_raison(self):
        ssh = FauxSsh()
        # `agent` n'est requis par aucune action réelle : action de test dont le besoin est non installable
        from unittest import mock
        import serveur_capacites
        besoins = dict(serveur_capacites.BESOINS, agent_test=("agent",))
        with mock.patch.object(serveur_capacites, "BESOINS", besoins):
            r = self.installer(ssh, actions=["agent_test"])
        self.assertEqual(ssh.lancees, [])
        self.assertEqual(r["capacites"]["agent"]["statut"], "bloque")
        self.assertIn("morceau 3", r["capacites"]["agent"]["detail"])
        self.assertFalse(r["ok"])

    def test_capacite_non_installable_jamais_lancee(self):
        import serveur_capacites
        from unittest import mock
        besoins = dict(serveur_capacites.BESOINS, editeur_test=("unity-editeur", "android-build"))
        ssh = FauxSsh()
        with mock.patch.object(serveur_capacites, "BESOINS", besoins):
            r = self.installer(ssh, actions=["editeur_test"])
        self.assertEqual(ssh.lancees.count("unity_cli"), 1)   # une fois pour unity-cli (installable), jamais pour l'éditeur
        self.assertEqual(r["capacites"]["unity-cli"]["statut"], "fait")
        self.assertEqual(r["capacites"]["unity-editeur"]["statut"], "bloque")
        self.assertEqual(r["capacites"]["android-build"]["statut"], "fait")   # sans lien de dépendance : la suite continue

    def test_les_delais_par_etape_sont_ceux_du_module(self):
        self.assertEqual(inst.DELAIS_ETAPE_S, {"docker": 1200, "durcissement": 900, "android_build": 1800,
                                               "android_emulateur": 1800, "unity_cli": 300})
        self.assertEqual(inst.DELAI_DEFAUT_S, 600)
        ssh = FauxSsh()
        self.installer(ssh, actions=["emulateur"])
        delais = {a["commande"].rsplit("--etape ", 1)[1]: a["delai"] for a in ssh.appels if "--etape" in a["commande"]}
        self.assertEqual(delais, {"docker": 1200, "android_build": 1800, "android_emulateur": 1800})

    def test_script_envoye_en_octets_identiques_au_fichier_du_depot(self):
        ssh = FauxSsh()
        self.installer(ssh)
        depots = [a for a in ssh.appels if "cat >" in a["commande"]]
        self.assertEqual(len(depots), 1)                    # déposé une seule fois par installation
        self.assertNotIn("/tmp", depots[0]["commande"])
        self.assertIn("install -d -m 700", depots[0]["commande"])
        envoye = depots[0]["stdin"]
        self.assertNotIn("\r", envoye)
        self.assertEqual(envoye.encode("utf-8"), SCRIPT.read_bytes())

    def test_etat_ecrit_avant_et_apres_chaque_etape(self):
        instantanes = []

        class Espion(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                if "--etape" in commande:
                    e = inst.lire_etat(self.dossier)["srv"]
                    instantanes.append((commande.rsplit("--etape ", 1)[1], {i: c["statut"] for i, c in e["capacites"].items()},
                                        e["installation"]["en_cours"]))
                return super().executer(hote, commande, cle, stdin, delai, runner)
        self.installer(Espion())
        self.assertEqual(instantanes[0], ("docker", {"base": "en_cours", "android-build": "a_faire"}, True))
        self.assertEqual(instantanes[1], ("android_build", {"base": "fait", "android-build": "en_cours"}, True))
        final = inst.lire_etat(self.dossier)["srv"]
        self.assertEqual({i: c["statut"] for i, c in final["capacites"].items()},
                         {"base": "fait", "android-build": "fait"})
        self.assertFalse(final["installation"]["en_cours"])
        self.assertTrue(final["capacites"]["base"]["maj"])

    def test_installer_ne_fait_pas_confiance_a_l_etat_en_cache(self):
        (self.dossier / inst.ETAT).write_text(json.dumps({"srv": {"capacites": {"base": {"statut": "fait"}},
                                                                   "installation": {"en_cours": False, "debut": None}}}),
                                              encoding="utf-8")
        ssh = FauxSsh(presentes=())
        self.installer(ssh)
        self.assertEqual(ssh.lancees, ["docker", "android_build"])

    def test_relecture_finale_corrige_une_etape_menteuse(self):
        class Menteur(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                r = super().executer(hote, commande, cle, stdin, delai, runner)
                if "--etape android_build" in commande:
                    s.presentes.discard("android-build")
                return r
        r = self.installer(Menteur())
        self.assertEqual(r["capacites"]["android-build"]["statut"], "bloque")
        self.assertFalse(r["ok"])

    def test_aucun_secret_dans_l_etat(self):
        ssh = FauxSsh(etapes={"docker": ("bloque", f"erreur avec {SERVEUR.cle} " + "x" * 500)})
        self.installer(ssh)
        brut = (self.dossier / inst.ETAT).read_text(encoding="utf-8")
        self.assertNotIn(SERVEUR.cle, brut)
        self.assertNotIn("x" * 201, brut)
        self.assertIn("***", brut)

    def test_lire_etat_ne_leve_jamais(self):
        self.assertEqual(inst.lire_etat(self.dossier), {})
        (self.dossier / inst.ETAT).write_text("{pas du json", encoding="utf-8")
        self.assertEqual(inst.lire_etat(self.dossier), {})
        (self.dossier / inst.ETAT).write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(inst.lire_etat(self.dossier), {})

    def test_action_inconnue_refusee_sans_appel(self):
        ssh = FauxSsh()
        with self.assertRaises(inst.ErreurInstallation):
            self.installer(ssh, actions=["inconnue"])
        self.assertEqual(ssh.appels, [])


class TestIndependance(unittest.TestCase):
    SOURCE = (RACINE / "outils" / "serveur_installation.py").read_text(encoding="utf-8")

    def test_aucune_reinstallation_possible(self):
        self.assertNotIn("reinstaller", self.SOURCE.lower())
        self.assertNotIn("serveur_fournisseur", self.SOURCE)

    def test_mot_ovh_absent_du_module(self):
        self.assertNotIn("ovh", self.SOURCE.lower())


if __name__ == "__main__":
    unittest.main()
