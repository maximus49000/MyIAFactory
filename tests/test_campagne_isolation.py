"""Le verrou et la file du poste (`outils/campagne.py`) après les trois blocages du 2026-11-23 :
- l'identité d'un processus noté est sa date de création, pas seulement son pid (une note fantôme dont le pid avait été
  repris par un `conhost.exe` retenait la file sans fin) ;
- un processus de test lancé par `tests_paralleles` (variable `MYIAFACTORY_ETAT_TESTS`) n'atteint jamais le vrai verrou
  ni la vraie file, même sans chemins explicites ;
- tout nouveau test qui appelle `campagne.executer`, `attendre_son_tour` ou `prendre` sans garde ni chemins
  temporaires est refusé tout de suite (lecture du code des tests, sans les lancer).
Processus simulés (`campagne.etat_processus` remplacé), sauf un test bon marché sur ce processus-ci."""
import ast
import inspect
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import campagne  # noqa: E402
from tests.test_campagne import garder_le_poste  # noqa: E402

GHOST = 23232
# Les vraies fonctions, avant que `garder_le_poste` ne pose ses gardes (leur signature est générique).
VRAIES = {n: getattr(campagne, n) for n in ("executer", "attendre_son_tour", "prendre", "liberer", "en_attente")}


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).astimezone().isoformat(timespec="seconds")


class Base(unittest.TestCase):
    def setUp(self):
        garder_le_poste(self)
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name).resolve()
        self.verrou = self.tmp / "tests-en-cours.json"
        self.attentes = self.tmp / "tests-en-attente"
        self.attentes.mkdir()
        self.processus = {}          # pid -> date de création ; absent : mort
        p = mock.patch.object(campagne, "etat_processus",
                              lambda pid: (pid in self.processus, self.processus.get(pid)))
        p.start()
        self.addCleanup(p.stop)

    def noter(self, pid, **champs):
        (self.attentes / f"{pid}.json").write_text(json.dumps({"pid": pid, "arrivee": 1.0, **champs}),
                                                   encoding="utf-8")


