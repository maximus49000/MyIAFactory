"""L'environnement du poste : ce qui est déjà là, ce qui reste à installer. Aucune installation, aucun programme lancé."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from moteur import agents, environnement, regles
from orchestrateur import fiches
from tests import test_moteur_parcours as parcours       # le module, pas la classe : ses tests ne se rejouent pas ici
from tests.test_moteur_regles import _lu, usage

CLASSER_MEME, PROPOSITION = parcours.CLASSER_MEME, parcours.PROPOSITION

JDK = {"outil": "JDK 21", "pour": "dev", "executables": ["java", "javac"],
       "installation": "winget install EclipseAdoptium.Temurin.21.JDK (environ 200 Mo, sans droits d'administrateur)"}
GRADLE = {"outil": "Gradle", "pour": "dev", "executables": ["gradle"], "installation": "gradle.org (environ 130 Mo)"}


class Enregistreur:
    """Un faux `which` et un faux lanceur de version qui gardent ce qu'on leur a demandé."""

    def __init__(self, presents=(), versions=None):
        self.presents, self.versions = dict(presents), versions or {}
        self.cherches, self.lances = [], []

    def which(self, nom, path=None):
        self.cherches.append((nom, path))
        return self.presents.get(nom) if path is None else None

    def executer(self, argv, delai_s):
        self.lances.append(list(argv))
        return self.versions.get(argv[1], (1, ""))


