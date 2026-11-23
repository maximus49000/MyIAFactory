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

    def __init__(self, presentes=(), etapes=None, acces=True, injoignable=False, tomber_a=None, depot_code=0):
        self.marqueur_fige = False          # vrai : l'étape « réussit » sans réécrire le marqueur
        self.marqueur = None                # contenu du marqueur de l'image (None : illisible) ; 255 : serveur injoignable
        self.depot_code, self.archives = depot_code, []             # archives : (commande, octets) de chaque dépôt de fichiers
        self.presentes = set(presentes)
        self.etapes = etapes or {}          # etape -> (statut, detail) ; absent : "fait" et la capacité devient présente
        self.acces, self.injoignable, self.tomber_a = acces, injoignable, tomber_a
        self.appels, self.lancees, self.nb_sondes = [], [], 0

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, runner=None):
        self.archives.append((commande, entree))
        self.appels.append({"hote": hote, "commande": commande, "stdin": None, "delai": delai})
        return self.depot_code, b"", ("tar: erreur" if self.depot_code else "")

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
        if commande.startswith('head -c 256 "$HOME/.myiafactory/'):
            if self.marqueur == 255:
                return 255, "", "Connection reset"
            return (0, self.marqueur + "\n", "") if isinstance(self.marqueur, str) else (1, "", "No such file")
        etape = commande.rsplit("--etape ", 1)[1].strip()
        if self.tomber_a == etape:
            return 255, "", "Connection reset"
        self.lancees.append(etape)
        statut, detail = self.etapes.get(etape, ("fait", f"{etape} ok"))
        if statut == "fait":
            self.presentes |= {c.id for c in CATALOGUE.values() if c.etape == etape and c.installable}
            if etape in ("emulateur_image", "agent_image") and not self.marqueur_fige:
                self.marqueur = inst.empreinte_etape(etape)                  # l'étape réécrit le marqueur
        return 0, "log\n" + json.dumps({"etape": etape, "statut": statut, "detail": detail}) + "\n", ""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def installer(self, ssh, actions=("apk",), accord=True, **kw):
        return inst.installer(SERVEUR, list(actions), accord, dossier=self.dossier, ssh=ssh, dormir=lambda s: None,
                              vivant=kw.pop("vivant", lambda p: False), **kw)


