"""Le verrou et la file du poste (`outils/campagne.py`) après les trois blocages du 2026-11-23 :
- l'identité d'un processus noté est sa date de création (Windows) ou son empreinte boot + starttime (Linux), pas
  seulement son pid (une note fantôme dont le pid avait été repris par un `conhost.exe` retenait la file sans fin) ;
- un processus de test lancé par `tests_paralleles` (variable `MYIAFACTORY_ETAT_TESTS`) n'atteint jamais le vrai verrou,
  la vraie file, le vrai bureau ni le vrai sceau, même sans chemins explicites ; la variable n'est jamais transmise aux
  commandes d'un projet ni aux agents du moteur ;
- tout nouveau test qui appelle le verrou sans garde ni chemins temporaires est refusé tout de suite (lecture du code
  des tests, sans les lancer).
Processus simulés (`campagne.etat_processus` remplacé), sauf un test bon marché sur ce processus-ci ; aucun
sous-processus."""
import ast
import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

IMPORTE_A = time.time()
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


def sans_isolation(test):
    ancien = os.environ.pop(campagne.VARIABLE_ETAT, None)
    if ancien is not None:
        test.addCleanup(os.environ.__setitem__, campagne.VARIABLE_ETAT, ancien)


class Base(unittest.TestCase):
    def setUp(self):
        garder_le_poste(self)
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name).resolve()
        self.verrou = self.tmp / "tests-en-cours.json"
        self.attentes = self.tmp / "tests-en-attente"
        self.attentes.mkdir()
        self.processus = {}          # pid -> (date de création, empreinte) ; absent : mort
        p = mock.patch.object(campagne, "etat_processus",
                              lambda pid: (pid in self.processus, *self.processus.get(pid, (None, None))))
        p.start()
        self.addCleanup(p.stop)

    def noter(self, pid, **champs):
        (self.attentes / f"{pid}.json").write_text(json.dumps({"pid": pid, "arrivee": 1.0, **champs}),
                                                   encoding="utf-8")

    def vus(self):
        return [e[1] for e in campagne._file(self.attentes)]


