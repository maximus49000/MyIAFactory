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
       "installation": "winget install EclipseAdoptium.Temurin.21.JDK (environ 200 Mo, sans droits d'administrateur)",
       "telechargement": "https://adoptium.net/temurin/releases/", "autonome": True,
       "objectif": "Compiler le jeu et signer l'apk à l'étape « dev ».",
       "etapes": ["Ouvrir la page.", "Télécharger le .zip du JDK 21.", "L'extraire dans le profil.", "Lancer java -version."]}
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

    def test_version_trop_ancienne_a_installer(self):
        jdk17 = dict(JDK, outil="JDK 17")
        presents = {"java": "C:/jre/bin/java.exe", "javac": "C:/jre/bin/javac.exe"}
        # java 8 écrit sur la sortie d'erreur « 1.8.0_351 » : c'est la version 8, trop ancienne pour un JDK 17
        e = Enregistreur(presents, {"--version": (1, "Unrecognized option: --version"),
                                    "-version": (0, "java version \"1.8.0_351\"\nJava(TM) SE Runtime Environment")})
        (r,) = environnement.verifier([jdk17], which=e.which, executer=e.executer, env={})
        self.assertEqual(r["etat"], "a_installer")
        self.assertIn("1.8.0_351", r["raison"])
        self.assertIn("17", r["raison"])
        self.assertEqual(environnement.a_installer([r]), [r])
        # 17.0.9 convient, 21 aussi ; la version minimale peut aussi venir d'un champ explicite
        for sortie, attendu in (("openjdk version \"17.0.9\" 2023-10-17", "en_place"), ("openjdk version \"21.0.4\"", "en_place"),
                                ("openjdk version \"11.0.2\"", "a_installer")):
            e = Enregistreur(presents, {"--version": (1, "x"), "-version": (0, sortie)})
            (r,) = environnement.verifier([jdk17], which=e.which, executer=e.executer, env={})
            self.assertEqual(r["etat"], attendu, sortie)
        e = Enregistreur(presents, {"-version": (0, "java version \"1.8.0_351\"")})
        (r,) = environnement.verifier([dict(JDK, version_min="11")], which=e.which, executer=e.executer, env={})
        self.assertEqual(r["etat"], "a_installer")

    def test_version_recente_installee_a_cote_d_une_ancienne(self):
        """Un JDK récent installé hors du PATH, alors qu'un vieux Java passe avant : l'outil est en place, avec le bon chemin."""
        ancien, recent = "C:/Program Files/OpenJDK/jdk8/bin/java.exe", "C:/Program Files/Eclipse Adoptium/jdk-25/bin/java.exe"
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "ProgramFiles"
            (base / "Eclipse Adoptium" / "jdk-25" / "bin").mkdir(parents=True)

            def which(nom, path=None):
                if path is None:
                    return {"java": ancien, "javac": ancien.replace("java.exe", "javac.exe")}.get(nom)
                return recent if nom == "java" and "Eclipse Adoptium" in path else None

            def executer(argv, delai_s):
                return (0, 'openjdk version "25.0.5"') if argv[0] == recent else (0, 'java version "1.8.0_302"')

            (r,) = environnement.verifier([dict(JDK, outil="JDK 17")], which=which, executer=executer,
                                          env={"ProgramFiles": str(base)})
        self.assertEqual((r["etat"], r["chemin"]), ("en_place", recent))
        self.assertIn("25.0.5", r["version"])
        self.assertIn("hors du PATH", r["raison"])
        # sans autre exemplaire, il reste à installer
        (r,) = environnement.verifier([dict(JDK, outil="JDK 17")], which=which, executer=executer, env={})
        self.assertEqual(r["etat"], "a_installer")

    def test_version_suffisante(self):
        suffisante = environnement.version_suffisante
        self.assertFalse(suffisante('java version "1.8.0_381"', "17"))        # Java 1.8 est la version 8
        self.assertTrue(suffisante('java version "1.8.0_381"', "8"))
        self.assertTrue(suffisante('openjdk version "21.0.2"', "17"))
        self.assertTrue(suffisante("17", "17"))
        self.assertFalse(suffisante("17", "17.0.1"))
        self.assertTrue(suffisante("8.7", "8.5"))
        self.assertFalse(suffisante("8.4.2", "8.5"))
        self.assertTrue(suffisante("Gradle 8.5", "8"))
        for lue, minimale in ((None, "17"), ("17", None), ("sans nombre", "17"), ("17", "aucune"), ("", "")):
            self.assertIsNone(suffisante(lue, minimale), (lue, minimale))

    def test_java_trop_ancien_a_installer(self):
        """La version minimale vient du champ `version_min` des jugements, pas du nom : « JDK » seul suffit."""
        presents = {"java": "C:/jre/bin/java.exe", "javac": "C:/jre/bin/javac.exe"}
        jdk = dict(JDK, outil="JDK", version_min="17")
        for sortie, attendu in (('java version "1.8.0_381"', "a_installer"), ('openjdk version "11.0.2"', "a_installer"),
                                ('openjdk version "17.0.9"', "en_place"), ('openjdk version "21.0.2"', "en_place")):
            e = Enregistreur(presents, {"-version": (0, sortie)})
            (r,) = environnement.verifier([jdk], which=e.which, executer=e.executer, env={})
            self.assertEqual(r["etat"], attendu, sortie)
            self.assertEqual(r["version_min"], "17")                  # le champ est gardé dans l'outil
        e = Enregistreur(presents, {"-version": (0, 'java version "1.8.0_381"')})
        (r,) = environnement.verifier([jdk], which=e.which, executer=e.executer, env={})
        self.assertIn("1.8.0_381", r["raison"])

    def test_agent_d_installation_pur(self):
        flux = [{"id": "valid", "nom": "V", "validation": True}, {"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}]
        services = [{"id": "facturation", "nom": "Facturation"}, {"id": "dev", "nom": "Dev"}]
        agent, brief = environnement.agent_d_installation([{"cle": "env-1", "role": "dev"}], [], flux, services)
        self.assertEqual((agent["cle"], agent["role"], agent["service"], agent["modele"], agent["lieu"]),
                         ("env-2", "environnement", "dev", "Sonnet", "local"))   # clé libre, service de la première étape d'agent
        self.assertNotIn("outils", agent)
        self.assertIn("Mise en place de l'environnement", brief)
        # avec des règles : les outils habituels, puis elles
        agent, _ = environnement.agent_d_installation([], [], flux, services, ["Bash(winget:*)", "Bash(winget:*)"])
        self.assertEqual(agent["cle"], "env-1")
        self.assertEqual(fiches.outils(agent)[-1], "Bash(winget:*)")
        self.assertEqual(fiches.outils(agent).count("Bash(winget:*)"), 1)
        self.assertEqual(fiches.outils(agent)[:3], ["Read", "Write", "Edit"])
        # sans flux : le premier service ; sans service : rien
        self.assertEqual(environnement.agent_d_installation([], [], [], services)[0]["service"], "facturation")
        self.assertEqual(environnement.agent_d_installation([], [], [], []), (None, None))
        # un agent du rôle existe déjà (en place ou en cours de recrutement) : aucun autre
        self.assertEqual(environnement.agent_d_installation([{"cle": "x", "role": "environnement"}], [], flux, services),
                         (None, None))
        self.assertEqual(environnement.agent_d_installation([], [{"cle": "x", "role": "environnement"}], flux, services),
                         (None, None))

    def test_version_illisible_n_est_pas_dite_verifiee(self):
        jdk17 = dict(JDK, outil="JDK 17")
        presents = {"java": "C:/jdk/bin/java.exe", "javac": "C:/jdk/bin/javac.exe"}
        for versions in ({}, {"--version": (0, "bizarre sans chiffre")}):
            e = Enregistreur(presents, versions)
            (r,) = environnement.verifier([jdk17], which=e.which, executer=e.executer, env={})
            self.assertEqual(r["etat"], "en_place")
            self.assertIn("non vérifiée", r["raison"])
        # sans version minimale, rien à dire
        e = Enregistreur(presents, {})
        for nom in ("JDK", "Android SDK 34 complet"):
            (r,) = environnement.verifier([dict(JDK, outil=nom)], which=e.which, executer=e.executer, env={})
            self.assertEqual(r["etat"], "en_place")
            self.assertNotIn("raison", r)

    def test_outil_absent_a_installer(self):
        e = Enregistreur({"java": "C:/jdk/bin/java.exe"})          # javac manque : le JDK n'est pas complet
        a, b = environnement.verifier([JDK, GRADLE], which=e.which, executer=e.executer, env={})
        self.assertEqual((a["etat"], b["etat"]), ("a_installer", "a_installer"))
        self.assertNotIn("chemin", a)
        self.assertEqual(e.lances, [])                                # rien n'est lancé pour ce qui n'est pas là
        self.assertEqual(a["installation"], JDK["installation"])      # le reste de la proposition est gardé
        self.assertEqual(environnement.a_installer([a, b]), [a, b])

    def test_aide_a_l_installation_valeurs_par_defaut_et_gardees(self):
        e = Enregistreur()
        ancien, complet = environnement.verifier(
            [{k: v for k, v in JDK.items() if k not in ("telechargement", "etapes", "autonome", "objectif")}, dict(GRADLE, telechargement="https://gradle.org/install/", etapes=["Télécharger.", "Extraire."],
                       autonome=True)], which=e.which, executer=e.executer, env={})
        self.assertEqual((ancien["telechargement"], ancien["etapes"], ancien["autonome"], ancien["objectif"]),
                         (None, [], False, None))
        self.assertEqual((complet["telechargement"], complet["etapes"], complet["autonome"]),
                         ("https://gradle.org/install/", ["Télécharger.", "Extraire."], True))
        self.assertEqual(environnement.autonomes_a_installer([ancien, complet]), [complet])
        faux = environnement.avec_aide({"outil": "X", "telechargement": "http://x", "etapes": "a", "autonome": "oui"})
        self.assertEqual((faux["telechargement"], faux["etapes"], faux["autonome"]), (None, [], False))

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

    def test_path_relu_dans_le_registre_apres_le_demarrage(self):
        """Un logiciel installé après le démarrage du moteur n'est pas dans le PATH du processus : le PATH à jour est relu
        dans le registre (système puis utilisateur, variables développées). Registre et fichiers simulés."""
        with tempfile.TemporaryDirectory() as t:
            racine = Path(t)
            for sous in ("Outils/jdk/bin", "profil/bin", "ailleurs"):
                (racine / sous).mkdir(parents=True)
            for sous, nom in (("Outils/jdk/bin", "java.exe"), ("Outils/jdk/bin", "javac.exe"), ("profil/bin", "gradle.exe")):
                f = racine / sous / nom
                f.write_bytes(b"x")
                f.chmod(0o755)
            lus = []
            valeurs = {("HKEY_LOCAL_MACHINE", "Path"): f"{racine / 'ailleurs'};%RACINE%\\Outils\\jdk\\bin;",
                       ("HKEY_CURRENT_USER", "Path"): '"%PROFIL%\\bin"'}

            def registre(r, sous_cle, nom):
                lus.append((r, sous_cle, nom))
                return valeurs.get((r, nom))

            seulement_les_dossiers = lambda nom, path=None: shutil.which(nom, path=path) if path else None
            env = {"RACINE": str(racine), "PROFIL": str(racine / "profil")}
            outils = [JDK, GRADLE]
            # sans registre (un processus qui a démarré avant l'installation) : rien n'est trouvé
            r = environnement.verifier(outils, which=seulement_les_dossiers, executer=lambda a, d: (0, "v 21"), env=env)
            self.assertEqual([x["etat"] for x in r], ["a_installer", "a_installer"])
            self.assertEqual(r[0]["introuvables"], ["java", "javac"])
            # avec le registre à jour : trouvé, chemins développés, sans aucune commande lancée pour le lire
            r = environnement.verifier(outils, which=seulement_les_dossiers, executer=lambda a, d: (0, "v 21"), env=env,
                                       lire=registre)
            self.assertEqual([x["etat"] for x in r], ["en_place", "en_place"])
            self.assertIn("jdk", r[0]["chemin"])
            self.assertIn("profil", r[1]["chemin"])
            self.assertTrue(any(c[0] == "HKEY_LOCAL_MACHINE" and c[1].endswith("Session Manager\\Environment") for c in lus))
            self.assertTrue(any(c[:2] == ("HKEY_CURRENT_USER", "Environment") for c in lus))

    def test_variables_du_registre_priment_sur_celles_du_processus(self):
        with tempfile.TemporaryDirectory() as t:
            neuf, vieux = Path(t) / "neuf", Path(t) / "vieux"
            for d in (neuf / "bin", vieux / "bin"):
                d.mkdir(parents=True)
            (neuf / "bin" / "java.exe").write_bytes(b"x")
            (neuf / "bin" / "java.exe").chmod(0o755)
            registre = lambda r, s, nom: str(neuf) if (r, nom) == ("HKEY_CURRENT_USER", "JAVA_HOME") else None
            trouve = environnement.trouver("java", which=lambda n, path=None: shutil.which(n, path=path) if path else None,
                                           env={"JAVA_HOME": str(vieux)}, lire=registre)
            self.assertEqual(trouve.lower(), str(neuf / "bin" / "java.exe").lower())

    def test_dossiers_d_installation_de_winget_et_des_jdk(self):
        with tempfile.TemporaryDirectory() as t:
            racine = Path(t)
            attendus = ["local/Microsoft/WinGet/Links", "local/Microsoft/WinGet/Packages/Gradle.Gradle_x/gradle-8.5/bin",
                        "pf/Eclipse Adoptium/jdk-21.0.4.7-hotspot/bin", "pf/Microsoft/jdk-17.0.9.8-hotspot/bin",
                        "pf/Java/jdk-11/bin"]
            for a in attendus + ["pf/Autre/bin"]:
                (racine / a).mkdir(parents=True)
            env = {"LOCALAPPDATA": str(racine / "local"), "ProgramFiles": str(racine / "pf")}
            vus = {p.relative_to(racine).as_posix() for p in environnement.dossiers_d_installation(env)}
            for a in attendus:
                self.assertIn(a, vus)
            self.assertNotIn("pf/Autre/bin", vus)
            self.assertEqual(list(environnement.dossiers_d_installation({})), [])       # rien sans ces variables
            # et un programme y est trouvé
            f = racine / attendus[2] / "java.exe"
            f.write_bytes(b"x")
            f.chmod(0o755)
            trouve = environnement.trouver("java", which=lambda n, path=None: shutil.which(n, path=path) if path else None,
                                           env=env)
            self.assertEqual(trouve.lower(), str(f).lower())

    def test_executable_au_nom_versionne_est_trouve_le_plus_recent_d_abord(self):
        sans_path = lambda n, path=None: shutil.which(n, path=path) if path else None
        with tempfile.TemporaryDirectory() as t:
            racine = Path(t)
            paquets = racine / "local/Microsoft/WinGet/Packages"
            vieux = paquets / "GodotEngine.GodotEngine_x" / "Godot_v4.2.2-stable_win64.exe"
            recent = paquets / "GodotEngine.GodotEngine_x" / "Godot_v4.3-stable_win64.exe"
            console = paquets / "GodotEngine.GodotEngine_x" / "Godot_v4.3-stable_win64_console.exe"
            for f in (vieux, recent, console):
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b"x")
                f.chmod(0o755)
            env = {"LOCALAPPDATA": str(racine / "local")}
            self.assertEqual(environnement.trouver("godot", which=sans_path, env=env).lower(), str(recent).lower())
            self.assertEqual([Path(c).name for c in environnement.candidats("godot", which=sans_path, env=env)],
                             [recent.name, console.name, vieux.name])
            self.assertIsNone(environnement.trouver("godot", which=sans_path, env={}))
            self.assertIsNone(environnement.trouver("gradle", which=sans_path, env=env))      # pas d'autre nom versionné
            # le nom versionné d'un dossier du PATH, et la version lue comme pour les autres
            e = Enregistreur({}, {"--version": (0, "4.3.stable.official")})
            (o,) = environnement.verifier([{"outil": "Godot", "executables": ["godot"]}], which=sans_path,
                                          executer=e.executer, env={**env, "PATH": str(recent.parent)})
            self.assertEqual((o["etat"], o["version"]), ("en_place", "4.3.stable.official"))

    def test_constat_dit_ce_qui_a_ete_cherche(self):
        presents = {"java": "C:/jre/bin/java.exe", "javac": "C:/jre/bin/javac.exe"}
        e = Enregistreur(presents, {"-version": (0, 'java version "1.8.0_351"')})
        (vieux,) = environnement.verifier([dict(JDK, outil="JDK 17")], which=e.which, executer=e.executer, env={})
        c = environnement.constat(vieux)
        self.assertEqual((c["trouve"], c["cherche"], c["version_demandee"]), (False, ["java", "javac"], "17"))
        self.assertIn("1.8.0_351", c["version_trouvee"])
        self.assertIn("version trouvée", environnement.texte_du_constat("JDK 17", c))
        (absent,) = environnement.verifier([JDK], which=Enregistreur({"java": "x"}).which, env={})
        c = environnement.constat(absent)
        self.assertEqual(c["introuvables"], ["javac"])
        self.assertEqual(environnement.texte_du_constat("JDK 21", c),
                         "JDK 21 : non trouvé (cherché : java, javac ; introuvable : javac ; version 21 minimum demandée)")
        (bon,) = environnement.verifier([JDK], which=Enregistreur(presents).which, executer=lambda a, d: (0, "21"), env={})
        self.assertEqual(environnement.texte_du_constat("JDK 21", environnement.constat(bon)), "JDK 21 : trouvé")

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

    def test_l_installateur_rejoint_le_service_de_la_premiere_etape(self):
        """Pas le premier service du projet (souvent la facturation, dans un projet créé au bureau) : celui qui ouvre le
        workflow."""
        o = self.vers_le_poste()["organisation"]
        self.assertEqual([s["id"] for s in o["services"]][0], "metier")
        self.assertEqual(next(a for a in o["agents"] if a["role"] == "environnement")["service"], "dev")

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
        d, actions = self.accepter(decision, installer=["JDK 21"])
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

    def test_sans_choix_rien_ne_s_installe_d_elle_meme(self):
        decision = self.vers_le_poste()
        _, actions = self.accepter(decision)              # « Accepter » sans choisir d'installer en autonomie
        self.assertEqual((actions, self.taches(etape="environnement"), self.taches(etape="cadrage")), ([], [], []))
        (q,) = self.decisions("environnement")
        self.assertEqual((q["portee"], [x["outil"] for x in q["environnement"]]), ("f1", ["JDK 21"]))
        self.assertTrue(q["environnement"][0]["autonome"])
        self.assertEqual(self.ok("releve")["fonctionnalites"][0]["decisions"][0]["environnement"][0]["etapes"][0],
                         "Ouvrir la page.")
        self.assertEqual(releve_valider(self.ok("releve")), [])

    def test_un_choix_hors_liste_ou_non_autonome_n_installe_rien(self):
        decision = self.vers_le_poste()
        self.accepter(decision, installer=["Gradle"])      # pas dans la proposition
        self.assertEqual(self.taches(etape="environnement"), [])
        self.assertEqual(len(self.decisions("environnement")), 1)

    def test_bouton_installer_en_autonomie_une_seule_tache_par_outil(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (q,) = self.decisions("environnement")
        d, actions = self.traiter(type="installer_outil", decision=q["id"], fonctionnalite="f1", outil="JDK 21")
        (t,) = self.taches(etape="environnement")
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "env-1")])
        self.assertEqual((t["fonctionnalite"], t["agent"], t["active"]), ("f1", "env-1", True))
        self.assertIn("Objectif : Compiler le jeu", " ".join(j["texte"] for j in self.ok("detail", entree={"tache": t["id"]})["journal"]))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(len(self.decisions("environnement")), 1)             # la décision reste jusqu'à la revérification
        r = self.ok("releve")["fonctionnalites"][0]["decisions"][0]["environnement"][0]
        self.assertTrue(r["en_cours"])                                         # le bouton disparaît
        d2, actions2 = self.traiter(type="installer_outil", decision=q["id"], fonctionnalite="f1", outil="JDK 21")
        self.assertIn("déjà en cours", self.statut(d2["id"])["reponse"])
        self.assertEqual(len(self.taches(etape="environnement")), 1)
        # fin de la tâche : tout est en place, la décision est levée et le cadrage démarre
        self.etat_du_poste = "en_place"
        suite = self.rendre(t["id"], "env-1", {"statut": "fait", "message": {"texte": "Installé."}})
        self.assertEqual(self.decisions("environnement"), [])
        self.assertEqual([(a[0], a[1]) for a in suite], [("agent", "metier-1")])

    def test_bouton_recrute_l_installateur_s_il_manque(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (q,) = self.decisions("environnement")
        (self.dossier / "fiches" / "env-1.md").unlink()
        (self.dossier / "fiches" / "briefs" / "environnement.md").unlink()
        self.traiter(type="installer_outil", decision=q["id"], fonctionnalite="f1", outil="JDK 21")
        fiche = next(a for a in fiches.lire_toutes(self.dossier / "fiches") if a["role"] == "environnement")
        self.assertIn("Bash(winget:*)", fiches.outils(fiche))
        self.assertTrue((self.dossier / "fiches" / "briefs" / "environnement.md").exists())
        self.assertEqual(len(self.taches(etape="environnement")), 1)

    def test_bouton_refuse_un_outil_non_autonome_ou_deja_en_place(self):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (q,) = self.decisions("environnement")
        d, _ = self.traiter(type="installer_outil", decision=q["id"], fonctionnalite="f1", outil="Inconnu")
        self.assertIn("pas dans cette liste", self.statut(d["id"])["reponse"])
        self.etat_du_poste = "en_place"          # installé à la main entre-temps : rien à lancer
        d, actions = self.traiter(type="installer_outil", decision=q["id"], fonctionnalite="f1", outil="JDK 21")
        self.assertIn("déjà en place", self.statut(d["id"])["reponse"])
        self.assertEqual(self.taches(etape="environnement"), [])
        self.assertEqual(self.decisions("environnement"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])

    def test_outil_non_autonome_pas_d_agent_ni_de_bouton(self):
        manuel = dict(JDK, autonome=False)
        decision = self.vers_le_poste_avec(manuel)
        self.assertFalse(any(a["role"] == "environnement" for a in decision["organisation"]["agents"]))
        self.accepter(decision, installer=["JDK 21"])                      # même coché : refusé, il n'est pas autonome
        self.assertEqual(self.taches(etape="environnement"), [])
        (q,) = self.decisions("environnement")
        d, _ = self.traiter(type="installer_outil", decision=q["id"], fonctionnalite="f1", outil="JDK 21")
        self.assertIn("ne s'installe pas en autonomie", self.statut(d["id"])["reponse"])

    def vers_le_poste_avec(self, outil):
        self.etat_du_poste = "a_installer"
        return self.vers_l_organisation({**POSTE, "environnement": [outil]}, CLASSER_MEME)[1]

    def test_installation_ratee_devient_decision(self):
        decision = self.vers_le_poste()
        self.accepter(decision, installer=["JDK 21"])
        (t,) = self.taches(etape="environnement")
        suite = self.rendre(t["id"], "env-1", {"statut": "fait", "message": {"texte": "Droits insuffisants."}})
        self.assertEqual(suite, [])                                                    # rien ne démarre en silence
        (q,) = self.decisions("environnement")
        self.assertEqual(q["portee"], "f1")
        self.assertIn("JDK 21", q["texte"])
        self.assertNotIn("winget install", q["texte"])                                 # le détail est par outil
        self.assertEqual(q["environnement"][0]["etapes"][0], "Ouvrir la page.")
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
        self.accepter(decision, installer=["JDK 21"])
        (t,) = self.taches(etape="environnement")
        self.rendre(t["id"], "env-1", {"statut": "echec", "message": {"texte": "Téléchargement refusé."}})
        (q,) = self.decisions("environnement")
        self.assertIn("L'installation a échoué", q["texte"])
        self.assertEqual(self.taches(etape="cadrage"), [])

    def test_c_est_fait_revérifie(self):
        decision = self.vers_le_poste()
        self.accepter(decision, installer=["JDK 21"])
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

    def _c_est_fait_avec_reglages(self, reglages):
        decision = self.vers_le_poste()
        self.accepter(decision)
        (q,) = self.decisions("environnement")
        self.reecrire(environnement=reglages)
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertEqual(actions, [])
        self.assertIn("JDK 21", self.verifie[-1])               # l'outil de la décision est bien regardé
        self.assertEqual(len(self.decisions("environnement")), 1)
        self.assertIn("non trouvé", self.statut(d["id"])["reponse"])

    def test_c_est_fait_verifie_meme_si_les_reglages_ne_connaissent_pas_l_outil(self):
        """Cause du bug : « C'est fait » ne revérifiait que les outils notés « à installer » dans les réglages du projet.
        Un outil absent des réglages n'était jamais regardé : la décision se levait sans rien vérifier."""
        self._c_est_fait_avec_reglages([])

    def test_c_est_fait_verifie_meme_si_les_reglages_disent_en_place(self):
        self._c_est_fait_avec_reglages([dict(JDK, etat="en_place", chemin="C:/vieux/java.exe")])

    def test_c_est_fait_decision_ancienne_sans_champs_d_aide(self):
        """Une décision posée avant l'objectif, le lien et les étapes ne porte que le nom et le texte de l'outil."""
        self.vers_le_poste("en_place")          # une fonctionnalité f1 existe
        regles.lancer(self.projet, "decision", {"action": "poser", "portee": "f1", "genre": "environnement",
                                                "texte": "Il manque Java.",
                                                "environnement": [{"outil": "JDK 21", "installation": "x"}]})
        self.etat_du_poste = "a_installer"
        (q,) = self.decisions("environnement")
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertEqual(len(self.decisions("environnement")), 1)
        self.assertEqual(actions, [])

    def deux_outils(self, trouves=("JDK 21",)):
        self.projet.verifier_environnement = lambda outils: [
            dict(o, etat="en_place" if o["outil"] in trouves else "a_installer",
                 **({"chemin": "C:/jdk/bin/java.exe"} if o["outil"] in trouves else {"introuvables": o.get("executables")}))
            for o in outils]
        self.etat_du_poste = "a_installer"
        decision = self.vers_l_organisation({**POSTE, "environnement": [JDK, GRADLE]}, CLASSER_MEME)[1]
        self.accepter(decision)
        (q,) = self.decisions("environnement")
        return q

    def test_c_est_fait_marque_chaque_outil_trouve_ou_non_trouve(self):
        q = self.deux_outils(trouves=())
        self.assertEqual([x["outil"] for x in q["environnement"]], ["JDK 21", "Gradle"])
        self.projet.verifier_environnement = lambda outils: [
            dict(o, etat="en_place" if o["outil"] == "JDK 21" else "a_installer", chemin="C:/jdk/bin/java.exe",
                 **({} if o["outil"] == "JDK 21" else {"introuvables": ["gradle"]})) for o in outils]
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertEqual(actions, [])                                    # Gradle manque : la décision reste, rien ne démarre
        (apres,) = self.decisions("environnement")
        jdk, gradle = apres["environnement"]
        self.assertEqual((jdk["etat"], jdk["verification"]["trouve"]), ("en_place", True))
        self.assertEqual((gradle["etat"], gradle["verification"]["trouve"], gradle["verification"]["cherche"],
                          gradle["verification"]["introuvables"]), ("a_installer", False, ["gradle"], ["gradle"]))
        self.assertTrue(apres["verifie_le"])                             # l'heure de la dernière vérification
        reponse = self.statut(d["id"])["reponse"]
        self.assertIn("Gradle : non trouvé (cherché : gradle", reponse)
        self.assertNotIn("JDK 21 : non trouvé", reponse)
        self.assertEqual(releve_valider(self.ok("releve")), [])
        self.assertEqual(self.ok("releve")["fonctionnalites"][0]["decisions"][0]["environnement"][1]["verification"]["trouve"],
                         False)
        # Gradle installé à la main : tout est trouvé, la décision disparaît et le cadrage reprend
        self.projet.verifier_environnement = lambda outils: [dict(o, etat="en_place") for o in outils]
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="fait")
        self.assertEqual(self.decisions("environnement"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])

    def test_forcer_un_outil_le_declare_installe_sans_le_verifier(self):
        q = self.deux_outils(trouves=("JDK 21",))
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="forcer", outil="Gradle")
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])          # le seul manquant est forcé
        self.assertEqual(self.decisions("environnement"), [])
        gradle = next(x for x in self.lire_factory()["environnement"] if x["outil"] == "Gradle")
        self.assertEqual((gradle["etat"], gradle["declare"], gradle["note"]),
                         ("en_place", True, "déclaré installé par le Directeur (non vérifié)"))
        self.assertTrue(any("non vérifié" in m["texte"] and "Gradle" in m["texte"] for m in self.fonc()["discussion"]))
        # l'agent qui part le sait : le message de départ le dit
        depart = regles.lancer(self.projet, "depart", {"agent": "metier-1", "tache": self.taches(etape="cadrage")[0]["id"]})
        self.assertIn("Gradle", depart["message"])
        self.assertIn("déclaré installé par le Directeur (non vérifié)", depart["message"])
        # et il n'est plus revérifié : un autre passage le garde en place
        self.assertEqual(regles._verifier_poste(self.projet, [GRADLE])[0]["etat"], "en_place")

    def test_forcer_un_outil_laisse_la_decision_s_il_en_reste(self):
        q = self.deux_outils(trouves=())
        d, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="forcer", outil="Gradle")
        self.assertEqual(actions, [])
        (apres,) = self.decisions("environnement")
        jdk, gradle = apres["environnement"]
        self.assertEqual((jdk["etat"], gradle["etat"], gradle["declare"]), ("a_installer", "en_place", True))
        self.assertIn("JDK 21", self.statut(d["id"])["reponse"])
        self.assertEqual(releve_valider(self.ok("releve")), [])
        # un outil déjà déclaré ne se force plus ; un inconnu non plus
        d2, _ = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="forcer", outil="Gradle")
        self.assertIn("pas à forcer", self.statut(d2["id"])["reponse"])
        # forcer toute la décision : tout ce qui n'est pas trouvé est déclaré
        d3, actions = self.traiter(type="environnement", decision=q["id"], fonctionnalite="f1", verdict="forcer")
        self.assertEqual(self.decisions("environnement"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])
        self.assertTrue(all(x.get("declare") for x in self.lire_factory()["environnement"]))

    def test_demande_forcer_validee_par_le_bureau(self):
        from bureau import demandes
        q = self.deux_outils(trouves=("JDK 21",))
        r = self.ok("releve")
        base = {"type": "environnement", "decision": q["id"], "fonctionnalite": "f1", "verdict": "forcer"}
        self.assertIsNone(demandes.verifier(dict(base, outil="Gradle"), r))
        self.assertIsNone(demandes.verifier(dict(base), r))
        self.assertTrue(demandes.verifier(dict(base, outil="JDK 21"), r))          # déjà trouvé
        self.assertTrue(demandes.verifier(dict(base, outil="Inconnu"), r))
        self.assertTrue(demandes.verifier(dict(base, verdict="fait", outil="Gradle"), r))
        self.assertEqual(demandes.nettoyer(dict(base, outil="Gradle", x=1))["outil"], "Gradle")

    def test_continuer_sans_laisse_avancer(self):
        decision = self.vers_le_poste()
        self.accepter(decision, installer=["JDK 21"])
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