class TestChargeDansEtat(Base):
    CHARGE = {"charge_par_coeur": 0.3, "memoire_libre_ratio": 0.7, "conteneurs_outils": 2}

    def etat(self):
        return inst.lire_etat(self.dossier)[SERVEUR.id]

    def test_sonde_enregistre_la_charge(self):
        inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge=self.CHARGE)
        self.assertEqual({k: v for k, v in self.etat()["charge"].items() if k != "maj"}, self.CHARGE)

    def test_lecture_de_charge_ratee_ne_stocke_rien_et_ne_leve_pas(self):
        inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge=self.CHARGE)
        inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge=None)
        self.assertNotIn("charge", self.etat())
        inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge="n'importe quoi")
        self.assertNotIn("charge", self.etat())

    def test_charge_avec_entier_demesure_est_refusee(self):
        for bad in (10 ** 400, float("nan"), float("inf")):
            inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge={**self.CHARGE, "charge_par_coeur": bad})
            self.assertNotIn("charge", self.etat())

    def test_la_charge_est_datee_et_la_date_conservee(self):
        inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge=self.CHARGE, horloge=lambda: 1234.5)
        self.assertEqual(self.etat()["charge"], {**self.CHARGE, "maj": 1234.5})
        inst._ecrire_etat(self.dossier, SERVEUR.id, {}, False, "")
        self.assertEqual(self.etat()["charge"]["maj"], 1234.5)

    def test_une_ecriture_d_installation_conserve_la_charge(self):
        inst.enregistrer_sonde(self.dossier, SERVEUR, {"base": "presente"}, charge=self.CHARGE)
        inst._ecrire_etat(self.dossier, SERVEUR.id, {}, False, "")
        self.assertEqual({k: v for k, v in self.etat()["charge"].items() if k != "maj"}, self.CHARGE)


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
        self.assertFalse(inst.lire_etat(self.dossier)[SERVEUR.id]["installation"]["en_cours"])


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

    def test_serveur_injoignable_leve_via_refus_acces_et_n_installe_rien(self):
        ssh = FauxSsh(injoignable=True)
        with self.assertRaises(inst.ErreurInstallation):          # l'accès est vérifié avant tout
            self.installer(ssh)
        self.assertEqual(ssh.lancees, [])
        self.assertFalse((self.dossier / inst.VERROU).exists())

    def test_sonde_partielle_inconnue_n_installe_rien(self):
        class Partielle(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                code, sortie, err = super().executer(hote, commande, cle, stdin, delai, runner)
                if commande == "bash -s" and "sudo=" not in (stdin or ""):
                    sortie = "\n".join(l for l in sortie.splitlines() if not l.startswith("android-build=")) + "\n"
                return code, sortie, err
        ssh = Partielle()
        r = self.installer(ssh)
        self.assertEqual(ssh.lancees, [])
        self.assertFalse(r["ok"])
        self.assertEqual({c["statut"] for c in r["capacites"].values()}, {"inconnue"})

    def test_delai_ssh_depasse_donne_inconnue_et_arrete_la_suite(self):
        class Delai(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                if "--etape android_build" in commande:
                    s.appels.append({"commande": commande})
                    return 124, "", "délai dépassé (1800 s)"
                return super().executer(hote, commande, cle, stdin, delai, runner)
        ssh = Delai()
        r = self.installer(ssh, actions=["emulateur"])
        self.assertEqual(ssh.lancees, ["docker"])
        self.assertEqual(r["capacites"]["android-build"]["statut"], "inconnue")
        self.assertIn("peut encore tourner", r["capacites"]["android-build"]["detail"])
        self.assertEqual(r["capacites"]["android-emulateur"]["statut"], "a_faire")
        self.assertFalse(r["ok"])

    def test_sortie_bruyante_avec_plusieurs_accolades_avant_le_json_final(self):
        class Bruyant(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                code, sortie, err = super().executer(hote, commande, cle, stdin, delai, runner)
                if "--etape" in commande:
                    sortie = '{"etape": "x", "statut": "bloque", "detail": "faux"}\n{pas du json\n  {"a":\n' + sortie
                return code, sortie, err
        r = self.installer(Bruyant())
        self.assertTrue(r["ok"])

    def test_erreur_systeme_du_dossier_devient_erreur_installation(self):
        fichier = self.dossier / "pas-un-dossier"
        fichier.write_text("x", encoding="utf-8")
        with self.assertRaises(inst.ErreurInstallation):
            inst.installer(SERVEUR, ["apk"], True, dossier=fichier / "sous", ssh=FauxSsh(), vivant=lambda p: False)

    def test_apercu_action_inconnue_leve_erreur_installation(self):
        with self.assertRaises(inst.ErreurInstallation):
            inst.apercu(SERVEUR, ["inconnue"], ssh=FauxSsh(), dossier=self.dossier)


class TestMemeProcessus(Base):
    def test_deux_appels_imbriques_le_second_est_refuse(self):
        refus = []

        class Imbrique(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                if "--etape docker" in commande and not refus:
                    try:
                        inst.installer(SERVEUR, ["apk"], True, dossier=self.dossier, ssh=FauxSsh(), vivant=lambda p: False)
                    except inst.ErreurInstallation as e:
                        refus.append(str(e))
                return super().executer(hote, commande, cle, stdin, delai, runner)
        r = self.installer(Imbrique())
        self.assertTrue(r["ok"])
        self.assertEqual(len(refus), 1)
        self.assertIn("déjà en cours", refus[0])
        self.assertFalse((self.dossier / inst.VERROU).exists())

    def test_deux_threads_le_second_refuse_le_premier_termine(self):
        import threading
        en_etape, liberer = threading.Event(), threading.Event()

        class Bloque(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                if "--etape docker" in commande:
                    en_etape.set()
                    liberer.wait(10)
                return super().executer(hote, commande, cle, stdin, delai, runner)
        sortie = {}
        t = threading.Thread(target=lambda: sortie.update(r=self.installer(Bloque())))
        t.start()
        self.assertTrue(en_etape.wait(10))
        ssh2 = FauxSsh()
        with self.assertRaises(inst.ErreurInstallation) as c:
            self.installer(ssh2)
        self.assertIn("déjà en cours", str(c.exception))
        self.assertEqual(ssh2.appels, [])
        self.assertTrue((self.dossier / inst.VERROU).exists())      # le verrou du premier n'est pas retiré
        self.assertTrue(inst.installation_en_cours(self.dossier, vivant=lambda p: False))
        liberer.set()
        t.join(10)
        self.assertTrue(sortie["r"]["ok"])
        self.assertFalse((self.dossier / inst.VERROU).exists())
        self.assertFalse(inst.installation_en_cours(self.dossier, vivant=lambda p: False))

    def test_verrou_a_notre_pid_sans_installation_locale_est_repris(self):
        (self.dossier / inst.VERROU).write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        self.assertFalse(inst.installation_en_cours(self.dossier, vivant=lambda p: True))
        self.assertTrue(self.installer(FauxSsh())["ok"])


class TestEtatPerime(Base):
    def _etat_perime(self):
        (self.dossier / inst.ETAT).write_text(json.dumps({"srv": {
            "capacites": {"base": {"statut": "fait", "detail": "", "geste": "", "maj": "x"},
                          "android-build": {"statut": "en_cours", "detail": "en cours", "geste": "", "maj": "x"}},
            "installation": {"en_cours": True, "debut": "x"}}}), encoding="utf-8")

    def test_etat_perime_sans_verrou_est_degrade_a_la_lecture(self):
        self._etat_perime()
        e = inst.lire_etat_vivant(self.dossier, vivant=lambda p: False)["srv"]
        self.assertEqual(e["capacites"]["android-build"]["statut"], "inconnue")
        self.assertIn("Installation interrompue", e["capacites"]["android-build"]["detail"])
        self.assertEqual(e["capacites"]["base"]["statut"], "fait")
        self.assertFalse(e["installation"]["en_cours"])
        self.assertEqual(inst.lire_etat(self.dossier)[SERVEUR.id]["capacites"]["android-build"]["statut"], "en_cours")  # brut stable

    def test_verrou_vivant_garde_en_cours(self):
        self._etat_perime()
        (self.dossier / inst.VERROU).write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        e = inst.lire_etat_vivant(self.dossier, vivant=lambda p: p == 4242)["srv"]
        self.assertEqual(e["capacites"]["android-build"]["statut"], "en_cours")
        self.assertTrue(e["installation"]["en_cours"])
        self.assertTrue(inst.installation_en_cours(self.dossier, vivant=lambda p: p == 4242))
        self.assertFalse(inst.installation_en_cours(self.dossier, vivant=lambda p: False))

    def test_interruption_en_cours_ne_laisse_aucun_en_cours(self):
        class Interrompu(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                if "--etape android_build" in commande:
                    raise KeyboardInterrupt()
                return super().executer(hote, commande, cle, stdin, delai, runner)
        with self.assertRaises(KeyboardInterrupt):
            self.installer(Interrompu())
        e = inst.lire_etat(self.dossier)[SERVEUR.id]
        self.assertNotIn("en_cours", {c["statut"] for c in e["capacites"].values()})
        self.assertEqual(e["capacites"]["android-build"]["statut"], "inconnue")
        self.assertFalse(e["installation"]["en_cours"])
        self.assertFalse((self.dossier / inst.VERROU).exists())
        self.assertTrue(self.installer(FauxSsh(presentes={"base"}))["ok"])      # le verrou et le processus sont libres

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
        ssh = FauxSsh(presentes=("base", "agent"))
        ssh.marqueur = inst.empreinte_etape("agent_image")             # image à jour : seule l'étape humaine manque
        # `agent-abonnement` est une étape humaine : jamais lancée par le moteur, refusée avec le geste du Directeur
        r = self.installer(ssh, actions=["agent-serveur"])
        self.assertEqual(ssh.lancees, [])
        self.assertEqual(r["capacites"]["agent-abonnement"]["statut"], "bloque")
        self.assertIn("enregistrer_jeton.sh", r["capacites"]["agent-abonnement"]["detail"])
        self.assertIn("docs/serveur-agents.md#connexion-a-l-abonnement", r["capacites"]["agent-abonnement"]["detail"])
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

    def _installer_image(self, ssh):
        import serveur_capacites
        from unittest import mock
        besoins = dict(serveur_capacites.BESOINS, image_test=("emulateur-image",))
        with mock.patch.object(serveur_capacites, "BESOINS", besoins):
            return self.installer(ssh, actions=["image_test"])

    def test_fichiers_de_l_etape_deposes_en_archive_tar_puis_etape_avec_son_dossier(self):
        import io
        import tarfile
        ssh = FauxSsh()
        r = self._installer_image(ssh)
        self.assertEqual(r["capacites"]["emulateur-image"]["statut"], "fait", r)
        self.assertEqual(len(ssh.archives), 1)                              # une seule fois par exécution
        commande, octets = ssh.archives[0]
        for morceau in ('install -d -m 700 "$HOME/myiafactory"', "umask 077", 'mktemp -d "$HOME/myiafactory/.depot.XXXXXX"',
                        "tar -x --no-same-owner", 'mv -f "$d/$f"', 'rm -rf "$d"', "$HOME/myiafactory/serveur_ovh"):
            self.assertIn(morceau, commande)
        with tarfile.open(fileobj=io.BytesIO(octets)) as tar:
            membres = {m.name: m for m in tar.getmembers()}
            self.assertEqual(sorted(membres), ["images/emulateur/Dockerfile", "images/emulateur/entree-tache.sh", "taches/pont.sh"])
            for nom, m in membres.items():
                self.assertTrue(m.isreg(), nom)
                self.assertEqual((m.uid, m.gid), (0, 0))
                self.assertEqual(m.mode, 0o755 if nom.endswith(".sh") else 0o644, nom)
                self.assertEqual(tar.extractfile(m).read(), (RACINE / "serveur_ovh" / nom).read_bytes())   # octets du dépôt, LF intacts
                self.assertNotIn(b"\r", tar.extractfile(m).read())
        etape = [a["commande"] for a in ssh.appels if "--etape emulateur_image" in a["commande"]]
        self.assertEqual(len(etape), 1)
        self.assertTrue(etape[0].startswith('SERVEUR_OVH_DIR="$HOME/myiafactory/serveur_ovh" bash '), etape[0])
        indices = [i for i, a in enumerate(ssh.appels) if a["commande"] in (inst.COMMANDE_DEPOT_FICHIERS, etape[0])]
        self.assertEqual(indices, sorted(indices))                           # le dépôt précède l'étape

    PRESENTES_IMAGE = ("base", "android-build", "android-emulateur", "emulateur-image")

    def _besoins_image(self):
        import serveur_capacites
        from unittest import mock
        return mock.patch.object(serveur_capacites, "BESOINS", dict(serveur_capacites.BESOINS, image_test=("emulateur-image",)))

    def test_empreinte_change_avec_un_fichier_local(self):
        import shutil
        import tempfile
        from unittest import mock
        avant = inst.empreinte_etape("emulateur_image")
        self.assertRegex(avant, r"^ubuntu=ubuntu:24\.04;jdk=17;fichiers=[0-9a-f]{16}$")
        with tempfile.TemporaryDirectory() as t:
            copie = Path(t) / "serveur_ovh"
            for rel in ("versions.json",) + inst.FICHIERS_ETAPE["emulateur_image"]:
                (copie / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(RACINE / "serveur_ovh" / rel, copie / rel)
            with mock.patch.object(inst, "RACINE_SERVEUR", copie):
                self.assertEqual(inst.empreinte_etape("emulateur_image"), avant)       # mêmes octets, même empreinte
                with open(copie / "taches" / "pont.sh", "ab") as f:
                    f.write(b"# modifie\n")
                self.assertNotEqual(inst.empreinte_etape("emulateur_image"), avant)

    def test_capacite_presente_mais_marqueur_perime_est_a_refaire(self):
        for contenu, perime in ((inst.empreinte_etape("emulateur_image"), False), ("ubuntu=ubuntu:24.04;jdk=17;fichiers=0000000000000000", True),
                                (None, True), (255, False)):
            with self.subTest(marqueur=contenu):
                ssh = FauxSsh(presentes=self.PRESENTES_IMAGE)
                ssh.marqueur = contenu
                with self._besoins_image():
                    ap = inst.apercu(SERVEUR, ["image_test"], ssh=ssh, dossier=self.dossier)
                    self.assertEqual(ap["manquantes"], ["emulateur-image"] if perime else [], ap)
                    ssh = FauxSsh(presentes=self.PRESENTES_IMAGE)
                    ssh.marqueur = contenu
                    r = self.installer(ssh, actions=["image_test"])
                self.assertEqual("emulateur_image" in ssh.lancees, perime)
                self.assertEqual(len(ssh.archives), 1 if perime else 0)
                if perime:
                    self.assertEqual(r["capacites"]["emulateur-image"]["statut"], "fait")

    def test_empreinte_perimee_rend_agent_a_mettre_a_jour(self):
        import tarfile
        import io
        from unittest import mock
        import serveur_capacites
        attendue = inst.empreinte_etape("agent_image")
        self.assertRegex(attendue, r"^ubuntu=ubuntu:24\.04;node=22;claude_code=2\.1\.328;fichiers=[0-9a-f]{16}$")
        # le jeton enregistré par le Directeur se dépose avec l'étape mais n'entre pas dans l'empreinte de l'image
        self.assertIn("taches/enregistrer_jeton.sh", inst.FICHIERS_ETAPE["agent_image"])
        self.assertEqual(inst.EMPREINTE_FICHIERS["agent_image"],
                         ("images/agent/Dockerfile", "images/agent/entree-agent.py", "images/agent/pont"))
        besoins = dict(serveur_capacites.BESOINS, agent_test=("agent",))
        presentes = ("base", "agent")
        for contenu, perime in ((attendue, False), ("ubuntu=ubuntu:24.04;node=22;claude_code=2.1.328;fichiers=0000000000000000", True),
                                (None, True), (255, False)):
            with self.subTest(marqueur=contenu), mock.patch.object(serveur_capacites, "BESOINS", besoins):
                ssh = FauxSsh(presentes=presentes)
                ssh.marqueur = contenu
                ap = inst.apercu(SERVEUR, ["agent_test"], ssh=ssh, dossier=self.dossier)
                self.assertEqual(ap["manquantes"], ["agent"] if perime else [], ap)
                self.assertEqual(ap["perimees"], ["agent"] if perime else [])
                lectures = [a["commande"] for a in ssh.appels if "agent-image.version" in a["commande"]]
                self.assertEqual(len(lectures), 1)
                self.assertTrue(lectures[0].startswith("head -c 256 "), lectures[0])
                ssh = FauxSsh(presentes=presentes)
                ssh.marqueur = contenu
                r = self.installer(ssh, actions=["agent_test"])
                self.assertEqual("agent_image" in ssh.lancees, perime)
                if perime:
                    self.assertEqual(r["capacites"]["agent"]["statut"], "fait", r)
                    commande, octets = ssh.archives[0]
                    with tarfile.open(fileobj=io.BytesIO(octets)) as tar:
                        self.assertEqual(sorted(tar.getnames()), sorted(inst.FICHIERS_ETAPE["agent_image"]))

    def test_lecture_du_marqueur_bornee_et_apercu_marque_la_capacite_perimee(self):
        ssh = FauxSsh(presentes=self.PRESENTES_IMAGE)
        ssh.marqueur = "ubuntu=autre"
        with self._besoins_image():
            ap = inst.apercu(SERVEUR, ["image_test"], ssh=ssh, dossier=self.dossier)
        lectures = [a["commande"] for a in ssh.appels if "emulateur-image.version" in a["commande"]]
        self.assertEqual(len(lectures), 1)
        self.assertTrue(lectures[0].startswith("head -c 256 "), lectures[0])      # lecture bornée : jamais un fichier énorme
        self.assertNotEqual(ap["etat"]["emulateur-image"], "presente")             # cohérent avec « manquantes »
        self.assertEqual(ap["perimees"], ["emulateur-image"])
        ssh = FauxSsh(presentes=self.PRESENTES_IMAGE)
        ssh.marqueur = inst.empreinte_etape("emulateur_image")
        with self._besoins_image():
            ap = inst.apercu(SERVEUR, ["image_test"], ssh=ssh, dossier=self.dossier)
        self.assertEqual((ap["etat"]["emulateur-image"], ap["perimees"]), ("presente", []))

    def test_sonde_finale_compare_aussi_l_empreinte(self):
        ssh = FauxSsh(presentes=self.PRESENTES_IMAGE)
        ssh.marqueur = "ubuntu=autre"
        ssh.marqueur_fige = True                                                  # l'étape dit « fait » mais le marqueur reste périmé
        r = self._installer_image(ssh)
        e = r["capacites"]["emulateur-image"]
        self.assertEqual(e["statut"], "bloque", r)
        self.assertIn("périmé", e["detail"])
        self.assertFalse(r["ok"])

    def test_depot_fichier_local_manquant_est_bloque_et_non_une_coupure_de_connexion(self):
        from unittest import mock
        vide = Path(self.dossier) / "vide"
        vide.mkdir()
        (vide / "mise_en_place.sh").write_bytes((RACINE / "serveur_ovh" / "mise_en_place.sh").read_bytes())
        with mock.patch.object(inst, "RACINE_SERVEUR", vide):
            ssh = FauxSsh()
            r = self._installer_image(ssh)
        e = r["capacites"]["emulateur-image"]
        self.assertEqual(e["statut"], "bloque", r)
        self.assertIn("introuvable", e["detail"])
        self.assertNotIn("connexion", e["detail"].lower())

    def _deposer_sous_bash(self, octets):
        """Exécute la VRAIE commande de dépôt sous bash, dans un faux HOME ; rend (code, dossier des fichiers déposés, restes)."""
        import subprocess
        import shutil
        if not shutil.which("bash") or not shutil.which("tar"):
            self.skipTest("bash ou tar absent")
        t = Path(self.dossier) / "faux-home"
        t.mkdir(exist_ok=True)
        faux = Path(self.dossier) / "faux-bin"                          # Git bash sur Windows ne sait pas faire `install -m 700` : repli mkdir
        faux.mkdir(exist_ok=True)
        (faux / "install").write_text('#!/bin/sh\n[ "$1" = -d ] && shift\n[ "$1" = -m ] && shift 2\nmkdir -p "$@"\n', newline="\n")
        (faux / "install").chmod(0o755)
        r = subprocess.run(["bash", "-c", inst.COMMANDE_DEPOT_FICHIERS], input=octets, capture_output=True, timeout=60,
                           env=dict(os.environ, HOME=t.as_posix(), PATH=faux.as_posix() + os.pathsep + os.environ["PATH"]))
        dest = t / "myiafactory" / "serveur_ovh"
        deposes = sorted(x.relative_to(dest).as_posix() for x in dest.rglob("*") if x.is_file()) if dest.exists() else []
        restes = sorted(x.name for x in (t / "myiafactory").iterdir() if x.name.startswith(".depot")) if (t / "myiafactory").exists() else []
        return r.returncode, deposes, restes, dest

    def test_commande_de_depot_sous_bash_complete_puis_tronquee(self):
        archive = inst._archive_fichiers("emulateur_image")
        attendus = sorted(inst.FICHIERS_ETAPE["emulateur_image"])
        code, deposes, restes, dest = self._deposer_sous_bash(archive)
        self.assertEqual((code, deposes, restes), (0, attendus, []))
        for rel in attendus:
            self.assertEqual((dest / rel).read_bytes(), (RACINE / "serveur_ovh" / rel).read_bytes())
        # Flux coupé à une frontière de membre (premier fichier entier, le reste absent) : rien n'est mis à jour.
        fins, position = [], 0
        for rel in inst.FICHIERS_ETAPE["emulateur_image"]:                   # fin de chaque membre : en-tête 512 + données arrondies à 512
            position += 512 + ((len((RACINE / "serveur_ovh" / rel).read_bytes()) + 511) // 512) * 512
            fins.append(position)
        # après le 1er membre, après le 2e (le 3e absent : tar réussit mais il manque un fichier), au milieu du 3e, entêtes coupés
        for coupe in (fins[0], fins[1], fins[1] + 100, fins[2] - 1024, 0, 700):
            with self.subTest(coupe=coupe):
                self.dossier = Path(tempfile.mkdtemp())                       # faux HOME neuf à chaque cas
                self.addCleanup(__import__("shutil").rmtree, self.dossier, True)
                code, deposes, restes, _ = self._deposer_sous_bash(archive[:coupe])
                self.assertNotEqual(code, 0)
                self.assertEqual(deposes, [])                                 # aucun fichier déposé, même partiel
                self.assertEqual(restes, [])                                  # dossier temporaire supprimé
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.dossier, True)
        code, deposes, restes, _ = self._deposer_sous_bash(b"pas une archive tar" * 100)
        self.assertNotEqual(code, 0)
        self.assertEqual((deposes, restes), ([], []))

    def test_depot_des_fichiers_en_echec(self):
        for code, statut in ((255, "inconnue"), (124, "inconnue"), (1, "bloque")):
            with self.subTest(code=code):
                ssh = FauxSsh(depot_code=code)
                r = self._installer_image(ssh)
                self.assertEqual(r["capacites"]["emulateur-image"]["statut"], statut, r)
                self.assertNotIn("emulateur_image", ssh.lancees)
                self.assertIn("Dépôt des fichiers", r["capacites"]["emulateur-image"]["detail"])

    def test_les_autres_etapes_ne_deposent_rien_de_plus(self):
        ssh = FauxSsh()
        self.installer(ssh, actions=["emulateur"])
        self.assertEqual(ssh.archives, [])
        self.assertFalse(any("SERVEUR_OVH_DIR" in a["commande"] for a in ssh.appels))

    def test_les_delais_par_etape_sont_ceux_du_module(self):
        self.assertEqual(inst.DELAIS_ETAPE_S, {"docker": 1200, "durcissement": 900, "android_build": 1800,
                                               "android_emulateur": 1800, "emulateur_image": 900, "agent_image": 900,
                                               "unity_cli": 300})
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
                    e = inst.lire_etat(self.dossier)[SERVEUR.id]
                    instantanes.append((commande.rsplit("--etape ", 1)[1], {i: c["statut"] for i, c in e["capacites"].items()},
                                        e["installation"]["en_cours"]))
                return super().executer(hote, commande, cle, stdin, delai, runner)
        self.installer(Espion())
        self.assertEqual(instantanes[0], ("docker", {"base": "en_cours", "android-build": "a_faire"}, True))
        self.assertEqual(instantanes[1], ("android_build", {"base": "fait", "android-build": "en_cours"}, True))
        final = inst.lire_etat(self.dossier)[SERVEUR.id]
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


class TestEtatConserve(Base):
    """Une installation ne réécrit que ses capacités : les autres, et les raisons de blocage, restent."""

    def _avant(self):
        inst._ecrire_etat(self.dossier, SERVEUR.id, {
            "agent": inst._entree("bloque", "Licence refusée", "Acceptez la licence."),
            "unity-cli": inst._entree("presente", "Constatée par la sonde."),
            "android-emulateur": inst._entree("bloque", "Pas de KVM", "Activez la virtualisation.")}, False, "debut")

    def test_installer_une_capacite_garde_les_autres_et_leurs_raisons(self):
        self._avant()
        r = self.installer(FauxSsh(presentes={"unity-cli"}), actions=["apk"])
        self.assertTrue(r["ok"])
        caps = inst.lire_etat(self.dossier)[SERVEUR.id]["capacites"]
        self.assertEqual((caps["base"]["statut"], caps["android-build"]["statut"]), ("fait", "fait"))
        self.assertEqual(caps["agent"]["statut"], "bloque")
        self.assertEqual(caps["agent"]["detail"], "Licence refusée")
        self.assertEqual(caps["agent"]["geste"], "Acceptez la licence.")
        self.assertEqual(caps["android-emulateur"]["detail"], "Pas de KVM")
        self.assertEqual(caps["unity-cli"]["statut"], "presente")

    def test_installer_charge_ne_vide_pas_l_etat(self):
        self._avant()
        inst._ecrire_etat(self.dossier, SERVEUR.id, {"base": inst._entree("presente")}, False, "debut",
                          charge={"charge_par_coeur": 0.1, "memoire_libre_ratio": 0.9, "conteneurs_outils": 0, "maj": 5.0})
        r = self.installer(FauxSsh(), actions=["charge"])
        self.assertTrue(r["ok"])
        e = inst.lire_etat(self.dossier)[SERVEUR.id]
        self.assertEqual(set(e["capacites"]), {"agent", "unity-cli", "android-emulateur", "base"})
        self.assertEqual(e["capacites"]["agent"]["detail"], "Licence refusée")
        self.assertEqual(e["charge"]["maj"], 5.0)

    def _caps(self):
        return inst.lire_etat(self.dossier)[SERVEUR.id]["capacites"]

    def test_entree_perimee_rafraichie_par_la_sonde_du_debut(self):
        inst._ecrire_etat(self.dossier, SERVEUR.id, {"unity-cli": inst._entree("presente", "vieux")}, False, "")
        self.installer(FauxSsh(presentes=()), actions=["apk"])           # la sonde dit « absente »
        self.assertEqual(self._caps()["unity-cli"]["statut"], "absente")

    def test_entree_presente_confirmee_par_la_sonde_reste_presente(self):
        inst._ecrire_etat(self.dossier, SERVEUR.id, {"unity-cli": inst._entree("absente")}, False, "")
        self.installer(FauxSsh(presentes={"unity-cli"}), actions=["apk"])
        self.assertEqual(self._caps()["unity-cli"]["statut"], "presente")

    def test_bloque_garde_sa_raison_si_la_sonde_dit_absente(self):
        inst._ecrire_etat(self.dossier, SERVEUR.id, {"agent": inst._entree("bloque", "Licence refusée", "Acceptez.")}, False, "")
        self.installer(FauxSsh(presentes=()), actions=["apk"])
        self.assertEqual((self._caps()["agent"]["statut"], self._caps()["agent"]["detail"]), ("bloque", "Licence refusée"))

    def test_sonde_inconnue_garde_l_etat_connu(self):
        class SansAgent(FauxSsh):
            def executer(s, hote, commande, cle, stdin=None, delai=60, runner=None):
                code, sortie, err = super().executer(hote, commande, cle, stdin, delai, runner)
                if commande == "bash -s" and "sudo=" not in (stdin or ""):
                    sortie = "".join(x + "\n" for x in sortie.splitlines() if not x.startswith("agent="))
                return code, sortie, err
        inst._ecrire_etat(self.dossier, SERVEUR.id, {"agent": inst._entree("presente", "vu")}, False, "")
        self.installer(SansAgent(), actions=["apk"])
        self.assertEqual(self._caps()["agent"]["statut"], "presente")

    def test_installer_charge_garde_toute_la_carte_meme_avec_une_sonde_differente(self):
        inst._ecrire_etat(self.dossier, SERVEUR.id, {"agent": inst._entree("bloque", "Licence", "g"),
                                                      "base": inst._entree("presente")}, False, "")
        self.installer(FauxSsh(presentes=()), actions=["charge"])
        self.assertEqual(set(self._caps()), {"agent", "base"})
        self.assertEqual(self._caps()["agent"]["detail"], "Licence")

    def test_etat_abime_a_la_main_ne_fait_jamais_lever(self):
        (self.dossier / inst.ETAT).write_text(json.dumps({SERVEUR.id: {"capacites": {
            "base": "presente", "agent": 3, "unity-cli": None, "android-build": {"statut": "en_cours"}},
            "installation": {"en_cours": True}}}), encoding="utf-8")
        e = inst.lire_etat_vivant(self.dossier, vivant=lambda p: False)[SERVEUR.id]
        self.assertEqual(e["capacites"]["android-build"]["statut"], "inconnue")
        self.assertEqual(e["capacites"]["base"], "presente")      # une entrée qui n'est pas un dictionnaire est laissée telle quelle


class TestDeuxFlux(Base):
    """L'installation générique et celle de la plateforme OVH ne tournent jamais en même temps."""

    def test_refuse_pendant_l_installation_de_la_plateforme(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        ssh = FauxSsh()
        with self.assertRaises(inst.ErreurInstallation) as c:
            self.installer(ssh, vivant=lambda p: p == 4242)
        self.assertIn("plateforme", str(c.exception).lower())
        self.assertTrue(c.exception.geste)
        self.assertEqual(ssh.lancees, [])
        self.assertFalse([a for a in ssh.appels if "cat >" in a["commande"]])
        self.assertTrue((self.dossier / "plateforme.lock").exists())          # le verrou de l'autre n'est pas touché
        self.assertFalse((self.dossier / inst.VERROU).exists())               # et le nôtre est rendu

    def test_refuse_si_le_verrou_de_la_plateforme_est_celui_de_ce_processus(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        with self.assertRaises(inst.ErreurInstallation):
            self.installer(FauxSsh())

    def test_verrou_plateforme_mort_ne_gene_pas(self):
        (self.dossier / "plateforme.lock").write_text(json.dumps({"pid": 999999}), encoding="utf-8")
        self.assertTrue(self.installer(FauxSsh())["ok"])

    def test_script_depose_dans_un_fichier_temporaire_puis_renomme(self):
        ssh = FauxSsh()
        self.installer(ssh)
        depot = [a for a in ssh.appels if "cat >" in a["commande"]][0]["commande"]
        self.assertIn('cat > "$HOME/myiafactory/mise_en_place.sh.$$.tmp"', depot)
        self.assertIn('mv -f "$HOME/myiafactory/mise_en_place.sh.$$.tmp" "$HOME/myiafactory/mise_en_place.sh"', depot)
        self.assertNotIn('cat > "$HOME/myiafactory/mise_en_place.sh"', depot)
        self.assertLess(depot.index("cat >"), depot.index("mv -f"))
        self.assertLess(depot.index("chmod 700"), depot.index("mv -f"))


class TestIndependance(unittest.TestCase):
    SOURCE = (RACINE / "outils" / "serveur_installation.py").read_text(encoding="utf-8")

    def test_aucune_reinstallation_possible(self):
        self.assertNotIn("reinstaller", self.SOURCE.lower())
        self.assertNotIn("serveur_fournisseur", self.SOURCE)

    def test_mot_ovh_absent_du_module(self):
        self.assertNotIn("ovh", self.SOURCE.lower())


if __name__ == "__main__":
    unittest.main()