class TestIdentite(Base):
    def test_pid_repris_apres_une_ancienne_note(self):
        """L'incident : `23232.json` (ancienne note, sans `demarre`), son pid repris par un processus créé après."""
        self.processus[GHOST] = (2_000_000_000.0, None)
        self.noter(GHOST, depuis=iso(1_900_000_000), tache="t1")
        self.assertEqual(campagne._file(self.attentes), [])
        self.assertEqual(campagne._devant(self.attentes, None), [])
        self.assertEqual(campagne.en_attente(self.attentes), {})

    def test_windows_date_de_creation_exacte(self):
        self.processus[GHOST] = (2_000_000_000.0, None)
        self.noter(GHOST, demarre=2_000_000_000.04, depuis=iso(2_000_000_005), tache="t1")
        self.assertEqual(self.vus(), [GHOST])
        self.assertEqual(list(campagne.en_attente(self.attentes)), ["t1"])
        self.noter(GHOST, demarre=2_000_000_000.1, depuis=iso(2_000_000_005))      # 0,1 s : un autre processus
        self.assertEqual(self.vus(), [])
        self.noter(GHOST, demarre=1_999_000_000.0, depuis=iso(2_000_000_100))
        self.assertEqual(self.vus(), [])

    def test_linux_empreinte_exacte_malgre_un_saut_d_horloge(self):
        """btime recalculé avec l'horloge murale : après un saut NTP, la date diffère, l'empreinte non."""
        self.processus[GHOST] = (2_000_000_100.0, "boot-a:4242")
        self.noter(GHOST, demarre=2_000_000_000.0, empreinte="boot-a:4242", depuis=iso(1_000_000_000))
        self.assertEqual(self.vus(), [GHOST])
        for autre in ("boot-a:4243", "boot-b:4242"):        # autre processus, ou même pid après un redémarrage
            self.noter(GHOST, demarre=2_000_000_100.0, empreinte=autre, depuis=iso(2_000_000_200))
            self.assertEqual(self.vus(), [])

    def test_linux_note_sans_empreinte_regle_des_anciennes_notes(self):
        self.processus[GHOST] = (2_000_000_000.0, "boot-a:4242")
        self.noter(GHOST, demarre=1.0, depuis=iso(2_000_000_100))
        self.assertEqual(self.vus(), [GHOST])
        self.noter(GHOST, demarre=2_000_000_000.0, depuis=iso(1_900_000_000))
        self.assertEqual(self.vus(), [])

    def test_ancienne_note_sans_dates_garde_l_ancienne_regle(self):
        self.processus[GHOST] = (2_000_000_000.0, None)
        self.noter(GHOST, depuis="10:00")             # illisible : seule l'existence du pid compte, comme avant
        self.noter(GHOST + 1)                         # mort
        self.assertEqual(self.vus(), [GHOST])
        self.processus[GHOST] = (None, None)          # identité illisible : idem
        self.noter(GHOST, demarre=5.0, empreinte="x:1")
        self.assertEqual(self.vus(), [GHOST])

    def test_ancienne_note_tolerance_de_deux_secondes(self):
        f = lambda reel: (lambda pid: (True, reel))      # noqa: E731 — l'ancienne forme à deux valeurs
        self.assertTrue(campagne.vivant_et_meme(7, None, 1000.0, etat=f(1001.9)))     # `depuis` arrondi à la seconde
        self.assertFalse(campagne.vivant_et_meme(7, None, 1000.0, etat=f(1002.5)))
        self.assertTrue(campagne.vivant_et_meme(7, None, 1000.0, etat=f(10.0)))
        self.assertFalse(campagne.vivant_et_meme(7, 1000.0, etat=lambda pid: (False, None)))
        self.assertTrue(campagne.vivant_et_meme(7, True, etat=f(5.0)))               # booléen : pas une date

    def test_le_verrou_d_un_pid_repris_est_repris(self):
        self.processus[GHOST] = (2_000_000_000.0, None)
        self.verrou.write_text(json.dumps({"pid": GHOST, "debut": iso(1_900_000_000)}), encoding="utf-8")
        with mock.patch.object(campagne, "mon_identite", lambda: (1234.5, "b:9")):
            self.assertIsNone(campagne.prendre(self.verrou, "r"))
        pris = json.loads(self.verrou.read_text(encoding="utf-8"))
        self.assertEqual((pris["pid"], pris["demarre"], pris["empreinte"]), (os.getpid(), 1234.5, "b:9"))
        campagne.liberer(self.verrou)

    def test_le_verrou_d_une_campagne_vivante_reste(self):
        self.processus[GHOST] = (2_000_000_000.0, None)
        for note in ({"pid": GHOST, "demarre": 2_000_000_000.0, "debut": iso(2_000_000_002)},
                     {"pid": GHOST, "debut": iso(2_000_000_002)}, {"pid": GHOST, "debut": "10:00"}):
            self.verrou.write_text(json.dumps(note), encoding="utf-8")
            self.assertEqual(campagne.prendre(self.verrou, "r"), note)

    def test_un_verrou_vide_n_est_repris_que_vieux(self):
        self.verrou.write_text("", encoding="utf-8")       # une autre campagne vient de le créer, pas encore écrit
        self.assertEqual(campagne.prendre(self.verrou, "r"), {"pid": None})
        self.assertTrue(self.verrou.exists())
        for decalage in (-60, 3600):                        # vide depuis une minute, ou daté du futur : repris
            self.verrou.write_text("{pas du json", encoding="utf-8")
            t = time.time() + decalage
            os.utime(self.verrou, (t, t))
            self.assertIsNone(campagne.prendre(self.verrou, "r"))
            campagne.liberer(self.verrou)

    def test_un_verrou_illisible_n_est_jamais_efface(self):
        self.verrou.write_text("", encoding="utf-8")
        ancien = time.time() - 60
        os.utime(self.verrou, (ancien, ancien))
        with mock.patch.object(campagne, "_lire_verrou", lambda v: ("illisible", None)):
            self.assertEqual(campagne.prendre(self.verrou, "r"), {"pid": None})
        self.assertTrue(self.verrou.exists())
        with mock.patch.object(campagne.Path, "read_text", side_effect=PermissionError("partage refusé")):
            self.assertEqual(campagne._lire_verrou(self.verrou), ("illisible", None))
        self.assertEqual(campagne._lire_verrou(self.tmp / "absent.json"), ("absent", None))
        self.verrou.write_bytes(b"\xff\xfe")
        self.assertEqual(campagne._lire_verrou(self.verrou), ("invalide", None))

    def test_creation_refusee_on_attend(self):
        with mock.patch.object(campagne.os, "open", side_effect=PermissionError("en cours d'effacement")):
            self.assertEqual(campagne.prendre(self.verrou, "r"), {"pid": None})

    def test_attendre_son_tour_passe_devant_une_note_fantome(self):
        self.processus[GHOST] = (2_000_000_000.0, None)
        self.noter(GHOST, depuis=iso(1_900_000_000))
        dormi = []
        self.assertTrue(campagne.attendre_son_tour("r", verrou=self.verrou, lister=lambda: [], dormir=dormi.append,
                                                   dire=lambda *a, **k: None, attentes=self.attentes))
        self.assertEqual(dormi, [])
        campagne.liberer(self.verrou)

    def test_la_note_d_attente_porte_l_identite(self):
        with mock.patch.object(campagne, "mon_identite", lambda: (1234.5, None)):
            campagne._noter_l_attente(self.attentes, "r", "m", "d", 1.0)
        x = json.loads((self.attentes / f"{os.getpid()}.json").read_text(encoding="utf-8"))
        self.assertEqual((x["demarre"], x["pid"], x["depuis"], "empreinte" in x), (1234.5, os.getpid(), "d", False))
        campagne._oublier_l_attente(self.attentes)


