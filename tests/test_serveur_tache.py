"""Demande de tâche et index du poste (`outils/serveur_tache.py`). Dossier temporaire : jamais le vrai ~/MyIAFactory."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import plateforme_ssh  # noqa: E402
import serveur_tache as st  # noqa: E402


def brut(**plus):
    return {"type": "emulation", "projet": "demo", "mode": "scenario", "scenario": "demarrage", **plus}


class TestDemande(unittest.TestCase):
    def test_demande_valide_par_defaut(self):
        d = st.valider_demande(brut())
        self.assertEqual(d.limites, st.LIMITES_DEFAUT)
        self.assertRegex(d.id, r"^t\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual((d.type, d.mode, d.scenario), ("emulation", "scenario", "demarrage"))

    def test_limites_ne_depassent_jamais_le_defaut(self):
        d = st.valider_demande(brut(limites={"duree_s": 60, "captures": 5}))
        self.assertEqual(d.limites["duree_s"], 60)
        self.assertEqual(d.limites["captures"], 5)
        self.assertEqual(d.limites["octets"], st.LIMITES_DEFAUT["octets"])
        for cle in st.LIMITES_DEFAUT:
            with self.assertRaises(ValueError):
                st.valider_demande(brut(limites={cle: st.LIMITES_DEFAUT[cle] + 1}))
            with self.assertRaises(ValueError):
                st.valider_demande(brut(limites={cle: 0}))
            with self.assertRaises(ValueError):
                st.valider_demande(brut(limites={cle: "10"}))
        with self.assertRaises(ValueError):
            st.valider_demande(brut(limites={"inconnue": 1}))

    def test_mode_scenario_exige_un_scenario(self):
        sans = brut()
        del sans["scenario"]
        with self.assertRaises(ValueError):
            st.valider_demande(sans)
        with self.assertRaises(ValueError):
            st.valider_demande(brut(scenario="../x"))
        with self.assertRaises(ValueError):
            st.valider_demande(brut(mode="autre"))
        self.assertEqual(st.valider_demande(brut(mode="pilote", scenario=None)).mode, "pilote")

    def test_id_hostile_refuse(self):
        for mauvais in ("../x", "a b", "", "t" * 200):
            with self.assertRaises(ValueError):
                st.valider_demande(brut(id=mauvais))
        self.assertEqual(st.valider_demande(brut(id="t20261119-101500-ab12")).id, "t20261119-101500-ab12")

    def test_type_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            st.valider_demande(brut(type="shell"))

    def test_limites_valeurs_hostiles(self):
        for mauvais in (True, False, 10 ** 40, float("nan"), float("inf"), 1.5, 60.0, -1, 0, None, [1]):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                st.valider_demande(brut(limites={"duree_s": mauvais}))
        with self.assertRaises(ValueError):
            st.valider_demande(brut(limites=[("duree_s", 5)]))

    def test_chiffres_et_fins_de_ligne_hostiles(self):
        ids = ("t١٢٣٤٥٦٧٨-101500-ab12", "t20261119-101500-ab12\n",
               "t２０261119-101500-ab12", "t20261119-101500-ab12 ")
        for mauvais in ids:
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                st.valider_demande(brut(id=mauvais))
        for mauvais in ("demarrage\n", "dｅmarrage", "١٢", "démarrage"):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                st.valider_demande(brut(scenario=mauvais))

    def test_message_limite_inconnue_sans_controles(self):
        with self.assertRaises(ValueError) as r:
            st.valider_demande(brut(limites={"a\x1b[31m\nb": 1}))
        self.assertNotIn("\x1b", str(r.exception))
        self.assertNotIn("\n", str(r.exception))

    def test_cles_inconnues_refusees(self):
        with self.assertRaises(ValueError):
            st.valider_demande(brut(commande="rm -rf /"))

    def test_textes_avec_controles_refuses(self):
        for mauvais in ("a\x7fb", "a\x85b", "a b", "a b", "a\nb", "a" * 201, 5):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                st.valider_demande(brut(projet=mauvais))

    def test_limites_immuables(self):
        d = st.valider_demande(brut())
        with self.assertRaises(TypeError):
            d.limites["duree_s"] = 1
        with self.assertRaises(TypeError):
            st.LIMITES_DEFAUT["duree_s"] = 1
        self.assertEqual(d.limites["duree_s"], 1200)

    def test_nouvel_id_deterministe(self):
        self.assertEqual(st.nouvel_id(lambda: 0, lambda n: "ab12"), "t19700101-000000-ab12")


def tid(n):
    return f"t20261119-101500-{n:04x}"


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        self.index = st.Index(self.dossier)

    def test_index_ecriture_atomique_et_lecture(self):
        self.assertEqual(self.index.lire(), {})
        self.index.enregistrer(tid(1), {"etat": "en_attente"})
        self.index.enregistrer(tid(2), {"etat": "en_cours"})
        self.index.enregistrer(tid(1), {"etat": "terminee"})
        self.assertEqual(self.index.lire(), {tid(1): {"etat": "terminee"}, tid(2): {"etat": "en_cours"}})
        self.index.retirer(tid(1))
        self.index.retirer(tid(99))
        self.assertEqual(list(self.index.lire()), [tid(2)])
        self.assertEqual([p.name for p in self.dossier.iterdir()], ["taches.json"])

    def test_index_abime_lu_comme_vide(self):
        for contenu in ("{pas du json", "[1, 2]", "", "[" * 100000):
            (self.dossier / "taches.json").write_text(contenu, encoding="utf-8")
            self.assertEqual(self.index.lire(), {})
        self.index.enregistrer(tid(1), {"etat": "en_attente"})
        self.assertEqual(self.index.lire(), {tid(1): {"etat": "en_attente"}})

    def test_id_hostile_refuse_dans_l_index(self):
        for mauvais in ("a", "../x", "", None, 5, tid(1) + "\n"):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                self.index.enregistrer(mauvais, {"etat": "en_attente"})
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                self.index.retirer(mauvais)

    def test_deux_ecritures_simultanees_sans_perte(self):
        erreurs = []

        def ecrire(base):
            try:
                for i in range(20):
                    self.index.enregistrer(tid(base + i), {"etat": "en_attente"})
            except Exception as e:  # noqa: BLE001
                erreurs.append(e)

        fils = [threading.Thread(target=ecrire, args=(b,)) for b in (0, 100)]
        [f.start() for f in fils]
        [f.join() for f in fils]
        self.assertEqual(erreurs, [])
        self.assertEqual(len(self.index.lire()), 40)

    def test_deux_processus_sans_perte(self):
        code = ("import sys\nsys.path.insert(0, sys.argv[1])\nimport serveur_tache as st\n"
                "i = st.Index(sys.argv[2], attente=60)\n"
                "for n in range(20):\n    i.enregistrer(f't20261119-101500-{1000 + n:04x}', {'etat': 'en_cours'})\n")
        sous = subprocess.Popen([sys.executable, "-I", "-c", code, str(RACINE / "outils"), str(self.dossier)])
        self.addCleanup(sous.kill)
        long = st.Index(self.dossier, attente=60)
        for n in range(20):
            long.enregistrer(tid(n), {"etat": "en_attente"})
        self.assertEqual(sous.wait(timeout=120), 0)
        self.assertEqual(len(long.lire()), 40)
        json.loads((self.dossier / "taches.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in self.dossier.iterdir()), ["taches.json"])

    def _verrou(self, contenu, age=0):
        chemin = self.dossier / "taches.lock"
        chemin.write_text(contenu, encoding="utf-8")
        if age:
            vieux = time.time() - age
            os.utime(chemin, (vieux, vieux))
        return chemin

    def _essai(self, contenu, age, vivant):
        """True si l'écriture a réussi (verrou repris), False si TimeoutError (verrou respecté)."""
        chemin = self._verrou(contenu, age)
        index = st.Index(self.dossier, attente=0.3, vivant=vivant)
        try:
            index.enregistrer(tid(1), {"etat": "en_attente"})
        except TimeoutError:
            chemin.unlink()
            return False
        return True

    def test_reprise_pid_mort(self):
        self.assertTrue(self._essai('{"pid": 4242}', 0, lambda pid: False))

    def test_pas_de_reprise_pid_vivant(self):
        self.assertFalse(self._essai('{"pid": 4242}', 0, lambda pid: True))

    def test_reprise_pid_propre_meme_si_vivant(self):
        self.assertTrue(self._essai('{"pid": %d}' % os.getpid(), 0, lambda pid: True))

    def test_fichier_vide_recent_respecte_puis_repris_apres_5_s(self):
        self.assertFalse(self._essai("", 0, lambda pid: True))
        self.assertTrue(self._essai("", 10, lambda pid: True))

    def test_pid_invalide_respecte_puis_repris_apres_5_s(self):
        for contenu in ('{"pid": true}', '{"pid": 1}', '{"pid": "7"}', "{x", '{"pid": 0}'):
            with self.subTest(contenu):
                self.assertFalse(self._essai(contenu, 0, lambda pid: True))
                self.assertTrue(self._essai(contenu, 10, lambda pid: True))

    def test_verrou_vivant_fait_attendre_et_n_est_pas_supprime(self):
        chemin = self._verrou('{"pid": 4242}')
        index = st.Index(self.dossier, attente=0.3, vivant=lambda pid: True)
        debut = time.monotonic()
        with self.assertRaises(TimeoutError):
            index.enregistrer(tid(1), {"etat": "en_attente"})
        self.assertGreaterEqual(time.monotonic() - debut, 0.25)
        self.assertEqual(json.loads(chemin.read_text(encoding="utf-8")), {"pid": 4242})
        self.assertFalse((self.dossier / "taches.lock.reprise").exists())

    def test_verrou_perime_impossible_a_retirer_ne_boucle_pas(self):
        self._verrou('{"pid": 4242}')
        index = st.Index(self.dossier, attente=0.3, vivant=lambda pid: False)
        debut = time.monotonic()
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("verrouillé")):
            with self.assertRaises(TimeoutError):
                index.enregistrer(tid(1), {"etat": "en_attente"})
        self.assertLess(time.monotonic() - debut, 5)

    def _temoin(self, contenu, age=0):
        chemin = self.dossier / "taches.lock.reprise"
        chemin.write_text(contenu, encoding="utf-8")
        if age:
            vieux = time.time() - age
            os.utime(chemin, (vieux, vieux))
        return chemin

    def test_regles_du_temoin_de_reprise(self):
        """Une tentative de reprise (`_reprendre`) face à un témoin déjà là : respecté ou retiré, le verrou intact."""
        cas = (("pid vivant frais", '{"pid": 4343}', 0, True), ("pid vivant vieux de 40 s", '{"pid": 4343}', 40, False),
               ("pid mort", '{"pid": 4343}', 0, False), ("vide frais", "", 0, True), ("vide vieux de 10 s", "", 10, False))
        for nom, contenu, age, respecte in cas:
            with self.subTest(nom):
                verrou = self._verrou('{"pid": 4242}')
                temoin = self._temoin(contenu, age)
                index = st.Index(self.dossier, vivant=lambda pid: pid == 4343 and "vivant" in nom)
                self.assertFalse(index._reprendre(verrou))     # le témoin d'un autre : jamais de reprise cette fois-ci
                self.assertEqual(temoin.exists(), respecte)
                self.assertTrue(verrou.exists())
                verrou.unlink()
                if temoin.exists():
                    temoin.unlink()

    def test_temoin_perime_retire_et_reprise_possible_ensuite(self):
        self._verrou('{"pid": 4242}')
        temoin = self._temoin('{"pid": 4343}')
        index = st.Index(self.dossier, attente=2, vivant=lambda pid: False)
        self.assertFalse(index._reprendre(self.dossier / "taches.lock"))
        self.assertFalse(temoin.exists())                      # retiré par le chemin de reprise, pas par autre chose
        index.enregistrer(tid(1), {"etat": "en_attente"})
        self.assertIn(tid(1), index.lire())

    def test_verrou_remplace_par_un_vivant_avant_le_temoin_n_est_pas_supprime(self):
        chemin = self._verrou('{"pid": 4343}')
        index = st.Index(self.dossier, attente=0.3, vivant=lambda pid: pid == 4242)
        index._avant_temoin = lambda: chemin.write_text('{"pid": 4242}', encoding="utf-8")
        with self.assertRaises(TimeoutError):
            index._prendre(time.monotonic() + 0.3)
        self.assertEqual(json.loads(chemin.read_text(encoding="utf-8")), {"pid": 4242})
        self.assertFalse((self.dossier / "taches.lock.reprise").exists())

    def test_temoin_perdu_avant_la_suppression_on_renonce(self):
        chemin = self._verrou('{"pid": 4343}')
        temoin = self.dossier / "taches.lock.reprise"
        index = st.Index(self.dossier, attente=0.3, vivant=lambda pid: pid == 777, pid=lambda: 101)

        def voler():
            temoin.write_text('{"pid": 777}', encoding="utf-8")      # un autre repreneur vivant tient le témoin
        index._apres_verification = voler
        self.assertFalse(index._reprendre(chemin))
        self.assertTrue(chemin.exists())
        self.assertEqual(json.loads(temoin.read_text(encoding="utf-8")), {"pid": 777})   # pas retiré à tort

    def test_course_de_reprise_un_seul_detenteur(self):
        """Deux repreneurs du même verrou périmé : un seul obtient le verrou, qui porte son pid ; l'autre attend ou
        expire, jamais deux détenteurs."""
        self._verrou('{"pid": 4242}')
        vivant = lambda pid: pid in (101, 102)      # noqa: E731
        a = st.Index(self.dossier, attente=2, vivant=vivant, pid=lambda: 101)
        b = st.Index(self.dossier, attente=1, vivant=vivant, pid=lambda: 102)
        dedans, suite = threading.Event(), threading.Event()

        def pause():
            dedans.set()
            suite.wait(10)
        a._apres_verification = pause
        resultats = {}

        def lancer(nom, index):
            try:
                resultats[nom] = index._prendre(time.monotonic() + index.attente)
            except TimeoutError as e:
                resultats[nom] = e
        ta = threading.Thread(target=lancer, args=("a", a))
        ta.start()
        self.assertTrue(dedans.wait(10))
        tb = threading.Thread(target=lancer, args=("b", b))
        tb.start()
        time.sleep(0.3)                         # b tourne pendant que a est entre vérification et suppression
        suite.set()
        ta.join(15)
        tb.join(15)
        pris = [n for n, r in resultats.items() if isinstance(r, Path)]
        self.assertEqual(len(pris), 1, resultats)
        pid = {"a": 101, "b": 102}[pris[0]]
        self.assertEqual(json.loads((self.dossier / "taches.lock").read_text(encoding="utf-8")), {"pid": pid})
        autre = "b" if pris[0] == "a" else "a"
        self.assertIsInstance(resultats[autre], TimeoutError)
        self.assertFalse((self.dossier / "taches.lock.reprise").exists())

    def test_verrou_libere_apres_exception(self):
        index = st.Index(self.dossier, attente=1)

        def boum(tout):
            raise RuntimeError("boum")
        with self.assertRaises(RuntimeError):
            index._modifier(boum)
        self.assertFalse((self.dossier / "taches.lock").exists())
        index.enregistrer(tid(1), {"etat": "en_attente"})

    def test_verrou_dun_autre_jamais_supprime_a_la_sortie(self):
        index = st.Index(self.dossier, attente=1)
        autre = self.dossier / "taches.lock"

        def vole(tout):
            autre.write_text('{"pid": 999999}', encoding="utf-8")
        index._modifier(vole)
        self.assertTrue(autre.exists())

    def test_erreur_de_lecture_transitoire_n_ecrase_rien(self):
        self.index.enregistrer(tid(1), {"etat": "en_attente"})
        vrai = Path.read_text

        def refuse(chemin, *a, **k):
            if chemin.name == "taches.json":
                raise PermissionError("antivirus")
            return vrai(chemin, *a, **k)
        with mock.patch.object(Path, "read_text", refuse):
            self.assertEqual(self.index.lire(), {})                    # affichage : vide
            with self.assertRaises(st.ErreurIndex):
                self.index.enregistrer(tid(2), {"etat": "en_attente"})
        self.assertEqual(list(self.index.lire()), [tid(1)])            # rien d'écrasé
        (self.dossier / "taches.json").unlink()
        self.index.enregistrer(tid(2), {"etat": "en_attente"})         # fichier absent : repart de vide
        self.assertEqual(list(self.index.lire()), [tid(2)])

    def test_entrees_non_dict_ignorees(self):
        (self.dossier / "taches.json").write_text('{"a": 5, "b": {"etat": "en_cours"}}', encoding="utf-8")
        self.assertEqual(self.index.lire(), {"b": {"etat": "en_cours"}})

    def test_etat_invalide_refuse(self):
        for fiche in ({"etat": "nimporte"}, {}, {"etat": None}, "x"):
            with self.assertRaises(ValueError):
                self.index.enregistrer(tid(1), fiche)
        self.assertEqual(self.index.lire(), {})