class Verifier(unittest.TestCase):
    def test_outil_present_en_place_avec_version(self):
        e = Enregistreur({"java": "C:/jdk/bin/java.exe", "javac": "C:/jdk/bin/javac.exe"},
                         {"--version": (2, "Unrecognized option"), "-version": (0, "openjdk version \"21.0.4\"\nRuntime")})
        (r,) = environnement.verifier([JDK], which=e.which, executer=e.executer, env={})
        self.assertEqual((r["etat"], r["chemin"], r["version"]), ("en_place", "C:/jdk/bin/java.exe", "openjdk version \"21.0.4\""))
        self.assertEqual(r["outil"], "JDK 21")
        self.assertEqual(e.lances, [["C:/jdk/bin/java.exe", "--version"], ["C:/jdk/bin/java.exe", "-version"]])
        # une version illisible ne fait pas perdre l'outil
        e = Enregistreur({"java": "C:/jdk/bin/java.exe", "javac": "C:/jdk/bin/javac.exe"})
        (r,) = environnement.verifier([JDK], which=e.which, executer=e.executer, env={})
        self.assertEqual((r["etat"], r["chemin"]), ("en_place", "C:/jdk/bin/java.exe"))
        self.assertNotIn("version", r)
        self.assertEqual([a[1] for a in e.lances], ["--version", "-version", "version"])    # la liste fixe, rien d'autre

    def test_outil_absent_a_installer(self):
        e = Enregistreur({"java": "C:/jdk/bin/java.exe"})          # javac manque : le JDK n'est pas complet
        a, b = environnement.verifier([JDK, GRADLE], which=e.which, executer=e.executer, env={})
        self.assertEqual((a["etat"], b["etat"]), ("a_installer", "a_installer"))
        self.assertNotIn("chemin", a)
        self.assertEqual(e.lances, [])                                # rien n'est lancé pour ce qui n'est pas là
        self.assertEqual(a["installation"], JDK["installation"])      # le reste de la proposition est gardé
        self.assertEqual(environnement.a_installer([a, b]), [a, b])

    def test_android_home_trouve(self):
        with tempfile.TemporaryDirectory() as t:
            racine = Path(t)
            for sous, nom in (("platform-tools", "adb.exe"), ("cmdline-tools/latest/bin", "sdkmanager.exe"),
                              ("build-tools/34.0.0", "apksigner.exe")):
                (racine / sous).mkdir(parents=True)
                f = racine / sous / nom
                f.write_bytes(b"x")
                f.chmod(0o755)
            (racine / "jdk" / "bin").mkdir(parents=True)
            java = racine / "jdk" / "bin" / "java.exe"
            java.write_bytes(b"x")
            java.chmod(0o755)
            seulement_les_emplacements = lambda nom, path=None: shutil.which(nom, path=path) if path else None
            outils = [{"outil": "SDK Android", "pour": "dev", "executables": ["adb", "sdkmanager", "apksigner"],
                       "installation": "x"}, {"outil": "JDK", "pour": "dev", "executables": ["java"], "installation": "y"}]
            vus = []
            r = environnement.verifier(outils, which=seulement_les_emplacements,
                                       executer=lambda argv, d: vus.append(argv) or (0, "ok 1.0"),
                                       env={"ANDROID_HOME": str(racine), "JAVA_HOME": str(racine / "jdk")})
            self.assertEqual([x["etat"] for x in r], ["en_place", "en_place"])
            self.assertIn("platform-tools", r[0]["chemin"])
            self.assertIn("jdk", r[1]["chemin"])
            # ANDROID_SDK_ROOT aussi ; sans aucune variable, le même poste n'a rien
            r = environnement.verifier(outils[:1], which=seulement_les_emplacements, executer=lambda a, d: (0, "v"),
                                       env={"ANDROID_SDK_ROOT": str(racine)})
            self.assertEqual(r[0]["etat"], "en_place")
            r = environnement.verifier(outils[:1], which=seulement_les_emplacements, executer=lambda a, d: (0, "v"), env={})
            self.assertEqual(r[0]["etat"], "a_installer")

    def test_jamais_de_commande_de_l_ia(self):
        e = Enregistreur({"java": "C:/jdk/bin/java.exe"}, {"--version": (0, "21")})
        mauvais = ["rm -rf", "java;calc", "a&b", "../x", "--version", "java x", "$(calc)", "a|b", "", "x" * 80,
                   "C:/Windows/System32/cmd.exe", "a\nb"]
        outils = [{"outil": f"Piège {k}", "pour": "dev", "executables": [nom], "installation": "x"}
                  for k, nom in enumerate(mauvais)]
        outils.append({"outil": "Mélange", "pour": "dev", "executables": ["java", "rm -rf"], "installation": "x"})
        sortie = environnement.verifier(outils, which=e.which, executer=e.executer, env={})
        self.assertEqual({x["etat"] for x in sortie}, {"a_installer"})
        self.assertTrue(all(x["refuses"] for x in sortie))
        self.assertEqual(sortie[-1]["refuses"], ["rm -rf"])              # même mêlé à un nom valide : l'outil n'est pas en place
        cherches = {n for n, _ in e.cherches}
        self.assertEqual(cherches, {"java"})                              # un nom refusé n'est même pas cherché
        for argv in e.lances:                                             # et seul un programme trouvé est lancé, avec une option fixe
            self.assertEqual(argv[0], "C:/jdk/bin/java.exe")
            self.assertIn(argv[1], environnement.OPTIONS_DE_VERSION)

    def test_un_executable_commun_n_est_cherche_qu_une_fois(self):
        e = Enregistreur({"java": "C:/jdk/bin/java.exe", "javac": "C:/jdk/bin/javac.exe"}, {"--version": (0, "21")})
        autre = {"outil": "Kotlin", "pour": "dev", "executables": ["java"], "installation": "z"}
        r = environnement.verifier([JDK, autre], which=e.which, executer=e.executer, env={})
        self.assertEqual([x["etat"] for x in r], ["en_place", "en_place"])
        self.assertEqual(sorted(n for n, _ in e.cherches), ["java", "javac"])
        self.assertEqual(len(e.lances), 1)

    def test_version_lue_par_un_vrai_programme_inoffensif(self):
        import sys
        code, sortie = environnement.executer_version([sys.executable, "--version"], 10)
        self.assertEqual(code, 0)
        self.assertIn("Python", sortie)


POSTE = {**PROPOSITION, "environnement": [JDK], "outils_installation": ["Bash(winget:*)", "PowerShell(Invoke-WebRequest:*)"]}


