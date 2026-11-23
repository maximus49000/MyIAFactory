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
import campagne  # noqa: E402
import serveur_tache  # noqa: E402
import tests_instantane  # noqa: E402
import tests_serveur  # noqa: E402


def garder_le_poste(test, autres=(tests_serveur.ATTENTES_SERVEUR,)):
    """Aucun test ne touche la vraie file ni le vrai verrou du poste (un test qui oubliait `attentes=` attendait derrière
    les vraies campagnes, sans fin) : les fonctions de `campagne` qui les lisent ou les écrivent refusent ces chemins."""
    reels = {Path(p).resolve() for p in (campagne.ATTENTES, campagne.VERROU, *autres)}
    for nom in ("_file", "_noter_l_attente", "_oublier_l_attente", "prendre", "liberer"):
        vrai = getattr(campagne, nom)

        def garde(chemin, *a, _vrai=vrai, _nom=nom, **k):
            if Path(chemin).resolve() in reels:
                raise AssertionError(f"campagne.{_nom} touche le vrai {chemin}")
            return _vrai(chemin, *a, **k)
        setattr(campagne, nom, garde)
        test.addCleanup(setattr, campagne, nom, vrai)

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
        self.appels_octets, self.appels_flux, self.nettoyages = [], [], []

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, _plus=()):
        if entree is None:                      # nettoyage au mieux
            self.nettoyages.append(commande)
            return 0, b"", ""
        donnees = entree.read()
        self.appels_octets.append({"hote": hote, "commande": commande, "cle": cle, "octets": donnees, "delai": delai,
                                   "plus": tuple(_plus)})
        r = self.depots.pop(0) if self.depots else (0, b"", "")
        if isinstance(r, BaseException):
            raise r
        return r

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

    def __init__(self, hors_limites=None, ecrire_leve=None, ecartes=(), deps=None):
        self.hors_limites, self.ecrire_leve = hors_limites, ecrire_leve
        self.ecartes, self.deps = list(ecartes), deps
        self.destinations = []
        self.executables_passes = None

    def lister(self, racine, git=None):
        if self.hors_limites:
            raise tests_instantane.HorsLimites(self.hors_limites)
        return ["a.py", "outils/x.py"], list(self.ecartes)

    def executables(self, racine, git=None):
        return {"outils/x.py"}

    def ecrire_tar(self, racine, fichiers, destination, executables=None):
        self.destinations.append(destination.name)
        self.executables_passes = set(executables or ())
        destination.write(b"un morceau d'archive")
        if isinstance(self.ecrire_leve, BaseException):
            raise self.ecrire_leve
        if self.ecrire_leve:
            raise tests_instantane.HorsLimites(self.ecrire_leve)
        return 2, 20

    def empreinte_verrou_node(self, racine):
        return self.deps


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
        garder_le_poste(self)

    def lancer(self, ssh, commande=("py", "-3.12", "-m", "unittest"), choisir=None, **k):
        def choisir_defaut(dossier, requises):
            self.requises = requises
            return SERVEUR
        options = dict(
            dossier=self.dossier, ssh=ssh, executer_poste=self.poste, noter=lambda *a, **kw: self.notes.append((a, kw)),
            horloge=lambda: 50.0, maintenant=lambda: self.mur[0], dire=lambda *a, **kw: self.dits.append(" ".join(a)),
            choisir=choisir or choisir_defaut, instantane=self.instantane, projet_de=lambda d: ("projet-a", Path(d)),
            injoignable=self.injoignable, attentes=self.attentes, sortie=io.BytesIO(), sortie_erreur=io.BytesIO(),
            nouvel_id=lambda: ID, dormir=lambda s: None, accord=lambda racine: None)
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
        self.assertIn(f"umask 077 && mkdir -p -- \"$HOME/tests\" && {{ mkdir -m 700 -- \"$HOME/tests/{ID}\" ||",
                      depot["commande"])
        self.assertIn(f"set -C && cat > \"$HOME/tests/{ID}\"/entree/entree.tar", depot["commande"])
        self.assertEqual(depot["octets"], b"un morceau d'archive")
        self.assertIn("ServerAliveInterval=15", depot["plus"])
        self.assertIn("ServerAliveCountMax=4", depot["plus"])
        self.assertEqual(depot["delai"], 120)
        flux = ssh.appels_flux[0]
        self.assertEqual(flux["commande"],
                         f"\"{tests_serveur.ENVELOPPE_DISTANTE}\" {ID} 2 4 8192 1800 projet-a -")
        self.assertTrue(tests_serveur.ENVELOPPE_DISTANTE.startswith("$HOME/"))
        self.assertEqual(json.loads(flux["premiere_ligne"]), ["python3", "outils/x.py", "a b;rm -rf ~"])
        self.assertIsNone(flux["delai_total"])
        self.assertEqual(self.instantane.executables_passes, {"outils/x.py"})
        # l'archive temporaire n'est jamais dans le projet, et elle est effacée à la fin
        chemin = self.instantane.destinations[0]
        self.assertFalse(os.path.abspath(chemin).startswith(os.path.abspath(self.dossier)))
        self.assertFalse(os.path.exists(chemin))
        self.assertFalse(os.path.exists(os.path.dirname(chemin)))
        self.assertEqual(ssh.nettoyages, [])

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


