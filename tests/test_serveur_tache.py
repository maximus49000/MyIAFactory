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


if __name__ == "__main__":
    unittest.main()