class TestLectureProc(unittest.TestCase):
    """`/proc` simulé : la lecture Linux, testée sous tous les systèmes."""

    def proc(self, stat, boot="boot-a\n", btime="cpu 1 2\nbtime 1700000000\n"):
        fichiers = {"/proc/42/stat": stat, "/proc/sys/kernel/random/boot_id": boot, "/proc/stat": btime}

        def lire(chemin):
            if fichiers.get(chemin) is None:
                raise FileNotFoundError(chemin)
            return fichiers[chemin]
        return lambda: campagne._lire_proc(42, lire=lire, tops_par_s=100)

    @staticmethod
    def stat(nom="py", etat="S", tops=12345):
        champs = [etat] + [str(i) for i in range(4, 22)] + [str(tops), "0"]
        return f"42 ({nom}) " + " ".join(champs)

    def test_empreinte_et_date(self):
        self.assertEqual(self.proc(self.stat())(), ("S", 1700000000 + 123.45, "boot-a:12345"))

    def test_nom_avec_parentheses_et_espaces(self):
        self.assertEqual(self.proc(self.stat(nom="a) (b c"))()[2], "boot-a:12345")

    def test_zombie_boot_illisible_stat_absent(self):
        self.assertEqual(self.proc(self.stat(etat="Z"))()[0], "Z")
        self.assertEqual(self.proc(self.stat(), boot=None)()[2], "?:12345")
        self.assertEqual(self.proc(self.stat(), btime=None)()[1:], (None, "boot-a:12345"))
        self.assertIsNone(self.proc(None)())
        self.assertIsNone(self.proc("42 (py) S 1")())

    def test_saut_d_horloge_meme_empreinte(self):
        avant = self.proc(self.stat(), btime="btime 1700000000\n")()
        apres = self.proc(self.stat(), btime="btime 1700000100\n")()      # btime recalculé après un saut NTP
        self.assertNotEqual(avant[1], apres[1])
        self.assertTrue(campagne.vivant_et_meme(42, avant[1], empreinte=avant[2],
                                                etat=lambda pid: (True, apres[1], apres[2])))