class PosteDuProjet(parcours.AvecParcours):
    """L'installation portée par le projet (créé au bureau avec son workflow) : sans fonctionnalité, jamais bloquante."""

    def setUp(self):
        super().setUp()
        from installation import mise_en_place
        self.etat_du_poste = "a_installer"
        self.verifie = []

        def verifier(outils):
            self.verifie.append([o["outil"] for o in outils])
            return [dict(o, etat=self.etat_du_poste) for o in outils]

        self.projet.verifier_environnement = verifier
        self.reecrire(environnement=[dict(JDK, etat="a_installer")])
        agent, brief = environnement.agent_d_installation(
            fiches.lire_toutes(self.dossier / "fiches"), [], [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}],
            [{"id": "dev", "nom": "Dev"}])
        fiche = mise_en_place._fiche(agent, self.dossier / "fiches" / f"{agent['cle']}.md")
        fiches.ecrire_fiche(fiche)
        self.ecrire(self.dossier / "fiches" / "briefs" / "environnement.md", brief)
        self.tache = regles.lancer(self.projet, "tache", environnement.tache_d_installation_du_projet([JDK]))["id"]

    def rendre(self, texte="Fait.", statut="fait"):
        e = agents.Execution(self.tache, "env-1", rapport=_lu({"statut": statut, "message": {"texte": texte}}),
                             usages=[usage()])
        return regles.traiter_retour(self.projet, e, self.etat)

    def decisions_du_projet(self):
        return [d for d in self.ok("etat")["decisions"] if d["genre"] == "environnement"]

    def test_la_tache_de_projet_est_lancee_seule(self):
        t = next(x for x in self.taches() if x["id"] == self.tache)
        self.assertEqual((t["fonctionnalite"], t["colonne"], t["etape"], t["role"]),
                         (None, "cadrage", "environnement", "environnement"))
        self.assertIn("JDK 21", " ".join(j["texte"] for j in t["journal"]))
        actions = regles.avancer(self.projet, self.etat)
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "env-1")])
        self.assertIn("Installe les outils du poste", actions[0][3])

    def test_installation_de_projet_reussie(self):
        regles.avancer(self.projet, self.etat)
        self.etat_du_poste = "en_place"
        suite = self.rendre("Java est installé.")
        self.assertEqual(suite, [])
        self.assertEqual(self.decisions_du_projet(), [])
        self.assertEqual(self.lire_factory()["environnement"][0]["etat"], "en_place")
        t = next(x for x in self.taches() if x["id"] == self.tache)
        self.assertEqual(t["colonne"], "fait")
        self.assertIn("poste est prêt", " ".join(j["texte"] for j in t["journal"]))      # une ligne au relevé

    def test_installation_de_projet_ratee_decision_de_projet(self):
        regles.avancer(self.projet, self.etat)
        self.assertEqual(self.rendre("Droits insuffisants."), [])
        (q,) = self.decisions_du_projet()
        self.assertEqual(q["portee"], "projet")
        self.assertIn("JDK 21", q["texte"])
        self.assertNotIn("winget install", q["texte"])
        self.assertEqual([x["outil"] for x in q["environnement"]], ["JDK 21"])
        self.assertEqual(self.ok("etat")["decisions"][0]["id"], q["id"])
        from bureau import releve
        self.assertEqual(releve.valider(self.ok("releve")), [])
        # un échec de l'agent donne la même décision, une seule
        self.rendre("Non.", statut="echec")
        self.assertEqual(len(self.decisions_du_projet()), 1)

    def test_installation_de_projet_ne_retient_pas_le_cadrage(self):
        regles.avancer(self.projet, self.etat)       # l'installation est en cours
        d, vus = self.demander({"classer_genre": CLASSER_MEME, "proposer_organisation": PROPOSITION})
        (decision,) = self.decisions("organisation")
        _, actions = self.accepter(decision)
        self.assertIn("metier-1", [a[1] for a in actions])        # le cadrage part, sans attendre l'installation
        self.assertEqual(self.taches(etape="cadrage")[0]["agent"], "metier-1")
        # et l'installation ratée ne retient rien non plus
        self.rendre("Non.")
        self.assertEqual(len(self.decisions_du_projet()), 1)
        self.assertEqual(self.fonc()["decisions"], [])

    def test_demande_environnement_sans_fonctionnalite(self):
        from bureau import demandes
        regles.avancer(self.projet, self.etat)
        self.rendre("Non.")
        (q,) = self.decisions_du_projet()
        r = self.ok("releve")
        self.assertIsNone(demandes.verifier({"type": "environnement", "decision": q["id"], "verdict": "fait"}, r))
        self.assertTrue(demandes.verifier({"type": "environnement", "decision": "d999", "verdict": "fait"}, r))
        self.assertTrue(demandes.verifier({"type": "environnement", "decision": q["id"], "verdict": "autre"}, r))
        # toujours rien : la décision reste, et le dit
        d, actions = self.traiter(type="environnement", decision=q["id"], verdict="fait")
        self.assertEqual(actions, [])
        self.assertIn("Il manque encore", self.statut(d["id"])["reponse"])
        self.assertEqual(len(self.decisions_du_projet()), 1)
        # installé à la main : revérifié, la décision est levée
        self.etat_du_poste = "en_place"
        d, actions = self.traiter(type="environnement", decision=q["id"], verdict="fait")
        self.assertEqual(self.decisions_du_projet(), [])
        self.assertEqual(self.lire_factory()["environnement"][0]["etat"], "en_place")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_c_est_fait_de_projet_verifie_la_decision_et_forcer_la_leve(self):
        regles.avancer(self.projet, self.etat)
        self.rendre("Non.")
        (q,) = self.decisions_du_projet()
        self.reecrire(environnement=[])          # les réglages ne connaissent plus l'outil : il est quand même regardé
        d, _ = self.traiter(type="environnement", decision=q["id"], verdict="fait")
        self.assertIn("non trouvé", self.statut(d["id"])["reponse"])
        self.assertIn("JDK 21", self.verifie[-1])
        (apres,) = self.decisions_du_projet()
        self.assertFalse(apres["environnement"][0]["verification"]["trouve"])
        self.assertEqual(releve_valider(self.ok("releve")), [])
        d, actions = self.traiter(type="environnement", decision=q["id"], verdict="forcer", outil="JDK 21")
        self.assertEqual((actions, self.decisions_du_projet()), ([], []))
        (jdk,) = self.lire_factory()["environnement"]
        self.assertEqual((jdk["etat"], jdk["declare"]), ("en_place", True))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_bouton_installer_en_autonomie_de_projet(self):
        regles.avancer(self.projet, self.etat)
        self.rendre("Non.")
        (q,) = self.decisions_du_projet()
        d, actions = self.traiter(type="installer_outil", decision=q["id"], outil="JDK 21")
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "env-1")])
        neuves = [t for t in self.taches(etape="environnement") if t["colonne"] != "fait"]
        self.assertEqual(len(neuves), 1)
        self.assertEqual((neuves[0]["fonctionnalite"], neuves[0]["colonne"]), (None, "cadrage"))
        self.assertTrue(self.ok("releve")["decisions_projet"][0]["environnement"][0]["en_cours"])
        d2, _ = self.traiter(type="installer_outil", decision=q["id"], outil="JDK 21")
        self.assertIn("déjà en cours", self.statut(d2["id"])["reponse"])
        self.assertEqual(releve_valider(self.ok("releve")), [])

    def test_continuer_sans_leve_la_decision_de_projet(self):
        regles.avancer(self.projet, self.etat)
        self.rendre("Non.")
        (q,) = self.decisions_du_projet()
        d, actions = self.traiter(type="environnement", decision=q["id"], verdict="continuer")
        self.assertEqual((actions, self.decisions_du_projet()), ([], []))
        self.assertEqual(self.lire_factory()["environnement"][0]["etat"], "a_installer")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        d2, _ = self.traiter(type="environnement", decision=q["id"], verdict="fait")
        self.assertIn("n'existe plus", self.statut(d2["id"])["reponse"])


def releve_valider(r):
    from bureau import releve
    return releve.valider(r)


if __name__ == "__main__":
    unittest.main()
