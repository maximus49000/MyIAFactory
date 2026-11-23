"""Licence Unity au serveur (tâche 14i, § 5.16) : capacités `unity-licence` et `unity-bac-a-sable`, choix automatique de
l'exécuteur (CODE SENSIBLE : il décide où du code de projet tourne), exigence `nom=etat`, code 81, étapes humaines guidées,
outil de l'expérience J13/J14. Tout est faux : ssh, `_bash`, `executer`, serveur ; aucune vraie licence n'est lue ni cherchée
(valeur `LICENCE-FACTICE` dans des HOME temporaires)."""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import serveur_capacites  # noqa: E402
import serveur_installation  # noqa: E402
import serveur_tache  # noqa: E402
import tests_serveur  # noqa: E402
import tests_unity_essai  # noqa: E402
from bureau import releve  # noqa: E402
from tests_profil import Profil  # noqa: E402

from tests.test_tests_serveur import ID, SERVEUR, Base, FauxSsh  # noqa: E402

UNITY = Profil(familles=("unity",), outils={"unity": "6000.6.7f1", "unity_revision": "b22767f04f04"},
               commandes=[["unity-editor", "-batchmode", "-nographics", "-projectPath", "/work", "-runTests",
                           "-testPlatform", "EditMode"]],
               ressources={"cpus": 4, "memoire_mo": 10240, "duree_s": 3600})
PYTHON = Profil(familles=("python",), outils={}, commandes=[["python3", "-m", "unittest"]])
COMMANDE_UNITY = ["unity-editor", "-batchmode", "-runTests"]


def etat(licence=None, variante=None, statut_licence="presente", bac="absente", hotes=None):
    """L'entrée locale d'un serveur (`serveurs-etat.json`)."""
    e = {"capacites": {"tests-image": {"statut": "presente"}, "unity-licence": {"statut": statut_licence},
                       "unity-bac-a-sable": {"statut": bac}}}
    if licence is not None:
        e["etats"] = {"unity-licence": {"etat": licence, "variante": variante, "hotes": hotes or []}}
    return e


class FauxInstantaneUnity:
    HorsLimites = tests_serveur.tests_instantane.HorsLimites

    def lister(self, racine, **k):
        return ["Assets/a.cs"], []

    def executables(self, racine, **k):
        return set()

    def ecrire_tar(self, racine, fichiers, destination, executables=None, **k):
        destination.write(b"archive")
        return 1, 7


class Route(Base):
    """`tests_serveur.executer` avec un profil Unity et l'état local d'un serveur donné."""

    def setUp(self):
        super().setUp()
        self.instantane = FauxInstantaneUnity()
        self.poses, self.notes_licence = [], []
        self.etape_posee = True

    def unity(self, ssh, entree, profil=UNITY, commande=COMMANDE_UNITY, **k):
        def poser(dossier_etat, serveur_id, cle):
            self.poses.append(cle)
            return len(self.poses) == 1

        def noter_licence(dossier_etat, serveur, etat_, **kw):
            self.notes_licence.append((etat_, kw))
            return "fait", "", self.etape_posee
        options = dict(analyse=lambda racine, **o: profil, etat_serveurs=lambda d: {SERVEUR.id: entree},
                       poser_etape=poser, noter_licence=noter_licence, version_hote_de=lambda racine: None,
                       ressources_forcees=lambda racine: {})
        options.update(k)
        return self.lancer(ssh, commande=commande, **options)

    @staticmethod
    def distante(ssh):
        return ssh.appels_flux[0]["commande"]