class TestIdentite(Base):
    def test_pid_repris_apres_la_note_n_est_plus_la_campagne(self):
        """L'incident : `23232.json` (ancienne note, sans `demarre`), son pid repris par un processus créé après."""
        self.processus[GHOST] = 2_000_000_000.0
        self.noter(GHOST, depuis=iso(1_900_000_000), tache="t1")
        self.assertEqual(campagne._file(self.attentes), [])
        self.assertEqual(campagne._devant(self.attentes, None), [])
        self.assertEqual(campagne.en_attente(self.attentes), {})

    def test_pid_repris_note_recente_avec_demarre(self):
        self.processus[GHOST] = 2_000_000_000.0
        self.noter(GHOST, demarre=1_999_000_000.0, depuis=iso(2_000_000_100))
        self.assertEqual(campagne._file(self.attentes), [])

    def test_meme_processus_meme_date_de_creation(self):
        self.processus[GHOST] = 2_000_000_000.4
        self.noter(GHOST, demarre=2_000_000_000.0, depuis=iso(2_000_000_005), tache="t1")
        self.assertEqual([e[1] for e in campagne._file(self.attentes)], [GHOST])
        self.assertEqual(list(campagne.en_attente(self.attentes)), ["t1"])

    def test_ancienne_note_sans_dates_garde_l_ancienne_regle(self):
        self.processus[GHOST] = 2_000_000_000.0
        self.noter(GHOST, depuis="10:00")             # illisible : seule l'existence du pid compte, comme avant
        self.noter(GHOST + 1)                         # mort
        self.assertEqual([e[1] for e in campagne._file(self.attentes)], [GHOST])
        self.processus[GHOST] = None                  # date de création illisible : idem
        self.noter(GHOST, demarre=5.0)
        self.assertEqual([e[1] for e in campagne._file(self.attentes)], [GHOST])

    def test_ancienne_note_processus_cree_avant_sa_date(self):
        self.processus[GHOST] = 1_900_000_000.0
        self.noter(GHOST, depuis=iso(2_000_000_000))
        self.assertEqual([e[1] for e in campagne._file(self.attentes)], [GHOST])

    def test_tolerance_de_deux_secondes(self):
        f = lambda reel: (lambda pid: (True, reel))      # noqa: E731
        self.assertTrue(campagne.vivant_et_meme(7, 1000.0, etat=f(1001.9)))
        self.assertTrue(campagne.vivant_et_meme(7, 1000.0, etat=f(998.1)))
        self.assertFalse(campagne.vivant_et_meme(7, 1000.0, etat=f(1002.5)))
        self.assertTrue(campagne.vivant_et_meme(7, None, 1000.0, etat=f(1001.9)))     # `depuis` arrondi à la seconde
        self.assertFalse(campagne.vivant_et_meme(7, None, 1000.0, etat=f(1002.5)))
        self.assertFalse(campagne.vivant_et_meme(7, 1000.0, etat=lambda pid: (False, None)))
        self.assertTrue(campagne.vivant_et_meme(7, True, etat=f(5.0)))               # booléen : pas une date

    def test_le_verrou_d_un_pid_repris_est_repris(self):
        self.processus[GHOST] = 2_000_000_000.0
        self.verrou.write_text(json.dumps({"pid": GHOST, "debut": iso(1_900_000_000)}), encoding="utf-8")
        self.assertIsNone(campagne.prendre(self.verrou, "r"))
        pris = json.loads(self.verrou.read_text(encoding="utf-8"))
        self.assertEqual(pris["pid"], os.getpid())
        self.assertIn("demarre", pris)
        campagne.liberer(self.verrou)

    def test_le_verrou_d_une_campagne_vivante_reste(self):
        self.processus[GHOST] = 2_000_000_000.0
        for note in ({"pid": GHOST, "demarre": 2_000_000_001.0, "debut": iso(2_000_000_002)},
                     {"pid": GHOST, "debut": iso(2_000_000_002)}, {"pid": GHOST, "debut": "10:00"}):
            self.verrou.write_text(json.dumps(note), encoding="utf-8")
            self.assertEqual(campagne.prendre(self.verrou, "r"), note)

    def test_un_verrou_vide_tout_juste_cree_n_est_pas_repris(self):
        self.verrou.write_text("", encoding="utf-8")       # une autre campagne vient de le créer, pas encore écrit
        self.assertEqual(campagne.prendre(self.verrou, "r"), {"pid": None})
        ancien = time.time() - 60
        os.utime(self.verrou, (ancien, ancien))            # vide depuis une minute : repris
        self.assertIsNone(campagne.prendre(self.verrou, "r"))
        campagne.liberer(self.verrou)

    def test_attendre_son_tour_passe_devant_une_note_fantome(self):
        self.processus[GHOST] = 2_000_000_000.0
        self.noter(GHOST, depuis=iso(1_900_000_000))
        dormi = []
        self.assertTrue(campagne.attendre_son_tour("r", verrou=self.verrou, lister=lambda: [], dormir=dormi.append,
                                                   dire=lambda *a, **k: None, attentes=self.attentes))
        self.assertEqual(dormi, [])
        campagne.liberer(self.verrou)

    def test_la_note_d_attente_porte_la_date_de_creation(self):
        with mock.patch.object(campagne, "mon_demarrage", lambda: 1234.5):
            campagne._noter_l_attente(self.attentes, "r", "m", "d", 1.0)
        x = json.loads((self.attentes / f"{os.getpid()}.json").read_text(encoding="utf-8"))
        self.assertEqual((x["demarre"], x["pid"], x["depuis"]), (1234.5, os.getpid(), "d"))
        campagne._oublier_l_attente(self.attentes)