# ================================================================ lanceur (tâche 5)

import io  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import tarfile  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\r\n\x00\xff\n\r\x1a" * 50
APK = b"PK\x03\x04" + bytes(range(256)) + b"\r\n\n\r\x00" * 10
CLE_PRIVEE = "C:/cles-privees/id_ed25519_ovh1_SECRET-CHEMIN"
SECRET_OVH = "SECRET-OVH-TACHE-0123456789"
ID1 = "t20261119-101500-aaaa"


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def declarer(dossier, caps=None, serveurs=None):
    caps = {"android-emulateur": "presente", "emulateur-image": "fait"} if caps is None else caps
    serveurs = serveurs or [("ovh1", caps)]
    (Path(dossier) / "serveurs.json").write_text(json.dumps(
        [{"id": sid, "nom": sid, "hote": f"{sid}.exemple.net", "utilisateur": "ubuntu", "cle": CLE_PRIVEE + sid}
         for sid, _c in serveurs]), encoding="utf-8")
    (Path(dossier) / "serveurs-etat.json").write_text(json.dumps(
        {sid: {"capacites": {k: {"statut": v} for k, v in c.items()}, "installation": {"en_cours": False}}
         for sid, c in serveurs}), encoding="utf-8")


def archive(membres):
    """membres : liste de (nom, octets) ou de TarInfo déjà préparés (avec octets ou None)."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for m in membres:
            if isinstance(m, tuple) and isinstance(m[0], tarfile.TarInfo):
                info, donnees = m
                tar.addfile(info, io.BytesIO(donnees) if donnees is not None else None)
            else:
                nom, donnees = m
                info = tarfile.TarInfo(nom)
                info.size = len(donnees)
                tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


def ligne_pont(ok, verbe, detail):
    return json.dumps({"ok": ok, "verbe": verbe, "detail": detail}) + "\n"


class FauxServeur:
    """Serveur factice en mémoire : reconnaît chaque opération par la première ligne `# tache:<op> <id> ...` du script
    (entrée standard de `bash -s`, ou commande elle-même) et enregistre tous les appels."""

    def __init__(self):
        self.verrou = threading.Lock()
        self.appels = []
        self.taches = {}
        self.creneau = None
        self.injoignable = None
        self.maintenant = 1_800_000_000
        self.codes_lancer = []
        self.pont = {}
        self.archive = None
        self.ids_existants = set()
        self.avd_apres = 0
        self.deposes = None

    # interface de plateforme_ssh
    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        code, sortie, erreur = self._repondre(hote, commande, stdin.encode("utf-8") if stdin is not None else None, delai)
        return code, sortie.decode("utf-8", "replace"), erreur

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, runner=None):
        return self._repondre(hote, commande, entree, delai)

    def ops(self, op=None):
        return [a for a in self.appels if op is None or a[0] == op]

    def tache(self, ident, etat="en_cours", statut=None, debut=None, fin=None, raison="", veilleur="vivant",
              enveloppe="absent", fichiers=None):
        self.taches[ident] = {"etat": {"id": ident, "etat": etat, "statut": statut,
                                       "debut": debut or iso(self.maintenant - 60), "fin": fin, "raison": raison},
                              "veilleur": veilleur, "enveloppe": enveloppe, "fichiers": dict(fichiers or {}),
                              "conteneur": etat == "en_cours", "apk": None, "arret": None}
        return self.taches[ident]

    def _repondre(self, hote, commande, entree, delai):
        script = entree.decode("utf-8", "replace") if commande == "bash -s" else commande
        premiere = script.split("\n", 1)[0]
        assert premiere.startswith("# tache:"), premiere
        mots = premiere[len("# tache:"):].split()
        op, args = mots[0], mots[1:]
        with self.verrou:
            self.appels.append((op, script, entree if commande != "bash -s" else None, delai))
            if self.injoignable:
                return 255, b"", self.injoignable
            return getattr(self, "_" + op)(args, script, entree)

    def _preparer(self, args, script, entree):
        ident = args[0]
        if ident in self.taches or ident in self.ids_existants:
            return 73, b"", "existe"
        with tarfile.open(fileobj=io.BytesIO(entree)) as tar:
            fichiers = {m.name: tar.extractfile(m).read() for m in tar}
        t = self.tache(ident, veilleur="absent")
        t["etat"] = None
        t["apk"] = fichiers["entree/app.apk"]
        t["demande"] = json.loads(fichiers["demande.json"])
        return 0, b"", ""

    def _deposer(self, args, script, entree):
        with tarfile.open(fileobj=io.BytesIO(entree)) as tar:
            self.deposes = {m.name: tar.extractfile(m).read() for m in tar}
        return 0, b"", ""

    def _effacer(self, args, script, entree):
        self.taches.pop(args[0], None)
        return 0, b"", ""

    def _abandon(self, args, script, entree):
        self.taches[args[0]]["apk"] = None
        return 0, b"", ""

    def _lancer(self, args, script, entree):
        ident = args[0]
        t = self.taches[ident]
        if self.codes_lancer:
            code = self.codes_lancer.pop(0)
            if code == 1:
                t["etat"] = {"id": ident, "etat": "echouee", "statut": "erreur", "debut": None,
                             "fin": iso(self.maintenant), "raison": "Démarrage du conteneur impossible."}
            if code == 124:
                return 124, b"", "délai dépassé (60 s)"
            return code, (json.dumps(t["etat"]) + "\n").encode() if t["etat"] else b"", ""
        if self.creneau in (None, ident):
            self.creneau = ident
            t["etat"] = {"id": ident, "etat": "en_cours", "statut": None, "debut": iso(self.maintenant),
                         "fin": None, "raison": "Conteneur en cours de démarrage."}
            t["veilleur"], t["conteneur"] = "vivant", True
            return 0, (json.dumps(t["etat"]) + "\n").encode(), ""
        t["etat"] = {"id": ident, "etat": "en_attente", "statut": None, "debut": None, "fin": None,
                     "raison": "Créneau d'émulation occupé."}
        return 75, (json.dumps(t["etat"]) + "\n").encode(), ""

    def _etat(self, args, script, entree):
        t = self.taches.get(args[0])
        if not t or t["etat"] is None:
            return 3, b"", ""
        texte = (f"maintenant={self.maintenant}\nveilleur={t['veilleur']}\nenveloppe={t['enveloppe']}\n"
                 f"etat={json.dumps(t['etat'])}\n")
        return 0, texte.encode(), ""

    def _nettoyer(self, args, script, entree):
        t = self.taches[args[0]]
        if "vivant" in (t["veilleur"], t["enveloppe"]):
            return 4, b"", ""
        t["conteneur"] = False
        if t["etat"]["etat"] == "en_cours":
            lu = json.loads(script.split("<<'FIN_ETAT'\n", 1)[1].split("\n", 1)[0])
            t["etat"] = lu
        return 0, b"", ""

    def _arreter(self, args, script, entree):
        t = self.taches.get(args[0])
        if not t:
            return 3, b"", ""
        if t["etat"] and t["etat"]["etat"] == "en_cours":
            t["arret"] = "fin" if "printf '%s\\n' fin" in script else "arret"
            fin = t["arret"] == "fin"
            t["etat"] = {**t["etat"], "etat": "terminee" if fin else "arretee", "statut": "ok",
                         "fin": iso(self.maintenant + 30), "raison": "Arrêt demandé."}
            t["veilleur"] = "mort"
        t["conteneur"] = False
        if self.creneau == args[0]:
            self.creneau = None
        return 0, b"", ""

    def _rapatrier(self, args, script, entree):
        if self.archive is not None:
            return 0, self.archive, ""
        t = self.taches.get(args[0])
        if not t:
            return 3, b"", ""
        return 0, archive([("./" + n, d) for n, d in sorted(t["fichiers"].items()) if not n.startswith(".")]), ""

    def _capture(self, args, script, entree):
        nom = f"captures/{args[1]}.png"
        donnees = self.taches[args[0]]["fichiers"].get(nom)
        if donnees is None:
            return 3, b"", ""
        return 0, archive([("./" + nom, donnees)]), ""

    def _avd(self, args, script, entree):
        t = self.taches[args[0]]
        if self.avd_apres is not None and len(self.ops("avd")) > self.avd_apres:
            return 0, b"pret\n", ""
        return 0, (b"attente\n" if t["etat"]["etat"] == "en_cours" else b"fini\n"), ""

    def _verbe(self, args, script, entree):
        derniere = [l for l in script.splitlines() if "docker exec" in l][-1]
        mots = shlex.split(derniere)
        verbe = mots[mots.index("/usr/local/bin/pont") + 1]
        code, sortie = self.pont.get(verbe, (0, ligne_pont(True, verbe, "fait")))
        return code, sortie.encode() if isinstance(sortie, str) else sortie, ""


class BaseLanceur(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name) / "config"
        self.dossier.mkdir()
        declarer(self.dossier)
        self.srv = FauxServeur()
        self.dest = Path(self.tmp.name) / "projet" / ".factory" / "serveur" / ID1
        self.pauses = []

    def demande(self, **plus):
        return st.valider_demande({**brut(id=ID1), **plus})

    def lancer(self, demande=None, apk=APK, **k):
        k.setdefault("dormir", self.pauses.append)
        return st.lancer(demande or self.demande(), apk, dossier=self.dossier, ssh=self.srv, **k)

    def fiche(self, ident=ID1, **plus):
        st.Index(self.dossier).enregistrer(ident, {"etat": "en_cours", "serveur_id": "ovh1", "mode": "pilote", **plus})


class TestChoixServeur(BaseLanceur):
    def test_choisir_serveur_refuse_sans_capacite(self):
        declarer(self.dossier, {"android-emulateur": "presente", "emulateur-image": "absente"})
        with self.assertRaises(st.RefusLancement) as r:
            st.choisir_serveur(self.dossier)
        self.assertIn("emulateur-image", str(r.exception))
        self.assertIsInstance(r.exception, ValueError)
        declarer(self.dossier, {"android-emulateur": "presente"})
        with self.assertRaises(st.RefusLancement):
            st.choisir_serveur(self.dossier)

    def test_choisir_serveur_refuse_serveur_injoignable(self):
        declarer(self.dossier, {"android-emulateur": "inconnue", "emulateur-image": "inconnue"})
        with self.assertRaises(st.RefusLancement) as r:
            st.choisir_serveur(self.dossier)
        self.assertIn("injoignable", str(r.exception))
        (self.dossier / "serveurs.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(st.RefusLancement):
            st.choisir_serveur(self.dossier)

    def test_choisir_le_premier_serveur_pret(self):
        declarer(self.dossier, serveurs=[("a", {"android-emulateur": "inconnue", "emulateur-image": "inconnue"}),
                                         ("b", {"android-emulateur": "absente"}),
                                         ("c", {"android-emulateur": "fait", "emulateur-image": "presente"}),
                                         ("d", {"android-emulateur": "fait", "emulateur-image": "presente"})])
        self.assertEqual(st.choisir_serveur(self.dossier).id, "c")


class TestLancer(BaseLanceur):
    def test_lancer_envoie_apk_en_octets_intacts(self):
        r = self.lancer()
        self.assertEqual(r, {"id": ID1, "etat": "en_cours", "serveur_id": "ovh1"})
        self.assertEqual(self.srv.taches[ID1]["apk"], APK)
        self.assertEqual(self.srv.taches[ID1]["demande"]["mode"], "scenario")
        self.assertEqual(self.srv.deposes, {"taches/lancer_emulation.sh": (
            RACINE / "serveur_ovh" / "taches" / "lancer_emulation.sh").read_bytes()})
        prep = self.srv.ops("preparer")[0]
        self.assertNotIn(b"PK", prep[1].encode())             # l'APK n'est jamais dans la commande
        lancement = self.srv.ops("lancer")[0][1]
        self.assertIn(f'lancer_emulation.sh" {ID1} scenario 1200 300\n', lancement)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "en_cours")
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["serveur_id"], "ovh1")

    def test_lancer_creneau_occupe_attend_puis_abandonne(self):
        self.srv.creneau = "t20261119-090000-ffff"
        r = self.lancer(attente_max_s=45)
        self.assertEqual(r["etat"], "en_attente")
        self.assertIn("abandon", r["erreur"].lower())
        self.assertEqual(len(self.srv.ops("lancer")), 4)                   # 0, 15, 30, 45 s
        self.assertEqual(self.pauses, [15, 15, 15])
        self.assertEqual({a[1].split("\n", 1)[0] for a in self.srv.ops("lancer")}, {f"# tache:lancer {ID1}"})
        self.assertEqual(len(self.srv.ops("abandon")), 1)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "en_attente")

    def test_creneau_libere_pendant_l_attente(self):
        self.srv.creneau = "t20261119-090000-ffff"

        def dormir(s):
            self.pauses.append(s)
            self.srv.creneau = None
        r = self.lancer(dormir=dormir)
        self.assertEqual(r["etat"], "en_cours")
        self.assertEqual(self.pauses, [15])

    def test_lancer_deux_fois_un_seul_creneau(self):
        resultats, erreurs = [], []
        demandes = [self.demande(id="t20261119-101500-0001"), self.demande(id="t20261119-101500-0002")]

        def un(d):
            try:
                resultats.append(st.lancer(d, APK, dossier=self.dossier, ssh=self.srv, attente_max_s=30,
                                           dormir=lambda s: None))
            except Exception as e:  # noqa: BLE001
                erreurs.append(e)
        fils = [threading.Thread(target=un, args=(d,)) for d in demandes]
        [f.start() for f in fils]
        [f.join(30) for f in fils]
        self.assertEqual(erreurs, [])
        self.assertEqual(sorted(r["etat"] for r in resultats), ["en_attente", "en_cours"])
        index = json.loads((self.dossier / "taches.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(f["etat"] for f in index.values()), ["en_attente", "en_cours"])

    def test_identifiant_en_collision_remplace(self):
        st.Index(self.dossier).enregistrer(ID1, {"etat": "terminee"})
        self.srv.ids_existants.add("t20261119-101500-0bad")
        ids = iter(["t20261119-101500-0bad", "t20261119-101500-0b0b"])
        with mock.patch.object(st, "nouvel_id", lambda *a, **k: next(ids)):
            r = self.lancer()
        self.assertEqual(r["id"], "t20261119-101500-0b0b")
        self.assertEqual(st.Index(self.dossier).lire()[ID1], {"etat": "terminee"})

    def test_apk_plafonne_vide_ou_mauvais_type_refuse_avant_ssh(self):
        with mock.patch.object(st, "APK_MAX_OCTETS", 10):
            with self.assertRaises(st.RefusLancement):
                self.lancer(apk=b"x" * 11)
            self.lancer(apk=b"x" * 10)
        self.srv.appels.clear()
        for mauvais in (b"", "texte", None, [1]):
            with self.assertRaises(st.RefusLancement, msg=repr(mauvais)):
                self.lancer(apk=mauvais)
        self.assertEqual(self.srv.appels, [])
        self.assertEqual(st.APK_MAX_OCTETS, 200 * 1024 * 1024)

    def test_demande_invalide_refusee_avant_ssh(self):
        with self.assertRaises(st.RefusLancement):
            st.lancer({"type": "shell"}, APK, dossier=self.dossier, ssh=self.srv)
        piegee = st.Demande(id="../x", type="emulation", projet="", mode="scenario", scenario="a",
                            limites=st.LIMITES_DEFAUT, demandeur="", apk=None)
        with self.assertRaises(st.RefusLancement):
            st.lancer(piegee, APK, dossier=self.dossier, ssh=self.srv)
        self.assertEqual(self.srv.appels, [])

    def test_erreur_d_index_avant_le_lancement_sans_trace(self):
        with mock.patch.object(st.Index, "enregistrer", side_effect=st.ErreurIndex("Index illisible")):
            r = self.lancer()
        self.assertEqual(r["etat"], "echouee")
        self.assertIn("Index", r["erreur"])
        self.assertEqual(self.srv.ops("lancer"), [])
        self.assertEqual(len(self.srv.ops("effacer")), 1)

    def test_index_occupe_apres_le_lancement_sans_trace(self):
        vrai = st.Index.enregistrer

        def parfois(index, ident, fiche):
            if fiche.get("etat") == "en_cours":
                raise TimeoutError("Index des tâches occupé : réessayez.")
            return vrai(index, ident, fiche)
        with mock.patch.object(st.Index, "enregistrer", parfois):
            r = self.lancer()
        self.assertEqual(r["etat"], "en_cours")
        self.assertIn("occupé", r["erreur"])

    def test_echec_de_l_enveloppe_brule_l_identifiant_sans_nouvel_essai(self):
        self.srv.codes_lancer = [1]
        r = self.lancer()
        self.assertEqual(r["etat"], "echouee")
        self.assertEqual(len(self.srv.ops("lancer")), 1)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "echouee")

    def test_delai_depasse_lit_l_etat_sans_relancer(self):
        self.srv.codes_lancer = [124]
        self.srv.tache(ID1)          # la tâche a bien démarré pendant le délai
        self.srv.taches[ID1]["apk"] = APK
        with mock.patch.object(self.srv, "_preparer", lambda *a: (0, b"", "")):
            r = self.lancer()
        self.assertEqual(r["etat"], "en_cours")
        self.assertEqual(len(self.srv.ops("lancer")), 1)
        self.assertEqual(len(self.srv.ops("etat")), 1)

    def test_code_4_ne_nettoie_que_si_rien_n_est_vivant(self):
        self.srv.codes_lancer = [4]
        self.srv.tache(ID1, veilleur="absent", enveloppe="vivant", debut=iso(self.srv.maintenant - 1000))
        with mock.patch.object(self.srv, "_preparer", lambda *a: (0, b"", "")):
            r = self.lancer()
        self.assertEqual(self.srv.ops("nettoyer"), [])
        self.assertEqual(r["etat"], "en_cours")


class TestEtatArret(BaseLanceur):
    def test_etat_injoignable_ne_leve_pas(self):
        self.fiche()
        self.srv.injoignable = "ssh: connect to host ovh1.exemple.net port 22: Connection timed out"
        r = st.etat(ID1, dossier=self.dossier, ssh=self.srv)
        self.assertEqual(r["etat"], "inconnu")
        self.assertIn("injoignable", r["raison"])
        for mauvais in ("../x", None, ID1 + "\n"):
            self.assertEqual(st.etat(mauvais, dossier=self.dossier, ssh=self.srv)["etat"], "inconnu")

        class Casse:
            def executer(self, *a, **k):
                raise plateforme_ssh.ErreurSsh("ssh introuvable")
            executer_octets = executer
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=Casse())["etat"], "inconnu")

    def test_etat_lit_le_serveur_et_met_l_index_a_jour(self):
        self.fiche(projet="demo")
        self.srv.tache(ID1, etat="terminee", statut="limite", fin=iso(self.srv.maintenant), veilleur="mort")
        r = st.etat(ID1, dossier=self.dossier, ssh=self.srv)
        self.assertEqual((r["etat"], r["statut"]), ("terminee", "limite"))
        f = st.Index(self.dossier).lire()[ID1]
        self.assertEqual((f["etat"], f["statut"], f["projet"]), ("terminee", "limite", "demo"))
        self.assertEqual(self.srv.ops("nettoyer"), [])

    def test_etat_illisible_ou_d_une_autre_tache(self):
        self.fiche()
        t = self.srv.tache(ID1)
        t["etat"] = {"id": "t20261119-101500-bbbb", "etat": "terminee"}
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.srv)["etat"], "inconnu")
        t["etat"] = {"id": ID1, "etat": "partie"}
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.srv)["etat"], "inconnu")

    def test_veilleur_mort_nettoie_et_echoue(self):
        self.fiche()
        self.srv.tache(ID1, veilleur="mort")
        r = st.etat(ID1, dossier=self.dossier, ssh=self.srv)
        self.assertEqual((r["etat"], r["statut"]), ("echouee", "erreur"))
        self.assertIn("veilleur", r["raison"].lower())
        self.assertEqual(len(self.srv.ops("nettoyer")), 1)
        self.assertIn(f"docker rm -f tache-{ID1}", self.srv.ops("nettoyer")[0][1])
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "echouee")

    def test_veilleur_absent_jeune_ou_enveloppe_vivante_respectes(self):
        self.fiche()
        self.srv.tache(ID1, veilleur="absent", debut=iso(self.srv.maintenant - 30))
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.srv)["etat"], "en_cours")
        self.srv.tache(ID1, veilleur="mort", enveloppe="vivant")
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.srv)["etat"], "en_cours")
        self.assertEqual(self.srv.ops("nettoyer"), [])
        self.srv.tache(ID1, veilleur="absent", debut=iso(self.srv.maintenant - 400))
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.srv)["etat"], "echouee")

    def test_arreter_est_idempotent(self):
        self.fiche()
        self.srv.tache(ID1)
        r1 = st.arreter(ID1, dossier=self.dossier, ssh=self.srv)
        r2 = st.arreter(ID1, dossier=self.dossier, ssh=self.srv)
        self.assertEqual((r1["etat"], r2["etat"]), ("arretee", "arretee"))
        self.assertEqual(self.srv.taches[ID1]["arret"], "arret")
        for _op, script, _e, _d in self.srv.ops("arreter"):
            self.assertIn(f"sudo -n docker stop", script)
            self.assertIn(f"tache-{ID1}", script)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "arretee")
        self.assertEqual(st.arreter("t20261119-101500-dead", dossier=self.dossier, ssh=self.srv)["etat"], "inconnu")

    def test_arreter_fin_normale(self):
        self.fiche()
        self.srv.tache(ID1)
        self.assertEqual(st.arreter(ID1, dossier=self.dossier, ssh=self.srv, fin=True)["etat"], "terminee")
        self.assertEqual(self.srv.taches[ID1]["arret"], "fin")


class TestRapatrier(BaseLanceur):
    def preparer(self, etat="terminee", statut="ok", fichiers=None, **k):
        self.fiche(**k)
        fichiers = {"pont.log": b"demarrer 10ms\ncapturer accueil 5ms\n", "captures/accueil.png": PNG} \
            if fichiers is None else fichiers
        self.srv.tache(ID1, etat=etat, statut=statut, fin=iso(self.srv.maintenant), veilleur="mort", fichiers=fichiers)

    def rapatrier(self, **k):
        return st.rapatrier(ID1, self.dest, dossier=self.dossier, ssh=self.srv, **k)

    def fichiers_ecrits(self):
        racine = Path(self.tmp.name)
        return sorted(p.relative_to(racine).as_posix() for p in racine.rglob("*") if p.is_file())

    def test_rapatrier_conserve_le_png_binaire(self):
        self.preparer()
        m = self.rapatrier()
        self.assertEqual(m["statut"], "ok")
        self.assertEqual([Path(c).read_bytes() for c in m["captures"]], [PNG])
        self.assertEqual(Path(m["captures"][0]), self.dest / "captures" / "accueil.png")
        self.assertEqual(Path(m["journal"]).read_bytes(), b"demarrer 10ms\ncapturer accueil 5ms\n")
        rapport = json.loads(Path(m["rapport"]).read_text(encoding="utf-8"))
        self.assertEqual((rapport["statut"], rapport["verbes"]), ("ok", 2))
        self.assertEqual(m["duree_s"], 60)
        self.assertEqual(self.rapatrier()["captures"], m["captures"])         # deuxième fois : remplacé, sans erreur

    def test_rapatrier_refuse_chemin_traversant_et_lien_symbolique(self):
        self.preparer()
        hostiles = []
        for nom, genre, cible in (("captures/lien.png", tarfile.SYMTYPE, "/etc/passwd"),
                                  ("captures/dur.png", tarfile.LNKTYPE, "pont.log"),
                                  ("captures/dev.png", tarfile.CHRTYPE, ""),
                                  ("captures/sous", tarfile.DIRTYPE, ""),
                                  ("captures/fifo.png", tarfile.FIFOTYPE, "")):
            info = tarfile.TarInfo(nom)
            info.type, info.linkname = genre, cible
            hostiles.append((info, None))
        self.srv.archive = archive([("./pont.log", b"ok\n"), ("../evil.txt", b"x"), ("/abs.txt", b"x"),
                                    ("C:/disque.txt", b"x"), ("captures/../../x.png", PNG), ("..\\y.png", PNG),
                                    ("./captures/ok.png", PNG), ("captures/A.png", PNG), ("captures/con.png", PNG),
                                    ("captures/faux.png", b"pas une image"), ("autre.sh", b"x"),
                                    ("./captures/ok.png", PNG + b"double"), *hostiles])
        m = self.rapatrier()
        self.assertEqual(self.fichiers_ecrits(), sorted([
            "config/serveurs.json", "config/serveurs-etat.json", "config/taches.json",
            f"projet/.factory/serveur/{ID1}/journal.txt", f"projet/.factory/serveur/{ID1}/captures/ok.png",
            f"projet/.factory/serveur/{ID1}/rapport.json"]))
        self.assertEqual((self.dest / "captures" / "ok.png").read_bytes(), PNG)
        self.assertEqual(m["statut"], "erreur")
        self.assertGreaterEqual(m["refuses"], 15)

    def test_rapatrier_borne_le_nombre_et_la_taille(self):
        self.preparer(limites={"captures": 2, "octets": 1000})
        self.srv.archive = archive([("./pont.log", b"x" * 10)] + [(f"./captures/c{i}.png", PNG[:8] + b"y" * 292)
                                                                  for i in range(10)])
        m = self.rapatrier()
        ecrits = [p for p in self.dest.rglob("*") if p.is_file() and p.name != "rapport.json"]
        self.assertLessEqual(len(ecrits), 2 + 5)
        self.assertLessEqual(len(m["captures"]), 2)
        self.assertLessEqual(sum(p.stat().st_size for p in ecrits), 1000)
        self.assertTrue(m["tronque"])
        self.assertEqual(m["statut"], "limite")

    def test_bombes_de_taille(self):
        self.preparer(limites={"octets": 1000})
        info = tarfile.TarInfo("./captures/bombe.png")
        info.size = 10 ** 10
        tampon = io.BytesIO()
        tampon.write(info.tobuf(format=tarfile.GNU_FORMAT))
        tampon.write(PNG)                              # données tronquées : la taille annoncée est fausse
        self.srv.archive = tampon.getvalue()
        m = self.rapatrier()
        self.assertEqual(m["captures"], [])
        self.assertNotEqual(m["statut"], "ok")
        self.srv.archive = b"\0" * (st.TAILLE_ARCHIVE_MARGE + 1000 + 10)       # flux au-delà du plafond : rien d'analysé
        m = self.rapatrier()
        self.assertEqual(m["captures"], [])
        self.assertTrue(m["tronque"])

    def test_destination_lien_refusee(self):
        self.preparer()
        self.dest.parent.mkdir(parents=True)
        self.dest.write_text("fichier", encoding="utf-8")
        m = self.rapatrier()
        self.assertEqual(m["statut"], "erreur")
        self.assertEqual(self.dest.read_text(encoding="utf-8"), "fichier")

    def test_statut_plantage_et_limite(self):
        self.preparer(fichiers={"pont.log": b"x\n", "plantage.txt": b"FATAL EXCEPTION\n"})
        self.assertEqual(self.rapatrier()["statut"], "plantage")
        self.preparer(statut="limite")
        self.assertEqual(self.rapatrier()["statut"], "limite")
        self.preparer(etat="arretee", statut="ok", limite_atteinte=True)
        self.assertEqual(self.rapatrier()["statut"], "limite")
        self.preparer(etat="echouee", statut="erreur")
        self.assertEqual(self.rapatrier()["statut"], "erreur")
        self.preparer(etat="en_cours", statut=None)
        self.srv.taches[ID1]["veilleur"] = "vivant"
        self.assertEqual(self.rapatrier()["statut"], "erreur")
        self.preparer()
        self.assertEqual(self.rapatrier()["statut"], "ok")

    def test_statut_limite_apres_code_3_du_pont(self):
        self.preparer(etat="en_cours", statut=None)
        self.srv.taches[ID1]["veilleur"] = "vivant"
        self.srv.pont["capturer"] = (3, ligne_pont(False, "capturer", "Limite de captures atteinte (50)."))
        r = st.verbe(ID1, "capturer", ["deux"], dossier=self.dossier, ssh=self.srv)
        self.assertEqual(r["code"], 3)
        st.arreter(ID1, dossier=self.dossier, ssh=self.srv)
        self.assertEqual(self.rapatrier()["statut"], "limite")


class TestVerbe(BaseLanceur):
    def setUp(self):
        super().setUp()
        self.fiche()
        self.srv.tache(ID1, fichiers={".avd-pret": b""})

    def verbe(self, v, args=(), **k):
        k.setdefault("dormir", self.pauses.append)
        return st.verbe(ID1, v, list(args), dossier=self.dossier, ssh=self.srv, **k)

    def test_verbe_valide_les_arguments_avant_ssh(self):
        for v, args in (("texte", ["a;b"]), ("texte", ["$(touch /x)"]), ("toucher", ["1", "99999"]),
                        ("capturer", ["../x"]), ("rm", ["-rf"]), ("journal", ["a", "b"]), ("toucher\n", ["1", "2"]),
                        ("texte", ["a\nb"]), ("touche", ["retour\n"]), ("texte", [5]), ("texte", [None])):
            with self.assertRaises(ValueError, msg=(v, args)):
                self.verbe(v, args)
        with self.assertRaises(ValueError):
            st.verbe("../x", "lancer", [], dossier=self.dossier, ssh=self.srv)
        self.assertEqual(self.srv.appels, [])

    def test_relais_sans_environnement_et_texte_avec_espaces(self):
        r = self.verbe("texte", ["Bonjour le monde, 3.5_kg-x"])
        self.assertEqual((r["ok"], r["code"], r["verbe"]), (True, 0, "texte"))
        script = self.srv.ops("verbe")[0][1]
        ligne = [l for l in script.splitlines() if "docker exec" in l][0]
        mots = shlex.split(ligne)
        i = mots.index("sudo")
        self.assertEqual(mots[i:], ["sudo", "-n", "docker", "exec", f"tache-{ID1}", "/usr/local/bin/pont", "texte",
                                    "Bonjour le monde, 3.5_kg-x"])
        self.assertNotIn(" -e", ligne)
        self.assertEqual(self.verbe("toucher", [540, 1200])["code"], 0)

    def test_reponse_du_pont_lue_avec_prudence(self):
        for sortie in ("pas du json\n", ligne_pont(True, "lancer", "a") * 2, "x" * (st.REPONSE_PONT_MAX + 1),
                       '{"ok": "oui", "verbe": "lancer", "detail": "x"}\n', "[1]\n", ""):
            self.srv.pont["lancer"] = (0, sortie)
            r = self.verbe("lancer")
            self.assertFalse(r["ok"], sortie[:50])
            self.assertIn("illisible", r["detail"])
        self.srv.pont["lancer"] = (2, ligne_pont(False, "lancer", "refus"))
        self.assertEqual(self.verbe("lancer")["code"], 2)

    def test_verbe_capturer_rapatrie_et_donne_le_chemin_local(self):
        self.srv.taches[ID1]["fichiers"]["captures/ecran-1.png"] = PNG
        r = self.verbe("capturer", ["ecran-1"], destination=self.dest)
        self.assertTrue(r["ok"])
        self.assertEqual(Path(r["capture"]), self.dest / "captures" / "ecran-1.png")
        self.assertEqual(Path(r["capture"]).read_bytes(), PNG)
        r = self.verbe("capturer", ["ecran-2"], destination=self.dest)     # absente du serveur
        self.assertFalse(r["ok"])
        self.assertNotIn("capture", r)

    def test_capture_par_defaut_sous_le_dossier(self):
        self.srv.taches[ID1]["fichiers"]["captures/ecran.png"] = PNG
        r = self.verbe("capturer", ["ecran"])
        self.assertTrue(Path(r["capture"]).is_relative_to(self.dossier))

    def test_demarrer_attend_l_avd(self):
        del self.srv.taches[ID1]["fichiers"][".avd-pret"]
        self.srv.avd_apres = 2
        r = self.verbe("demarrer")
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.srv.ops("avd")), 3)
        self.assertEqual(self.pauses, [st.AVD_PAS_S] * 2)
        self.assertEqual(len(self.srv.ops("verbe")), 1)

    def test_demarrer_sans_avd_abandonne_borne(self):
        self.srv.avd_apres = None
        r = self.verbe("demarrer")
        self.assertEqual((r["ok"], r["code"]), (False, 4))
        self.assertLessEqual(sum(self.pauses), st.AVD_ATTENTE_S)
        self.assertEqual(self.srv.ops("verbe"), [])
        self.srv.taches[ID1]["etat"]["etat"] = "terminee"
        self.pauses.clear()
        r = self.verbe("demarrer")
        self.assertFalse(r["ok"])
        self.assertEqual(self.pauses, [])

    def test_verbe_serveur_injoignable(self):
        self.srv.injoignable = "Connection refused"
        r = self.verbe("lancer")
        self.assertEqual((r["ok"], r["code"]), (False, 255))


class TestMasquage(BaseLanceur):
    def test_sorties_masquees_sans_secret(self):
        (self.dossier / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-KEY-TACHE-XYZ",
                                                           "secret": SECRET_OVH, "consommateur": "CONSO-TACHE-XYZ",
                                                           "serveur": "ns1.exemple"}), encoding="utf-8")
        fuite = f"erreur {SECRET_OVH} APP-KEY-TACHE-XYZ {CLE_PRIVEE}ovh1"
        sorties = []
        self.fiche()
        self.srv.tache(ID1, raison=fuite, fichiers={"pont.log": fuite.encode()})
        sorties.append(st.etat(ID1, dossier=self.dossier, ssh=self.srv))
        self.srv.pont["journal"] = (0, ligne_pont(True, "journal", fuite))
        sorties.append(st.verbe(ID1, "journal", [], dossier=self.dossier, ssh=self.srv))
        sorties.append(st.rapatrier(ID1, self.dest, dossier=self.dossier, ssh=self.srv))
        sorties.append(json.loads((self.dest / "rapport.json").read_text(encoding="utf-8")))
        sorties.append(st.arreter(ID1, dossier=self.dossier, ssh=self.srv))
        self.srv.injoignable = fuite
        sorties.append(st.etat(ID1, dossier=self.dossier, ssh=self.srv))
        sorties.append(st.verbe(ID1, "lancer", [], dossier=self.dossier, ssh=self.srv))
        sorties.append(self.lancer(self.demande(id="t20261119-101500-0003")))
        tout = json.dumps(sorties, ensure_ascii=False) + (self.dossier / "taches.json").read_text(encoding="utf-8")
        for secret in (SECRET_OVH, "APP-KEY-TACHE-XYZ", "CONSO-TACHE-XYZ", CLE_PRIVEE):
            self.assertNotIn(secret, tout)
        self.assertIn("***", tout)


# ---------------------------------------------------------------- motifs Python et pont.sh

ACCEPTES = [("toucher", ["540", "1200"]), ("toucher", ["0", "9999"]), ("toucher", ["0012", "1"]),
            ("glisser", ["100", "1500", "100", "300"]), ("touche", ["retour"]), ("touche", ["accueil"]),
            ("touche", ["menu"]), ("attendre", ["0"]), ("attendre", ["7"]), ("attendre", ["99"]), ("attendre", ["120"]),
            ("texte", ["Bonjour le monde, 3.5_kg-x"]), ("texte", ["un deux"]), ("texte", ["a"]), ("texte", ["A."]),
            ("texte", ["a" * 60]), ("capturer", ["accueil-1"]), ("capturer", ["a"]), ("capturer", ["n0"]),
            ("capturer", ["0_x"]), ("capturer", ["b" * 40]), ("journal", []), ("journal", ["pair"]),
            ("journal", ["ActivityManager:I"]), ("journal", ["com.exemple.app"]), ("installer", []), ("lancer", []),
            ("arreter", [])]
COMMUNS = [";", "$(x)", "`x`", "a\nb", "", "$(touch ../pwn)", "*", "a;b", "x'y", "a|b", "&", ">", "a\r", "\r", "--",
           "-s", "?", "[", "a&b", "a>b"]
REFUSES = ([("toucher", [v, "1"]) for v in COMMUNS + ["..", "-1", "99999", "1.5", " 1"]]
           + [("toucher", ["10", v]) for v in ("-1", "99999")] + [("toucher", ["10"]), ("toucher", ["10", "20", "30"])]
           + [("glisser", ["1", "2", "3", v]) for v in ("..", "-1", "99999", "10000")]
           + [("glisser", ["1", "2", "3"]), ("glisser", ["1", "2", "3", "4", "5"])]
           + [("attendre", [v]) for v in COMMUNS + ["..", "-1", "99999", "121", "1000", "010"]]
           + [("capturer", [v]) for v in COMMUNS + ["..", "../x", "a/b", "A", "x.png", "a" * 41, "_a", "a\n"]]
           + [("capturer", ["a", "b"])]
           + [("texte", [v]) for v in COMMUNS + ["a" * 61, "a/b", "é", "50%", " a", ".x"]]
           + [("touche", [v]) for v in COMMUNS + ["..", "-1", "99999", "power", "retour ", "KEYCODE_POWER", "retour\n"]]
           + [("journal", [v]) for v in COMMUNS + ["a b", "a/b", "a" * 61, ":x", ".x"]] + [("journal", ["a", "b"])]
           + [("installer", [v]) for v in ("/etc/passwd", "../entree/app.apk", ";", "")]
           + [("demarrer", ["-1"]), ("lancer", [".."]), ("arreter", ["99999"])]
           + [(v, []) for v in ("rm", "", "TOUCHER", "toucher;ls", "sh", "eval", "demarrer\n", "../pont")])


class TestMotifs(unittest.TestCase):
    def test_table_python(self):
        for v, args in ACCEPTES:
            self.assertEqual(st.valider_verbe(v, args), tuple(args), (v, args))
        for v, args in REFUSES:
            with self.assertRaises(ValueError, msg=(v, args)):
                st.valider_verbe(v, args)
        self.assertEqual(set(st.VERBES), {"demarrer", "installer", "lancer", "toucher", "glisser", "texte", "touche",
                                          "attendre", "capturer", "journal", "arreter"})

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_motifs_python_et_pont_s_accordent(self):
        from tests.test_serveur_pont import Banc
        with Banc(PONT_PAQUET="com.exemple.app") as banc:
            for v, args in ACCEPTES + REFUSES:
                if v == "lancer" and not args:
                    continue                                # exige un paquet installé : couvert par installer
                with self.subTest(verbe=v, args=args):
                    try:
                        st.valider_verbe(v, args)
                        python = True
                    except ValueError:
                        python = False
                    code, _d = banc.lancer(v, *args)
                    self.assertEqual(python, code != 2, (v, args, code, _d))


# ---------------------------------------------------------------- scripts réels sous bash (faux sudo et docker)

def posix(chemin):
    if shutil.which("cygpath"):
        return subprocess.run(["cygpath", "-u", str(chemin)], capture_output=True, text=True, check=True).stdout.strip()
    return Path(chemin).as_posix()


class BashSsh:
    """« SSH » qui exécute vraiment la commande avec le bash du poste, HOME dans un dossier temporaire."""

    def __init__(self, racine):
        self.home = Path(racine) / "home"
        self.bin = Path(racine) / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        self.journal = Path(racine) / "docker.log"
        for nom, corps in (("sudo", '[ "$1" = -n ] && shift\nexec "$@"'),
                           ("docker", 'echo "docker $*" >> "$FAUX_DOCKER"\nexit 0')):
            (self.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (self.bin / nom).chmod(0o755)

    def _env(self):
        return dict(os.environ, HOME=posix(self.home), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                    FAUX_DOCKER=posix(self.journal), MSYS="winsymlinks:lnk")

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, runner=None):
        r = subprocess.run(["bash", "-c", commande], input=entree or b"", capture_output=True, env=self._env(),
                           timeout=max(delai, 60))
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        code, sortie, erreur = self.executer_octets(hote, commande, cle,
                                                    stdin.encode("utf-8") if stdin is not None else None, delai)
        return code, sortie.decode("utf-8", "replace"), erreur

    def bash(self, script):
        return subprocess.run(["bash", "-c", script], capture_output=True, env=self._env(), timeout=60)

    def docker(self):
        return self.journal.read_text(encoding="utf-8") if self.journal.exists() else ""


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestScriptsReels(BaseLanceur):
    def setUp(self):
        super().setUp()
        self.ssh = BashSsh(self.tmp.name)
        self.tache = self.ssh.home / "taches" / ID1
        self.serveur = st.choisir_serveur(self.dossier)

    def ecrire_etat(self, **e):
        (self.tache / "sortie").mkdir(parents=True, exist_ok=True)
        e = {"id": ID1, "etat": "terminee", "statut": "ok", "debut": "2026-11-19T10:15:00Z",
             "fin": "2026-11-19T10:16:40Z", "raison": "fin", **e}
        (self.tache / "etat.json").write_text(json.dumps(e) + "\n", encoding="utf-8", newline="\n")

    def test_preparer_et_deposer_reels(self):
        code, _e = st._envoyer(self.serveur, self.ssh, self.demande(), APK)
        self.assertEqual(code, 0, _e)
        self.assertEqual((self.tache / "entree" / "app.apk").read_bytes(), APK)
        self.assertEqual(json.loads((self.tache / "demande.json").read_text(encoding="utf-8"))["id"], ID1)
        self.assertEqual(st._envoyer(self.serveur, self.ssh, self.demande(), APK)[0], 73)     # collision
        self.assertEqual(sorted(p.name for p in (self.ssh.home / "taches").iterdir()), [ID1])
        self.assertIsNone(st._deposer_enveloppe(self.serveur, self.ssh))
        depose = self.ssh.home / "myiafactory" / "serveur_ovh" / "taches" / "lancer_emulation.sh"
        self.assertEqual(depose.read_bytes(), (RACINE / "serveur_ovh" / "taches" / "lancer_emulation.sh").read_bytes())

    def test_rapatrier_reel_fichiers_ordinaires_seulement(self):
        self.fiche()
        self.ecrire_etat()
        sortie = self.tache / "sortie"
        (sortie / "captures").mkdir()
        (sortie / "pont.log").write_bytes(b"demarrer 3ms\n")
        (sortie / "captures" / "accueil.png").write_bytes(PNG)
        (sortie / "emulateur.pid").write_text("123", encoding="utf-8")
        dehors = Path(self.tmp.name) / "dehors.txt"
        dehors.write_bytes(b"SECRET DU SERVEUR")
        (sortie / "autre.bin").write_bytes(PNG)
        r = self.ssh.bash(f'cd "{posix(sortie / "captures")}" && ln -s "{posix(dehors)}" lien.png; '
                          f'ln ../autre.bin dur.png; ln -s "{posix(dehors)}" ../plantage.txt; true')
        self.assertEqual(r.returncode, 0, r.stderr)
        m = st.rapatrier(ID1, self.dest, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(m["captures"], [str(self.dest / "captures" / "accueil.png")])
        self.assertEqual((self.dest / "captures" / "accueil.png").read_bytes(), PNG)
        self.assertEqual(Path(m["journal"]).read_bytes(), b"demarrer 3ms\n")
        self.assertEqual(m["statut"], "ok")
        self.assertEqual(m["duree_s"], 100)
        tout = b"".join(p.read_bytes() for p in self.dest.rglob("*") if p.is_file())
        self.assertNotIn(b"SECRET DU SERVEUR", tout)

    def test_etat_reel_veilleur_mort_nettoie(self):
        self.fiche()
        self.ecrire_etat(etat="en_cours", statut=None, fin=None)
        (self.tache / "veilleur.pid").write_text("999999\n", encoding="utf-8")
        r = st.etat(ID1, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual((r["etat"], r["statut"]), ("echouee", "erreur"))
        self.assertIn(f"docker rm -f tache-{ID1}", self.ssh.docker())
        sur_disque = json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))
        self.assertEqual((sur_disque["etat"], sur_disque["debut"]), ("echouee", "2026-11-19T10:15:00Z"))

    def test_etat_reel_absent_et_arreter_reel_idempotent(self):
        self.fiche()
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.ssh)["etat"], "inconnu")
        self.ecrire_etat()
        for _ in range(2):
            r = st.arreter(ID1, dossier=self.dossier, ssh=self.ssh)
            self.assertEqual(r["etat"], "terminee")
        self.assertEqual(self.ssh.docker().count(f"docker stop -t 10 tache-{ID1}"), 2)
        self.assertFalse((self.tache / "arret").exists())          # tâche finie : aucun fichier arret
        self.assertEqual(st.verbe(ID1, "lancer", [], dossier=self.dossier, ssh=self.ssh)["ok"], False)


if __name__ == "__main__":
    unittest.main()