class TestIdentiteReelle(unittest.TestCase):
    def test_ce_processus_et_un_pid_absent(self):
        """Le seul test sur de vrais processus : ce processus-ci, et un pid qui n'existe pas."""
        vivant, demarre, empreinte = campagne._etat_reel(os.getpid())
        self.assertTrue(vivant)
        if demarre is not None:      # Windows (GetProcessTimes) et Linux (/proc) ; ailleurs : repli sur le pid
            self.assertLessEqual(IMPORTE_A - 120, demarre)
            self.assertLessEqual(demarre, IMPORTE_A + (0 if empreinte is None else campagne.TOLERANCE_S))
            self.assertTrue(campagne.vivant_et_meme(os.getpid(), *campagne.mon_identite()[:1],
                                                    empreinte=campagne.mon_identite()[1], etat=campagne._etat_reel))
            faux = {"empreinte": "autre:1"} if empreinte else {}
            self.assertFalse(campagne.vivant_et_meme(os.getpid(), demarre - 100, etat=campagne._etat_reel, **faux))
        self.assertEqual(campagne._etat_reel(999999999)[0], False)
        self.assertEqual(campagne._etat_reel(0), (False, None, None))


class TestIsolation(unittest.TestCase):
    def setUp(self):
        garder_le_poste(self)          # la preuve : le moindre accès au vrai verrou ou à la vraie file lève
        self._t = tempfile.TemporaryDirectory(prefix=campagne.PREFIXE_ETAT)
        self.addCleanup(self._t.cleanup)
        self.etat = Path(self._t.name).resolve() / "0"
        self.etat.mkdir()
        p = mock.patch.dict(os.environ, {campagne.VARIABLE_ETAT: str(self.etat)})
        p.start()
        self.addCleanup(p.stop)

    def test_executer_sans_chemins_ne_touche_que_le_dossier_isole(self):
        vu, notes, erreurs = {}, [], io.StringIO()

        def lancer(c, d):
            vu["verrou"] = json.loads((self.etat / "tests-en-cours.json").read_text(encoding="utf-8"))["pid"]
            return 0
        with mock.patch.object(campagne, "processus", side_effect=AssertionError("processus du poste lus")), \
                contextlib.redirect_stderr(erreurs):
            code = campagne.executer(["x"], dossier=self._t.name, dormir=lambda s: None, dire=lambda *a, **k: None,
                                     lancer=lancer, noter=lambda *a, **k: notes.append(k))
        self.assertEqual((code, vu["verrou"], len(notes)), (0, os.getpid(), 1))
        self.assertFalse((self.etat / "tests-en-cours.json").exists())
        self.assertIn("campagne isolée (test)", erreurs.getvalue())

    def test_attendre_son_tour_sans_chemins(self):
        self.assertTrue(campagne.attendre_son_tour("r", dormir=lambda s: None, dire=lambda *a, **k: None))
        self.assertTrue((self.etat / "tests-en-cours.json").exists())
        self.assertEqual(campagne.en_attente(), {})
        campagne.liberer()
        self.assertFalse((self.etat / "tests-en-cours.json").exists())

    def test_mesures_jamais_au_vrai_bureau(self):
        from bureau import tests_mesures
        vus = []
        with mock.patch.object(tests_mesures, "noter_campagne", lambda racine, **k: vus.append(k)):
            campagne._noter_par_defaut("r", commande="x")
        self.assertEqual((vus[0]["bureau"], vus[0]["sceau"]),
                         (self.etat / "bureau.json", self.etat / "tests-sceau.json"))

    def test_variable_ignoree_hors_d_un_dossier_du_lanceur(self):
        sans_prefixe = tempfile.TemporaryDirectory()
        self.addCleanup(sans_prefixe.cleanup)
        for valeur in ("  ", str(self.etat / "absent"), str(RACINE), sans_prefixe.name):
            with mock.patch.dict(os.environ, {campagne.VARIABLE_ETAT: valeur}):
                self.assertFalse(campagne.isole(), valeur)
                self.assertEqual((campagne.verrou_par_defaut(), campagne.attentes_par_defaut(),
                                  campagne.dossier_etat()), (campagne.VERROU, campagne.ATTENTES, campagne.DOSSIER_ETAT))
        self.assertEqual(campagne.dossier_etat(), self.etat)
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

    def test_les_commandes_d_un_projet_ne_recoivent_jamais_la_variable(self):
        v = campagne.VARIABLE_ETAT
        self.assertEqual(campagne._env_de_la_commande(None, {"A": "1", v: "x"}), {"A": "1"})
        self.assertEqual(campagne._env_de_la_commande({"B": "2", v: "y"}, {"A": "1"}), {"A": "1", "B": "2"})
        self.assertIsNone(campagne._env_de_la_commande(None, {"A": "1"}))
        vus = []

        class Faux:
            stdout = io.BytesIO(b"Ran 1 test\n")

            def __init__(self, *a, env=None, **k):
                vus.append(env)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def wait(self):
                return 0
        with mock.patch.object(campagne.subprocess, "Popen", Faux):
            self.assertEqual(campagne._lancer(["x"], None, sortie=io.BytesIO())[0], 0)
        self.assertNotIn(v, vus[0])
        self.assertEqual(vus[0].get("PATH"), os.environ.get("PATH"))

    def test_le_moteur_ne_donne_jamais_la_variable_aux_agents(self):
        from moteur import detache
        self.assertEqual(detache.VARIABLE_ETAT_TESTS, campagne.VARIABLE_ETAT)
        vus = []

        class Faux:
            pid = os.getpid()

        def lancer(argv, entree, sortie, erreurs, env, cwd):
            vus.append(env)
            return Faux()
        reg = detache.Registre(Path(self._t.name) / ".factory", lancer=lancer)
        reg._lancer("t1", {}, ["claude"], b"", {"PATH": "x", campagne.VARIABLE_ETAT: "y"}, self._t.name)
        reg._lancer("t2", {}, ["claude"], b"", None, self._t.name)        # hérité de `os.environ`
        self.assertEqual(vus[0], {"PATH": "x", detache.VARIABLE_TACHE: "t1", detache.VARIABLE_AGENT: "t1"})
        self.assertNotIn(campagne.VARIABLE_ETAT, vus[1])


