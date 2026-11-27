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

from tests import plateforme_tests  # noqa: E402



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

    def test_fusionner_deux_fils_sans_perte(self):
        self.index.enregistrer(tid(1), {"etat": "en_attente", "serveur_id": "ovh1", "projet": "demo"})
        erreurs = []

        def a():
            try:
                for i in range(30):
                    self.index.fusionner(tid(1), {"limite_atteinte": True, "compte_a": i})
            except Exception as e:  # noqa: BLE001
                erreurs.append(e)

        def b():
            try:
                for i in range(30):
                    self.index.fusionner(tid(1), {"etat": "en_cours", "compte_b": i})
            except Exception as e:  # noqa: BLE001
                erreurs.append(e)
        fils = [threading.Thread(target=f) for f in (a, b)]
        vrai = st.Index._lire_pour_ecrire

        def lent(index):
            tout = vrai(index)
            time.sleep(0.002)                        # élargit la fenêtre lecture -> écriture
            return tout
        with mock.patch.object(st.Index, "_lire_pour_ecrire", lent):
            [f.start() for f in fils]
            [f.join(60) for f in fils]
        self.assertEqual(erreurs, [])
        f = self.index.lire()[tid(1)]
        self.assertEqual((f["limite_atteinte"], f["etat"], f["compte_a"], f["compte_b"], f["serveur_id"], f["projet"]),
                         (True, "en_cours", 29, 29, "ovh1", "demo"))

    def test_fusionner_erreur_de_lecture_n_efface_rien(self):
        fiche = {"etat": "en_cours", "serveur_id": "ovh1", "limites": {"captures": 2}, "projet": "demo"}
        self.index.enregistrer(tid(1), fiche)
        vrai = Path.read_text

        def refuse(chemin, *a, **k):
            if chemin.name == "taches.json":
                raise PermissionError("antivirus")
            return vrai(chemin, *a, **k)
        with mock.patch.object(Path, "read_text", refuse):
            with self.assertRaises(st.ErreurIndex):
                self.index.fusionner(tid(1), {"etat": "terminee"})
        self.assertEqual(self.index.lire()[tid(1)], fiche)
        with self.assertRaises(ValueError):
            self.index.fusionner(tid(2), {"limite_atteinte": True})       # fiche absente, sans état : rien d'écrit
        self.assertEqual(list(self.index.lire()), [tid(1)])

    def test_reserver_borne_et_liberer(self):
        self.index.enregistrer(tid(1), {"etat": "en_cours"})
        self.assertEqual([self.index.reserver(tid(1), "n", 2) for _ in range(3)], [(True, 2), (True, 2), (False, 2)])
        self.index.liberer(tid(1), "n")
        self.assertEqual(self.index.reserver(tid(1), "n", 2), (True, 2))
        self.index.fusionner(tid(1), {"max": 5})
        self.assertEqual(self.index.reserver(tid(1), "n", lambda fiche: fiche["max"]), (True, 5))   # lu sous le verrou
        with self.assertRaises(ValueError):
            self.index.reserver(tid(9), "n", 2)

    def test_index_demesure_jamais_lu(self):
        # Taille plafonnée : vide pour l'affichage, ErreurIndex pour une écriture (rien n'est réécrit).
        self.index.enregistrer(tid(1), {"etat": "en_cours", "projet": "x" * 3000})
        avant = (self.dossier / "taches.json").read_bytes()
        self.assertGreater(len(avant), 2000)
        with mock.patch.object(st, "INDEX_MAX_OCTETS", 2000):
            self.assertEqual(self.index.lire(), {})
            with self.assertRaises(st.ErreurIndex):
                self.index.enregistrer(tid(2), {"etat": "en_cours"})
            with self.assertRaises(st.ErreurIndex):
                self.index.fusionner(tid(1), {"etat": "terminee"})
        self.assertEqual((self.dossier / "taches.json").read_bytes(), avant)
        self.assertEqual(st.INDEX_MAX_OCTETS, 8 * 1024 * 1024)

    def test_index_non_utf8_dit_illisible_et_non_demesure(self):
        (self.dossier / "taches.json").write_bytes(b'{"a": "\xff\xfe"}')
        self.assertEqual(self.index.lire(), {})
        with self.assertRaises(st.ErreurIndex) as c:
            self.index.enregistrer(tid(1), {"etat": "en_cours"})
        self.assertIn("UTF-8", str(c.exception))
        self.assertNotIn("démesuré", str(c.exception))
        self.assertEqual((self.dossier / "taches.json").read_bytes(), b'{"a": "\xff\xfe"}')

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
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00\x00\x02\x00isomiso2" + b"\r\n\x00\xff" * 40
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
        self.empreinte = None          # marqueur de l'image sur le serveur ; None : l'empreinte du dépôt (à jour)

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

    def _image(self, args, script, entree):
        import serveur_installation
        texte = serveur_installation.empreinte_etape("emulateur_image") if self.empreinte is None else self.empreinte
        return (0, (texte + "\n").encode(), "") if texte else (1, b"", "")

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
        if t["etat"] is not None and t["etat"]["etat"] != "en_attente":     # identifiant à l'état final : refus 4
            return 4, (json.dumps(t["etat"]) + "\n").encode(), ""
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
        if t["etat"] is None or t["etat"]["etat"] == "en_attente":
            t["etat"] = json.loads(script.split("<<'FIN_ETAT'\n", 1)[1].split("\n", 1)[0])
            t["apk"] = None
        elif t["etat"]["etat"] == "en_cours":
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

    def _film(self, args, script, entree):
        nom = args[1]
        f = self.taches[args[0]]["fichiers"]
        membres = [("./" + n, d) for n, d in sorted(f.items())
                   if n == f"videos/{nom}.mp4" or n.startswith(f"videos/{nom}-img/")]
        return (0, archive(membres), "") if membres else (3, b"", "")

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


class TestHotes(unittest.TestCase):
    """Réseau borné : les hôtes de la demande (noms DNS seulement) et leur transport jusqu'à l'enveloppe."""

    def test_aucun_hote_par_defaut(self):
        d = st.valider_demande(brut())
        self.assertEqual(d.hotes, ())
        self.assertEqual(st.valider_hotes(None), ())
        self.assertEqual(st.valider_hotes([]), ())

    def test_hotes_valides(self):
        d = st.valider_demande(brut(hotes=["service.exemple", "api.service.exemple"]))
        self.assertEqual(d.hotes, ("service.exemple", "api.service.exemple"))

    def test_hotes_refuses(self):
        for mauvais in (["127.0.0.1"], ["10.1.2.3"], ["localhost"], ["Service.Exemple"], ["a.exemple:443"], ["a.exemple/x"],
                        ["x.internal"], ["a.exemple", "a.exemple"], [1], "a.exemple", {"a": 1},
                        [f"h{i}.exemple" for i in range(6)], ["a.exemple\n"], ["a b.exemple"], ["a.exemple;rm"], [""]):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                st.valider_demande(brut(hotes=mauvais))

    def test_champ_inconnu_toujours_refuse(self):
        with self.assertRaises(ValueError):
            st.valider_demande(brut(reseau=True))


