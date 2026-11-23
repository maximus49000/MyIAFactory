"""Le journal des campagnes de tests (`bureau/tests_mesures.py`) et le verrou de fichier partagé.

Tests économes : dossiers temporaires créés une fois par classe, `bureau.json` et sceau injectés, `maintenant` fixe,
aucun `sleep`, aucun sous-processus."""
import ast
import contextlib
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import reglages, tests_mesures, tests_sceau, verrou_fichier

RACINE = Path(__file__).resolve().parent.parent
T = "2026-11-23T10:12:03+01:00"
CLES = {"t", "lieu", "source", "tache", "commande", "portee", "duree_s", "attente_s", "code", "nb_tests",
        "sortie_octets"}


def maintenant():
    return T


@contextlib.contextmanager
def _garde_boucle(toujours_existe=False, limite=200):
    """Remplace `os.open` pendant le bloc : au-delà de `limite` appels, `RuntimeError` (une boucle sans fin devient un
    échec franc au lieu de bloquer la campagne) ; `toujours_existe` : chaque ouverture dit « existe déjà »."""
    from unittest import mock
    vrai, appels = os.open, [0]

    def ouvrir(*a, **k):
        appels[0] += 1
        if appels[0] > limite:
            raise RuntimeError("boucle sans fin dans le verrou")
        if toujours_existe:
            raise FileExistsError(a[0])
        return vrai(*a, **k)
    with mock.patch.object(verrou_fichier.os, "open", ouvrir):
        yield


def _ligne_valide(**autres):
    base = {"t": T, "lieu": "poste", "source": "mesure", "tache": None, "commande": "npx vitest run",
            "portee": "partielle", "duree_s": 1.0, "attente_s": 0.0, "code": 0, "nb_tests": None, "sortie_octets": None}
    base.update(autres)
    return base


class TestModules(unittest.TestCase):
    def test_modules_compatibles_python_3_9(self):
        for nom in ("verrou_fichier", "tests_mesures", "tests_sceau"):
            source = (RACINE / "bureau" / (nom + ".py")).read_text(encoding="utf-8")
            ast.parse(source, filename=nom, feature_version=(3, 9))

    def test_verrou_reglages_inchange(self):
        self.assertIs(reglages._verrou_fichier, verrou_fichier.verrou_fichier)
        self.assertEqual((verrou_fichier.VERROU_ATTENTE_S, verrou_fichier.VERROU_PERIME_S), (10, 60))

    def test_verrou_tenu_par_un_dossier_perime_rend_la_main(self):
        """Une marque `.verrou` impossible à reprendre (un dossier vieux d'une heure) : une `OSError` rend la main
        (`TimeoutError` au bout de l'attente sous POSIX, refus immédiat sous Windows), jamais une boucle sans fin."""
        from unittest import mock
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        marque = tmp / "f.json.verrou"
        marque.mkdir()
        vieux = marque.stat().st_mtime - 3600
        os.utime(marque, (vieux, vieux))
        with mock.patch.object(verrou_fichier, "VERROU_ATTENTE_S", 0):
            with self.assertRaises(OSError):
                with verrou_fichier.verrou_fichier(tmp / "f.json"):
                    pass
            # même chose quand l'ouverture exclusive dit « existe déjà » (le chemin POSIX) : la reprise échoue, la main
            # est rendue au bout de l'attente
            with _garde_boucle(toujours_existe=True):
                with self.assertRaises(TimeoutError):
                    with verrou_fichier.verrou_fichier(tmp / "f.json"):
                        pass
        self.assertTrue(marque.is_dir())


