"""Migration du serveur OVH existant vers la liste générique (`outils/serveur_migration.py`). SSH factice, dossier
temporaire : jamais le vrai ~/MyIAFactory, jamais de réseau, jamais d'appel d'écriture au fournisseur OVH."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import plateforme_ssh  # noqa: E402
import serveur_fournisseur  # noqa: E402
import serveur_installation  # noqa: E402
import serveur_migration as mig  # noqa: E402
import serveur_modele  # noqa: E402
from serveur_capacites import CATALOGUE  # noqa: E402

SECRET_OVH = "SECRET-OVH-VALEUR-987654"
CLE_PRIVEE = "PRIVATE-KEY-CONTENT-ABCDEF"
MUTANTS = ("rm ", "mv ", "apt", "systemctl", "tee ", "chmod", "useradd", "sed -i", "docker run", "curl", "wget", "reinstall",
           "mkdir", "touch ", "ufw")


class FauxSsh:
    """Serveur factice : répond aux sondes ; note chaque commande et son entrée standard."""
    ErreurSsh = plateforme_ssh.ErreurSsh
    CHANGEMENT_CLE = plateforme_ssh.CHANGEMENT_CLE

    def __init__(self, presentes=("base",), injoignable=False):
        self.presentes, self.injoignable, self.appels = set(presentes), injoignable, []

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        self.appels.append({"hote": hote, "commande": commande, "stdin": stdin or "", "cle": cle})
        if self.injoignable:
            return 255, "", "ssh: connect to host: Connection timed out"
        ids = re.findall(r'echo "([a-z-]+)=0"', stdin or "")
        return 0, "".join(f"{i}={'0' if i in self.presentes else '1'}\n" for i in ids), ""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name) / "secrets"
        self.d.mkdir()

    def installer_ovh(self, ip="203.0.113.9"):
        (self.d / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": SECRET_OVH, "secret": SECRET_OVH + "2",
                                                      "consommateur": SECRET_OVH + "3", "serveur": "ns000.ip-1-2-3.eu"}), encoding="utf-8")
        (self.d / "plateforme.json").write_text(json.dumps({"ip": ip, "etat": {"pret": True}}), encoding="utf-8")
        (self.d / plateforme_ssh.NOM_CLE).write_text(CLE_PRIVEE, encoding="utf-8")
        (self.d / (plateforme_ssh.NOM_CLE + ".pub")).write_text("ssh-ed25519 AAAA pub\n", encoding="utf-8")

    def instantane(self):
        return {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}


class TestDetecter(Base):
    def test_detecter_sans_fichiers_ne_propose_rien(self):
        self.assertIsNone(mig.detecter(self.d))

    def test_detecter_propose_le_serveur_ovh_depuis_le_cache(self):
        self.installer_ovh()
        p = mig.detecter(self.d)
        s = p["serveur"]
        self.assertEqual((s.fournisseur, s.hote, s.utilisateur), ("ovh", "203.0.113.9", "ubuntu"))
        self.assertTrue(os.path.isabs(s.cle))
        self.assertEqual(Path(s.cle), (self.d / plateforme_ssh.NOM_CLE).resolve())
        self.assertEqual(sorted(p["source"]), sorted(["ovh.json", "plateforme.json", plateforme_ssh.NOM_CLE]))
        for secret in (SECRET_OVH, CLE_PRIVEE):
            self.assertNotIn(secret, repr(p))
        serveur_modele.valider(vars(s))         # la proposition est un serveur valide

    def test_detecter_n_ecrase_pas_un_serveur_deja_declare(self):
        self.installer_ovh()
        serveur_modele.ajouter({"nom": "Autre", "hote": "srv.exemple.fr", "utilisateur": "bob", "cle": str(self.d / "k")}, self.d)
        self.assertIsNone(mig.detecter(self.d))

    def test_detecter_prudent_si_serveurs_json_abime(self):
        self.installer_ovh()
        (self.d / "serveurs.json").write_text("{pas du json", encoding="utf-8")
        self.assertIsNone(mig.detecter(self.d))

    def test_detecter_none_si_un_element_manque_ou_est_invalide(self):
        cas = {
            "sans ovh.json": lambda: (self.d / "ovh.json").unlink(),
            "ovh.json incomplet": lambda: (self.d / "ovh.json").write_text('{"point": "x"}', encoding="utf-8"),
            "sans plateforme.json": lambda: (self.d / "plateforme.json").unlink(),
            "cache sans ip": lambda: (self.d / "plateforme.json").write_text("{}", encoding="utf-8"),
            "ip piégée": lambda: (self.d / "plateforme.json").write_text('{"ip": "-oProxyCommand=x"}', encoding="utf-8"),
            "ip pas un texte": lambda: (self.d / "plateforme.json").write_text('{"ip": 12}', encoding="utf-8"),
            "cache illisible": lambda: (self.d / "plateforme.json").write_text("[", encoding="utf-8"),
            "sans clé dédiée": lambda: (self.d / plateforme_ssh.NOM_CLE).unlink(),
        }
        for nom, casse in cas.items():
            with self.subTest(nom):
                for p in self.d.iterdir():
                    p.unlink()
                self.installer_ovh()
                casse()
                self.assertIsNone(mig.detecter(self.d))


class TestApercu(Base):
    def test_apercu_ne_fait_que_lire(self):
        self.installer_ovh()
        p = mig.detecter(self.d)
        avant = self.instantane()
        ssh = FauxSsh(presentes=("base", "android-build"))
        a = mig.apercu(p, ssh=ssh)
        self.assertEqual(self.instantane(), avant)
        self.assertEqual(a["capacites"]["base"], "presente")
        self.assertEqual(a["capacites"]["android-build"], "presente")
        self.assertEqual(a["capacites"]["android-emulateur"], "absente")
        self.assertEqual(set(a["capacites"]), set(CATALOGUE))
        self.assertTrue(ssh.appels)
        for appel in ssh.appels:
            self.assertEqual(appel["commande"], "bash -s")
            for mot in MUTANTS:
                self.assertNotIn(mot, appel["stdin"])
        self.assertNotIn(CLE_PRIVEE, repr(a))
        self.assertNotIn(SECRET_OVH, repr(a))

    def test_sondes_en_echec_donnent_inconnue_et_pas_absente(self):
        self.installer_ovh()
        a = mig.apercu(mig.detecter(self.d), ssh=FauxSsh(injoignable=True))
        self.assertEqual(set(a["capacites"].values()), {"inconnue"})
        self.assertFalse(a["joignable"])


class TestConfirmer(Base):
    def test_confirmer_sans_accord_strict_n_ecrit_rien(self):
        self.installer_ovh()
        p = mig.detecter(self.d)
        avant = self.instantane()
        for accord in (False, None, "true", 1, "oui", [True], {}):
            with self.subTest(accord=accord):
                ssh = FauxSsh()
                with self.assertRaises(mig.ErreurMigration) as c:
                    mig.confirmer(p, accord, self.d, ssh=ssh)
                self.assertEqual(c.exception.code, "accord")
                self.assertEqual(self.instantane(), avant)
                self.assertEqual(ssh.appels, [])           # pas même une sonde

    def test_confirmer_ecrit_le_serveur_et_l_etat_sonde(self):
        self.installer_ovh()
        s = mig.confirmer(mig.detecter(self.d), True, self.d, ssh=FauxSsh(presentes=("base", "android-build")))
        declares, rejets = serveur_modele.lire_avec_rejets(self.d)
        self.assertEqual((declares, rejets), ([s], []))
        self.assertEqual((s.fournisseur, s.hote, s.utilisateur), ("ovh", "203.0.113.9", "ubuntu"))
        etat = serveur_installation.lire_etat(self.d)[s.id]["capacites"]
        self.assertEqual(etat["base"]["statut"], "presente")
        self.assertEqual(etat["android-build"]["statut"], "presente")
        self.assertEqual(etat["android-emulateur"]["statut"], "absente")
        self.assertNotIn(CLE_PRIVEE, (self.d / "serveurs.json").read_text(encoding="utf-8"))
        self.assertNotIn(SECRET_OVH, (self.d / "serveurs.json").read_text(encoding="utf-8"))

    def test_confirmer_deux_fois_refusee(self):
        self.installer_ovh()
        p = mig.detecter(self.d)
        mig.confirmer(p, True, self.d, ssh=FauxSsh())
        avant = self.instantane()
        ssh = FauxSsh()
        with self.assertRaises(mig.ErreurMigration) as c:
            mig.confirmer(p, True, self.d, ssh=ssh)
        self.assertEqual(c.exception.code, "deja")
        self.assertIn("déjà déclaré", str(c.exception))
        self.assertEqual(self.instantane(), avant)
        self.assertEqual(ssh.appels, [])

    def test_serveur_injoignable_enregistre_inconnue_jamais_absente(self):
        self.installer_ovh()
        s = mig.confirmer(mig.detecter(self.d), True, self.d, ssh=FauxSsh(injoignable=True))
        etat = serveur_installation.lire_etat(self.d)[s.id]["capacites"]
        self.assertEqual({v["statut"] for v in etat.values()}, {"inconnue"})

    def test_anciens_fichiers_laisses_intacts(self):
        self.installer_ovh()
        avant = self.instantane()
        mig.confirmer(mig.detecter(self.d), True, self.d, ssh=FauxSsh())
        apres = self.instantane()
        for nom in ("ovh.json", "plateforme.json", plateforme_ssh.NOM_CLE, plateforme_ssh.NOM_CLE + ".pub"):
            self.assertEqual(apres[nom], avant[nom])
        self.assertEqual(sorted(set(apres) - set(avant)), ["serveurs-etat.json", "serveurs.json"])

    def test_installation_en_cours_refuse_sans_rien_ecrire(self):
        self.installer_ovh()
        avant = self.instantane()
        with mock.patch.object(serveur_installation, "installation_en_cours", return_value=True):
            with self.assertRaises(mig.ErreurMigration) as c:
                mig.confirmer(mig.detecter(self.d), True, self.d, ssh=FauxSsh())
        self.assertEqual(c.exception.code, "occupe")
        self.assertEqual(self.instantane(), avant)

    def test_verrou_pris_entre_temps_annule_l_inscription(self):
        self.installer_ovh()
        avant = self.instantane()
        faute = serveur_installation.ErreurInstallation("Une installation est déjà en cours sur ce poste.", "Attendez.")
        with mock.patch.object(serveur_installation, "enregistrer_sonde", side_effect=faute):
            with self.assertRaises(mig.ErreurMigration) as c:
                mig.confirmer(mig.detecter(self.d), True, self.d, ssh=FauxSsh())
        self.assertEqual(c.exception.code, "occupe")
        self.assertEqual(self.instantane(), avant)          # ni serveur déclaré sans état, ni état orphelin

    def test_aucune_reinstallation_possible(self):
        self.installer_ovh()
        ecritures = []

        def piege(nom):
            def f(*a, **k):
                ecritures.append(nom)
                raise AssertionError(nom)
            return f
        with mock.patch.object(serveur_fournisseur.FournisseurOvh, "reinstaller", piege("reinstaller")), \
                mock.patch.object(serveur_fournisseur.FournisseurOvh, "etat_tache", piege("etat_tache")), \
                mock.patch.object(serveur_fournisseur.FournisseurOvh, "lire", piege("lire")), \
                mock.patch.object(serveur_fournisseur, "obtenir", piege("obtenir")), \
                mock.patch("plateforme_ovh.reinstaller", piege("plateforme_ovh.reinstaller")), \
                mock.patch("ovh_api.ClientOvh", piege("ClientOvh")):
            p = mig.detecter(self.d)
            mig.apercu(p, ssh=FauxSsh())
            mig.confirmer(p, True, self.d, ssh=FauxSsh())
        self.assertEqual(ecritures, [])


if __name__ == "__main__":
    unittest.main()