class TestLancer(BaseLanceur):
    def test_sans_hote_la_commande_n_a_pas_de_neuvieme_argument(self):
        self.lancer()
        commande = self.srv.ops("lancer")[0][1]
        ligne = [x for x in commande.splitlines() if x.startswith("exec bash")][0]
        self.assertTrue(ligne.endswith(" 50 104857600"), ligne)
        self.assertEqual(self.srv.taches[ID1]["demande"]["hotes"], [])
        self.assertNotIn("reseau", st.Index(self.dossier).lire()[ID1])

    def test_avec_hotes_la_commande_les_porte_et_la_fiche_le_dit(self):
        r = self.lancer(self.demande(hotes=["service.exemple", "api.service.exemple"]))
        self.assertEqual(r["etat"], "en_cours")
        ligne = [x for x in self.srv.ops("lancer")[0][1].splitlines() if x.startswith("exec bash")][0]
        self.assertTrue(ligne.endswith(" 50 104857600 service.exemple,api.service.exemple"), ligne)
        self.assertEqual(self.srv.taches[ID1]["demande"]["hotes"], ["service.exemple", "api.service.exemple"])
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["reseau"], ["service.exemple", "api.service.exemple"])

    def test_une_demande_a_hote_invalide_ne_part_jamais(self):
        with self.assertRaises(st.RefusLancement):
            self.lancer({**brut(id=ID1), "hotes": ["10.0.0.1"]})
        self.assertEqual(self.srv.ops("preparer"), [])

    def test_lancer_envoie_apk_en_octets_intacts(self):
        r = self.lancer()
        self.assertEqual(r, {"id": ID1, "etat": "en_cours", "serveur_id": "ovh1"})
        self.assertEqual(self.srv.taches[ID1]["apk"], APK)
        self.assertEqual(self.srv.taches[ID1]["demande"]["mode"], "scenario")
        self.assertEqual(self.srv.deposes, {nom: (RACINE / "serveur_ovh" / nom).read_bytes()      # commun.sh : sourcé par l'enveloppe
                                            for nom in ("taches/lancer_emulation.sh", "taches/commun.sh")})
        prep = self.srv.ops("preparer")[0]
        self.assertNotIn(b"PK", prep[1].encode())             # l'APK n'est jamais dans la commande
        lancement = self.srv.ops("lancer")[0][1]
        self.assertIn(f'lancer_emulation.sh" {ID1} scenario 1200 600 6144 2 50 104857600\n', lancement)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "en_cours")
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["serveur_id"], "ovh1")

    def test_lancer_passe_les_limites_de_la_demande_a_l_enveloppe(self):
        # T5 : mémoire et processeurs (valeurs de l'enveloppe), captures et octets de la demande, dans cet ordre.
        self.lancer(self.demande(limites={"duree_s": 300, "captures": 3, "octets": 5000}))
        lancement = self.srv.ops("lancer")[0][1]
        self.assertEqual(lancement.splitlines()[-1],
                         f'exec bash "{st.ENVELOPPE_DISTANTE}" {ID1} scenario 300 600 6144 2 3 5000')

    def test_image_perimee_refusee_avant_tout_envoi(self):
        # M3 : l'empreinte de l'image du serveur est relue (une lecture fixe) ; périmée -> refus, rien n'est envoyé.
        self.srv.empreinte = "ubuntu=20.04;jdk=17;fichiers=0000000000000000"
        with self.assertRaises(st.RefusLancement) as r:
            self.lancer()
        self.assertIn("périmée", str(r.exception))
        self.assertEqual([a[0] for a in self.srv.appels], ["image"])
        self.srv.empreinte = ""                                            # marqueur absent : périmée aussi
        with self.assertRaises(st.RefusLancement):
            self.lancer()
        self.srv.appels.clear()
        declarer(self.dossier, {"android-emulateur": "presente", "emulateur-image": "a_faire"})
        with self.assertRaises(st.RefusLancement):                         # l'état connu le dit : aucune connexion
            self.lancer()
        self.assertEqual(self.srv.appels, [])

    def test_image_a_jour_lancement_normal(self):
        self.assertEqual(self.lancer()["etat"], "en_cours")
        self.assertEqual(self.srv.appels[0][0], "image")
        self.assertEqual(len(self.srv.ops("image")), 1)

    def test_depot_de_l_enveloppe_lit_aussi_la_sortie_d_erreur(self):
        # T5 : code 0 mais un message de tar ou de mv sur la sortie d'erreur : dépôt douteux, refusé.
        serveur = st.choisir_serveur(self.dossier)
        avert = "Warning: Permanently added 'ovh1.exemple.net' (ED25519) to the list of known hosts.\r\n"
        for erreur, attendu in (("", None), (avert, None), ("tar: entree: Cannot open: Permission denied\n", "douteux"),
                                (avert + "mv: cannot move\n", "douteux")):
            with self.subTest(erreur=erreur), mock.patch.object(st, "_octets", return_value=(0, b"", erreur)):
                r = st._deposer_enveloppe(serveur, self.srv)
                if attendu is None:
                    self.assertIsNone(r)
                else:
                    self.assertIn(attendu, r)

    def test_depot_de_l_enveloppe_par_la_variante_silencieuse(self):
        # Une bannière de sshd ne doit pas rendre chaque dépôt « douteux » : LogLevel=ERROR sur ce seul appel.
        serveur = st.choisir_serveur(self.dossier)
        appels = []

        class Ssh:
            def executer_octets(self, *a, **k):
                appels.append("commun")
                return 0, b"", "Bienvenue sur ce serveur (bannière)\n"

            def executer_octets_silencieux(self, *a, **k):
                appels.append("silencieux")
                return 0, b"", ""
        self.assertIsNone(st._deposer_enveloppe(serveur, Ssh()))
        self.assertEqual(appels, ["silencieux"])

    def test_messages_image_perimee_et_empreinte_locale_illisible(self):
        with mock.patch.object(st.serveur_installation, "empreinte_etape", side_effect=OSError("absent")):
            with self.assertRaises(st.RefusLancement) as r:
                self.lancer()
        self.assertIn("empreinte locale", str(r.exception))
        self.assertNotIn("périmée", str(r.exception))
        self.srv.empreinte = "ubuntu=20.04;jdk=17;fichiers=0000000000000000"
        with self.assertRaises(st.RefusLancement) as r:
            self.lancer()
        self.assertIn("à mettre à jour", str(r.exception))
        (self.dossier / "serveurs-etat.json").write_text(json.dumps({"ovh1": {"capacites": {
            "android-emulateur": {"statut": "presente"},
            "emulateur-image": {"statut": "a_faire",
                                "detail": "À mettre à jour : les fichiers déposés sur le serveur sont périmés."}},
            "installation": {"en_cours": False}}}), encoding="utf-8")
        with self.assertRaises(st.RefusLancement) as r:
            st.choisir_serveur(self.dossier)
        self.assertIn("emulateur-image périmée (à mettre à jour)", str(r.exception))

    def test_archive_sans_copie_superflue(self):
        # M8 : mêmes octets qu'une archive tarfile, et une seule copie de l'APK en mémoire pendant la construction.
        import tracemalloc
        membres = [("entree/app.apk", APK, 0o644), ("demande.json", b'{"id": "x"}\n', 0o600)]
        tampon = io.BytesIO()
        with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for nom, donnees, droits in membres:
                info = tarfile.TarInfo(nom)
                info.size, info.mode, info.mtime, info.uid, info.gid, info.uname, info.gname = (
                    len(donnees), droits, 0, 0, 0, "", "")
                tar.addfile(info, io.BytesIO(donnees))
        self.assertEqual(st._archive(membres), tampon.getvalue())
        gros = b"PK\x03\x04" + b"\x00" * (20 * 1024 * 1024)
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            archive_ = st._archive([("entree/app.apk", gros, 0o644)])
            _actuel, pic = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertGreater(len(archive_), len(gros))
        self.assertLess(pic, 1.5 * len(gros))

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
        vrai = st.Index.fusionner

        def parfois(index, ident, champs):
            if champs.get("etat") == "en_cours":
                raise TimeoutError("Index des tâches occupé : réessayez.")
            return vrai(index, ident, champs)
        with mock.patch.object(st.Index, "fusionner", parfois):
            r = self.lancer()
        self.assertEqual(r["etat"], "en_cours")
        self.assertIn("occupé", r["erreur"])

    def test_echec_de_l_enveloppe_brule_l_identifiant_sans_nouvel_essai(self):
        self.srv.codes_lancer = [1]
        r = self.lancer()
        self.assertEqual(r["etat"], "echouee")
        self.assertEqual(len(self.srv.ops("lancer")), 1)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "echouee")
        self.assertEqual(len(self.srv.ops("abandon")), 1)               # identifiant brûlé : APK retiré
        self.assertIsNone(self.srv.taches[ID1]["apk"])

    def test_envoi_sans_reponse_n_efface_rien(self):
        for code in (124, 255):
            self.srv.appels.clear()
            with mock.patch.object(self.srv, "_preparer", lambda *a, c=code: (c, b"", "délai")):
                r = self.lancer()
            self.assertEqual(r["etat"], "echouee")
            self.assertEqual(self.srv.ops("effacer"), [])
            self.assertEqual(self.srv.ops("lancer"), [])
        with mock.patch.object(self.srv, "_preparer", lambda *a: (1, b"", "disque plein")):
            self.lancer()
        self.assertEqual(len(self.srv.ops("effacer")), 1)

    def test_attente_max_invalide_refusee_avant_ssh(self):
        for mauvais in (None, -1, "10", True, 1.5):
            with self.assertRaises(st.RefusLancement, msg=repr(mauvais)):
                self.lancer(attente_max_s=mauvais)
        self.assertEqual(self.srv.appels, [])

    def test_inactivite_par_defaut_depasse_le_demarrage_du_pont(self):
        self.assertEqual(st.LIMITES_DEFAUT["inactivite_s"], 600)
        self.assertGreater(st.LIMITES_DEFAUT["inactivite_s"], 300)
        with self.assertRaises(ValueError):
            st.valider_demande(brut(limites={"inactivite_s": 601}))

    def test_inactivite_du_pilote_entre_300_et_600(self):
        pilote = {"mode": "pilote", "scenario": None}
        for mauvais in (1, 60, 299, 601):
            with self.assertRaises(ValueError, msg=mauvais) as r:
                st.valider_demande(brut(limites={"inactivite_s": mauvais}, **pilote))
            self.assertIn("inactivite_s", str(r.exception))
        for bon in (300, 450, 600):
            self.assertEqual(st.valider_demande(brut(limites={"inactivite_s": bon}, **pilote)).limites["inactivite_s"], bon)
        self.assertEqual(st.valider_demande(brut(limites={"inactivite_s": 60})).limites["inactivite_s"], 60)   # scénario
        with self.assertRaises(st.RefusLancement):
            self.lancer({**brut(id=ID1), "mode": "pilote", "scenario": None, "limites": {"inactivite_s": 120}})
        self.assertEqual(self.srv.appels, [])

    def test_arreter_pendant_l_attente_du_creneau(self):
        self.srv.creneau = "t20261119-090000-ffff"

        def dormir(s):
            self.pauses.append(s)
            if len(self.pauses) == 1:
                st.arreter(ID1, dossier=self.dossier, ssh=self.srv)
                self.srv.creneau = None                 # le créneau se libère : l'émulateur ne doit pas démarrer
        r = self.lancer(dormir=dormir)
        self.assertEqual(r["etat"], "arretee")
        self.assertNotIn("erreur", r)                                     # issue normale, pas « identifiant déjà utilisé »
        self.assertEqual(self.srv.taches[ID1]["etat"]["etat"], "arretee")
        self.assertIsNone(self.srv.taches[ID1]["apk"])
        self.assertIsNone(self.srv.creneau)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "arretee")

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

    def test_archive_abimee_erreur_mais_coupee_au_plafond_limite(self):
        self.preparer(limites={"octets": 4000})
        self.srv.archive = b"pas une archive tar" * 20
        self.assertEqual(self.rapatrier()["statut"], "erreur")
        complete = archive([("./pont.log", b"x\n" * 100), ("./captures/a.png", PNG + b"z" * 3000)])
        self.srv.archive = complete[:1500]                                   # coupée avant le plafond : abîmée
        self.assertEqual(self.rapatrier()["statut"], "erreur")
        with mock.patch.object(st, "TAILLE_ARCHIVE_MARGE", 0):
            self.srv.archive = complete[:4000]                               # coupée exactement au plafond (head -c)
            m = self.rapatrier()
        self.assertEqual(m["statut"], "limite")
        self.assertTrue(m["tronque"])

    def test_archive_complete_demande_une_capture_de_plus(self):
        self.preparer(limites={"captures": 2})
        script = st._script_rapatrier(ID1, st._limites({"captures": 2}))
        self.assertIn("head -z -n 3 ", script)
        self.assertIn("head -z -n 1 ", st._script_rapatrier(ID1, st._limites({"captures": 2}), "ecran"))

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

    def test_videos_images_et_logcat_rapatries(self):
        self.preparer(fichiers={"pont.log": b"filmer demo 3ms\n", "logcat.txt": b"# journal - x\nI Test: un\n",
                                "videos/demo.mp4": MP4, "videos/demo-img/demo-001.png": PNG,
                                "videos/demo-img/demo-002.png": PNG + b"2", "videos/court.mp4": MP4 + b"c"})
        m = self.rapatrier()
        self.assertEqual(m["statut"], "ok", m)
        self.assertEqual(Path(m["logcat"]).read_bytes(), b"# journal - x\nI Test: un\n")
        par = {Path(v["mp4"]).name: v for v in m["videos"]}
        self.assertEqual(set(par), {"demo.mp4", "court.mp4"})
        self.assertEqual(Path(par["demo.mp4"]["mp4"]), self.dest / "videos" / "demo.mp4")
        self.assertEqual(Path(par["demo.mp4"]["mp4"]).read_bytes(), MP4)
        self.assertEqual([Path(p).name for p in par["demo.mp4"]["images"]], ["demo-001.png", "demo-002.png"])
        self.assertEqual(par["court.mp4"]["images"], [])
        rapport = json.loads(Path(m["rapport"]).read_text(encoding="utf-8"))
        self.assertEqual(rapport["logcat"], "logcat.txt")
        self.assertIn({"mp4": "videos/demo.mp4", "images": ["videos/demo-img/demo-001.png",
                                                             "videos/demo-img/demo-002.png"]}, rapport["videos"])

    def test_videos_hostiles_refusees(self):
        self.preparer()
        lien = tarfile.TarInfo("videos/lien.mp4")
        lien.type, lien.linkname = tarfile.SYMTYPE, "/etc/passwd"
        dossier = tarfile.TarInfo("videos")
        dossier.type = tarfile.SYMTYPE
        dossier.linkname = "/home"
        self.srv.archive = archive([
            ("./videos/ok.mp4", MP4), ("videos/faux.mp4", b"pas une video" * 3), ("videos/../x.mp4", MP4),
            ("videos/con.mp4", MP4), ("videos/A.mp4", MP4), ("videos/ok-img/../../y.png", PNG),
            ("videos/ok-img/autre-001.png", PNG), ("videos/ok-img/ok-1.png", PNG), ("videos/ok-img/ok-001.png", b"pas png"),
            ("videos/ok-img/ok-001.PNG", PNG), ("videos/ok.mp4.exe", MP4), ("videos/sous/ok.mp4", MP4),
            ("videos/ok-img/ok-002.png", PNG), (lien, None), (dossier, None)])
        m = self.rapatrier()
        self.assertEqual(m["statut"], "erreur")
        self.assertGreaterEqual(m["refuses"], 12)
        ecrits = sorted(p.relative_to(self.dest).as_posix() for p in self.dest.rglob("*") if p.is_file())
        self.assertEqual(ecrits, ["rapport.json", "videos/ok-img/ok-002.png", "videos/ok.mp4"])

    def test_videos_bornees_en_nombre_et_en_taille(self):
        self.preparer()
        membres = [(f"./videos/v{i}.mp4", MP4) for i in range(7)]
        membres += [(f"./videos/v0-img/v0-{i:03d}.png", PNG) for i in range(1, 160)]
        self.srv.archive = archive(membres)
        m = self.rapatrier()
        self.assertEqual(len(m["videos"]), 5)
        self.assertEqual(len(m["videos"][0]["images"]), 30)              # 30 images par film au plus
        self.assertTrue(m["tronque"])
        self.assertEqual(m["statut"], "limite")
        with mock.patch.object(st, "VIDEO_MAX_OCTETS", 50):                 # au-delà de la taille d'une vidéo
            self.srv.archive = archive([("./videos/grosse.mp4", MP4)])
            m = self.rapatrier()
        self.assertEqual((m["videos"], m["statut"]), ([], "limite"))
        with mock.patch.object(st, "LOGCAT_MAX_OCTETS", 10):               # logcat.txt démesuré : pas pris
            self.srv.archive = archive([("./logcat.txt", b"x" * 50)])
            m = self.rapatrier()
        self.assertIsNone(m["logcat"])
        self.assertTrue(m["tronque"])

    def test_images_sans_leur_video_refusees_et_jamais_ecrites(self):
        self.preparer()
        self.srv.archive = archive([("./videos/orphelin-img/orphelin-001.png", PNG), ("./videos/ok.mp4", MP4),
                                    ("./videos/ok-img/ok-001.png", PNG), ("./videos/faux.mp4", b"pas une video" * 3),
                                    ("./videos/faux-img/faux-001.png", PNG)])
        m = self.rapatrier()
        self.assertEqual(m["statut"], "erreur")
        self.assertGreaterEqual(m["refuses"], 3)                                 # orphelin, faux.mp4, image de faux
        ecrits = sorted(p.relative_to(self.dest).as_posix() for p in self.dest.rglob("*") if p.is_file())
        self.assertEqual(ecrits, ["rapport.json", "videos/ok-img/ok-001.png", "videos/ok.mp4"])
        self.assertFalse((self.dest / "videos" / "orphelin-img").exists())

    def test_images_d_une_video_coupee_par_les_limites_sont_une_limite(self):
        self.preparer()
        with mock.patch.object(st, "VIDEO_MAX_OCTETS", 50):
            self.srv.archive = archive([("./videos/grosse.mp4", MP4), ("./videos/grosse-img/grosse-001.png", PNG)])
            m = self.rapatrier()
        self.assertEqual((m["statut"], m["refuses"]), ("limite", 0))
        self.assertFalse((self.dest / "videos" / "grosse-img").exists())

    def test_logcat_un_peu_trop_long_est_coupe_au_plafond(self):
        self.preparer()
        with mock.patch.object(st, "LOGCAT_MAX_OCTETS", 10):
            self.srv.archive = archive([("./pont.log", b"x\n"), ("./logcat.txt", b"0123456789ABCDE")])
            m = self.rapatrier()
        self.assertEqual(Path(m["logcat"]).read_bytes(), b"0123456789")
        self.assertEqual((m["statut"], m["tronque"]), ("ok", False))

    def test_bombe_de_taille_video(self):
        self.preparer(limites={"octets": 1000})
        info = tarfile.TarInfo("./videos/bombe.mp4")
        info.size = 10 ** 10
        tampon = io.BytesIO()
        tampon.write(info.tobuf(format=tarfile.GNU_FORMAT))
        tampon.write(MP4)
        self.srv.archive = tampon.getvalue()
        m = self.rapatrier()
        self.assertEqual(m["videos"], [])
        self.assertNotEqual(m["statut"], "ok")

    def test_une_recette_en_echec_ne_laisse_jamais_ok_sur_le_disque(self):
        # I2 : la recette a échoué (installer -> 4) ; le veilleur a écrit arretee/ok : le rapport dit erreur.
        for code, attendu in ((4, "erreur"), (2, "erreur"), (3, "limite")):
            with self.subTest(code=code):
                self.preparer(etat="arretee", statut="ok")
                echec = {"etape": 1, "verbe": "installer", "code": code, "reponse": "adb install a échoué."}
                m = self.rapatrier(echec=echec)
                self.assertEqual(m["statut"], attendu)
                rapport = json.loads(Path(m["rapport"]).read_text(encoding="utf-8"))
                self.assertEqual(rapport["statut"], attendu)
                self.assertEqual(rapport["echec"]["verbe"], "installer")
        self.preparer(fichiers={"pont.log": b"x\n", "plantage.txt": b"FATAL EXCEPTION\n"})
        self.assertEqual(self.rapatrier(echec={"etape": 0, "verbe": "lancer", "code": 4, "reponse": ""})["statut"],
                         "plantage")                                         # le plantage prime
        self.preparer()
        self.assertEqual(self.rapatrier(echec=None)["statut"], "ok")

    def test_les_journaux_ne_comptent_pas_dans_les_octets_des_captures(self):
        # M6 : des captures proches de la limite ne deviennent pas « limite » à cause des journaux.
        self.preparer(limites={"octets": 1000})
        self.srv.archive = archive([("./pont.log", b"j" * 600), ("./emulateur.log", b"e" * 600),
                                    ("./captures/a.png", PNG[:8] + b"y" * 892)])
        m = self.rapatrier()
        self.assertEqual((m["statut"], m["tronque"]), ("ok", False))
        self.assertEqual(len(m["captures"]), 1)
        self.assertEqual(Path(m["journal"]).read_bytes(), b"j" * 600)
        self.assertEqual((self.dest / "emulateur.log").read_bytes(), b"e" * 600)
        self.srv.archive = archive([("./pont.log", b"j" * (st.JOURNAL_MAX_OCTETS + 1)),
                                    ("./captures/a.png", PNG[:8] + b"y" * 892)])
        with mock.patch.object(st, "TAILLE_ARCHIVE_MARGE", st.TAILLE_ARCHIVE_MARGE + st.JOURNAL_MAX_OCTETS):
            m = self.rapatrier()
        self.assertTrue(m["tronque"])                                        # un journal démesuré n'est pas pris
        self.assertFalse((self.dest / "journal.txt").exists() and
                         (self.dest / "journal.txt").stat().st_size > st.JOURNAL_MAX_OCTETS)

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

    def test_capturer_compte_par_le_lanceur_au_dela_de_la_limite(self):
        self.fiche(limites={"captures": 2})
        for n in ("a", "b", "c"):
            self.srv.taches[ID1]["fichiers"][f"captures/{n}.png"] = PNG
        self.srv.pont["capturer"] = (2, ligne_pont(False, "capturer", "Nom de capture déjà pris : x."))
        self.assertEqual(self.verbe("capturer", ["x"])["code"], 2)                 # refus du pont : place rendue
        del self.srv.pont["capturer"]
        self.assertTrue(self.verbe("capturer", ["a"])["ok"])
        self.assertTrue(self.verbe("capturer", ["b"])["ok"])
        appels = len(self.srv.ops("verbe"))
        r = self.verbe("capturer", ["c"])
        self.assertEqual((r["ok"], r["code"]), (False, 3))
        self.assertIn("Limite de captures", r["detail"])
        self.assertEqual(len(self.srv.ops("verbe")), appels)                       # rien relayé
        f = st.Index(self.dossier).lire()[ID1]
        self.assertEqual((f["captures_prises"], f["limite_atteinte"]), (2, True))
        self.assertTrue(self.verbe("toucher", ["1", "2"])["ok"])                   # les autres verbes passent

    def test_place_de_capture_gardee_si_la_reponse_est_perdue(self):
        self.fiche(limites={"captures": 4})
        for code, sortie in ((124, ""), (255, ""), (0, "pas du json\n"), (1, "")):
            self.srv.pont["capturer"] = (code, sortie)
            if code in (124, 255):
                with mock.patch.object(self.srv, "_verbe", lambda *a, c=code: (c, b"", "délai")):
                    r = self.verbe("capturer", ["x"])
            else:
                r = self.verbe("capturer", ["x"])
            self.assertFalse(r["ok"])
            self.assertNotIn("_lisible", r)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["captures_prises"], 4)   # aucune place rendue
        self.assertEqual(self.verbe("capturer", ["y"])["code"], 3)

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

    def test_finfilm_rapatrie_la_video_et_ses_images(self):
        f = self.srv.taches[ID1]["fichiers"]
        f.update({"videos/demo.mp4": MP4, "videos/demo-img/demo-001.png": PNG, "videos/demo-img/demo-002.png": PNG,
                  "videos/autre.mp4": MP4})
        self.srv.pont["finfilm"] = (0, ligne_pont(True, "finfilm", "videos/demo.mp4 (200 octets, 3 s, 2 images)."))
        r = self.verbe("finfilm", destination=self.dest)
        self.assertTrue(r["ok"], r)
        self.assertEqual(Path(r["video"]), self.dest / "videos" / "demo.mp4")
        self.assertEqual(Path(r["video"]).read_bytes(), MP4)
        self.assertEqual([Path(p).name for p in r["images"]], ["demo-001.png", "demo-002.png"])
        self.assertFalse((self.dest / "videos" / "autre.mp4").exists())              # seulement ce film
        self.assertEqual(self.srv.ops("film")[0][1].split("\n", 1)[0], f"# tache:film {ID1} demo")

    def test_finfilm_reponse_douteuse_ne_rapatrie_rien(self):
        for detail in ("videos/../x.mp4 (1 octets, 1 s, 0 images).", "videos/CON.mp4 (1 octets)", "rien", "videos/con.mp4 (1)"):
            with self.subTest(detail=detail):
                self.srv.pont["finfilm"] = (0, ligne_pont(True, "finfilm", detail))
                r = self.verbe("finfilm", destination=self.dest)
                self.assertFalse(r["ok"])
                self.assertNotIn("video", r)
        self.assertEqual(self.srv.ops("film"), [])

    def test_demarrer_sur_une_tache_finie_donne_la_raison_du_serveur(self):
        # Conteneur mort au démarrage : « la tâche n'est plus en cours » ET la raison écrite par le veilleur (l'agent et le
        # rapport de la recette voient pourquoi : AVD non créé...).
        del self.srv.taches[ID1]["fichiers"][".avd-pret"]
        self.srv.avd_apres = None
        self.srv.taches[ID1]["etat"].update(etat="echouee", statut="erreur", fin=iso(self.srv.maintenant),
                                            raison="Le conteneur s'est arrêté au démarrage : Création de l'AVD emul impossible.")
        self.srv.taches[ID1]["veilleur"] = "mort"
        r = self.verbe("demarrer")
        self.assertEqual((r["ok"], r["code"]), (False, 4))
        self.assertIn("n'est plus en cours", r["detail"])
        self.assertIn("Création de l'AVD emul impossible", r["detail"])

    def test_verbe_serveur_injoignable(self):
        self.srv.injoignable = "Connection refused"
        r = self.verbe("lancer")
        self.assertEqual((r["ok"], r["code"]), (False, 255))

    def test_delai_ssh_par_verbe(self):
        # M5 : `arreter` du pont peut durer ~80 s, `installer` ~180 s : marge au-dessus de leur propre borne.
        # arreter et finfilm : jusqu'à ~250 s de film (SIGINT, attente, adb pull, ffmpeg 120 s) en plus de leur propre borne
        for v, attendu in (("arreter", 480), ("installer", 240), ("toucher", st.DELAI_VERBE_S), ("demarrer", 360),
                           ("filmer", 60), ("finfilm", 420)):
            with self.subTest(verbe=v):
                self.verbe(v, {"toucher": ["1", "2"], "filmer": ["demo"]}.get(v, []))
                self.assertEqual(self.srv.ops("verbe")[-1][3], attendu)

    def test_nom_de_capture_reserve_sous_windows_refuse_avant_ssh(self):
        for nom in ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9", "com0", "lpt0"):
            with self.subTest(nom=nom), self.assertRaises(ValueError):
                self.verbe("capturer", [nom])
        self.assertEqual(self.srv.appels, [])


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
            ("capturer", ["0_x"]), ("capturer", ["b" * 40]), ("capturer", ["console"]), ("capturer", ["com10"]),
            ("capturer", ["con-1"]), ("capturer", ["lpt"]), ("capturer", ["nulle"]), ("capturer", ["aux_2"]),
            ("journal", []), ("journal", ["pair"]),
            ("journal", ["ActivityManager:I"]), ("journal", ["com.exemple.app"]), ("installer", []), ("lancer", []),
            ("arreter", []), ("filmer", ["demo"]), ("filmer", ["clip_2", "180"]), ("filmer", ["v", "1"]),
            ("filmer", ["film-9", "99"]), ("finfilm", [])]
