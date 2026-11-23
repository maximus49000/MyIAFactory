"""La route serveur des campagnes de tests (`outils/tests_serveur.py`) : règles de repli R1–R5, mémoire de
l'injoignable (300 s), jamais de repli après un test en échec ou un Ctrl-C, `--serveur` sans repli, mesure `lieu=serveur`.
Tout est faux : `ssh` (objet), `choisir`, `instantane`, `executer_poste`, horloges ; aucun sous-processus, aucun réseau."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import serveur_tache  # noqa: E402
import tests_instantane  # noqa: E402
import tests_serveur  # noqa: E402

SERVEUR = SimpleNamespace(id="ovh-1", nom="OVH", hote="203.0.113.7", utilisateur="ubuntu",
                          cle="C:/Users/x/.ssh/id_ed25519_myiafactory")
ID = "t20261123-101500-ab12"


class FauxProcessus:
    def __init__(self):
        self.tue = False

    def kill(self):
        self.tue = True


class FauxSsh:
    """`executer_octets` (dépôt) et `executer_en_flux` (session) ; chaque réponse est prise dans une file."""

    def __init__(self, depots=(), sessions=()):
        self.depots, self.sessions = list(depots), list(sessions)
        self.appels_octets, self.appels_flux = [], []

    def executer_octets(self, hote, commande, cle, entree=None, delai=60):
        donnees = entree.read() if hasattr(entree, "read") else entree
        self.appels_octets.append({"hote": hote, "commande": commande, "cle": cle, "octets": donnees, "delai": delai,
                                   "chemin": getattr(entree, "name", None)})
        return self.depots.pop(0) if self.depots else (0, b"", "")

    def executer_en_flux(self, hote, commande, cle, premiere_ligne, sortie, sur_attente=None, delai_connexion=30,
                         popen=None, sortie_erreur=None, delai_total=None, delai_silence=None):
        self.appels_flux.append({"hote": hote, "commande": commande, "cle": cle, "premiere_ligne": premiere_ligne,
                                 "delai_total": delai_total})
        s = self.sessions.pop(0) if self.sessions else {}
        if isinstance(s, BaseException):
            raise s
        if callable(s):
            return s(sortie=sortie, sur_attente=sur_attente, popen=popen, sortie_erreur=sortie_erreur)
        return dict({"code": 0, "octets": 0, "fin": "", "fin_serveur": (0, 100, 110, 0), "erreur": "",
                     "code_ssh": 0, "raison": "fin", "refus": None}, **s)


class FauxInstantane:
    HorsLimites = tests_instantane.HorsLimites

    def __init__(self, hors_limites=None, ecrire_leve=None):
        self.hors_limites, self.ecrire_leve = hors_limites, ecrire_leve
        self.destinations = []
        self.executables_passes = None

    def lister(self, racine, git=None):
        if self.hors_limites:
            raise tests_instantane.HorsLimites(self.hors_limites)
        return ["a.py", "outils/x.py"], []

    def executables(self, racine, git=None):
        return {"outils/x.py"}

    def ecrire_tar(self, racine, fichiers, destination, executables=None):
        self.destinations.append(destination.name)
        self.executables_passes = set(executables or ())
        destination.write(b"un morceau d'archive")
        if self.ecrire_leve:
            raise tests_instantane.HorsLimites(self.ecrire_leve)
        return 2, 20

    def empreinte_verrou_node(self, racine):
        return None


class Poste:
    def __init__(self, code=0):
        self.appels, self.code = [], code

    def __call__(self, commande, dossier=None, attendre=True):
        self.appels.append((list(commande), dossier, attendre))
        return self.code


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = os.path.join(self._t.name, "projet")
        os.mkdir(self.dossier)
        self.injoignable = Path(self._t.name) / "tests-serveur-injoignable.json"
        self.attentes = Path(self._t.name) / "tests-en-attente"
        self.poste = Poste()
        self.notes = []
        self.dits = []
        self.mur = [1_000_000.0]
        self.instantane = FauxInstantane()

    def lancer(self, ssh, commande=("py", "-3.12", "-m", "unittest"), choisir=None, **k):
        def choisir_defaut(dossier, requises):
            self.requises = requises
            return SERVEUR
        options = dict(
            dossier=self.dossier, ssh=ssh, executer_poste=self.poste, noter=lambda *a, **kw: self.notes.append((a, kw)),
            horloge=lambda: 50.0, maintenant=lambda: self.mur[0], dire=lambda *a, **kw: self.dits.append(" ".join(a)),
            choisir=choisir or choisir_defaut, instantane=self.instantane, projet_de=lambda d: ("projet-a", Path(d)),
            injoignable=self.injoignable, attentes=self.attentes, sortie=io.BytesIO(), sortie_erreur=io.BytesIO(),
            nouvel_id=lambda: ID)
        options.update(k)
        return tests_serveur.executer(list(commande), **options)

    def dit(self, texte):
        return any(texte in d for d in self.dits)


class TestRoute(Base):
    def test_campagne_au_serveur_rend_le_code_et_note(self):
        ssh = FauxSsh(sessions=[{"code": 1, "fin_serveur": (1, 100, 290, 12), "code_ssh": 1}])
        self.assertEqual(self.lancer(ssh), 1)
        self.assertEqual(self.poste.appels, [])
        self.assertEqual(len(self.notes), 1)
        a, kw = self.notes[0]
        self.assertEqual(kw["lieu"], "serveur")
        self.assertEqual(kw["duree_s"], 190)
        self.assertAlmostEqual(kw["attente_s"], 12, delta=1)
        self.assertEqual(kw["code"], 1)
        self.assertEqual(self.requises, ("tests-image",))

    def test_commande_distante_et_premiere_ligne(self):
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, commande=("py", "-3.12", "outils/x.py", "a b;rm -rf ~")), 0)
        depot = ssh.appels_octets[0]
        self.assertEqual(depot["hote"], "ubuntu@203.0.113.7")
        self.assertIn(f"install -d -m 700 \"$HOME/tests/{ID}/entree\"", depot["commande"])
        self.assertIn(f"\"$HOME/tests/{ID}/entree/entree.tar\"", depot["commande"])
        self.assertEqual(depot["octets"], b"un morceau d'archive")
        flux = ssh.appels_flux[0]
        self.assertEqual(flux["commande"], f"{tests_serveur.ENVELOPPE_DISTANTE} {ID} 2 4 8192 1800 projet-a -")
        self.assertEqual(json.loads(flux["premiere_ligne"]), ["python3", "outils/x.py", "a b;rm -rf ~"])
        self.assertIsNone(flux["delai_total"])
        self.assertEqual(self.instantane.executables_passes, {"outils/x.py"})
        # l'archive temporaire n'est jamais dans le projet, et elle est effacée à la fin
        chemin = self.instantane.destinations[0]
        self.assertFalse(os.path.abspath(chemin).startswith(os.path.abspath(self.dossier)))
        self.assertFalse(os.path.exists(chemin))
        self.assertFalse(os.path.exists(os.path.dirname(chemin)))
        # la clé n'apparaît jamais dans ce qui est dit
        self.assertFalse(any("id_ed25519" in d for d in self.dits))

    def test_sortie_d_erreur_montree_sans_prefixe_et_mesuree(self):
        def session(sortie, sur_attente, popen, sortie_erreur):
            sortie.write(b"bonjour\n")
            for ligne in (b"| ..\n", b"| Ran 7 tests in 0.2s\n", b"| \n", b"| OK\n"):
                sortie_erreur.write(ligne)
            return {"code": 0, "octets": 8, "fin": "bonjour\n", "fin_serveur": (0, 10, 20, 0),
                    "erreur": "| ..\n| Ran 7 tests in 0.2s\n| \n| OK\n", "code_ssh": 0, "raison": "fin",
                    "refus": None}
        affiche = io.BytesIO()
        self.assertEqual(self.lancer(FauxSsh(sessions=[session]), sortie_erreur=affiche), 0)
        self.assertEqual(affiche.getvalue(), b"..\nRan 7 tests in 0.2s\n\nOK\n")
        kw = self.notes[0][1]
        from bureau import tests_mesures
        self.assertEqual(tests_mesures.nb_tests_de(kw["fin"]), 7)

    def test_commande_conteneur(self):
        c = tests_serveur.commande_conteneur
        self.assertEqual(c(["py", "-3.12", "outils/x.py"]), ["python3", "outils/x.py"])
        self.assertEqual(c(["npx.cmd", "vitest", "run"]), ["npx", "vitest", "run"])
        self.assertEqual(c(["npm.cmd", "test"]), ["npm", "test"])
        self.assertEqual(c(["python.exe", "-m", "unittest"]), ["python3", "-m", "unittest"])
        self.assertEqual(c(["python", "x.py", "py"]), ["python3", "x.py", "py"])
        self.assertEqual(c(["node", "x.js"]), ["node", "x.js"])

    def test_attente_d_une_place_notee_puis_retiree(self):
        vu = {}

        def session(sortie, sur_attente, popen, sortie_erreur):
            sur_attente(2, 3)
            notes = list(self.attentes.glob("*.json"))
            vu["motif"] = json.loads(notes[0].read_text(encoding="utf-8"))["motif"] if notes else None
            return {"code": 0, "fin_serveur": (0, 10, 20, 5), "raison": "fin", "refus": None, "fin": "", "erreur": "",
                    "octets": 0, "code_ssh": 0}
        self.assertEqual(self.lancer(FauxSsh(sessions=[session])), 0)
        self.assertEqual(vu["motif"], "place de tests au serveur (rang 2/3)")
        self.assertEqual(list(self.attentes.glob("*.json")), [])

    def test_sans_attendre_places_prises_rend_3(self):
        etat = {}

        def session(sortie, sur_attente, popen, sortie_erreur):
            p = popen(["ssh"])
            etat["p"] = p
            sur_attente(1, 2)
            return {"code": 255, "fin_serveur": None, "raison": "perdue", "refus": None, "fin": "", "erreur": "",
                    "octets": 0, "code_ssh": 255}
        tests_serveur_popen = lambda *a, **k: FauxProcessus()  # noqa: E731
        self.assertEqual(self.lancer(FauxSsh(sessions=[session]), attendre=False, _popen=tests_serveur_popen), 3)
        self.assertTrue(etat["p"].tue)
        self.assertEqual(self.poste.appels, [])
        self.assertEqual(self.notes, [])
        self.assertFalse(self.injoignable.exists())


class TestRepli(Base):
    def test_repli_r1_aucun_serveur_pret(self):
        def refus(dossier, requises):
            raise serveur_tache.RefusLancement("Aucun serveur prêt.")
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, choisir=refus), 0)
        self.assertEqual(len(self.poste.appels), 1)
        self.assertTrue(self.dit("tests au poste"))
        self.assertEqual(ssh.appels_octets + ssh.appels_flux, [])

    def test_repli_r2_depot_injoignable(self):
        ssh = FauxSsh(depots=[(255, b"", "ssh: connect to host: Connection timed out")])
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(len(self.poste.appels), 1)
        self.assertEqual(ssh.appels_flux, [])
        memo = json.loads(self.injoignable.read_text(encoding="utf-8"))
        self.assertEqual(memo["serveur_id"], "ovh-1")
        self.assertEqual(memo["jusqu_a"], self.mur[0] + 300)

    def test_injoignable_memorise_300_s(self):
        ssh = FauxSsh(depots=[(124, b"", "délai"), (0, b"", "")])
        self.lancer(ssh)
        self.assertEqual(len(ssh.appels_octets), 1)
        self.mur[0] += 100
        self.lancer(ssh)
        self.assertEqual(len(ssh.appels_octets), 1)        # aucun appel ssh
        self.assertEqual(ssh.appels_flux, [])
        self.assertEqual(len(self.poste.appels), 2)
        self.mur[0] += 201                                  # 301 s après
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(len(ssh.appels_octets), 2)
        self.assertEqual(len(ssh.appels_flux), 1)
        self.assertEqual(len(self.poste.appels), 2)
        self.assertFalse(self.injoignable.exists())          # succès au serveur : mémoire effacée

    def test_memoire_d_un_autre_serveur_ou_hors_bornes_ignoree(self):
        self.injoignable.write_text(json.dumps({"serveur_id": "autre", "jusqu_a": self.mur[0] + 200}), encoding="utf-8")
        ssh = FauxSsh()
        self.lancer(ssh)
        self.assertEqual(len(ssh.appels_flux), 1)
        self.injoignable.write_text(json.dumps({"serveur_id": "ovh-1", "jusqu_a": self.mur[0] + 10_000}),
                                    encoding="utf-8")
        self.lancer(ssh)
        self.assertEqual(len(ssh.appels_flux), 2)

    def test_repli_r3_disque_ou_image(self):
        for code in (76, 77):
            with self.subTest(code=code):
                self.poste.appels.clear()
                ssh = FauxSsh(sessions=[{"code": code, "fin_serveur": (code, 1, 2, 0), "refus": code}])
                self.assertEqual(self.lancer(ssh), 0)
                self.assertEqual(len(self.poste.appels), 1)
                self.assertFalse(self.injoignable.exists())
        self.assertEqual(self.notes, [])

    def test_code_76_77_du_test_lui_meme_sans_repli(self):
        for code in (76, 77, 70, 2):
            with self.subTest(code=code):
                ssh = FauxSsh(sessions=[{"code": code, "fin_serveur": (code, 1, 2, 0), "refus": None}])
                self.assertEqual(self.lancer(ssh), code)
        self.assertEqual(self.poste.appels, [])

    def test_refus_d_argument_sans_repli(self):
        ssh = FauxSsh(sessions=[{"code": 2, "fin_serveur": (2, 1, 2, 0), "refus": 2}])
        self.assertEqual(self.lancer(ssh), 2)
        self.assertEqual(self.poste.appels, [])

    def test_repli_r4_session_perdue(self):
        ssh = FauxSsh(sessions=[{"code": 255, "fin_serveur": None, "code_ssh": 255, "raison": "perdue"}])
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(len(self.poste.appels), 1)
        self.assertTrue(self.injoignable.exists())
        self.injoignable.unlink()
        ssh = FauxSsh(sessions=[{"code": 255, "fin_serveur": (255, 1, 2, 0), "code_ssh": 255}])
        self.assertEqual(self.lancer(ssh), 255)
        self.assertEqual(len(self.poste.appels), 1)

    def test_fin_absente_sans_code_de_connexion_jamais_un_succes(self):
        ssh = FauxSsh(sessions=[{"code": 0, "fin_serveur": None, "code_ssh": 0, "raison": "perdue"}])
        self.assertNotEqual(self.lancer(ssh), 0)
        self.assertEqual(self.poste.appels, [])

    def test_ssh_tue_par_ctrl_c_ne_replie_pas(self):
        ssh = FauxSsh(sessions=[{"code": 0xC000013A, "fin_serveur": None, "code_ssh": 0xC000013A, "raison": "perdue"}])
        self.assertEqual(self.lancer(ssh), 130)
        self.assertEqual(self.poste.appels, [])

    def test_repli_r5_hors_limites(self):
        self.instantane = FauxInstantane(ecrire_leve="200 Mo dépassés")
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(len(self.poste.appels), 1)
        self.assertEqual(ssh.appels_octets, [])
        self.assertFalse(os.path.exists(self.instantane.destinations[0]))
        self.instantane = FauxInstantane(hors_limites="le projet n'est pas un dépôt git")
        self.assertEqual(self.lancer(FauxSsh()), 0)
        self.assertEqual(len(self.poste.appels), 2)
        self.assertTrue(self.dit("pas un dépôt git"))

    def test_jamais_de_repli_apres_echec_de_test(self):
        ssh = FauxSsh(sessions=[{"code": 1, "fin_serveur": (1, 1, 2, 0)}])
        self.assertEqual(self.lancer(ssh), 1)
        self.assertEqual(self.poste.appels, [])

    def test_interruption_ne_replie_pas(self):
        ssh = FauxSsh(sessions=[KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            self.lancer(ssh)
        self.assertEqual(self.poste.appels, [])
        self.assertEqual(self.notes, [])

    def test_forcer_sans_repli(self):
        ssh = FauxSsh(depots=[(255, b"", "refusé")])
        self.assertEqual(self.lancer(ssh, forcer=True), 4)
        self.assertEqual(self.poste.appels, [])

    def test_repli_dit_une_ligne_et_passe_au_poste_une_fois(self):
        ssh = FauxSsh(depots=[(255, b"", "")])
        self.lancer(ssh, commande=("npx.cmd", "vitest"), attendre=False)
        self.assertEqual(self.poste.appels, [(["npx.cmd", "vitest"], self.dossier, False)])
        lignes = [d for d in self.dits if "tests au poste" in d]
        self.assertEqual(len(lignes), 1)
        self.assertTrue(lignes[0].startswith("Serveur "))
        self.assertTrue(lignes[0].endswith(": tests au poste (une campagne à la fois)."))


class TestMain(unittest.TestCase):
    def test_options(self):
        vu = {}

        def faux(commande, **k):
            vu.update(k, commande=commande)
            return 5
        self.assertEqual(tests_serveur.main(["--dossier", "D", "--sans-attendre", "--serveur", "--", "py", "x"],
                                            executer=faux), 5)
        self.assertEqual(vu, {"commande": ["py", "x"], "dossier": "D", "attendre": False, "forcer": True})
        self.assertEqual(tests_serveur.main(["--", ], executer=faux), 2)
        self.assertEqual(tests_serveur.main(["--inconnue", "--", "x"], executer=faux), 2)

        def interrompu(commande, **k):
            raise KeyboardInterrupt
        self.assertEqual(tests_serveur.main(["--", "x"], executer=interrompu), 130)


if __name__ == "__main__":
    unittest.main()