class TestCorrectifs(Base):
    def session(self, **champs):
        return dict({"code": 0, "octets": 0, "fin": "", "fin_serveur": (0, 100, 110, 0), "erreur": "", "code_ssh": 0,
                     "raison": "fin", "refus": None}, **champs)

    def test_r4_seulement_si_rien_du_conteneur(self):
        # rien reçu (connexion) : repli
        ssh = FauxSsh(sessions=[{"code": 255, "fin_serveur": None, "code_ssh": 255, "raison": "connexion"}])
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(len(self.poste.appels), 1)
        # seulement l'attente d'une place, aucun octet : repli
        def attente_seule(sortie, sur_attente, popen, sortie_erreur):
            sur_attente(1, 1)
            return self.session(code=255, fin_serveur=None, code_ssh=255, raison="perdue")
        self.assertEqual(self.lancer(FauxSsh(sessions=[attente_seule])), 0)
        self.assertEqual(len(self.poste.appels), 2)

    def test_session_perdue_apres_le_depart_ne_relance_rien(self):
        def sortie_vue(sortie, sur_attente, popen, sortie_erreur):
            sortie.write(b"debut\n")
            return self.session(code=255, octets=6, fin_serveur=None, code_ssh=255, raison="perdue")

        def erreur_vue(sortie, sur_attente, popen, sortie_erreur):
            sortie_erreur.write(b"| test_a ... ok\n")
            return self.session(code=255, fin_serveur=None, code_ssh=255, raison="perdue")
        for session in (sortie_vue, erreur_vue):
            with self.subTest(session=session.__name__):
                if self.injoignable.exists():
                    self.injoignable.unlink()
                self.assertEqual(self.lancer(FauxSsh(sessions=[session])), 1)
                self.assertEqual(self.poste.appels, [])
                self.assertTrue(self.dit("rien n'est relancé"))
                self.assertTrue(self.injoignable.exists())
        self.assertEqual(self.notes, [])

    def test_lecteur_d_erreur_encore_vivant(self):
        # marque non validée (lecteur pas fini) : fin_serveur None, ssh 0 → jamais un succès, jamais de repli
        ssh = FauxSsh(sessions=[{"code": 0, "octets": 50, "fin_serveur": None, "code_ssh": 0, "raison": "perdue"}])
        self.assertEqual(self.lancer(ssh), 1)
        self.assertEqual(self.poste.appels, [])

    def test_refus_qui_replient(self):
        for code in (78, 79, 125, 126, 127):
            with self.subTest(code=code):
                ssh = FauxSsh(sessions=[{"code": code, "fin_serveur": (code, 1, 2, 0), "refus": code}])
                n = len(self.poste.appels)
                self.assertEqual(self.lancer(ssh), 0)
                self.assertEqual(len(self.poste.appels), n + 1)
        self.assertEqual(self.notes, [])

    def test_arrets_au_serveur_sans_repli_et_notes(self):
        attendus = {74: "disque, inodes ou taille du dossier de travail", 130: "arrêtée au serveur (signal)",
                    124: "délai dépassé au serveur", 1: "l'enveloppe a échoué"}
        for code, texte in attendus.items():
            with self.subTest(code=code):
                self.dits.clear()
                self.notes.clear()
                ssh = FauxSsh(sessions=[{"code": code, "fin_serveur": (code, 100, 150, 0), "refus": code}])
                self.assertEqual(self.lancer(ssh), code)
                self.assertEqual(self.poste.appels, [])
                self.assertTrue(self.dit(texte), self.dits)
                self.assertEqual(len(self.notes), 1)
                self.assertEqual(self.notes[0][1]["code"], code)
                self.assertEqual(self.notes[0][1]["duree_s"], 50)

    def test_refus_2_nettoie_le_dossier_distant(self):
        ssh = FauxSsh(sessions=[{"code": 2, "fin_serveur": (2, 1, 2, 0), "refus": 2}])
        self.assertEqual(self.lancer(ssh), 2)
        self.assertEqual(ssh.nettoyages, [f"rm -rf -- \"$HOME/tests/{ID}\""])
        self.assertEqual(self.notes, [])

    def test_depot_refuse_nettoie_et_replie(self):
        ssh = FauxSsh(depots=[(1, b"", "No space left on device")])
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(ssh.nettoyages, [f"rm -rf -- \"$HOME/tests/{ID}\""])
        self.assertFalse(self.injoignable.exists())
        self.assertEqual(ssh.appels_flux, [])

    def test_identifiant_deja_pris_un_autre_est_tire(self):
        ids = iter(["t20261123-101500-aaaa", "t20261123-101500-bbbb"])
        ssh = FauxSsh(depots=[(73, b"", ""), (0, b"", "")])
        self.assertEqual(self.lancer(ssh, nouvel_id=lambda: next(ids)), 0)
        self.assertEqual(len(ssh.appels_octets), 2)
        self.assertIn("t20261123-101500-bbbb", ssh.appels_flux[0]["commande"])
        self.assertEqual(ssh.nettoyages, [])           # jamais l'effacement du dossier d'un autre

        ssh = FauxSsh(depots=[(73, b"", "")] * 5)
        self.assertEqual(self.lancer(ssh), 0)
        self.assertEqual(len(ssh.appels_octets), 5)
        self.assertEqual(ssh.appels_flux, [])
        self.assertEqual(len(self.poste.appels), 1)

    def test_messages_du_depot(self):
        cas = [("@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@", "clé d'hôte changée"),
               ("ubuntu@203.0.113.7: Permission denied (publickey).", "accès refusé")]
        for erreur, texte in cas:
            with self.subTest(texte=texte):
                if self.injoignable.exists():
                    self.injoignable.unlink()          # sinon le second essai est court-circuité par la mémoire
                self.assertEqual(self.lancer(FauxSsh(depots=[(255, b"", erreur)])), 0)
                self.assertTrue(self.dit(texte))

    def test_ctrl_c_pendant_le_depot(self):
        ssh = FauxSsh(depots=[(0xC000013A, b"", "")])
        self.assertEqual(self.lancer(ssh), 130)
        self.assertEqual(self.poste.appels, [])
        self.assertEqual(ssh.appels_flux, [])
        self.assertFalse(self.injoignable.exists())
        self.assertFalse(os.path.exists(os.path.dirname(self.instantane.destinations[0])))

    def test_interruption_pendant_instantane_ou_depot_efface_l_archive(self):
        self.instantane = FauxInstantane(ecrire_leve=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.lancer(FauxSsh())
        self.assertFalse(os.path.exists(os.path.dirname(self.instantane.destinations[0])))
        self.instantane = FauxInstantane()
        with self.assertRaises(KeyboardInterrupt):
            self.lancer(FauxSsh(depots=[KeyboardInterrupt()]))
        self.assertFalse(os.path.exists(os.path.dirname(self.instantane.destinations[0])))
        self.assertEqual(self.poste.appels, [])

    def test_validations_avant_tout_envoi(self):
        cas = [dict(places=5), dict(places=0), dict(places=True), dict(places="2"),
               dict(nouvel_id=lambda: "../x"), dict(nouvel_id=lambda: f"{ID};rm"),
               dict(projet_de=lambda d: ("../Projet", Path(d))), dict(projet_de=lambda d: None)]
        for options in cas:
            with self.subTest(options=options):
                ssh = FauxSsh()
                n = len(self.poste.appels)
                self.assertEqual(self.lancer(ssh, **options), 0)
                self.assertEqual(ssh.appels_octets + ssh.appels_flux, [])
                self.assertEqual(len(self.poste.appels), n + 1)
        for deps in ("zz", "0123456789abcdef; rm", "ABCDEF0123456789"):
            with self.subTest(deps=deps):
                self.instantane = FauxInstantane(deps=deps)
                ssh = FauxSsh()
                self.lancer(ssh)
                self.assertEqual(ssh.appels_octets + ssh.appels_flux, [])
        self.instantane = FauxInstantane(deps="0123456789abcdef")
        ssh = FauxSsh()
        self.lancer(ssh)
        self.assertTrue(ssh.appels_flux[0]["commande"].endswith(" projet-a 0123456789abcdef"))

    def test_ecartes_dits_en_une_ligne(self):
        self.instantane = FauxInstantane(ecartes=[f"f{i} (lien)" for i in range(12)])
        self.lancer(FauxSsh())
        lignes = [d for d in self.dits if "écarté" in d]
        self.assertEqual(len(lignes), 1)
        self.assertIn("12 fichier(s)", lignes[0])
        self.assertIn("f9 (lien)", lignes[0])
        self.assertNotIn("f10 (lien)", lignes[0])

    def test_mesure_qui_casse_ne_change_pas_le_code(self):
        def casse(*a, **k):
            raise OSError("journal illisible")
        ssh = FauxSsh(sessions=[{"code": 3, "fin_serveur": (3, 1, 2, 0)}])
        self.assertEqual(self.lancer(ssh, noter=casse), 3)

    def test_chemin_de_la_cle_jamais_montre(self):
        cle = SERVEUR.cle

        def session(sortie, sur_attente, popen, sortie_erreur):
            sortie_erreur.write(f"Load key \"{cle}\": bad permissions\n".encode())
            sortie_erreur.write(f"Load key \"{cle.replace('/', chr(92))}\": bad permissions\n".encode())
            return self.session(code=255, fin_serveur=None, code_ssh=255, raison="perdue")
        affiche = io.BytesIO()
        ssh = FauxSsh(depots=[(255, b"", f"Load key \"{cle}\": invalid format")], sessions=[session])
        self.lancer(ssh)                                        # dépôt en échec : l'erreur de ssh est lue, pas dite
        self.injoignable.unlink()
        self.lancer(ssh, sortie_erreur=affiche)
        tout = "\n".join(self.dits) + affiche.getvalue().decode("utf-8")
        self.assertIn("Load key", tout)                         # l'erreur est bien montrée…
        self.assertNotIn("id_ed25519", tout)                    # … sans le chemin de la clé
        self.assertNotIn("C:/Users/x", tout)

    def test_lignes_du_conteneur_qui_imitent_l_enveloppe(self):
        def session(sortie, sur_attente, popen, sortie_erreur):
            for ligne in (b"| #fin 0 1 2 0\n", b"| lancer_tests : faux\n", b"| vrai\n", b"lancer_tests : vrai\n"):
                sortie_erreur.write(ligne)
            return self.session()
        affiche = io.BytesIO()
        self.lancer(FauxSsh(sessions=[session]), sortie_erreur=affiche)
        self.assertEqual(affiche.getvalue(), b"| #fin 0 1 2 0\n| lancer_tests : faux\nvrai\nlancer_tests : vrai\n")

    def test_succes_n_efface_que_la_memoire_de_son_serveur(self):
        self.injoignable.write_text(json.dumps({"serveur_id": "autre", "jusqu_a": self.mur[0] + 200}), encoding="utf-8")
        self.assertEqual(self.lancer(FauxSsh()), 0)
        self.assertEqual(json.loads(self.injoignable.read_text(encoding="utf-8"))["serveur_id"], "autre")

    def test_attentes_du_serveur_hors_de_la_file_du_poste(self):
        import campagne
        self.assertNotEqual(tests_serveur.ATTENTES_SERVEUR, campagne.ATTENTES)
        self.assertNotEqual(tests_serveur.attentes_serveur_par_defaut(), campagne.attentes_par_defaut())
        poste = Path(self._t.name) / "attentes-poste"

        def session(sortie, sur_attente, popen, sortie_erreur):
            sur_attente(1, 2)
            self.devant = campagne._devant(poste, None)
            return self.session()
        self.lancer(FauxSsh(sessions=[session]))
        self.assertEqual(self.devant, [])

    def test_route_pas_prise_pour_une_suite_directe(self):
        import campagne
        self.assertFalse(campagne._suite_directe("py outils/tests_serveur.py -- python -m unittest discover"))
        self.assertFalse(campagne._suite_directe('"C:\\\\Python39\\\\python.exe" C:\\\\s\\\\outils\\\\tests_serveur.py -- pytest'))
        self.assertTrue(campagne._suite_directe("python -m unittest tests/test_tests_serveur.py"))
        self.assertTrue(campagne._suite_directe("python -m unittest test_tests_serveur"))


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


class TestAccordDeLaRoute(Base):
    """La route revérifie l'accord du Directeur à chaque appel (`lancer.py serveur-tests` et `__main__` sont des
    portes) ; `--serveur` force la route, jamais l'accord."""

    def test_sans_accord_le_poste_sans_aucune_connexion(self):
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, accord=lambda racine: "non réglé"), 0)
        self.assertEqual((ssh.appels_octets, ssh.appels_flux), ([], []))
        self.assertEqual(len(self.poste.appels), 1)
        self.assertTrue(self.dit("non réglé"))

    def test_sans_accord_serveur_force_code_2(self):
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, accord=lambda racine: "non réglé", forcer=True), 2)
        self.assertEqual((ssh.appels_octets, ssh.appels_flux, self.poste.appels), ([], [], []))

    def test_accord_juge_sur_le_dossier_resolu_par_refus_route(self):
        from bureau import deport_types
        vus = []
        ancien = deport_types.refus_route
        deport_types.refus_route = lambda racine, action, bureau=None: vus.append((racine, action)) or "non"
        self.addCleanup(setattr, deport_types, "refus_route", ancien)
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, accord=None), 0)
        self.assertEqual(vus, [(str(Path(self.dossier).resolve()), "tests")])
        self.assertEqual(ssh.appels_flux, [])

    def test_accord_qui_leve_est_un_refus(self):
        from bureau import deport_types
        ancien = deport_types.refus_route

        def casse(*a, **k):
            raise RuntimeError("x")
        deport_types.refus_route = casse
        self.addCleanup(setattr, deport_types, "refus_route", ancien)
        self.assertIn("accord illisible", tests_serveur._refus_par_defaut(self.dossier))

    def test_file_du_serveur_isolee_dans_un_processus_de_test(self):
        from unittest import mock
        isole = Path(self._t.name) / "etat"
        with mock.patch.object(campagne, "isole", lambda: True), \
                mock.patch.object(campagne, "dossier_etat", lambda: isole):
            self.assertEqual(tests_serveur.attentes_serveur_par_defaut(), isole / tests_serveur.ATTENTES_SERVEUR.name)
        with mock.patch.object(campagne, "isole", lambda: False):
            self.assertEqual(tests_serveur.attentes_serveur_par_defaut(), tests_serveur.ATTENTES_SERVEUR)
        self.assertIsNone(tests_serveur.executer.__kwdefaults__["attentes"])      # résolu à l'appel


if __name__ == "__main__":
    unittest.main()