class TestIdentiteReelle(unittest.TestCase):
    def test_ce_processus_et_un_pid_absent(self):
        """Le seul test sur de vrais processus : ce processus-ci, et un pid qui n'existe pas."""
        vivant, demarre = campagne.etat_processus(os.getpid())
        self.assertTrue(vivant)
        if demarre is not None:      # Windows (GetProcessTimes) et Linux (/proc) ; ailleurs : repli sur le pid
            self.assertLess(abs(time.time() - demarre), 86400)
            self.assertLessEqual(demarre, time.time() + campagne.TOLERANCE_S)
            self.assertTrue(campagne.vivant_et_meme(os.getpid(), campagne.mon_demarrage()))
            self.assertFalse(campagne.vivant_et_meme(os.getpid(), demarre - 100))
            self.assertFalse(campagne.vivant_et_meme(os.getpid(), None, demarre - 100))
        self.assertEqual(campagne.etat_processus(999999999), (False, None))
        self.assertEqual(campagne.etat_processus(0), (False, None))


class TestIsolation(unittest.TestCase):
    def setUp(self):
        garder_le_poste(self)          # la preuve : le moindre accès au vrai verrou ou à la vraie file lève
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.etat = Path(self._t.name).resolve() / "etat"
        p = mock.patch.dict(os.environ, {campagne.VARIABLE_ETAT: str(self.etat)})
        p.start()
        self.addCleanup(p.stop)

    def test_executer_sans_chemins_ne_touche_que_le_dossier_isole(self):
        vu, notes = {}, []

        def lancer(c, d):
            vu["verrou"] = json.loads((self.etat / "tests-en-cours.json").read_text(encoding="utf-8"))["pid"]
            return 0
        with mock.patch.object(campagne, "processus", side_effect=AssertionError("processus du poste lus")):
            code = campagne.executer(["x"], dossier=self._t.name, dormir=lambda s: None, dire=lambda *a, **k: None,
                                     lancer=lancer, noter=lambda *a, **k: notes.append(k))
        self.assertEqual((code, vu["verrou"], len(notes)), (0, os.getpid(), 1))
        self.assertFalse((self.etat / "tests-en-cours.json").exists())

    def test_attendre_son_tour_sans_chemins(self):
        (self.etat / "tests-en-attente").mkdir(parents=True)
        self.assertTrue(campagne.attendre_son_tour("r", dormir=lambda s: None, dire=lambda *a, **k: None))
        self.assertTrue((self.etat / "tests-en-cours.json").exists())
        self.assertEqual(campagne.en_attente(), {})
        campagne.liberer()
        self.assertFalse((self.etat / "tests-en-cours.json").exists())

    def test_hors_isolation_les_vrais_chemins_resolus_a_l_appel(self):
        self.assertEqual(campagne.dossier_etat(), self.etat)
        with mock.patch.dict(os.environ, {campagne.VARIABLE_ETAT: "  "}):
            self.assertEqual((campagne.verrou_par_defaut(), campagne.attentes_par_defaut(), campagne.dossier_etat()),
                             (campagne.VERROU, campagne.ATTENTES, campagne.DOSSIER_ETAT))
        os.environ.pop(campagne.VARIABLE_ETAT)
        self.assertFalse(campagne.isole())
        self.assertEqual(campagne.verrou_par_defaut(), Path("~/MyIAFactory/tests-en-cours.json").expanduser())
        self.assertEqual(campagne.attentes_par_defaut(), Path("~/MyIAFactory/tests-en-attente").expanduser())

    def test_aucun_chemin_fige_a_l_import(self):
        for f, noms in ((VRAIES["executer"], ("verrou", "attentes", "lister")),
                        (VRAIES["attendre_son_tour"], ("verrou", "attentes", "lister")),
                        (VRAIES["prendre"], ("verrou",)), (VRAIES["liberer"], ("verrou",)),
                        (VRAIES["en_attente"], ("attentes",))):
            sig = inspect.signature(f)
            for n in noms:
                self.assertIsNone(sig.parameters[n].default, f"{f.__name__}({n}=…)")


# --- Lecture du code des tests : un appel au verrou sans garde ni chemins explicites est refusé.
SURVEILLEES = {"executer": (3, 8), "attendre_son_tour": (2, 6), "prendre": (0, None)}    # rang de verrou, d'attentes
PERMIS = {"test_campagne.py"}      # le fichier de la garde elle-même
INDICES = tuple(f"campagne.{n}".encode() for n in SURVEILLEES) + (b"from campagne import",)