# --- Lecture du code des tests : un appel au verrou sans garde ni chemins explicites est refusé.
# Le rang positionnel de chaque chemin, par fonction surveillée.
SURVEILLEES = {"executer": {"verrou": 3, "attentes": 8}, "attendre_son_tour": {"verrou": 2, "attentes": 6},
               "prendre": {"verrou": 0}, "liberer": {"verrou": 0}, "en_attente": {"attentes": 0}}
MODULES = {"campagne", "outils.campagne"}
GARDE = "garder_le_poste"
SOURCES_DE_LA_GARDE = {"tests.test_campagne", "test_campagne"}
INDICES = tuple(f"campagne.{n}(".encode() for n in SURVEILLEES) + (
    b"from campagne import", b"from outils.campagne import", b"import campagne as", b"import outils.campagne",
    b"from outils import campagne")
MISES_EN_PLACE = {"setUp", "setUpClass", "asyncSetUp"}


def _pointe(e):
    if isinstance(e, ast.Name):
        return e.id
    if isinstance(e, ast.Attribute):
        haut = _pointe(e.value)
        return f"{haut}.{e.attr}" if haut else None
    return None


def _noms(arbre, nom_fichier):
    """Les noms du module de `campagne`, de ses fonctions surveillées, et si `garder_le_poste` est la vraie."""
    modules, fonctions = set(), {}
    vraie_garde = False
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            modules |= {a.asname or a.name for a in n.names if a.name in MODULES}
        elif isinstance(n, ast.ImportFrom):
            if n.module in MODULES:
                fonctions.update({a.asname or a.name: a.name for a in n.names if a.name in SURVEILLEES})
            elif n.module == "outils":
                modules |= {a.asname or a.name for a in n.names if a.name == "campagne"}
            elif n.module in SOURCES_DE_LA_GARDE and any(a.name == GARDE and a.asname in (None, GARDE)
                                                          for a in n.names):
                vraie_garde = True
    definie_ici = any(isinstance(n, ast.FunctionDef) and n.name == GARDE for n in arbre.body)
    if definie_ici:
        vraie_garde = Path(nom_fichier).name == "test_campagne.py"      # une copie locale n'est pas la garde
    return modules, fonctions, vraie_garde


