"""Lecture de l'état d'un serveur distant (`outils/serveur_etat.py`). SSH factice : aucune connexion réelle."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import plateforme_ssh  # noqa: E402
import serveur_etat  # noqa: E402
from serveur_capacites import CATALOGUE  # noqa: E402
from serveur_modele import Serveur  # noqa: E402

SERVEUR = Serveur("srv", "Serveur", "203.0.113.7", "factory", "cle-privee")
MUTANTS = re.compile(r"\b(apt|apt-get|rm|systemctl|tee|mv|chmod|usermod|install|dpkg|curl|wget)\b")


class FauxSsh:
    """Remplace le module `plateforme_ssh` : enregistre les appels, rend une réponse programmée."""
    ErreurSsh = plateforme_ssh.ErreurSsh
    CHANGEMENT_CLE = plateforme_ssh.CHANGEMENT_CLE
    _verifier_hote = staticmethod(plateforme_ssh._verifier_hote)

    def __init__(self, reponse=(0, "", ""), erreur=None):
        self.reponse, self.erreur, self.appels = reponse, erreur, []

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        self.appels.append({"hote": hote, "commande": commande, "cle": cle, "stdin": stdin})
        if self.erreur:
            raise self.erreur
        return self.reponse


def sortie_complete(valeurs=None):
    valeurs = valeurs or {}
    return "\n".join(f"{i}={valeurs.get(i, 1)}" for i in CATALOGUE) + "\n"


class TestSonder(unittest.TestCase):
    def test_une_seule_connexion_pour_toutes_les_sondes(self):
        ssh = FauxSsh((0, sortie_complete({"base": 0, "unity-cli": 0}), ""))
        etat = serveur_etat.sonder(SERVEUR, ssh=ssh)
        self.assertEqual(len(ssh.appels), 1)
        self.assertEqual(set(etat), set(CATALOGUE))
        self.assertEqual(etat["base"], "presente")
        self.assertEqual(etat["unity-cli"], "presente")
        self.assertEqual(etat["agent"], "absente")
        self.assertEqual(ssh.appels[0]["hote"], "factory@203.0.113.7")
        self.assertEqual(ssh.appels[0]["commande"], "bash -s")
        for cap in CATALOGUE.values():
            self.assertIn(cap.sonde, ssh.appels[0]["stdin"])
            self.assertIn(f'echo "{cap.id}=', ssh.appels[0]["stdin"])

    def test_chaque_sonde_dans_son_sous_shell_sans_lecture_de_stdin(self):
        ssh = FauxSsh((0, sortie_complete(), ""))
        serveur_etat.sonder(SERVEUR, ssh=ssh)
        lignes = [l for l in ssh.appels[0]["stdin"].splitlines() if l.strip()]
        self.assertEqual(len(lignes), len(CATALOGUE))
        for l in lignes:
            self.assertTrue(l.startswith("( "), l)
            self.assertIn("</dev/null", l)

    def test_ssh_coupe_donne_inconnue_pas_absente(self):
        for reponse in ((255, "", "Connection refused"), (124, "", "délai"), (0, "", ""), (1, sortie_complete(), "")):
            etat = serveur_etat.sonder(SERVEUR, ssh=FauxSsh(reponse))
            self.assertEqual(set(etat), set(CATALOGUE))
            self.assertEqual(set(etat.values()), {"inconnue"}, reponse)

    def test_exception_ssh_donne_inconnue_sans_lever(self):
        for erreur in (plateforme_ssh.ErreurSsh("absent"), OSError("boum"), ValueError("hôte")):
            etat = serveur_etat.sonder(SERVEUR, ssh=FauxSsh(erreur=erreur))
            self.assertEqual(set(etat.values()), {"inconnue"})

    def test_sortie_illisible_donne_inconnue(self):
        for sortie in ("n'importe quoi", "base=oui\nunity-cli=2\n", "\x00\xff", None):
            etat = serveur_etat.sonder(SERVEUR, ssh=FauxSsh((0, sortie, "")))
            self.assertEqual(set(etat.values()), {"inconnue"}, sortie)

    def test_identifiant_manquant_inconnu_et_lignes_etrangeres_ignorees(self):
        sortie = "bruit de bienvenue\n" + sortie_complete({"base": 0}).replace("agent=1\n", "") + "extra=0\n"
        etat = serveur_etat.sonder(SERVEUR, ssh=FauxSsh((0, sortie, "")))
        self.assertEqual(etat["agent"], "inconnue")
        self.assertEqual(etat["base"], "presente")
        self.assertEqual(etat["unity-cli"], "absente")
        self.assertNotIn("extra", etat)

    def test_lignes_contradictoires_donnent_inconnue(self):
        etat = serveur_etat.sonder(SERVEUR, ssh=FauxSsh((0, sortie_complete() + "base=0\n", "")))
        self.assertEqual(etat["base"], "inconnue")
        self.assertEqual(etat["unity-cli"], "absente")

    def test_aucune_commande_mutante_envoyee(self):
        ssh = FauxSsh((0, sortie_complete(), ""))
        serveur_etat.sonder(SERVEUR, ssh=ssh)
        serveur_etat.refus_acces(SERVEUR, ssh=ssh)
        serveur_etat.charge(SERVEUR, ssh=ssh)
        self.assertEqual(len(ssh.appels), 3)
        for appel in ssh.appels:
            self.assertIsNone(MUTANTS.search(appel["commande"]), appel["commande"])
            self.assertIsNone(MUTANTS.search(appel["stdin"]), appel["stdin"])

    def test_hote_invalide_refuse_avant_tout_appel(self):
        ssh = FauxSsh((0, sortie_complete(), ""))
        for hote in ("-oProxyCommand=x", "", "a b", "h;rm -rf /"):
            mauvais = Serveur("x", "x", hote, "factory", "cle")
            etat = serveur_etat.sonder(mauvais, ssh=ssh)
            self.assertEqual(set(etat.values()), {"inconnue"})
            self.assertIsNotNone(serveur_etat.refus_acces(mauvais, ssh=ssh))
            self.assertIsNone(serveur_etat.charge(mauvais, ssh=ssh))
        self.assertEqual(ssh.appels, [])

    def test_runner_transmis_a_ssh_seulement_si_fourni(self):
        class Espion(FauxSsh):
            def executer(self, *a, **kw):
                self.kw = kw
                return super().executer(*a, **kw)
        ssh = Espion((0, sortie_complete(), ""))
        serveur_etat.sonder(SERVEUR, ssh=ssh)
        self.assertNotIn("runner", ssh.kw)
        marque = object()
        serveur_etat.sonder(SERVEUR, ssh=ssh, runner=marque)
        self.assertIs(ssh.kw["runner"], marque)


class TestCibleStricte(unittest.TestCase):
    def test_cible_refuse_un_retour_a_la_ligne_final(self):
        for hote, utilisateur in (("h\n", "factory"), ("203.0.113.7", "u\n"), ("a$b", "factory")):
            with self.subTest(hote=hote, utilisateur=utilisateur):
                with self.assertRaises(ValueError):
                    serveur_etat.cible(Serveur("srv", "S", hote, utilisateur, "cle-privee"))
        self.assertEqual(serveur_etat.cible(SERVEUR), "factory@203.0.113.7")


class TestRefusAcces(unittest.TestCase):
    def test_acces_correct(self):
        ssh = FauxSsh((0, "user=factory\nsudo=0\n", ""))
        self.assertIsNone(serveur_etat.refus_acces(SERVEUR, ssh=ssh))
        self.assertEqual(len(ssh.appels), 1)

    def test_refus_acces_root_et_sudo_a_mot_de_passe(self):
        root = serveur_etat.refus_acces(SERVEUR, ssh=FauxSsh((0, "user=root\nsudo=0\n", "")))
        self.assertIn("sudo", root)
        self.assertIn("utilisateur", root)
        mdp = serveur_etat.refus_acces(SERVEUR, ssh=FauxSsh((0, "user=factory\nsudo=1\n", "")))
        self.assertIn("sans mot de passe", mdp)

    def test_ssh_impossible(self):
        msg = serveur_etat.refus_acces(SERVEUR, ssh=FauxSsh((255, "", "Permission denied (publickey)")))
        self.assertIn("SSH", msg)
        self.assertIn("203.0.113.7", msg)
        msg = serveur_etat.refus_acces(SERVEUR, ssh=FauxSsh(erreur=plateforme_ssh.ErreurSsh("client absent")))
        self.assertIn("SSH", msg)

    def test_changement_de_cle_conseille_ssh_keygen_sans_oublier_seul(self):
        ssh = FauxSsh((255, "", "@@@ WARNING: REMOTE " + plateforme_ssh.CHANGEMENT_CLE + "! @@@"))
        msg = serveur_etat.refus_acces(SERVEUR, ssh=ssh)
        self.assertIn("ssh-keygen -R 203.0.113.7", msg)
        self.assertEqual(len(ssh.appels), 1)

    def test_sortie_illisible_refuse(self):
        self.assertIsNotNone(serveur_etat.refus_acces(SERVEUR, ssh=FauxSsh((0, "bruit", ""))))


LOADAVG = "load=2.00\ncpu=4\nmemtotal=8000000\nmemlibre=2000000\nconteneurs=3\n"


class TestCharge(unittest.TestCase):
    def test_valeurs(self):
        ssh = FauxSsh((0, LOADAVG, ""))
        self.assertEqual(serveur_etat.charge(SERVEUR, ssh=ssh),
                         {"charge_par_coeur": 0.5, "memoire_libre_ratio": 0.25, "conteneurs_outils": 3})
        self.assertEqual(len(ssh.appels), 1)

    def test_inatteignable_ou_illisible_donne_none(self):
        for rep in ((255, "", "x"), (124, "", ""), (0, "", ""), (0, "load=a\ncpu=4\n", ""),
                    (0, LOADAVG.replace("cpu=4", "cpu=0"), ""), (0, LOADAVG.replace("memtotal=8000000", "memtotal=0"), ""),
                    (0, LOADAVG.replace("load=2.00", "load=nan"), "")):
            self.assertIsNone(serveur_etat.charge(SERVEUR, ssh=FauxSsh(rep)), rep)
        self.assertIsNone(serveur_etat.charge(SERVEUR, ssh=FauxSsh(erreur=plateforme_ssh.ErreurSsh("x"))))

    def test_script_tolere_docker_absent(self):
        ssh = FauxSsh((0, LOADAVG, ""))
        serveur_etat.charge(SERVEUR, ssh=ssh)
        self.assertIn("docker ps -q 2>/dev/null", ssh.appels[0]["stdin"])
        self.assertIn("wc -l", ssh.appels[0]["stdin"])


class TestHygiene(unittest.TestCase):
    def test_aucune_mention_du_fournisseur(self):
        source = (Path(__file__).resolve().parent.parent / "outils" / "serveur_etat.py").read_text(encoding="utf-8")
        self.assertNotIn("ovh", source.lower())


if __name__ == "__main__":
    unittest.main()