COMMUNS = [";", "$(x)", "`x`", "a\nb", "", "$(touch ../pwn)", "*", "a;b", "x'y", "a|b", "&", ">", "a\r", "\r", "--",
           "-s", "?", "[", "a&b", "a>b"]
REFUSES = ([("toucher", [v, "1"]) for v in COMMUNS + ["..", "-1", "99999", "1.5", " 1"]]
           + [("toucher", ["10", v]) for v in ("-1", "99999")] + [("toucher", ["10"]), ("toucher", ["10", "20", "30"])]
           + [("glisser", ["1", "2", "3", v]) for v in ("..", "-1", "99999", "10000")]
           + [("glisser", ["1", "2", "3"]), ("glisser", ["1", "2", "3", "4", "5"])]
           + [("attendre", [v]) for v in COMMUNS + ["..", "-1", "99999", "121", "1000", "010"]]
           + [("capturer", [v]) for v in COMMUNS + ["..", "../x", "a/b", "A", "x.png", "a" * 41, "_a", "a\n"]]
           # noms réservés de Windows (la capture ne pourrait pas être rapatriée sur le poste) ; CON, Con.png : déjà
           # refusés par le motif (minuscules, sans point)
           + [("capturer", [v]) for v in ("con", "prn", "aux", "nul", "com0", "com1", "com9", "lpt0", "lpt1", "lpt9",
                                          "CON", "Con", "con.png", "nul.txt")]
           + [("capturer", ["a", "b"])]
           + [("texte", [v]) for v in COMMUNS + ["a" * 61, "a/b", "é", "50%", " a", ".x"]]
           + [("touche", [v]) for v in COMMUNS + ["..", "-1", "99999", "power", "retour ", "KEYCODE_POWER", "retour\n"]]
           + [("journal", [v]) for v in COMMUNS + ["a b", "a/b", "a" * 61, ":x", ".x"]] + [("journal", ["a", "b"])]
           + [("installer", [v]) for v in ("/etc/passwd", "../entree/app.apk", ";", "")]
           + [("demarrer", ["-1"]), ("lancer", [".."]), ("arreter", ["99999"])]
           + [(v, []) for v in ("rm", "", "TOUCHER", "toucher;ls", "sh", "eval", "demarrer\n", "../pont")]
           + [("filmer", [v]) for v in COMMUNS + ["..", "../x", "a/b", "A", "x.mp4", "a" * 41, "con", "lpt1"]]
           + [("filmer", ["demo", v]) for v in COMMUNS + ["0", "181", "030", "-1", "1.5", "999", "1000"]]
           + [("filmer", []), ("filmer", ["a", "30", "x"]), ("finfilm", ["demo"]), ("finfilm", [";"])])