def _appel_surveille(appel, modules, fonctions):
    f = appel.func
    if isinstance(f, ast.Attribute) and f.attr in SURVEILLEES and _pointe(f.value) in modules:
        return f.attr
    if isinstance(f, ast.Name) and f.id in fonctions:
        return fonctions[f.id]
    return None


def _explicite(appel, nom):
    def rien(e):
        return isinstance(e, ast.Constant) and e.value is None
    cles = {k.arg: k.value for k in appel.keywords if k.arg}
    for cle, rang in SURVEILLEES[nom].items():
        if cle in cles:
            if rien(cles[cle]):
                return False
        elif len(appel.args) <= rang or rien(appel.args[rang]) or isinstance(appel.args[rang], ast.Starred):
            return False
    return True


def _lignes_de_garde(noeud):
    return [n.lineno for n in ast.walk(noeud) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == GARDE]


def fuites(source, nom_fichier="<test>"):
    """Les appels qui pourraient atteindre le vrai verrou ou la vraie file : `[(fichier, ligne, appel)]`. Permis : une
    classe dont la mise en place (`setUp`…, ou celle d'une base du module) appelle la vraie `garder_le_poste` ; une
    fonction qui l'appelle avant ; un appel aux chemins explicites (ni `None`, ni `*a`/`**k`)."""
    arbre = ast.parse(source)
    modules, fonctions, vraie_garde = _noms(arbre, nom_fichier)
    classes = {n.name: n for n in arbre.body if isinstance(n, ast.ClassDef)}

    def gardee(classe, vues=()):
        if vraie_garde and any(isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name in MISES_EN_PLACE
                               and _lignes_de_garde(m) for m in classe.body):
            return True
        return any(isinstance(b, ast.Name) and b.id in classes and b.id not in vues
                   and gardee(classes[b.id], vues + (classe.name,)) for b in classe.bases)

    def verifier(noeud, garde_avant):
        sortie = []
        for n in ast.walk(noeud):
            if isinstance(n, ast.Call):
                nom = _appel_surveille(n, modules, fonctions)
                if nom and not _explicite(n, nom) and not any(l < n.lineno for l in garde_avant(n)):
                    sortie.append((nom_fichier, n.lineno, nom))
        return sortie

    trouvees = []
    for haut in arbre.body:
        if isinstance(haut, ast.ClassDef):
            if gardee(haut):
                continue
            for m in haut.body:
                lignes = _lignes_de_garde(m) if vraie_garde else []
                trouvees += verifier(m, lambda n, l=lignes: l)
        elif isinstance(haut, (ast.FunctionDef, ast.AsyncFunctionDef)) and haut.name != GARDE:
            lignes = _lignes_de_garde(haut) if vraie_garde else []
            trouvees += verifier(haut, lambda n, l=lignes: l)
        elif not isinstance(haut, (ast.FunctionDef, ast.AsyncFunctionDef)):
            trouvees += verifier(haut, lambda n: [])
    return trouvees