class TestVerrou(unittest.TestCase):
    """Le verrou ne tourne jamais sans fin : l'échéance est vérifiée à chaque tour. Attente ramenée à 0 (pas de sommeil
    réel) ; une garde transforme une boucle sans fin en échec franc."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fichier(self):
        type(self).n += 1
        return self.tmp / ("f%d.json" % self.n)

    def test_marque_qui_disparait_sans_cesse_ne_boucle_pas(self):
        from unittest import mock
        with mock.patch.object(verrou_fichier, "VERROU_ATTENTE_S", 0), _garde_boucle(toujours_existe=True):
            with self.assertRaises(TimeoutError):           # « existe » à l'ouverture, absente au constat
                with verrou_fichier.verrou_fichier(self.fichier()):
                    pass

    def test_lien_casse_a_la_place_de_la_marque(self):
        from unittest import mock
        chemin = self.fichier()
        marque = Path(str(chemin) + ".verrou")
        try:
            os.symlink(str(self.tmp / "nulle-part"), str(marque))
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles ici")
        with mock.patch.object(verrou_fichier, "VERROU_ATTENTE_S", 0), _garde_boucle():
            with self.assertRaises(TimeoutError):           # lien récent : attendu, puis la main est rendue
                with verrou_fichier.verrou_fichier(chemin):
                    pass
            self.assertFalse(os.path.exists(str(self.tmp / "nulle-part")))   # la cible du lien n'est jamais créée
            with mock.patch.object(verrou_fichier, "VERROU_PERIME_S", -1):   # (Windows ne date pas un lien lui-même)
                with verrou_fichier.verrou_fichier(chemin):   # lien périmé : repris (constat par `lstat`)
                    pass
        self.assertFalse(os.path.lexists(str(marque)))

    def test_marque_recente_d_un_autre_programme(self):
        from unittest import mock
        chemin = self.fichier()
        marque = Path(str(chemin) + ".verrou")
        marque.write_text("", encoding="utf-8")
        with mock.patch.object(verrou_fichier, "VERROU_ATTENTE_S", 0):
            with self.assertRaises(TimeoutError):
                with verrou_fichier.verrou_fichier(chemin):
                    pass
        with self.assertRaises(TimeoutError):                 # attente courte du lanceur, sans toucher au réglage
            with verrou_fichier.verrou_fichier(chemin, attente_s=0):
                pass
        self.assertTrue(marque.exists())                      # la marque d'autrui n'est pas enlevée

    def test_reentrance_leve_timeout_sans_bloquer(self):
        from unittest import mock
        issue = []

        def fil():
            with verrou_fichier.verrou_fichier(self.fichier()):
                try:
                    with verrou_fichier.verrou_fichier(self.fichier()):
                        issue.append("pris")
                except TimeoutError:
                    issue.append("timeout")
        with mock.patch.object(verrou_fichier, "VERROU_ATTENTE_S", 0.05):
            f = threading.Thread(target=fil, daemon=True)
            f.start()
            f.join(2)
            if f.is_alive():                                  # l'ancien verrou bloquait : on le libère pour finir
                verrou_fichier._VERROU_ECRITURE.release()
                f.join(2)
        self.assertEqual(issue, ["timeout"])

    def test_remplacer_reessaie_un_fichier_occupe(self):
        from unittest import mock
        source, cible = self.fichier(), self.fichier()
        source.write_text("1", encoding="utf-8")
        vrai, pauses, echecs = os.replace, [], [PermissionError("occupé"), PermissionError("occupé")]

        def replace(a, b):
            if echecs:
                raise echecs.pop()
            vrai(a, b)
        with mock.patch.object(verrou_fichier.os, "replace", replace), \
                mock.patch.object(verrou_fichier, "_dormir", pauses.append):
            verrou_fichier.remplacer(source, cible)
            self.assertEqual(cible.read_text(encoding="utf-8"), "1")
            self.assertEqual(pauses, [0.02, 0.02])
            source.write_text("2", encoding="utf-8")
            echecs.extend([PermissionError("occupé")] * 5)
            with self.assertRaises(PermissionError):
                verrou_fichier.remplacer(source, cible)
        self.assertEqual(cible.read_text(encoding="utf-8"), "1")

    def test_valeurs_du_spec(self):
        m = tests_mesures
        self.assertEqual(m.BUREAU, Path("~/MyIAFactory/bureau.json").expanduser())
        self.assertEqual((m.NOM_JOURNAL, m.MAX_LIGNES, m.MAX_OCTETS_LIGNE, m.MAX_COMMANDE, m.SEUIL_BAISSE),
                         ("tests-mesures.jsonl", 2000, 2048, 200, 0.02))
        self.assertEqual((m.LIEUX, m.SOURCES, m.PORTEES), (("poste", "github", "cloud", "serveur"),
                                                           ("mesure", "declare"), ("complete", "partielle")))
        self.assertEqual(m.journal_de(Path("x")), Path("x") / ".factory" / "tests-mesures.jsonl")

    def test_nb_tests_des_sorties_types(self):
        n = tests_mesures.nb_tests_de
        self.assertEqual(n("Ran 318 tests in 4.2s\n\nOK"), 318)
        self.assertEqual(n("....\n==== 3 failed, 315 passed, 2 skipped in 9.1s ===="), 320)
        self.assertEqual(n("= 1 failed, 2 passed, 1 warning, 3 errors in 0.12s ="), 6)
        self.assertEqual(n(" Tests  306 passed (306)"), 306)
        self.assertEqual(n(" \x1b[2m Tests \x1b[22m \x1b[1m\x1b[31m3 failed\x1b[39m | 303 passed\x1b[22m (306)\n"
                           "   Duration  4.1s"), 306)
        self.assertEqual(n("Tests:       1 failed, 11 passed, 12 total\nTime: 3 s"), 12)
        self.assertEqual(n("Ran 1 test in 0.001s\n\nOK"), 1)
        for rien in ("bonjour", "", "Ran beaucoup de tests", "no tests ran in 0.01s"):
            self.assertIsNone(n(rien), msg=rien)
        self.assertEqual(n("Ran 999 tests in 1s\n" + "x\n" * 5000 + "Ran 7 tests in 1s\nOK"), 7)   # la dernière

    def test_portee_compare_la_commande_normalisee(self):
        meme = tests_mesures.meme_commande
        self.assertTrue(meme("npx vitest run", "npx vitest run"))
        self.assertTrue(meme(" npx  vitest  run ", "npx vitest run"))
        self.assertTrue(meme("npx\tvitest run\n", " npx vitest  run"))
        self.assertFalse(meme("npx vitest run --reporter=dot", "npx vitest run"))
        self.assertFalse(meme("npx vitest run src/a.test.ts", "npx vitest run"))
        self.assertFalse(meme("npx vitest run", None))              # sans commande enregistrée : jamais complète
        self.assertFalse(meme("", ""))
        self.assertFalse(meme("  ", " "))

    def test_ligne_forme_du_spec(self):
        l = tests_mesures.ligne(lieu="poste", source="mesure", tache="t-12", commande="c" * 300, portee="complete",
                                duree_s=412.64, attente_s=35.04, code=0, nb_tests=318, sortie_octets=48211, t=T)
        self.assertEqual(set(l), CLES)
        self.assertEqual(l, {"t": T, "lieu": "poste", "source": "mesure", "tache": "t-12", "commande": "c" * 200,
                             "portee": "complete", "duree_s": 412.6, "attente_s": 35.0, "code": 0, "nb_tests": 318,
                             "sortie_octets": 48211})
        l = tests_mesures.ligne(lieu="github", source="mesure", tache=None, commande="x", portee="partielle",
                                duree_s=1, attente_s=0, code=1, n=3, run=123456, t=T)
        self.assertEqual(set(l), CLES | {"n", "run"})
        self.assertEqual((l["n"], l["run"], l["nb_tests"], l["sortie_octets"]), (3, 123456, None, None))
        mauvais = [dict(lieu="ailleurs"), dict(source="devine"), dict(portee="touches"), dict(duree_s=-1),
                   dict(duree_s=float("nan")), dict(attente_s=float("inf")), dict(duree_s="12"), dict(commande=None)]
        for m in mauvais:
            args = dict(lieu="poste", source="mesure", tache=None, commande="x", portee="partielle", duree_s=1,
                        attente_s=0, code=0, t=T)
            args.update(m)
            with self.assertRaises(ValueError, msg=repr(m)):
                tests_mesures.ligne(**args)
        bizarre = tests_mesures.ligne(lieu="poste", source="mesure", tache="\ud800" * 300, commande="\udcff\U0001F600" * 150,
                                      portee="partielle", duree_s=1, attente_s=0, code=0, t=T)
        brut = json.dumps(bizarre, ensure_ascii=False).encode("utf-8")      # encodable et sous 2 Ko, quoi qu'il arrive
        self.assertLessEqual(len(brut), tests_mesures.MAX_OCTETS_LIGNE)


class TestJournal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def journal(self):
        type(self).n += 1
        return self.tmp / ("j%d" % self.n) / ".factory" / "tests-mesures.jsonl"

    def test_rotation_garde_les_2000_dernieres(self):
        chemin = self.journal()
        chemin.parent.mkdir(parents=True)
        chemin.write_text("".join(json.dumps(_ligne_valide(i=i)) + "\n" for i in range(2000)), encoding="utf-8")
        tests_mesures.ajouter(chemin, _ligne_valide(i=2000))
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        self.assertEqual(tests_mesures.LIGNES_APRES_ROTATION, 1800)        # de la marge : pas une réécriture par ajout
        self.assertEqual(len(lignes), 1800)
        self.assertEqual([json.loads(lignes[0])["i"], json.loads(lignes[-1])["i"]], [201, 2000])
        self.assertEqual(sorted(p.name for p in chemin.parent.iterdir()), [chemin.name])   # pas de temporaire laissé
        tests_mesures.ajouter(chemin, _ligne_valide(i=2001))
        self.assertEqual([l["i"] for l in tests_mesures.lire(chemin)][::1800], [201, 2001])  # 1 801 : simple ajout

    def test_ajouter_refuse_un_lien_dur(self):
        chemin = self.journal()
        chemin.parent.mkdir(parents=True)
        autre = chemin.parent.parent / "precieux.txt"
        autre.write_bytes(b"ne pas toucher")
        try:
            os.link(str(autre), str(chemin))
        except (OSError, NotImplementedError):
            self.skipTest("liens durs indisponibles ici")
        with self.assertRaises(OSError):
            tests_mesures.ajouter(chemin, _ligne_valide(i=1))
        self.assertEqual(autre.read_bytes(), b"ne pas toucher")

    def test_ajouter_refuse_un_dossier_factory_en_lien(self):
        chemin = self.journal()
        ailleurs = chemin.parent.parent / "ailleurs"
        ailleurs.mkdir(parents=True)
        try:
            os.symlink(str(ailleurs), str(chemin.parent), target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(ailleurs), str(chemin.parent))
            except (ImportError, AttributeError, OSError):
                self.skipTest("ni lien symbolique ni jonction ici")
        with self.assertRaises(OSError):
            tests_mesures.ajouter(chemin, _ligne_valide(i=1))
        self.assertEqual(list(ailleurs.iterdir()), [])

    def test_max_n_des_mesures(self):
        chemin = self.journal()
        self.assertEqual(tests_mesures.max_n(chemin), 0)
        for l in (_ligne_valide(n=3), _ligne_valide(n=9, source="declare"), _ligne_valide(n=True),
                  _ligne_valide(n="12"), _ligne_valide(n=5), _ligne_valide(), _ligne_valide(n=4)):
            tests_mesures.ajouter(chemin, l)
        self.assertEqual(tests_mesures.max_n(chemin), 5)

    def test_ajouter_cree_le_dossier_et_refuse_une_ligne_trop_longue(self):
        chemin = self.journal()
        tests_mesures.ajouter(chemin, _ligne_valide(i=1))
        with self.assertRaises(ValueError):
            tests_mesures.ajouter(chemin, _ligne_valide(commande="x" * 3000))
        self.assertEqual([l["i"] for l in tests_mesures.lire(chemin)], [1])

    def test_lire_tolere_un_journal_abime(self):
        chemin = self.journal()
        chemin.parent.mkdir(parents=True)
        lignes = [
            "﻿" + json.dumps(_ligne_valide(i=1)),
            '{"lieu": "poste", "source": "mesu',                       # tronquée
            json.dumps(_ligne_valide(i=2, commande="x" * 50000)),      # 50 Ko
            "[1, 2]",
            json.dumps(_ligne_valide(i=3, duree_s=-1)),
            json.dumps(_ligne_valide(i=4, lieu="ailleurs")),
            json.dumps(_ligne_valide(i=5, duree_s="12")),
            json.dumps(_ligne_valide(i=6, duree_s=True)),
            '{"lieu": "poste", "source": "mesure", "portee": "partielle", "duree_s": NaN}',
            '{"lieu": "poste", "source": "mesure", "portee": "partielle", "duree_s": Infinity}',
            "[" * 50000,
            "",
            json.dumps(_ligne_valide(i=7)),
        ]
        chemin.write_bytes(("\n".join(lignes)).encode("utf-8") + b"\n\xff\xfe\n")
        self.assertEqual([l["i"] for l in tests_mesures.lire(chemin)], [1, 7])
        dossier = self.journal()
        dossier.mkdir(parents=True)                                    # un dossier à la place du fichier
        self.assertEqual(tests_mesures.lire(dossier), [])
        self.assertEqual(tests_mesures.lire(self.journal()), [])       # absent


class TestProjetEnregistre(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        t = cls.tmp
        for rel in ("p/reglages.json", "p/sous/reglages.json", "q/.factory/reglages.json", "autre/q/reglages.json",
                    "Été Spécial/reglages.json"):
            (t / rel).parent.mkdir(parents=True, exist_ok=True)
            (t / rel).write_text("{}", encoding="utf-8")
        for rel in ("p/app", "p/.claude/worktrees/x", "hors"):
            (t / rel).mkdir(parents=True)
        cls.bureau = t / "bureau.json"
        cls.bureau.write_text(json.dumps({"projets": [
            {"chemin": "p/reglages.json", "id": "p-id"}, "q/.factory/reglages.json", "autre/q/reglages.json",
            {"chemin": "p/sous/reglages.json"}, "Été Spécial/reglages.json"]}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_projet_enregistre_resout_sous_dossier_copie_et_casse(self):
        p = self.tmp / "p"
        attendu = ("p-id", p)
        for dossier in (p, p / "app", p / ".claude" / "worktrees" / "x", str(p / "app") + os.sep):
            self.assertEqual(tests_mesures.projet_enregistre(dossier, bureau=self.bureau), attendu, msg=str(dossier))
        if os.name == "nt":
            self.assertEqual(tests_mesures.projet_enregistre(str(p / "app").upper(), bureau=self.bureau), attendu)
            self.assertEqual(tests_mesures.projet_enregistre("\\\\?\\" + str(p / "app"), bureau=self.bureau), attendu)
        self.assertIsNone(tests_mesures.projet_enregistre(self.tmp / "hors", bureau=self.bureau))
        self.assertIsNone(tests_mesures.projet_enregistre(self.tmp / "pp", bureau=self.bureau))   # préfixe, pas parent
        self.assertIsNone(tests_mesures.projet_enregistre(self.tmp, bureau=self.bureau))
        self.assertEqual(tests_mesures.projet_enregistre(p / "sous" / "z", bureau=self.bureau),
                         ("sous", p / "sous"))                                                 # le plus long
        self.assertEqual(tests_mesures.projet_enregistre(self.tmp / "q" / ".factory", bureau=self.bureau)[1],
                         self.tmp / "q")
        # concordance avec le bureau : mêmes id que `reglages.lire_bureau`, doublons suffixés compris
        for entree in reglages.lire_bureau(self.bureau)["projets"]:
            racine = entree["chemin"].parent
            if racine.name == ".factory":
                racine = racine.parent
            self.assertEqual(tests_mesures.projet_enregistre(racine, bureau=self.bureau), (entree["id"], racine))
        ids = {e["id"] for e in reglages.lire_bureau(self.bureau)["projets"]}
        self.assertEqual(ids, {"p-id", "q", "q-2", "sous", "ete-special"})

    def test_projet_enregistre_ne_leve_jamais(self):
        abime = self.tmp / "abime.json"
        for contenu in ("{pas du json", "[]", '{"projets": 3}', '{"projets": [null, 4, {"chemin": 5}, ""]}',
                        '{"projets": [{"chemin": "p/reglages.json", "id": "MAUVAIS ID"}]}', "[" * 100000):
            abime.write_text(contenu, encoding="utf-8")
            self.assertIsNone(tests_mesures.projet_enregistre(self.tmp / "p", bureau=abime), msg=contenu[:40])
        self.assertIsNone(tests_mesures.projet_enregistre(self.tmp / "p", bureau=self.tmp / "absent.json"))
        self.assertIsNone(tests_mesures.projet_enregistre("\x00", bureau=self.bureau))
        self.assertIsNone(tests_mesures.projet_enregistre(None, bureau=self.bureau))


class TestNoter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def projet(self, sceau=None):
        """Un projet enregistré dans son propre bureau, avec son propre sceau : `(dossier, bureau, sceau, id)`."""
        type(self).n += 1
        nom = "projet-%d" % self.n
        dossier = self.tmp / nom
        dossier.mkdir()
        (dossier / "reglages.json").write_text("{}", encoding="utf-8")
        bureau = self.tmp / (nom + "-bureau.json")
        bureau.write_text(json.dumps({"projets": ["%s/reglages.json" % nom]}), encoding="utf-8")
        chemin_sceau = self.tmp / (nom + "-sceau") / "tests-sceau.json"
        if sceau is not None:
            chemin_sceau.parent.mkdir()
            chemin_sceau.write_bytes(sceau)
        return dossier, bureau, chemin_sceau, nom

    def noter(self, projet, **k):
        dossier, bureau, sceau, _ = projet
        args = dict(commande="python -m unittest", duree_s=1.0, attente_s=0.0, code=0, bureau=bureau, sceau=sceau,
                    maintenant=maintenant)
        args.update(k)
        return tests_mesures.noter_campagne(dossier / "app", **args)

    def test_noter_campagne_numerote_et_compte(self):
        pr = self.projet()
        dossier, _, sceau, id_ = pr
        l1 = self.noter(pr, duree_s=12.34, attente_s=3.0, fin="Ran 5 tests in 1s\n\nOK", octets=900, tache="t-1")
        l2 = self.noter(pr, duree_s=4.5, code=1, run=777, lieu="github")
        self.assertEqual((l1["n"], l2["n"]), (1, 2))
        self.assertEqual(set(l1), CLES | {"n"})
        self.assertEqual((l1["duree_s"], l1["attente_s"], l1["nb_tests"], l1["sortie_octets"], l1["tache"], l1["t"],
                          l1["source"], l1["lieu"], l1["portee"]),
                         (12.3, 3.0, 5, 900, "t-1", T, "mesure", "poste", "partielle"))
        self.assertEqual((l2["run"], l2["lieu"]), (777, "github"))
        entree = tests_sceau.lire(id_, sceau=sceau)
        self.assertEqual((entree["campagnes"], entree["cumul_s"], entree["maj"]), (2, 16.8, T))
        self.assertIsNone(self.noter(pr, run=777, lieu="github"))                  # même exécution GitHub : une fois
        self.assertEqual(tests_sceau.lire(id_, sceau=sceau)["campagnes"], 2)
        self.assertEqual(tests_mesures.lire(tests_mesures.journal_de(dossier)), [l1, l2])
        # dossier non enregistré : rien n'est écrit, ni journal ni sceau
        hors = self.tmp / ("hors-%d" % self.n)
        hors.mkdir()
        neuf = self.tmp / "sceau-neuf" / "tests-sceau.json"
        self.assertIsNone(tests_mesures.noter_campagne(hors, commande="x", duree_s=1, attente_s=0, code=0,
                                                       bureau=pr[1], sceau=neuf, maintenant=maintenant))
        self.assertFalse(neuf.parent.exists())
        self.assertFalse((hors / ".factory").exists())

    def test_portee_suit_la_commande_enregistree(self):
        pr = self.projet()
        self.assertEqual(self.noter(pr, commande="npx vitest run")["portee"], "partielle")   # rien d'enregistré
        tests_sceau.modifier(pr[3], lambda e: e.update(commande_complete="npx vitest run"), sceau=pr[2],
                             maintenant=maintenant)
        self.assertEqual(self.noter(pr, commande=" npx  vitest  run ")["portee"], "complete")
        self.assertEqual(self.noter(pr, commande="npx vitest run --reporter=dot")["portee"], "partielle")
        self.assertEqual(self.noter(pr, commande="npx vitest run src/a.test.ts")["portee"], "partielle")

    def test_reference_nb_tests_ne_suit_pas_une_baisse(self):
        def suite(*nombres, code=0):
            pr = self.projet()
            tests_sceau.modifier(pr[3], lambda e: e.update(commande_complete="py -m unittest"), sceau=pr[2],
                                 maintenant=maintenant)
            for nb in nombres:
                self.noter(pr, commande="py -m unittest", fin="Ran %d tests in 2s\n\nOK" % nb, code=code)
            return tests_sceau.lire(pr[3], sceau=pr[2])["derniers_nb_tests"]
        self.assertEqual(suite(318, 306), 318)            # baisse de 3,8 % : la référence reste (l'alerte tient)
        self.assertEqual(suite(318, 315), 315)            # 0,9 % : suivie
        self.assertEqual(suite(318, 330), 330)
        self.assertIsNone(suite(318, code=1))             # rouge : ne compte pas
        pr = self.projet()                                # partielle : ne compte pas
        self.noter(pr, fin="Ran 318 tests in 2s\n\nOK")
        self.assertIsNone(tests_sceau.lire(pr[3], sceau=pr[2])["derniers_nb_tests"])

    def test_noter_campagne_tait_les_erreurs(self):
        contenu = b"{pas du json"
        pr = self.projet(sceau=contenu)
        self.assertIsNone(self.noter(pr))
        self.assertEqual(pr[2].read_bytes(), contenu)
        self.assertFalse(tests_mesures.journal_de(pr[0]).exists())
        pr = self.projet()
        tests_mesures.journal_de(pr[0]).mkdir(parents=True)              # journal impossible à écrire
        self.assertIsNone(self.noter(pr))
        self.assertEqual(tests_sceau.lire(pr[3], sceau=pr[2])["campagnes"], 0)   # rien compté sans ligne écrite
        self.assertIsNone(self.noter(self.projet(), lieu="ailleurs"))
        self.assertIsNone(self.noter(self.projet(), duree_s=float("nan")))

    def test_noter_declarations_sans_toucher_au_sceau(self):
        pr = self.projet(sceau=b'{"autre": {"campagnes": 3}}')
        dossier, bureau, sceau, _ = pr
        declarations = [{"commande": "npx vitest run src/a", "portee": "touches", "duree_s": 12.34, "code": 0},
                        {"commande": "npx vitest run", "portee": "complete", "duree_s": 250, "code": 1},
                        {"commande": "npx vitest run", "portee": "complete", "code": 0},
                        {"commande": "x", "portee": "toutes", "duree_s": 1, "code": 0},
                        "pas un objet"]
        n = tests_mesures.noter_declarations(dossier, "cloud", "t-9", declarations, bureau=bureau, sceau=sceau,
                                             maintenant=maintenant)
        self.assertEqual(n, 2)
        lignes = tests_mesures.lire(tests_mesures.journal_de(dossier))
        self.assertEqual([(l["source"], l["portee"], l["duree_s"], l["lieu"], l["tache"], l["code"]) for l in lignes],
                         [("declare", "partielle", 12.3, "cloud", "t-9", 0), ("declare", "complete", 250.0, "cloud",
                                                                            "t-9", 1)])
        self.assertEqual(sceau.read_bytes(), b'{"autre": {"campagnes": 3}}')
        self.assertEqual(sorted(p.name for p in sceau.parent.iterdir()), [sceau.name])     # verrou rendu
        for args in ((self.tmp, "cloud", None, declarations), (dossier, "ailleurs", None, declarations),
                     (dossier, "serveur", None, "pas une liste")):
            self.assertEqual(tests_mesures.noter_declarations(*args, bureau=bureau, sceau=sceau), 0)

    def test_noter_declarations_sous_le_verrou_du_journal(self):
        """Les déclarations s'écrivent sous le même verrou que les campagnes du poste (celui du sceau, attente courte) :
        une rotation simultanée ne peut pas perdre leur ligne. Verrou tenu ailleurs : rien n'est écrit, rien ne lève."""
        from unittest import mock
        dossier, bureau, sceau, _ = self.projet(sceau=b"{}")
        marque = Path(str(sceau) + ".verrou")
        marque.write_text("", encoding="utf-8")                      # une campagne du poste écrit en ce moment
        with mock.patch.object(tests_sceau, "ATTENTE_LANCEUR_S", 0):
            n = tests_mesures.noter_declarations(dossier, "serveur", None, [{"commande": "x", "portee": "complete",
                                                                             "duree_s": 1, "code": 0}],
                                                 bureau=bureau, sceau=sceau, maintenant=maintenant)
            self.assertEqual(n, 0)
            self.assertFalse(tests_mesures.journal_de(dossier).exists())
            self.assertIsNone(self.noter((dossier, bureau, sceau, None)))  # le lanceur n'attend pas 10 s non plus
        self.assertTrue(marque.exists())

    def test_run_deja_note_dans_les_50_dernieres_lignes_seulement(self):
        pr = self.projet()
        long_run = "r" * 60                                                # tronqué à 40 au journal : reconnu quand même
        self.assertIsNotNone(self.noter(pr, run=long_run, lieu="github"))
        self.assertIsNone(self.noter(pr, run=long_run, lieu="github"))
        journal = tests_mesures.journal_de(pr[0])
        with open(str(journal), "a", encoding="utf-8") as f:              # 50 campagnes plus récentes, d'un coup
            f.write("".join(json.dumps(_ligne_valide(run=i)) + "\n" for i in range(50)))
        self.assertIsNotNone(self.noter(pr, run=long_run, lieu="github"))  # sortie des 50 dernières : notée
        self.assertIsNone(self.noter(pr, run=49, lieu="github"))


if __name__ == "__main__":
    unittest.main()