def _nom_appele(appel, importes):
    f = appel.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "campagne":
        return f.attr if f.attr in SURVEILLEES else None
    if isinstance(f, ast.Name) and f.id in importes:
        return importes[f.id]
    return None


def _explicite(appel, nom):
    cles = {k.arg for k in appel.keywords if k.arg}
    rangs = SURVEILLEES[nom]
    for cle, rang in zip(("verrou", "attentes"), rangs):
        if rang is not None and cle not in cles and len(appel.args) <= rang:
            return False
    return True


def _garde(noeud):
    for n in ast.walk(noeud):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == "garder_le_poste") or \
                    (isinstance(f, ast.Attribute) and f.attr == "garder_le_poste"):
                return True
    return False


def fuites(source, nom_fichier="<test>"):
    """Les appels qui pourraient atteindre le vrai verrou ou la vraie file : `[(fichier, ligne, appel)]`."""
    arbre = ast.parse(source)
    importes = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and n.module == "campagne":
            importes.update({a.asname or a.name: a.name for a in n.names if a.name in SURVEILLEES})
    classes = {n.name: n for n in arbre.body if isinstance(n, ast.ClassDef)}

    def gardee(classe, vues=()):
        if _garde(classe):
            return True
        return any(isinstance(b, ast.Name) and b.id in classes and b.id not in vues
                   and gardee(classes[b.id], vues + (classe.name,)) for b in classe.bases)
    sortie = []
    for haut in arbre.body:
        if isinstance(haut, ast.ClassDef) and gardee(haut):
            continue
        for n in ast.walk(haut):
            if isinstance(n, ast.Call):
                nom = _nom_appele(n, importes)
                if nom and not _explicite(n, nom):
                    sortie.append((nom_fichier, n.lineno, nom))
    return sortie


class TestAucuneFuite(unittest.TestCase):
    def test_aucun_test_n_atteint_le_vrai_verrou(self):
        debut = time.monotonic()
        trouvees = []
        for f in sorted((RACINE / "tests").glob("*.py")):
            if f.name in PERMIS:
                continue
            brut = f.read_bytes()
            if any(m in brut for m in INDICES):      # seuls ces fichiers sont analysés (le reste : 0,6 s de trop)
                trouvees += fuites(brut.decode("utf-8"), f.name)
        self.assertEqual(trouvees, [], "garder_le_poste(self) dans setUp, ou verrou= et attentes= temporaires")
        self.assertLess(time.monotonic() - debut, 0.5)

    def test_le_detecteur_voit_une_fuite(self):
        fuite = ("import campagne\nclass T:\n    def test(self):\n        campagne.executer(['x'], verrou=v)\n"
                 "        campagne.attendre_son_tour('r', lister=l)\n        campagne.prendre()\n"
                 "def aide():\n    campagne.executer(['x'], attentes=a)\n")
        self.assertEqual([(ligne, nom) for _, ligne, nom in fuites(fuite)],
                         [(4, "executer"), (5, "attendre_son_tour"), (6, "prendre"), (8, "executer")])
        from_import = "from campagne import executer as ex\nclass T:\n    def t(self):\n        ex(['x'])\n"
        self.assertEqual(len(fuites(from_import)), 1)

    def test_le_detecteur_accepte_garde_et_chemins(self):
        sain = ("import campagne\nclass Base:\n    def setUp(self):\n        garder_le_poste(self)\n"
                "class T(Base):\n    def t(self):\n        campagne.executer(['x'])\n"
                "class U:\n    def t(self):\n        campagne.executer(['x'], verrou=v, attentes=a)\n"
                "        campagne.attendre_son_tour('r', True, v, attentes=a)\n        campagne.prendre(v)\n"
                "        x = campagne.executer\n")
        self.assertEqual(fuites(sain), [])


if __name__ == "__main__":
    unittest.main()
