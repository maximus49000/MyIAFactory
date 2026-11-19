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


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        self.index = st.Index(self.dossier)

    def test_index_ecriture_atomique_et_lecture(self):
        self.assertEqual(self.index.lire(), {})
        self.index.enregistrer("a", {"etat": "en_attente"})
        self.index.enregistrer("b", {"etat": "en_cours"})
        self.index.enregistrer("a", {"etat": "terminee"})
        self.assertEqual(self.index.lire(), {"a": {"etat": "terminee"}, "b": {"etat": "en_cours"}})
        self.index.retirer("a")
        self.index.retirer("absent")
        self.assertEqual(list(self.index.lire()), ["b"])
        self.assertEqual([p.name for p in self.dossier.iterdir()], ["taches.json"])

    def test_index_abime_lu_comme_vide(self):
        for contenu in ("{pas du json", "[1, 2]", ""):
            (self.dossier / "taches.json").write_text(contenu, encoding="utf-8")
            self.assertEqual(self.index.lire(), {})
        self.index.enregistrer("a", {"etat": "en_attente"})
        self.assertEqual(self.index.lire(), {"a": {"etat": "en_attente"}})

    def test_deux_ecritures_simultanees_sans_perte(self):
        erreurs = []

        def ecrire(prefixe):
            try:
                for i in range(20):
                    self.index.enregistrer(f"{prefixe}{i}", {"etat": "en_attente"})
            except Exception as e:  # noqa: BLE001
                erreurs.append(e)

        fils = [threading.Thread(target=ecrire, args=(p,)) for p in "xy"]
        [f.start() for f in fils]
        [f.join() for f in fils]
        self.assertEqual(erreurs, [])
        self.assertEqual(len(self.index.lire()), 40)

    def test_deux_processus_sans_perte(self):
        code = ("import sys\nsys.path.insert(0, sys.argv[1])\nimport serveur_tache as st\n"
                "i = st.Index(sys.argv[2], attente=60)\n"
                "for n in range(20):\n    i.enregistrer(f'p{n}', {'etat': 'en_cours'})\n")
        sous = subprocess.Popen(["py", "-3.12", "-I", "-c", code, str(RACINE / "outils"), str(self.dossier)])
        self.addCleanup(sous.kill)
        long = st.Index(self.dossier, attente=60)
        for n in range(20):
            long.enregistrer(f"m{n}", {"etat": "en_attente"})
        self.assertEqual(sous.wait(timeout=120), 0)
        self.assertEqual(len(long.lire()), 40)
        json.loads((self.dossier / "taches.json").read_text(encoding="utf-8"))
        self.assertFalse((self.dossier / "taches.lock").exists())

    def _verrou(self, contenu, age=0):
        chemin = self.dossier / "taches.lock"
        chemin.write_text(contenu, encoding="utf-8")
        if age:
            vieux = time.time() - age
            os.utime(chemin, (vieux, vieux))
        return chemin

    def test_verrou_perime_est_repris(self):
        cas = {"pid mort": ('{"pid": 4242}', 0), "pid propre": ('{"pid": %d}' % os.getpid(), 0),
               "vide ancien": ("", 10), "illisible ancien": ("{x", 10), "pid bool": ('{"pid": true}', 10),
               "pid 1": ('{"pid": 1}', 10)}
        for nom, (contenu, age) in cas.items():
            with self.subTest(nom):
                self._verrou(contenu, age)
                index = st.Index(self.dossier, attente=2, vivant=lambda pid: False)
                index.enregistrer("a", {"etat": "en_attente"})
                self.assertIn("a", index.lire())
                self.assertFalse((self.dossier / "taches.lock").exists())

    def test_verrou_vivant_ou_frais_fait_attendre(self):
        for nom, contenu in (("vide frais", ""), ("pid vivant", '{"pid": 4242}')):
            with self.subTest(nom):
                chemin = self._verrou(contenu)
                index = st.Index(self.dossier, attente=0.3, vivant=lambda pid: True)
                debut = time.monotonic()
                with self.assertRaises(TimeoutError):
                    index.enregistrer("a", {"etat": "en_attente"})
                self.assertGreaterEqual(time.monotonic() - debut, 0.25)
                self.assertTrue(chemin.exists())          # le verrou d'un autre n'est jamais supprimé
                chemin.unlink()

    def test_verrou_perime_impossible_a_retirer_ne_boucle_pas(self):
        self._verrou('{"pid": 4242}')
        index = st.Index(self.dossier, attente=0.3, vivant=lambda pid: False)
        debut = time.monotonic()
        with mock.patch.object(st.os, "rename", side_effect=PermissionError("verrouillé")):
            with self.assertRaises(TimeoutError):
                index.enregistrer("a", {"etat": "en_attente"})
        self.assertLess(time.monotonic() - debut, 5)

    def test_verrou_libere_apres_exception(self):
        index = st.Index(self.dossier, attente=1)

        def boum(tout):
            raise RuntimeError("boum")
        with self.assertRaises(RuntimeError):
            index._modifier(boum)
        self.assertFalse((self.dossier / "taches.lock").exists())
        index.enregistrer("a", {"etat": "en_attente"})

    def test_verrou_dun_autre_jamais_supprime_a_la_sortie(self):
        index = st.Index(self.dossier, attente=1)
        autre = self.dossier / "taches.lock"

        def vole(tout):
            autre.write_text('{"pid": 999999}', encoding="utf-8")
        index._modifier(vole)
        self.assertTrue(autre.exists())

    def test_erreur_de_lecture_transitoire_n_ecrase_rien(self):
        self.index.enregistrer("a", {"etat": "en_attente"})
        vrai = Path.read_text

        def refuse(chemin, *a, **k):
            if chemin.name == "taches.json":
                raise PermissionError("antivirus")
            return vrai(chemin, *a, **k)
        with mock.patch.object(Path, "read_text", refuse):
            self.assertEqual(self.index.lire(), {})                    # affichage : vide
            with self.assertRaises(st.ErreurIndex):
                self.index.enregistrer("b", {"etat": "en_attente"})
        self.assertEqual(list(self.index.lire()), ["a"])               # rien d'écrasé
        (self.dossier / "taches.json").unlink()
        self.index.enregistrer("b", {"etat": "en_attente"})            # fichier absent : repart de vide
        self.assertEqual(list(self.index.lire()), ["b"])

    def test_entrees_non_dict_ignorees(self):
        (self.dossier / "taches.json").write_text('{"a": 5, "b": {"etat": "en_cours"}}', encoding="utf-8")
        self.assertEqual(self.index.lire(), {"b": {"etat": "en_cours"}})

    def test_etat_invalide_refuse(self):
        for fiche in ({"etat": "nimporte"}, {}, {"etat": None}, "x"):
            with self.assertRaises(ValueError):
                self.index.enregistrer("a", fiche)
        self.assertEqual(self.index.lire(), {})


if __name__ == "__main__":
    unittest.main()