class TestChoix(Route):
    def test_conteneur_choisi(self):
        self.assertEqual(tests_serveur.executeur_pour(UNITY, etat("conteneur", "B2")), ("conteneur", "B2"))
        self.assertEqual(tests_serveur.executeur_pour(UNITY, etat("conteneur", None)), ("conteneur", "B1"))
        ssh = FauxSsh()
        self.assertEqual(self.unity(ssh, etat("conteneur", "B2")), 0)
        d = self.distante(ssh)
        self.assertIn("myiafactory/tests-unity-6000.6.7f1 unity", d)
        self.assertTrue(d.endswith(" conteneur B2"), d)
        self.assertEqual(self.poste.appels, [])
        # B3 retenue par J13 : les hôtes de licence relevés partent avec elle (l'accord QU1 reste exigé)
        ssh = FauxSsh()
        self.unity(ssh, etat("conteneur", "B3", hotes=["license.unity3d.com"]), reseau_licence=lambda r: True)
        self.assertTrue(self.distante(ssh).endswith(" conteneur B3 license.unity3d.com"), self.distante(ssh))

    def test_hote_jamais_sans_bac_a_sable(self):
        with self.assertRaises(tests_serveur.RepliUnity) as e:
            tests_serveur.executeur_pour(UNITY, etat("hote", bac="absente"))
        self.assertIn(tests_serveur.RAISON_BAC_ABSENT, e.exception.raison)
        # par la route : Repli dit, aucun appel au serveur (ni dépôt ni session), le poste prend la campagne
        ssh = FauxSsh()
        self.unity(ssh, etat("hote", bac="absente"))
        self.assertEqual((ssh.appels_octets, ssh.appels_flux), ([], []))
        self.assertEqual(len(self.poste.appels), 1)
        self.assertTrue(self.dit("bac à sable Unity absent : rien ne tourne sur l'hôte sans lui"), self.dits)
        # demandé EXPLICITEMENT (outil J14, --serveur) sans les prérequis : refusé aussi, jamais lancé
        for entree in (etat("hote", bac="absente"), etat("conteneur", "B1", bac="presente"), etat(None, bac="presente"),
                       etat("hote", statut_licence="absente", bac="presente")):
            ssh = FauxSsh()
            code = self.unity(ssh, entree, forcer=True, executeur="hote_bac_a_sable", licence="B1")
            self.assertEqual(code, 4, entree)
            self.assertEqual((ssh.appels_octets, ssh.appels_flux), ([], []), entree)
        # hors de la famille unity : jamais l'hôte
        ssh = FauxSsh()
        self.assertEqual(self.unity(ssh, etat("hote", bac="presente"), profil=PYTHON, commande=("python", "-m", "unittest"),
                                    forcer=True, executeur="hote_bac_a_sable"), 4)
        self.assertEqual(ssh.appels_flux, [])

    def test_hote_avec_bac_a_sable(self):
        self.assertEqual(tests_serveur.executeur_pour(UNITY, etat("hote", bac="presente")), ("hote_bac_a_sable", "B1"))
        ssh = FauxSsh()
        self.assertEqual(self.unity(ssh, etat("hote", bac="presente")), 0)
        self.assertTrue(self.distante(ssh).endswith(" hote_bac_a_sable B1"), self.distante(ssh))
        # 18e argument : la version de repli décidée par le Directeur (tests.profil_force.unity_version_hote)
        ssh = FauxSsh()
        self.unity(ssh, etat("hote", bac="presente"), version_hote_de=lambda racine: "6000.6.10f1")
        self.assertTrue(self.distante(ssh).endswith(" hote_bac_a_sable B1 - 6000.6.10f1"), self.distante(ssh))
        self.assertTrue(self.dit("résultats indicatifs"))
        with self.assertRaises(tests_serveur.Repli):
            tests_serveur._arguments_executeur("conteneur", "B1", None, None, ".", version_hote="6000.6.10f1")
        with self.assertRaises(tests_serveur.Repli):
            tests_serveur._arguments_executeur("hote_bac_a_sable", "B1", None, None, ".", version_hote="6000.6.10f1; id")

    def test_absente_repli_et_etape_humaine(self):
        d = Path(self._t.name) / "etat-local"
        poser = tests_serveur.poser_etape_humaine
        for _ in range(2):
            ssh = FauxSsh()
            self.unity(ssh, etat(None), dossier_etat=d, poser_etape=poser)
            self.assertEqual((ssh.appels_octets, ssh.appels_flux), ([], []))
        self.assertEqual(len(self.poste.appels), 2)
        self.assertTrue(self.dit("licence Unity absente : expérience B non faite"), self.dits)
        self.assertEqual(sum("Étape humaine posée" in x for x in self.dits), 1)           # posée UNE fois
        e = serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence")
        etape = e["etapes"]["unity-licence"]
        self.assertTrue(releve.mode_operatoire_ok(etape["mode_operatoire"]))
        self.assertTrue(releve.etape_humaine_ok(etape))
        self.assertEqual(len(etape["mode_operatoire"]), 5)
        self.assertEqual((etape["genre"], etape["autonome"], etape["bouton"]), ("environnement", False, "Vérifier la licence"))
        self.assertEqual(etape["lien"], releve.LIEN_LICENCES_HUB)
        self.assertIn("--bureau-distant", etape["mode_operatoire"][0])
        self.assertTrue(releve.etape_humaine_ok(releve.etape_humaine_serveur("unity-editeur-6000.6.7f1")))
        # une décision environnement d'un relevé : lien et mode opératoire validés s'ils sont donnés
        erreurs = []
        releve._verifier_outils_a_installer({"environnement": [{"outil": "x"}], "lien": "http://x", "mode_operatoire": ["a"]},
                                            "ici", erreurs)
        self.assertEqual(len(erreurs), 2, erreurs)
        # une sonde n'efface jamais l'état relevé
        serveur_installation._ecrire_etat(d, SERVEUR.id, {"base": {"statut": "presente"}}, False, "", fusionner=False)
        self.assertIn("etapes", serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence"))

    def test_code_81_rend_la_licence_absente(self):
        ssh = FauxSsh(sessions=[{"fin_serveur": (81, 100, 110, 0), "code": 81}])
        self.assertEqual(self.unity(ssh, etat("conteneur", "B1")), 81)
        self.assertEqual([n[0] for n in self.notes_licence], ["absente"])
        self.assertIn("refusée", self.notes_licence[0][1]["raison"])
        # pendant une évaluation (J13), 81 est un résultat : rien n'est noté, aucune ligne de mesure
        self.notes_licence.clear()
        self.notes.clear()
        ssh = FauxSsh(sessions=[{"fin_serveur": (81, 100, 110, 0), "code": 81}])
        self.unity(ssh, etat(None), executeur="conteneur", licence="B1", evaluation=True)
        self.assertEqual((self.notes_licence, self.notes), ([], []))
        # le vrai `noter_licence_unity` : l'étape unity_licence_etat au serveur, puis l'état local avec l'état d'avant
        d = Path(self._t.name) / "etat-local"
        lignes = []

        class SshEtape:
            def __init__(self, statut="fait"):
                self.statut = statut

            def executer(self, cible, commande, cle, stdin=None, delai=60):
                lignes.append((commande, stdin))
                return 0, json.dumps({"etape": "unity_licence_etat", "statut": self.statut, "detail": "ok"}), ""
        tests_serveur.noter_licence_unity(d, SERVEUR, "conteneur", "B2", ssh=SshEtape())
        tests_serveur.noter_licence_unity(d, SERVEUR, "absente", raison="licence refusée", ssh=SshEtape())
        self.assertEqual([x[1] for x in lignes], ["conteneur B2\n", "absente\n"])
        self.assertTrue(all("--etape unity_licence_etat" in x[0] for x in lignes))
        e = serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence")
        self.assertEqual((e["etat"], e["precedent"]["etat"], e["precedent"]["variante"]), ("absente", "conteneur", "B2"))
        self.assertIn("unity-licence", e["etapes"])
        # « Vérifier la licence » : l'état d'avant est réécrit (l'étape exige les fichiers de licence), l'étape humaine retirée
        self.assertEqual(tests_serveur.verifier_licence_unity(d, SERVEUR, ssh=SshEtape("a_faire"))[:23], "Licence Unity non rétab")
        self.assertEqual(serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence")["etat"], "absente")
        message = tests_serveur.verifier_licence_unity(d, SERVEUR, ssh=SshEtape())
        self.assertEqual(message, "État rétabli ; la licence sera vérifiée à la prochaine campagne.")   # libellé honnête (I3)
        e = serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence")
        self.assertEqual((e["etat"], e["variante"], e["etapes"]), ("conteneur", "B2", {}))
        # une étape refusée par le serveur n'écrit rien de local (sauf « absente »)
        avant = serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence")
        tests_serveur.noter_licence_unity(d, SERVEUR, "hote", ssh=SshEtape("bloque"))
        self.assertEqual(serveur_installation.lire_etat_capacite(d, SERVEUR.id, "unity-licence")["etat"], avant["etat"])
        with self.assertRaises(ValueError):
            tests_serveur.noter_licence_unity(d, SERVEUR, "conteneur", None, ssh=SshEtape())

    def test_python_du_projet_ne_demande_pas_la_licence(self):
        for entree in (etat(None, statut_licence="absente"), etat("absente")):
            ssh = FauxSsh()
            self.requises = None
            code = self.unity(ssh, entree, profil=PYTHON, commande=("python", "-m", "unittest"))
            self.assertEqual(code, 0)
            self.assertEqual(self.requises, ("tests-image",))
            d = self.distante(ssh)
            self.assertNotIn("conteneur", d)
            self.assertNotIn("unity", d)
            self.assertEqual(self.poses, [])
        self.assertEqual(tests_serveur.executeur_pour(PYTHON, etat(None)), ("conteneur", None))

    def test_carte_du_serveur(self):
        from bureau import serveurs as carte
        self.assertIsNone(carte._fiche_unity({"capacites": {"base": {"statut": "presente"}}}))
        f = carte._fiche_unity(etat("conteneur", "B2", bac="presente"))
        self.assertEqual((f["licence"]["etat"], f["licence"]["variante"], f["bac_a_sable"]), ("conteneur", "B2", "pret"))
        e = etat("absente")
        e["etats"]["unity-licence"]["etapes"] = {"unity-licence": releve.etape_humaine_serveur("unity-licence"),
                                                 "piege": {"genre": "environnement", "texte": "x", "lien": "javascript:1"}}
        f = carte._fiche_unity(e)
        self.assertEqual([x["id"] for x in f["etapes"]], ["unity-licence"])     # une étape mal formée n'est jamais montrée
        self.assertEqual(carte.route_post("/api/serveurs/s1/verifier-licence"), ("verifier-licence", "s1"))

    def test_verdict_d_adoption_unity(self):
        v = tests_serveur.verdict_unity(82, "conteneur")
        self.assertEqual((v["statut"], v["raison"], v["executeur"], v["risque"]),
                         ("echoue", "aucun test découvert", "dans le conteneur", None))
        v = tests_serveur.verdict_unity(0, "hote_bac_a_sable", nb_tests=3)
        self.assertEqual((v["statut"], v["executeur"]), ("passe", "sur l'hôte, bac à sable"))
        self.assertEqual(len(v["risque"].splitlines()), 1)
        self.assertEqual(tests_serveur.verdict_unity(0, "conteneur", nb_tests=0)["statut"], "echoue")


class TestExigence(unittest.TestCase):
    def test_exigence_nom_etat(self):
        s = SimpleNamespace(id="s1")

        def choisir(entree, requises):
            with mock.patch.object(serveur_tache.serveur_modele, "lire", return_value=[s]), \
                    mock.patch.object(serveur_tache.serveur_installation, "lire_etat_vivant", return_value={"s1": entree}):
                return serveur_tache.choisir_serveur("x", requises=requises)
        with self.assertRaises(serveur_tache.RefusLancement) as e:
            choisir(etat("hote"), ("unity-licence=conteneur",))
        self.assertIn("relevé : hote", str(e.exception))
        self.assertIs(choisir(etat("conteneur", "B1"), ("unity-licence=conteneur",)), s)
        self.assertIs(choisir(etat("hote"), ("unity-licence=hote",)), s)
        with self.assertRaises(serveur_tache.RefusLancement):               # relevé conteneur mais sonde : absente
            choisir(etat("conteneur", "B1", statut_licence="absente"), ("unity-licence=conteneur",))
        with self.assertRaises(serveur_tache.RefusLancement):               # jamais relevé
            choisir(etat(None), ("unity-licence=conteneur",))
        self.assertIs(choisir(etat("hote"), ("unity-licence", "tests-image")), s)   # sans « = » : le sens d'avant


class TestCapacites(unittest.TestCase):
    def test_capacites_du_catalogue(self):
        lic, bac = serveur_capacites.CATALOGUE["unity-licence"], serveur_capacites.CATALOGUE["unity-bac-a-sable"]
        self.assertEqual((lic.libelle, lic.depend, lic.etape, lic.installable),
                         ("Licence Unity de Hub pour les tests", ("base",), "unity_licence_etat", False))
        self.assertEqual(lic.raison_non_installable, "licence de Unity Hub : reconnecter Hub par la session graphique")
        self.assertEqual((bac.libelle, bac.depend, bac.etape, bac.installable),
                         ("Bac à sable de l'hôte pour les tests Unity (option A)", ("unity-licence", "session-graphique"),
                          "unity_bac_a_sable", True))
        for mot in ("cat", "base64", "xxd", "cp"):
            self.assertIsNone(re.search(rf"(?<![\w-]){mot}(?![\w-])", lic.sonde), mot)
        self.assertIn("unity-bac-a-sable.version", bac.sonde)
        script = (RACINE / "serveur_ovh" / "mise_en_place.sh").read_text(encoding="utf-8")
        self.assertIn("  unity_licence_etat) etape_unity_licence_etat ;;", script)

    @unittest.skipIf(shutil.which("bash") is None or os.name == "nt", "bash Linux requis")
    def test_sonde_de_la_licence(self):
        sonde = serveur_capacites.CATALOGUE["unity-licence"].sonde
        with tempfile.TemporaryDirectory() as h:
            home = Path(h)

            def lancer():
                r = subprocess.run(["bash", "-c", sonde], capture_output=True, text=True, timeout=30,
                                   env=dict(os.environ, HOME=home.as_posix()), stdin=subprocess.DEVNULL)
                return r.returncode, r.stdout.strip()
            self.assertEqual(lancer(), (1, "absente"))                            # état de départ
            (home / ".myiafactory").mkdir()
            (home / ".myiafactory" / "unity-licence.etat").write_text("conteneur B2\n", encoding="utf-8")
            self.assertEqual(lancer(), (1, "absente"))                            # aucun fichier de licence
            lic = home / ".config" / "unity3d" / "Unity" / "licenses"
            lic.mkdir(parents=True)
            (lic / "UnityEntitlementLicense.xml").write_text("LICENCE-FACTICE", encoding="utf-8")
            self.assertEqual(lancer(), (0, "conteneur"))
            (home / ".myiafactory" / "unity-licence.etat").write_text("hote\n", encoding="utf-8")
            self.assertEqual(lancer(), (0, "hote"))
            (home / ".myiafactory" / "unity-licence.etat").write_text("n'importe quoi\n", encoding="utf-8")
            self.assertEqual(lancer(), (1, "absente"))

    @unittest.skipIf(shutil.which("bash") is None or os.name == "nt", "bash Linux requis")
    def test_etape_unity_licence_etat(self):
        script = RACINE / "serveur_ovh" / "mise_en_place.sh"
        with tempfile.TemporaryDirectory() as h:
            home = Path(h)

            def etape(ligne):
                r = subprocess.run(["bash", str(script), "--etape", "unity_licence_etat"], input=ligne, capture_output=True,
                                   text=True, timeout=30, env=dict(os.environ, HOME=home.as_posix(), DISQUE_LIBRE_GO="50"))
                return json.loads(r.stdout.strip().splitlines()[-1])["statut"]
            marqueur = home / ".myiafactory" / "unity-licence.etat"
            self.assertEqual(etape("conteneur B1\n"), "a_faire")                 # sans fichier de licence : rien d'écrit
            self.assertFalse(marqueur.exists())
            self.assertEqual(etape("conteneur B9\n"), "bloque")
            self.assertEqual(etape("hote; id\n"), "bloque")
            self.assertEqual(etape("absente\n"), "fait")
            self.assertEqual(marqueur.read_text(encoding="utf-8"), "absente\n")
            lic = home / ".local" / "share" / "unity3d" / "Unity"
            lic.mkdir(parents=True)
            (lic / "Unity_lic.ulf").write_text("LICENCE-FACTICE", encoding="utf-8")
            self.assertEqual(etape("conteneur B2\n"), "fait")
            self.assertEqual(marqueur.read_text(encoding="utf-8"), "conteneur B2\n")
            self.assertEqual(oct(marqueur.stat().st_mode & 0o777), "0o600")


class Essai(unittest.TestCase):
    """L'outil de l'expérience J13/J14 : faux `bash`, faux `executer`, faux serveur."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.t = Path(t.name)
        self.projet = self.t / "projet"
        self.projet.mkdir()
        self.scripts, self.lances, self.notes, self.poses, self.rafraichis = [], [], [], [], []
        self.codes = {}
        self.audit = (0, "ok utilisateur\nok seccomp\nbilan 0 echec(s)\n")

    def bash(self, serveur, script):
        self.scripts.append(script)
        if "auditer" in script:
            return self.audit + ("",)
        if "-printf" in script:
            return 0, ("fichier /home/u/.config/unity3d/Unity/licenses/UnityEntitlementLicense.xml 2048\n"
                       "<?xml LICENCE-FACTICE contenu jamais gardé\n"
                       "socket /run/user/1000/Unity-LicenseClient-u.sock\n"), ""
        return 0, "", ""

    def executer(self, commande, **k):
        self.lances.append((list(commande), k))
        return self.codes.get(k["licence"], 81) if k["executeur"] == "conteneur" else self.codes.get("hote", 0)

    def essai(self, variantes=("B1", "B2"), hote=False, entree=None, accord=False, hotes=()):
        return tests_unity_essai.essai(
            SERVEUR.id, str(self.projet), "Jeu.Tests.UnTest", variantes, hote, hotes, dossier_etat=self.t,
            bash=self.bash, executer=self.executer,
            noter_licence=lambda d, s, e, v=None, **k: self.notes.append((e, v)) or ("fait", ""),
            poser_etape=lambda d, sid, cle: self.poses.append(cle) or True, accord_b3=lambda r: accord,
            lire_serveurs=lambda d: [SERVEUR], etat_serveurs=lambda d: {SERVEUR.id: entree or etat(None)},
            rafraichir=lambda s, d: self.rafraichis.append(s.id), empreinte_bac="bac_a_sable=A;utilisateur=unity-tests;fichiers=0123456789abcdef",
            analyse=lambda r, **o: UNITY, nouvel_id=lambda: ID, horloge=lambda: 0.0, dire=lambda *a: None,
            releves=self.t / "tests-unity-essai.json")

    def test_essai_ordre_des_variantes(self):
        self.codes = {"B1": 81, "B2": 0, "B3": 0}
        r = self.essai(("B1", "B2", "B3"))
        self.assertEqual((r["verdict"], r["variante"]), ("conteneur", "B2"))
        self.assertEqual([(k["licence"], k["forcer"], k["evaluation"], k["executeur"]) for _, k in self.lances],
                         [("B1", True, True, "conteneur"), ("B2", True, True, "conteneur"), ("B2", True, True, "conteneur")])
        self.assertEqual([p["passage"] for p in r["passages"]], ["froid", "froid", "chaud"])
        self.assertTrue(all(c[-2:] == ["-testFilter", "Jeu.Tests.UnTest"] for c, _ in self.lances))
        self.assertEqual(self.notes, [("conteneur", "B2")])
        ecrit = json.loads((self.t / "tests-unity-essai.json").read_text(encoding="utf-8"))
        self.assertEqual(ecrit["essais"][-1]["verdict"], "conteneur")
        # 81 partout : hote, l'étape QU2 posée
        self.lances.clear(), self.notes.clear()
        self.codes = {}
        r = self.essai()
        self.assertEqual(r["verdict"], "hote")
        self.assertEqual(self.notes, [("hote", None)])
        self.assertEqual(self.poses, ["unity-editeur-6000.6.7f1"])

    def test_essai_indetermine_n_ecrit_rien(self):
        for code in (82, 3, 2, 4):
            self.lances.clear()
            self.codes = {"B1": code, "B2": 0}
            r = self.essai()
            self.assertEqual((r["verdict"], r["etat_ecrit"]), ("indetermine", None), code)
            self.assertEqual([k["licence"] for _, k in self.lances], ["B1"], code)      # B2 n'est pas tentée
        self.assertEqual((self.notes, self.poses), ([], []))
        with self.assertRaises(tests_unity_essai.Refus):
            tests_unity_essai.commande_essai(str(self.projet), "x; rm -rf /", analyse=lambda r, **o: UNITY)

    def test_b3_jamais_sans_accord(self):
        r = self.essai(("B1", "B2", "B3"), accord=False, hotes=["license.unity3d.com"])
        self.assertNotIn("B3", [k["licence"] for _, k in self.lances])
        self.assertEqual(r["verdict"], "hote")                                   # 81 dans toutes les variantes PERMISES
        self.assertTrue(any("QU1" in m for m in r["messages"]))
        self.lances.clear()
        self.essai(("B1", "B2", "B3"), accord=True)                               # accordée mais sans hôtes : écartée
        self.assertNotIn("B3", [k["licence"] for _, k in self.lances])
        self.lances.clear()
        self.essai(("B1", "B2", "B3"), accord=True, hotes=["license.unity3d.com"])
        b3 = [k for _, k in self.lances if k["licence"] == "B3"]
        self.assertEqual(b3[0]["hotes_licence"], ["license.unity3d.com"])
        with self.assertRaises(tests_unity_essai.Refus):
            self.essai(("B3",), accord=True, hotes=["attaquant.example"])

    def test_inventaire_noms_seulement(self):
        self.codes = {"B1": 0}
        r = self.essai(("B1",))
        inventaire = [s for s in self.scripts if "-printf" in s]
        self.assertEqual(len(inventaire), 1)
        for mot in ("cat", "head", "tail", "base64", "xxd", "cp", "od", "strings", "less", "more"):
            self.assertIsNone(re.search(rf"(?<![\w-]){mot}(?![\w-])", inventaire[0]), mot)
        self.assertNotIn("unityhub", inventaire[0])
        self.assertEqual(r["inventaire"]["fichiers"],
                         [{"nom": "/home/u/.config/unity3d/Unity/licenses/UnityEntitlementLicense.xml", "taille": 2048}])
        self.assertEqual(r["inventaire"]["sockets"], ["/run/user/1000/Unity-LicenseClient-u.sock"])
        self.assertNotIn("FACTICE", json.dumps(r))

    def test_marqueur_audit_seulement_si_tout_passe(self):
        hote = etat("hote", bac="absente")
        with self.assertRaises(tests_unity_essai.Refus):                          # J14 seulement après un J13 « hote »
            self.essai(hote=True, entree=etat("conteneur", "B1"))
        for sortie in ((0, "ok utilisateur\nechec invisible-.ssh : visible\nbilan 1 echec(s)\n"),
                       (1, "ok utilisateur\nbilan 0 echec(s)\n"), (0, "ok utilisateur\n"), (0, "")):
            self.scripts.clear(), self.lances.clear()
            self.audit = sortie
            r = self.essai(hote=True, entree=hote)
            self.assertEqual(r["verdict"], "audit_echoue", sortie)
            self.assertFalse([s for s in self.scripts if "unity-bac-a-sable.version" in s], sortie)
            self.assertEqual((self.lances, self.rafraichis), ([], []), sortie)
        self.scripts.clear()
        self.audit = (0, "ok utilisateur\nok seccomp\nbilan 0 echec(s)\n")
        r = self.essai(hote=True, entree=hote)
        self.assertEqual(r["verdict"], "bac_a_sable_pret")
        audit = [s for s in self.scripts if "auditer" in s][0]
        self.assertIn(f"sudo -n /usr/local/lib/myiafactory/unity-bac-a-sable.sh auditer {ID} 4 10240 900 6000.6.7f1 aucun 10",
                      audit)
        self.assertTrue([s for s in self.scripts if "unity-bac-a-sable.version" in s])
        self.assertEqual(self.rafraichis, [SERVEUR.id])
        self.assertEqual([(k["executeur"], k["licence"]) for _, k in self.lances], [("hote_bac_a_sable", "B1")] * 2)
        self.assertEqual(r["risque"], tests_serveur.RISQUE_A)
        with self.assertRaises(tests_unity_essai.Refus):
            tests_unity_essai.script_marqueur("x'; rm -rf ~; '")


MIXTE = Profil(familles=("python", "unity"), outils={"unity": "6000.6.7f1"},
               commandes=[["python3", "-m", "unittest"], UNITY.commandes[0]], ressources=dict(UNITY.ressources))


class TestCorrectifs(Route):
    """Relecture 14i : M1, M3, M6 (route) ; I3 vu plus haut."""

    def test_profil_mixte_python_sans_licence_unity_avec(self):
        # M1 : profil (« python », « unity ») de sur-la-route : la commande python part par tests-image, sans licence
        for entree in (etat(None, statut_licence="absente"), etat("absente")):
            ssh = FauxSsh()
            self.requises = None
            self.assertEqual(self.unity(ssh, entree, profil=MIXTE, commande=("python", "-m", "unittest")), 0)
            self.assertEqual(self.requises, ("tests-image",))
            self.assertNotIn("unity", self.distante(ssh))
            self.assertNotIn("conteneur", self.distante(ssh))
        self.assertEqual(self.poses, [])
        # la commande Unity du même profil suit la règle (comme executeur_pour : « unity » dans les familles)
        ssh = FauxSsh()
        self.unity(ssh, etat("conteneur", "B1"), profil=MIXTE)
        self.assertTrue(self.distante(ssh).endswith(" conteneur B1"), self.distante(ssh))
        self.assertIn("myiafactory/tests-unity-6000.6.7f1 unity", self.distante(ssh))
        ssh = FauxSsh()
        self.unity(ssh, etat(None), profil=MIXTE)
        self.assertEqual(ssh.appels_flux, [])
        self.assertEqual(self.poses, ["unity-licence"])

    def test_mot_de_la_sonde_discordant(self):
        # M3 : le mot imprimé par la sonde (conteneur/hote) doit égaler l'état local, sinon absente, discordance dite
        e = etat("conteneur", "B1")
        e["capacites"]["unity-licence"]["mot"] = "hote"
        lic = tests_serveur.licence_relevee(e)
        self.assertEqual(lic["etat"], "absente")
        self.assertIn("discordants", lic["raison"])
        with self.assertRaises(tests_serveur.RepliUnity):
            tests_serveur.executeur_pour(UNITY, e)
        e["capacites"]["unity-licence"]["mot"] = "conteneur"
        self.assertEqual(tests_serveur.executeur_pour(UNITY, e), ("conteneur", "B1"))
        # la sonde rend ce mot (ligne « unity-licence.mot=… »), rangé avec la capacité par enregistrer_sonde
        import serveur_etat

        class SshSonde:
            def executer(self, cible, commande, cle, stdin=None, delai=60):
                self.script = stdin
                return 0, "base=0\nunity-licence=0\nunity-licence.mot=hote\nunity-bac-a-sable=1\n", ""
        s = SshSonde()
        mots = {}
        statuts = serveur_etat.sonder(SERVEUR, ssh=s, mots=mots)
        self.assertEqual((statuts["unity-licence"], mots), ("presente", {"unity-licence": "hote"}))
        self.assertIn('unity-licence.mot=', s.script)
        d = Path(self._t.name) / "etat-sonde"
        serveur_installation.enregistrer_sonde(d, SERVEUR, statuts, mots=mots, charge={"charge_par_coeur": 0.5,
                                               "memoire_libre_ratio": 0.5, "conteneurs_outils": 1})
        lu = serveur_installation.lire_etat(d)[SERVEUR.id]
        self.assertEqual(lu["capacites"]["unity-licence"]["mot"], "hote")
        self.assertIn("charge", lu)
        mots = {}
        s.executer = lambda *a, **k: (0, "unity-licence=0\nunity-licence.mot=hote;id\n", "")
        serveur_etat.sonder(SERVEUR, ssh=s, mots=mots)
        self.assertEqual(mots, {})                                              # un mot hors table est ignoré

    def test_etape_dite_seulement_quand_posee(self):
        # M6 : « étape posée » n'est dit que si elle vient de l'être
        for posee in (True, False):
            self.dits.clear()
            self.etape_posee = posee
            ssh = FauxSsh(sessions=[{"fin_serveur": (81, 100, 110, 0), "code": 81}])
            self.unity(ssh, etat("conteneur", "B1"))
            self.assertEqual(any("posée" in x for x in self.dits), posee, self.dits)
            self.assertTrue(self.dit("licence Unity refusée"))

    def test_sonde_et_charge_gardees(self):
        # M2 : « Vérifier la licence » (bureau) et le rafraîchissement de J14 rangent la charge avec la sonde
        from bureau import serveurs as carte
        appels = []
        with mock.patch.object(carte.Travaux, "_sonder_et_enregistrer", lambda self, s, d: appels.append(s.id) or None), \
                mock.patch.object(tests_serveur, "verifier_licence_unity", lambda d, s, **k: "Sonde relancée."):
            t = carte.Travaux(ssh=object())
            self.assertTrue(t.verifier_licence(SERVEUR, Path(self._t.name)))
            t.attendre(10)
        self.assertEqual(appels, [SERVEUR.id])
        import serveur_etat
        ranges = []
        with mock.patch.object(serveur_etat, "sonder", lambda s, mots=None, **k: {"base": "presente"}), \
                mock.patch.object(serveur_etat, "charge", lambda s, **k: {"charge_par_coeur": 1.0}), \
                mock.patch.object(serveur_installation, "enregistrer_sonde", lambda d, s, e, **k: ranges.append(k)):
            tests_unity_essai._rafraichir(SERVEUR, Path(self._t.name))
        self.assertEqual(ranges[0]["charge"], {"charge_par_coeur": 1.0})


class TestCorrectifsEssai(Essai):
    def test_hote_seulement_si_b1_et_b2_rendent_81(self):
        # I2 : B1 seule (ou B2 seule) qui rend 81 ne prouve rien pour A : indéterminé, rien d'écrit
        for variantes in (("B1",), ("B2",), ("B1", "B3")):
            self.lances.clear()
            r = self.essai(variantes, accord=True, hotes=["license.unity3d.com"])
            self.assertEqual((r["verdict"], r["etat_ecrit"]), ("indetermine", None), variantes)
        self.assertEqual((self.notes, self.poses), ([], []))
        self.assertEqual(self.essai(("B1", "B2"))["verdict"], "hote")

    def test_ecriture_impossible_releve_ecrit_quand_meme(self):
        # M5 : une écriture locale refusée (installation en cours) n'interrompt pas l'essai : le relevé est écrit
        def refuse(*a, **k):
            raise serveur_installation.ErreurInstallation("Une installation est en cours.")
        self.codes = {"B1": 0}
        r = tests_unity_essai.essai(
            SERVEUR.id, str(self.projet), "Jeu.Tests.UnTest", ("B1",), False, (), dossier_etat=self.t, bash=self.bash,
            executer=self.executer, noter_licence=refuse, poser_etape=lambda *a: True, accord_b3=lambda r: False,
            lire_serveurs=lambda d: [SERVEUR], etat_serveurs=lambda d: {SERVEUR.id: etat(None)}, analyse=lambda r, **o: UNITY,
            horloge=lambda: 0.0, dire=lambda *a: None, releves=self.t / "tests-unity-essai.json")
        self.assertEqual((r["verdict"], r["etat_ecrit"]), ("conteneur", "non_ecrit"))
        self.assertTrue((self.t / "tests-unity-essai.json").exists())
        # J14 : l'état local de l'audit d'abord ; refusé, le marqueur n'est PAS posé et rien ne tourne sur l'hôte
        self.scripts.clear(), self.lances.clear()
        r = tests_unity_essai.essai(
            SERVEUR.id, str(self.projet), "Jeu.Tests.UnTest", ("B1", "B2"), True, (), dossier_etat=self.t, bash=self.bash,
            executer=self.executer, lire_serveurs=lambda d: [SERVEUR],
            etat_serveurs=lambda d: {SERVEUR.id: etat("hote")}, analyse=lambda r, **o: UNITY, modifier=refuse,
            rafraichir=lambda s, d: self.rafraichis.append(s.id), empreinte_bac="bac_a_sable=A", nouvel_id=lambda: ID,
            horloge=lambda: 0.0, dire=lambda *a: None, releves=self.t / "tests-unity-essai.json")
        self.assertEqual(r["verdict"], "etat_non_ecrit")
        self.assertFalse([s for s in self.scripts if "unity-bac-a-sable.version" in s])
        self.assertEqual((self.lances, self.rafraichis), ([], []))


if __name__ == "__main__":
    unittest.main()