class Poste(parcours.AvecParcours):
    """Le parcours d'une nouvelle fonctionnalité, côté environnement du poste (conception, section 5 bis)."""

    def setUp(self):
        super().setUp()
        self.verifie = []
        self.etat_du_poste = "a_installer"

        def verifier(outils):
            self.verifie.append([o["outil"] for o in outils])
            return [dict(o, etat=self.etat_du_poste, **({"chemin": "C:/jdk/bin/java.exe", "version": "openjdk 21"}
                                                         if self.etat_du_poste == "en_place" else {}))
                    for o in outils]

        self.projet.verifier_environnement = verifier

    def vers_le_poste(self, etat="a_installer"):
        self.etat_du_poste = etat
        return self.vers_l_organisation(POSTE, CLASSER_MEME)[1]

    def rendre(self, tache, agent, rapport):
        e = agents.Execution(tache, agent, rapport=_lu(rapport), usages=[usage()])
        return regles.traiter_retour(self.projet, e, self.etat)

    def test_la_proposition_porte_l_environnement_verifie(self):
        decision = self.vers_le_poste()
        o = decision["organisation"]
        self.assertEqual([(x["outil"], x["etat"]) for x in o["environnement"]], [("JDK 21", "a_installer")])
        self.assertEqual(o["outils_installation"], ["Bash(winget:*)", "PowerShell(Invoke-WebRequest:*)"])
        self.assertIn("À installer : JDK 21", decision["texte"])
        installateur = next(a for a in o["agents"] if a["role"] == "environnement")      # un agent pour installer
        self.assertEqual((installateur["cle"], installateur["lieu"]), ("env-1", "local"))
        self.assertIn("environnement", o["briefs"])
        self.assertEqual(self.ok("releve")["decisions_projet"][0]["organisation"]["environnement"][0]["etat"],
                         "a_installer")

    def test_tout_en_place_pas_de_tache_d_installation(self):
        decision = self.vers_le_poste("en_place")
        self.assertIn("Déjà en place sur le poste : JDK 21", decision["texte"])
        self.assertFalse(any(a["role"] == "environnement" for a in decision["organisation"]["agents"]))
        _, actions = self.accepter(decision)
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])      # le cadrage démarre tout de suite
        self.assertEqual(self.taches(etape="environnement"), [])
        self.assertFalse((self.dossier / "fiches" / "env-1.md").exists())

    def test_acceptation_cree_la_tache_d_environnement_avant_le_cadrage(self):
        decision = self.vers_le_poste()
        d, actions = self.accepter(decision)
        (t,) = self.taches(etape="environnement")
        self.assertEqual((t["titre"], t["role"], t["colonne"], t["agent"], t["fonctionnalite"]),
                         ("Mise en place de l'environnement", "environnement", "f1-dev", "env-1", "f1"))
        self.assertTrue(t["active"])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "env-1")])         # l'installateur d'abord
        self.assertEqual(self.taches(etape="cadrage"), [])                              # le cadrage vient après
        self.assertIn("JDK 21", " ".join(j["texte"] for j in self.ok("detail", entree={"tache": t["id"]})["journal"]))
        self.assertIn("vérifie", actions[0][3])
        fiche = fiches.lire_fiche(self.dossier / "fiches" / "env-1.md")
        outils = fiches.outils(fiche)
        self.assertIn("Bash(winget:*)", outils)
        self.assertIn("PowerShell(Invoke-WebRequest:*)", outils)
        self.assertEqual(outils[:3], ["Read", "Write", "Edit"])         # ses outils habituels restent
        autre = fiches.lire_fiche(self.dossier / "fiches" / "lea.md")
        self.assertNotIn("Bash(winget:*)", fiches.outils(autre))        # et personne d'autre n'a ces règles
        # l'installateur rend compte, tout est en place : le poste est noté, puis le cadrage démarre
        self.etat_du_poste = "en_place"
        suite = self.rendre(t["id"], "env-1", {"statut": "fait", "message": {"texte": "Java est installé."}})
        self.assertEqual([(a[0], a[1]) for a in suite], [("agent", "metier-1")])
        self.assertEqual(self.taches(etape="cadrage")[0]["agent"], "metier-1")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.lire_factory()["environnement"][0]["etat"], "en_place")

    def test_installation_ratee_devient_decision(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (t,) = self.taches(etape="environnement")
        suite = self.rendre(t["id"], "env-1", {"statut": "fait", "message": {"texte": "Droits insuffisants."}})
        self.assertEqual(suite, [])                                                    # rien ne démarre en silence
        (q,) = self.decisions("environnement")
        self.assertEqual(q["portee"], "f1")
        self.assertIn("JDK 21", q["texte"])
        self.assertIn("winget install", q["texte"])                                    # comment l'installer à la main
        self.assertIn("C'est fait", q["texte"])
        self.assertEqual([x["outil"] for x in q["environnement"]], ["JDK 21"])
        self.assertEqual(self.taches(etape="cadrage"), [])
        self.assertEqual(regles.avancer(self.projet, self.etat), [])                   # le cadrage attend la réponse
        r = self.ok("releve")
        self.assertEqual(releve_valider(r), [])
        # un message libre n'ouvre pas le cadrage non plus
        _, actions = self.traiter(type="message", fonctionnalite="f1", texte="Alors ?")
        self.assertEqual(actions, [])

    def test_agent_d_installation_en_echec_devient_decision(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (t,) = self.taches(etape="environnement")
        self.rendre(t["id"], "env-1", {"statut": "echec", "message": {"texte": "Téléchargement refusé."}})
        (q,) = self.decisions("environnement")
        self.assertIn("L'installation a échoué", q["texte"])
        self.assertEqual(self.taches(etape="cadrage"), [])

    def test_c_est_fait_revérifie(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (t,) = self.taches(etape="environnement")
        self.rendre(t["id"], "env-1", {"statut": "fait", "message": {"texte": "Non."}})
        (q,) = self.decisions("environnement")
        # toujours rien : la décision reste, et le dit
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertEqual(actions, [])
        self.assertIn("Il manque encore", self.statut(d["id"])["reponse"])
        self.assertEqual(len(self.decisions("environnement")), 1)
        # installé à la main : « C'est fait » revérifie, lève la décision et le cadrage démarre
        self.etat_du_poste = "en_place"
        n = len(self.verifie)
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertGreater(len(self.verifie), n)
        self.assertEqual(self.decisions("environnement"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])
        self.assertEqual(self.lire_factory()["environnement"][0]["etat"], "en_place")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_continuer_sans_laisse_avancer(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (t,) = self.taches(etape="environnement")
        self.rendre(t["id"], "env-1", {"statut": "fait", "message": {"texte": "Non."}})
        (q,) = self.decisions("environnement")
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="continuer")
        self.assertEqual(self.decisions("environnement"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])
        self.assertEqual(self.lire_factory()["environnement"][0]["etat"], "a_installer")     # noté tel quel
        self.assertTrue(any("sans ces outils" in m["texte"] for m in self.fonc()["discussion"]))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        # une autre réponse est refusée
        d2, _ = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertIn("n'existe plus", self.statut(d2["id"])["reponse"])

    def test_environnement_note_dans_les_reglages_et_au_depart(self):
        decision = self.vers_le_poste("en_place")
        _, actions = self.accepter(decision)
        (outil,) = self.lire_factory()["environnement"]
        self.assertEqual((outil["outil"], outil["etat"], outil["chemin"], outil["version"]),
                         ("JDK 21", "en_place", "C:/jdk/bin/java.exe", "openjdk 21"))
        depart = regles.lancer(self.projet, "depart", {"agent": "metier-1", "tache": self.taches(etape="cadrage")[0]["id"]})
        self.assertIn("## Outils du poste", depart["message"])
        self.assertIn("JDK 21 : C:/jdk/bin/java.exe (openjdk 21)", depart["message"])
        # une demande suivante qui a besoin des mêmes outils les trouve « déjà en place » : le projet les connaît
        self.assertEqual(self.ok("etat")["decisions"], [])


def releve_valider(r):
    from bureau import releve
    return releve.valider(r)


if __name__ == "__main__":
    unittest.main()