def analyser_les_tests(dossier=RACINE / "tests"):
    """`(fuites, fichiers analysés)` : seuls les fichiers dont les octets montrent un appel ou un import de `campagne`
    sont analysés."""
    trouvees, analyses = [], 0
    for f in sorted(Path(dossier).glob("*.py")):
        brut = f.read_bytes()
        if any(m in brut for m in INDICES):
            analyses += 1
            trouvees += fuites(brut.decode("utf-8"), f.name)
    return trouvees, analyses


ENTETE = "import campagne\nfrom tests.test_campagne import garder_le_poste\n"


class TestAucuneFuite(unittest.TestCase):
    def test_aucun_test_n_atteint_le_vrai_verrou(self):
        trouvees, analyses = analyser_les_tests()
        self.assertEqual(trouvees, [], "garder_le_poste(self) dans setUp, ou verrou= et attentes= temporaires")
        self.assertGreaterEqual(analyses, 3)         # le préfiltre voit bien les modules du verrou…
        self.assertLessEqual(analyses, 10)           # … et eux seuls : le travail reste borné

    def lignes(self, source):
        return [(ligne, nom) for _, ligne, nom in fuites(source)]

    def test_le_detecteur_voit_une_fuite(self):
        fuite = (ENTETE + "class T:\n    def test(self):\n        campagne.executer(['x'], verrou=v)\n"
                 "        campagne.attendre_son_tour('r', lister=l)\n        campagne.prendre()\n"
                 "        campagne.liberer(verrou=None)\n        campagne.en_attente()\n"
                 "def aide():\n    campagne.executer(['x'], attentes=a)\n")
        self.assertEqual(self.lignes(fuite), [(5, "executer"), (6, "attendre_son_tour"), (7, "prendre"),
                                              (8, "liberer"), (9, "en_attente"), (11, "executer")])

    def test_le_detecteur_voit_les_alias(self):
        for imp, appel in (("import campagne as c", "c.executer(['x'])"),
                           ("import outils.campagne", "outils.campagne.executer(['x'])"),
                           ("from outils import campagne as k", "k.prendre()"),
                           ("from outils.campagne import executer", "executer(['x'])"),
                           ("from campagne import attendre_son_tour as t", "t('r')")):
            self.assertEqual(len(fuites(f"{imp}\nclass T:\n    def t(self):\n        {appel}\n")), 1, imp)

    def test_la_garde_doit_etre_la_vraie_et_dans_la_mise_en_place(self):
        appel = "    def t(self):\n        campagne.executer(['x'])\n"
        ailleurs = ENTETE + "class T:\n    def autre(self):\n        garder_le_poste(self)\n" + appel
        self.assertEqual(len(fuites(ailleurs)), 1)                           # pas dans setUp
        copie = ("import campagne\ndef garder_le_poste(test):\n    pass\n"
                 "class T:\n    def setUp(self):\n        garder_le_poste(self)\n" + appel)
        self.assertEqual(len(fuites(copie)), 1)                              # une copie locale (peut-être vide)
        self.assertEqual(len(fuites(copie, "test_campagne.py")), 0)          # la vraie, dans son fichier

    def test_le_detecteur_accepte_garde_et_chemins(self):
        sain = (ENTETE + "class Base:\n    def setUp(self):\n        garder_le_poste(self)\n"
                "class T(Base):\n    def t(self):\n        campagne.executer(['x'])\n"
                "class U:\n    def t(self):\n        campagne.executer(['x'], verrou=v, attentes=a)\n"
                "        campagne.attendre_son_tour('r', True, v, attentes=a)\n        campagne.prendre(v)\n"
                "        campagne.liberer(self.verrou)\n        campagne.en_attente(self.attentes)\n"
                "        x = campagne.executer\n"
                "    def u(self):\n        garder_le_poste(self)\n        campagne.executer(['x'], **kw)\n")
        self.assertEqual(fuites(sain), [])


if __name__ == "__main__":
    unittest.main()