class TestMotifs(unittest.TestCase):
    def test_table_python(self):
        for v, args in ACCEPTES:
            self.assertEqual(st.valider_verbe(v, args), tuple(args), (v, args))
        for v, args in REFUSES:
            with self.assertRaises(ValueError, msg=(v, args)):
                st.valider_verbe(v, args)
        self.assertEqual(set(st.VERBES), {"demarrer", "installer", "lancer", "toucher", "glisser", "texte", "touche",
                                          "attendre", "capturer", "journal", "arreter", "filmer", "finfilm"})

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_motifs_python_et_pont_s_accordent(self):
        from tests.test_serveur_pont import Banc
        with Banc(PONT_PAQUET="com.exemple.app") as banc:
            for v, args in ACCEPTES + REFUSES:
                if (v == "lancer" and not args) or (v == "finfilm" and not args):
                    continue                                # exige un paquet installé / un film en cours : couverts ailleurs
                with self.subTest(verbe=v, args=args):
                    try:
                        st.valider_verbe(v, args)
                        python = True
                    except ValueError:
                        python = False
                    code, _d = banc.lancer(v, *args)
                    self.assertEqual(python, code != 2, (v, args, code, _d))
                    if v == "filmer" and code == 0:
                        self.assertEqual(banc.lancer("finfilm")[0], 0)      # un seul film à la fois : on le finit


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
        self.pont = ""
        for nom, corps in (("sudo", '[ "$1" = -n ] && shift\nexec "$@"'),
                           ("docker", 'echo "docker $*" >> "$FAUX_DOCKER"\n'
                                      '[ "$1" = exec ] && printf \'%s\\n\' "$FAUX_PONT"\nexit 0')):
            (self.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (self.bin / nom).chmod(0o755)

    def _env(self):
        return dict(os.environ, HOME=posix(self.home), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                    FAUX_DOCKER=posix(self.journal), MSYS="winsymlinks:lnk", FAUX_PONT=self.pont)

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
        commun = self.ssh.home / "myiafactory" / "serveur_ovh" / "taches" / "commun.sh"     # sourcé par l'enveloppe
        self.assertEqual(commun.read_bytes(), (RACINE / "serveur_ovh" / "taches" / "commun.sh").read_bytes())

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

    def lancer_enveloppe_agent(self):
        """Un vrai processus `bash lancer_agent.sh <id>` vivant, son pid dans enveloppe.pid ; renvoie l'arrêt à appeler."""
        dossier = self.ssh.home / "faux"
        dossier.mkdir()
        (dossier / "lancer_agent.sh").write_text("sleep 60\n", encoding="utf-8", newline="\n")
        r = self.ssh.bash(f'cd "{posix(dossier)}" && {{ nohup bash lancer_agent.sh {ID1} </dev/null >/dev/null 2>&1 & '
                          f'echo $! > "{posix(self.tache)}/enveloppe.pid"; }}')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(lambda: self.ssh.bash(f'kill $(cat "{posix(self.tache)}/enveloppe.pid") 2>/dev/null; true'))

    def test_etat_et_nettoyer_reels_voient_l_enveloppe_d_agent_vivante(self):
        self.fiche()
        self.ecrire_etat(etat="en_cours", statut=None, fin=None)
        (self.tache / "veilleur.pid").write_text("999999\n", encoding="utf-8")
        self.lancer_enveloppe_agent()
        lu = st._etat_json((self.tache / "etat.json").read_text(encoding="utf-8"), ID1)
        self.assertEqual(st._nettoyer(self.serveur, self.ssh, ID1, lu), lu)          # code 4 : rien nettoyé
        self.assertNotIn("docker rm", self.ssh.docker())
        r = st.etat(ID1, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(r["etat"], "en_cours")
        self.assertEqual(json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))["etat"], "en_cours")

    def test_arreter_reel_en_attente_retire_le_paquet_d_un_agent(self):
        self.fiche(etat="en_attente")
        (self.tache / "entree").mkdir(parents=True)
        for nom in ("projet.bundle", "app.apk", "argv.json"):
            (self.tache / "entree" / nom).write_bytes(b"x")
        r = st.arreter(ID1, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(r["etat"], "arretee")
        self.assertEqual(sorted(p.name for p in (self.tache / "entree").iterdir()), ["argv.json"])

    def test_arreter_reel_d_un_agent_laisse_l_arret_au_veilleur(self):
        """Tâche d'agent : jamais de docker stop -t 10 (le veilleur arrête avec -t 60, le temps que l'entrée conclue) ;
        une tâche d'émulation garde le sien."""
        self.fiche()
        self.ecrire_etat()
        (self.tache / "entree").mkdir(parents=True, exist_ok=True)
        (self.tache / "entree" / "demande.json").write_text(json.dumps({"id": ID1, "type": "agent"}), encoding="utf-8")
        st.arreter(ID1, dossier=self.dossier, ssh=self.ssh)
        self.assertNotIn(f"docker stop -t 10 tache-{ID1}", self.ssh.docker())
        (self.tache / "entree" / "demande.json").write_text(json.dumps({"id": ID1, "type": "emulation"}), encoding="utf-8")
        st.arreter(ID1, dossier=self.dossier, ssh=self.ssh)
        self.assertIn(f"docker stop -t 10 tache-{ID1}", self.ssh.docker())

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

    def captures(self, n):
        dossier = self.tache / "sortie" / "captures"
        dossier.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (dossier / f"c{i}.png").write_bytes(PNG + bytes([i]))
        return dossier

    def test_rapatrier_reel_videos_images_et_logcat(self):
        self.fiche()
        self.ecrire_etat()
        sortie = self.tache / "sortie"
        (sortie / "pont.log").write_bytes(b"filmer demo 3ms\n")
        (sortie / "logcat.txt").write_bytes(b"# journal - x\nI: un\n")
        videos = sortie / "videos"
        (videos / "demo-img").mkdir(parents=True)
        (videos / "demo.mp4").write_bytes(MP4)
        (videos / "demo-img" / "demo-001.png").write_bytes(PNG)
        dehors = Path(self.tmp.name) / "dehors"
        dehors.mkdir()
        (dehors / "vol-001.png").write_bytes(PNG)
        (dehors / "vol.mp4").write_bytes(MP4)
        r = self.ssh.bash(f'cd "{posix(videos)}" && ln -s "{posix(dehors)}" vol-img && ln -s "{posix(dehors / "vol.mp4")}" '
                          f'vol.mp4 && [ -L vol-img ]')
        if r.returncode != 0:
            self.skipTest("liens symboliques non pris en charge")
        m = st.rapatrier(ID1, self.dest, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(m["statut"], "ok", m)
        self.assertEqual([(Path(v["mp4"]).name, [Path(i).name for i in v["images"]]) for v in m["videos"]],
                         [("demo.mp4", ["demo-001.png"])])
        self.assertEqual(Path(m["logcat"]).read_bytes(), b"# journal - x\nI: un\n")
        self.assertFalse((self.dest / "videos" / "vol-img").exists())
        self.assertFalse((self.dest / "videos" / "vol.mp4").exists())
        # un seul film (pilote, après finfilm) : la vidéo et ses images, rien d'autre
        dest2 = Path(self.tmp.name) / "projet" / ".factory" / "serveur" / "film"
        chemin, images, raison = st._rapatrier_film(self.serveur, self.ssh, ID1, "demo", dest2, st._limites({}))
        self.assertEqual((Path(chemin).name, [Path(i).name for i in images], raison), ("demo.mp4", ["demo-001.png"], None))
        self.assertEqual(sorted(p.relative_to(dest2).as_posix() for p in dest2.rglob("*") if p.is_file()),
                         ["videos/demo-img/demo-001.png", "videos/demo.mp4"])

    def test_rapatrier_reel_captures_au_dela_de_la_limite(self):
        self.fiche(limites={"captures": 2})
        self.ecrire_etat()
        (self.tache / "sortie" / "pont.log").write_bytes(b"capturer c0 3ms\n")
        self.captures(10)
        m = st.rapatrier(ID1, self.dest, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(m["statut"], "limite")
        self.assertTrue(m["tronque"])
        self.assertEqual(len(m["captures"]), 2)
        self.assertEqual(m["refuses"], 0)

    def test_rapatrier_reel_dossier_captures_remplace_par_un_lien(self):
        self.fiche()
        self.ecrire_etat()
        (self.tache / "sortie" / "pont.log").write_bytes(b"x\n")
        dehors = Path(self.tmp.name) / "dehors"
        dehors.mkdir()
        (dehors / "vol.png").write_bytes(PNG)
        r = self.ssh.bash(f'cd "{posix(self.tache / "sortie")}" && ln -s "{posix(dehors)}" captures && [ -L captures ]')
        if r.returncode != 0:
            self.skipTest("liens symboliques non pris en charge")
        m = st.rapatrier(ID1, self.dest, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(m["captures"], [])
        self.assertEqual(m["statut"], "ok")
        self.assertFalse((self.dest / "captures").exists())

    def test_capture_reelle_unique_par_le_relais(self):
        self.fiche(limites={"captures": 5})
        self.ecrire_etat(etat="en_cours", statut=None, fin=None)
        captures = self.captures(2)
        self.ssh.bash(f'cd "{posix(captures)}" && ln -s c0.png lien.png; true')
        self.ssh.pont = ligne_pont(True, "capturer", "captures/c1.png (90 octets).").strip()
        res = st.verbe(ID1, "capturer", ["c1"], dossier=self.dossier, ssh=self.ssh, destination=self.dest)
        self.assertTrue(res["ok"], res)
        self.assertEqual(Path(res["capture"]).read_bytes(), PNG + b"\x01")
        self.assertEqual(sorted(p.name for p in (self.dest / "captures").iterdir()), ["c1.png"])
        res = st.verbe(ID1, "capturer", ["lien"], dossier=self.dossier, ssh=self.ssh, destination=self.dest)
        self.assertFalse(res["ok"])                                        # un lien n'est jamais rapatrié
        res = st.verbe(ID1, "capturer", ["absente"], dossier=self.dossier, ssh=self.ssh, destination=self.dest)
        self.assertFalse(res["ok"])
        self.assertIn(f"docker exec tache-{ID1} /usr/local/bin/pont capturer c1", self.ssh.docker())

    def test_arreter_reel_en_attente(self):
        self.fiche(etat="en_attente")
        self.ecrire_etat(etat="en_attente", statut=None, debut=None, fin=None)
        (self.tache / "entree").mkdir()
        (self.tache / "entree" / "app.apk").write_bytes(APK)
        r = st.arreter(ID1, dossier=self.dossier, ssh=self.ssh)
        self.assertEqual(r["etat"], "arretee")
        sur_disque = json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))
        self.assertEqual((sur_disque["etat"], sur_disque["id"]), ("arretee", ID1))
        self.assertFalse((self.tache / "entree" / "app.apk").exists())
        self.assertFalse((self.tache / "etat.json.lanceur.tmp").exists())
        self.assertFalse((self.tache / "arret").exists())
        self.assertEqual(st.arreter(ID1, dossier=self.dossier, ssh=self.ssh)["etat"], "arretee")   # idempotent
        self.assertEqual(sorted(p.name for p in self.tache.iterdir()), ["entree", "etat.json", "sortie"])

    def veilleur_factice(self):
        """Un veilleur simulé : attend le fichier arret, puis écrit l'état final comme lancer_emulation.sh (fin -> terminee,
        autre -> arretee, statut ok)."""
        script = r'''d="$1"; i=0
until [ -e "$d/arret" ]; do sleep 0.1; i=$((i + 1)); [ "$i" -lt 300 ] || exit 1; done
m=""; IFS= read -r m < "$d/arret"; e=arretee; [ "$m" = fin ] && e=terminee
printf '{"id": "%s", "etat": "%s", "statut": "ok", "debut": "2026-11-19T10:15:00Z", "fin": "2026-11-19T10:16:40Z", "raison": "%s"}\n' \
  "$2" "$e" "$m" > "$d/etat.json.v" && mv -f "$d/etat.json.v" "$d/etat.json"'''
        p = subprocess.Popen(["bash", "-c", script, "bash", posix(self.tache), ID1], env=self.ssh._env(),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        return p

    def test_arreter_reel_en_cours_ecrit_arret_et_attend_le_veilleur(self):
        self.fiche()
        for fin, motif, final in ((True, "fin", "terminee"), (False, "arret", "arretee")):
            with self.subTest(motif=motif):
                self.ecrire_etat(etat="en_cours", statut=None, fin=None)
                for reste in ("arret", "arret.tmp"):
                    (self.tache / reste).unlink(missing_ok=True)
                v = self.veilleur_factice()
                debut = time.monotonic()
                r = st.arreter(ID1, dossier=self.dossier, ssh=self.ssh, fin=fin)
                self.assertEqual(v.wait(30), 0)
                self.assertLess(time.monotonic() - debut, 25)
                self.assertEqual((r["etat"], r["statut"]), (final, "ok"))
                self.assertEqual((self.tache / "arret").read_text(encoding="utf-8"), motif + "\n")
                self.assertFalse((self.tache / "arret.tmp").exists())
        # Le script seul : aucun bruit sur la sortie d'erreur, code 0.
        self.ecrire_etat(etat="en_cours", statut=None, fin=None)
        (self.tache / "arret").unlink()
        v = self.veilleur_factice()
        code, _s, erreur = self.ssh.executer("h", "bash -s", "c", stdin=st._script(
            st._ARRETER, ID1, MOTIF="arret", JSON=json.dumps({"id": ID1, "etat": "arretee"})))
        v.wait(30)
        self.assertEqual((code, erreur), (0, ""))

    def test_chaque_modele_passe_bash_n_et_s_execute(self):
        """Tous les scripts distants du module : syntaxe (bash -n) puis exécution réelle, sans bruit sur stderr."""
        modeles = {n for n, v in vars(st).items() if isinstance(v, str) and v.startswith("# tache:")}
        self.assertEqual(modeles, {"_ETAT", "_NETTOYER", "_ARRETER", "_PREPARER", "_DEPOSER", "_LANCER", "_EFFACER",
                                   "_ABANDON", "_AVD", "_VERBE", "_RAPATRIER", "_IMAGE"})
        self.fiche(limites={"captures": 3})
        lim = st._limites({"captures": 3})
        final = json.dumps({"id": ID1, "etat": "arretee", "statut": None, "debut": None, "fin": "2026-11-19T10:16:40Z",
                            "raison": "test"})
        rendus = {"_PREPARER": st._script(st._PREPARER, ID1), "_DEPOSER": st._DEPOSER, "_IMAGE": st._IMAGE,
                  "_LANCER": st._script(st._LANCER, ID1, MODE="pilote", DUREE="60", INACTIVITE="600", MEMOIRE="6144",
                                        CPUS="2", CAPTURES="3", OCTETS="5000", HOTES=""),
                  "_ETAT": st._script(st._ETAT, ID1), "_NETTOYER": st._script(st._NETTOYER, ID1, JSON=final),
                  "_ARRETER": st._script(st._ARRETER, ID1, MOTIF="arret", JSON=final),
                  "_EFFACER": st._script(st._EFFACER, ID1), "_ABANDON": st._script(st._ABANDON, ID1),
                  "_AVD": st._script(st._AVD, ID1), "_VERBE": st._script(st._VERBE, ID1, VERBE="texte 'un deux'"),
                  "_RAPATRIER": st._script_rapatrier(ID1, lim), "capture": st._script_rapatrier(ID1, lim, "c1"),
                  "film": st._script_rapatrier(ID1, lim, film="c1")}
        for nom, script in rendus.items():
            self.assertNotRegex(script, r"@[A-Z]+@", nom)                 # aucun jeton oublié
            r = subprocess.run(["bash", "-n"], input=script.encode(), capture_output=True, timeout=30)
            self.assertEqual((r.returncode, r.stderr), (0, b""), nom)

        def bash_s(nom, attendu=0):
            code, sortie, erreur = self.ssh.executer("h", "bash -s", "c", stdin=rendus[nom])
            self.assertEqual((code, erreur), (attendu, ""), nom)
            return sortie

        code, erreur = st._envoyer(self.serveur, self.ssh, self.demande(), APK)
        self.assertEqual((code, erreur), (0, ""))
        self.assertIsNone(st._deposer_enveloppe(self.serveur, self.ssh))
        souche = self.ssh.home / "myiafactory" / "serveur_ovh" / "taches" / "lancer_emulation.sh"
        souche.write_text('printf "%s " "$@" > "$HOME/lance.txt"\n', encoding="utf-8", newline="\n")
        bash_s("_LANCER")
        self.assertEqual((self.ssh.home / "lance.txt").read_text(encoding="utf-8"), f"{ID1} pilote 60 600 6144 2 3 5000 ")
        marqueur = self.ssh.home / ".myiafactory" / "emulateur-image.version"
        bash_s("_IMAGE", attendu=1)                                         # marqueur absent : code non nul, rien dit
        marqueur.parent.mkdir()
        marqueur.write_text("ubuntu=x;jdk=17;fichiers=abc\n", encoding="utf-8", newline="\n")
        self.assertEqual(bash_s("_IMAGE"), "ubuntu=x;jdk=17;fichiers=abc\n")
        self.ecrire_etat(etat="en_cours", statut=None, fin=None)
        self.assertEqual(bash_s("_AVD").strip(), "attente")
        (self.tache / "sortie" / ".avd-pret").write_bytes(b"")
        self.assertEqual(bash_s("_AVD").strip(), "pret")
        self.assertIn("veilleur=absent", bash_s("_ETAT"))
        self.ssh.pont = ligne_pont(True, "texte", "ok").strip()
        bash_s("_VERBE")
        self.assertIn(f"docker exec tache-{ID1} /usr/local/bin/pont texte un deux", self.ssh.docker())
        (self.tache / "sortie" / "pont.log").write_bytes(b"texte 3ms\n")
        self.captures(2)
        (self.tache / "sortie" / "videos" / "c1-img").mkdir(parents=True)
        (self.tache / "sortie" / "videos" / "c1.mp4").write_bytes(MP4)
        (self.tache / "sortie" / "videos" / "c1-img" / "c1-001.png").write_bytes(PNG)
        for nom, attendus in (("_RAPATRIER", {"./pont.log", "captures/c0.png", "captures/c1.png", "videos/c1.mp4",
                                              "videos/c1-img/c1-001.png"}),
                              ("capture", {"captures/c1.png"}),
                              ("film", {"videos/c1.mp4", "videos/c1-img/c1-001.png"})):
            code, donnees, erreur = self.ssh.executer_octets("h", "bash -s", "c", entree=rendus[nom].encode())
            self.assertEqual((code, erreur), (0, ""), nom)
            with tarfile.open(fileobj=io.BytesIO(donnees), ignore_zeros=True) as tar:
                self.assertEqual({m.name for m in tar}, attendus, nom)
        (self.tache / "veilleur.pid").write_text("999999\n", encoding="utf-8")
        bash_s("_NETTOYER")
        self.assertEqual(json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))["etat"], "arretee")
        bash_s("_ARRETER")                                                  # état final : rien touché
        self.assertTrue((self.tache / "entree" / "app.apk").exists())
        # _ARRETER dans chaque état (le garde aurait ainsi vu une ligne abîmée de n'importe quelle branche)
        self.ecrire_etat(etat="en_attente", statut=None, debut=None, fin=None)
        bash_s("_ARRETER")
        self.assertEqual(json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))["etat"], "arretee")
        self.assertFalse((self.tache / "entree" / "app.apk").exists())
        (self.tache / "entree" / "app.apk").write_bytes(APK)
        (self.tache / "etat.json").unlink()
        bash_s("_ARRETER")
        self.assertEqual(json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))["etat"], "arretee")
        self.assertFalse((self.tache / "entree" / "app.apk").exists())
        (self.tache / "entree" / "app.apk").write_bytes(APK)
        self.ecrire_etat(etat="en_cours", statut=None, fin=None)
        (self.tache / "arret").unlink(missing_ok=True)
        v = self.veilleur_factice()
        bash_s("_ARRETER")
        self.assertEqual(v.wait(30), 0)
        self.assertEqual(json.loads((self.tache / "etat.json").read_text(encoding="utf-8"))["etat"], "arretee")
        self.assertTrue((self.tache / "entree" / "app.apk").exists())
        bash_s("_ABANDON")
        self.assertFalse((self.tache / "entree" / "app.apk").exists())
        bash_s("_EFFACER", attendu=4)                                       # état présent : jamais effacé
        self.assertTrue(self.tache.exists())


if __name__ == "__main__":
    unittest.main()
