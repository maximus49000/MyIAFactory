import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

import workflow_github as wf  # noqa: E402

COMMANDES = {
    "apk": "./gradlew assembleDebug",
    "tests": "python -m unittest",
    "charge": "python charge.py",
}


class TestDeportWorkflow(unittest.TestCase):
    def ecrire(self, texte, binaire=None):
        dossier = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(dossier, ignore_errors=True))
        chemin = Path(dossier) / "myiafactory.yml"
        if binaire is not None:
            chemin.write_bytes(binaire)
        else:
            chemin.write_text(texte, encoding="utf-8", newline="")
        return chemin

    def test_sans_charge_pas_de_schedule(self):
        texte = wf.generer("Mon projet", ["apk", "tests"], COMMANDES)
        self.assertNotIn("schedule", texte)
        self.assertIn("workflow_dispatch", texte)
        self.assertNotIn("push", texte)          # relecture finale (I3) : un push + un dispatch = deux runs par commit
        self.assertNotIn("if:", texte)           # sans planification, aucun job n'a de condition

    def test_charge_donne_le_cron(self):
        texte = wf.generer("Mon projet", ["apk", "charge"], COMMANDES, charge_heure="03:00")
        self.assertIn("cron: '0 3 * * *'", texte)
        self.assertIn("UTC", texte)
        self.assertIn("cron: '30 14 * * *'", wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure="14:30"))

    def test_une_tache_par_action_et_upload_apk(self):
        texte = wf.generer("Mon projet", ["apk", "tests"], COMMANDES)
        self.assertIn("  apk:\n", texte)
        self.assertIn("  tests:\n", texte)
        self.assertEqual(texte.count("actions/upload-artifact@v4"), 1)
        self.assertIn("actions/download-artifact@v4", texte)
        self.assertIn("actions/checkout@v4", texte)
        self.assertIn("needs: [apk]", texte)
        self.assertIn("path: '**/build/outputs/apk/**/*.apk'", texte)    # un * non guillemeté serait un alias YAML

    def test_pas_de_needs_si_apk_n_est_pas_deporte(self):
        texte = wf.generer("Mon projet", ["tests"], COMMANDES)
        self.assertNotIn("needs:", texte)
        self.assertNotIn("download-artifact", texte)

    def test_uniquement_ubuntu_latest(self):
        texte = wf.generer("Mon projet", ["apk", "tests", "charge"], COMMANDES)
        lignes = [l for l in texte.splitlines() if "runs-on" in l]
        self.assertEqual(len(lignes), 3)
        self.assertTrue(all(l.strip() == "runs-on: ubuntu-latest" for l in lignes))

    def test_deterministe_et_fins_de_ligne(self):
        a = wf.generer("Mon projet", ["apk", "tests"], COMMANDES)
        self.assertEqual(a, wf.generer("Mon projet", ["apk", "tests"], COMMANDES))
        self.assertNotIn("\r", a)
        self.assertTrue(a.startswith("# généré par MyIAFactory empreinte="))

    def test_commande_vide_refusee(self):
        for vide in ("", "   ", None):
            with self.assertRaises(ValueError) as c:
                wf.generer("p", ["apk", "tests"], {"apk": "x", "tests": vide})
            self.assertIn("commande", str(c.exception))
        with self.assertRaises(ValueError):
            wf.generer("p", ["apk", "tests"], {"apk": "x"})

    def test_action_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            wf.generer("p", ["bidon"], {"bidon": "x"})

    def test_commande_dans_un_bloc_litteral(self):
        texte = wf.generer("p", ["apk"], {"apk": "echo \"a\" && echo 'b'\nls"})
        self.assertIn("        run: |\n          echo \"a\" && echo 'b'\n          ls\n", texte)

    def test_premiere_ligne_indentee_reste_un_yaml_valide(self):
        texte = wf.generer("p", ["apk"], {"apk": "  ./gradlew assembleDebug\nls\n  sous-ligne"})
        self.assertIn("        run: |\n          ./gradlew assembleDebug\n          ls\n            sous-ligne\n", texte)
        texte = wf.generer("p", ["apk"], {"apk": "\n\n    a\n      b\n\n"})
        self.assertIn("        run: |\n          a\n            b\n", texte)
        with self.assertRaises(ValueError) as c:
            wf.generer("p", ["apk"], {"apk": "\n  \n"})
        self.assertIn("commande", str(c.exception))

    def test_nom_avec_caracteres_speciaux_reste_entre_guillemets(self):
        texte = wf.generer("a: b # c $d", ["apk"], COMMANDES)
        self.assertIn('name: "a: b # c $d"\n', texte)

    def test_heure_invalide_refusee(self):
        for h in ("25:00", "3h", "12:60", ""):
            with self.assertRaises(ValueError):
                wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure=h)

    def test_nom_injecte_neutralise(self):
        texte = wf.generer("p\nevil: 1", ["apk"], COMMANDES)
        self.assertNotIn("\nevil: 1", texte)

    def test_etat_absent(self):
        self.assertEqual(wf.etat_du_fichier(Path(tempfile.gettempdir()) / "nexiste-pas-wf.yml", "x"), "absent")

    def test_etat_a_jour_meme_en_crlf(self):
        voulu = wf.generer("p", ["apk", "tests"], COMMANDES)
        chemin = self.ecrire(voulu)
        self.assertEqual(wf.etat_du_fichier(chemin, voulu), "a_jour")
        chemin = self.ecrire(None, binaire=voulu.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(wf.etat_du_fichier(chemin, voulu), "a_jour")

    def test_changement_de_cadence_a_valider(self):
        ancien = wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure="03:00")
        nouveau = wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure="04:00")
        self.assertEqual(wf.etat_du_fichier(self.ecrire(ancien), nouveau), "a_valider")

    def test_modifie_a_la_main(self):
        voulu = wf.generer("p", ["apk", "tests"], COMMANDES)
        chemin = self.ecrire(voulu.replace("python -m unittest", "python -m unittest -v"))
        self.assertEqual(wf.etat_du_fichier(chemin, voulu), "modifie_a_la_main")

    def test_sans_marqueur_modifie_a_la_main(self):
        chemin = self.ecrire("name: a la main\non: push\n")
        self.assertEqual(wf.etat_du_fichier(chemin, wf.generer("p", ["apk"], COMMANDES)), "modifie_a_la_main")

    def test_diff_unifie(self):
        d = wf.diff("a\nb\n", "a\nc\n")
        self.assertIn("-b", d)
        self.assertIn("+c", d)
        self.assertEqual(wf.diff("a\n", "a\n"), "")


if __name__ == "__main__":
    unittest.main()


class TestWorkflowParCatalogue(unittest.TestCase):
    def setUp(self):
        from bureau.deport_types import CATALOGUES
        self.android = CATALOGUES["application-mobile-android"]

    def test_android_commandes_par_defaut_sans_needs_et_artefact_du_catalogue(self):
        texte = wf.generer("Mon projet", ["apk", "tests"], {}, catalogue=self.android)
        self.assertIn("./gradlew assembleDebug", texte)
        self.assertIn("./gradlew testDebugUnitTest", texte)
        self.assertNotIn("needs", texte)
        self.assertNotIn("download-artifact", texte)
        self.assertIn("path: 'app/build/outputs/apk/debug/*.apk'", texte)
        self.assertNotIn("**/build/outputs", texte)

    def test_une_commande_donnee_l_emporte_sur_celle_du_catalogue(self):
        texte = wf.generer("p", ["apk", "tests"], {"tests": "./gradlew test --info"}, catalogue=self.android)
        self.assertIn("./gradlew test --info", texte)
        self.assertNotIn("testDebugUnitTest", texte)
        self.assertIn("./gradlew assembleDebug", texte)

    def test_action_absente_du_catalogue_refusee(self):
        with self.assertRaises(ValueError):
            wf.generer("p", ["charge"], {"charge": "x"}, catalogue=self.android)

    def test_le_generique_n_a_pas_de_commande_par_defaut_et_garde_son_artefact(self):
        with self.assertRaises(ValueError):
            wf.generer("p", ["apk"], {})
        self.assertIn("path: '**/build/outputs/apk/**/*.apk'", wf.generer("p", ["apk"], {"apk": "build"}))


class TestDeclencheurs(unittest.TestCase):
    """Relecture finale (I3) : jamais `push` ; `schedule` seulement si `charge` est déportée, et alors seuls `charge`
    et les jobs dont elle dépend tournent la nuit."""

    @staticmethod
    def jobs(texte):
        """{id du job: texte de son bloc}."""
        blocs, courant = {}, None
        for ligne in texte.split("\njobs:\n", 1)[1].splitlines():
            if ligne.startswith("  ") and not ligne.startswith("   ") and ligne.endswith(":"):
                courant = ligne.strip()[:-1]
                blocs[courant] = ""
            elif courant:
                blocs[courant] += ligne + "\n"
        return blocs

    def test_jamais_de_push(self):
        for actions in (["apk"], ["apk", "tests", "charge"], ["charge"]):
            texte = wf.generer("p", actions, COMMANDES)
            self.assertNotIn("push", texte.split("jobs:")[0])
            self.assertIn("  workflow_dispatch:\n", texte)

    def test_la_nuit_seule_la_charge_et_ce_dont_elle_depend(self):
        texte = wf.generer("p", ["apk", "tests", "charge"], COMMANDES)
        jobs = self.jobs(texte)
        self.assertIn("schedule", texte)
        self.assertIn("if: github.event_name != 'schedule'", jobs["tests"])
        self.assertNotIn("if:", jobs["charge"])          # planification ou bouton manuel
        self.assertNotIn("if:", jobs["apk"])             # la charge consomme l'APK : il doit tourner la nuit aussi

    def test_charge_sans_apk_deporte(self):
        jobs = self.jobs(wf.generer("p", ["tests", "charge"], COMMANDES))
        self.assertIn("if: github.event_name != 'schedule'", jobs["tests"])
        self.assertNotIn("if:", jobs["charge"])


class TestFormeYaml(unittest.TestCase):
    """Relecture finale : la forme du YAML généré, vérifiée sans analyseur (et avec PyYAML s'il est là)."""

    def textes(self):
        from bureau.deport_types import CATALOGUES, GENERIQUE
        android = CATALOGUES["application-mobile-android"]
        return [(wf.generer("p", ["apk", "tests", "charge"], COMMANDES), GENERIQUE),
                (wf.generer("p", ["apk", "tests"], {"apk": "a\n  b", "tests": "t"}), GENERIQUE),
                (wf.generer("p", ["apk", "tests", "lint"], {}, catalogue=android), android)]

    def test_forme(self):
        import re
        for texte, catalogue in self.textes():
            self.assertNotIn("\t", texte)
            lignes = texte.splitlines()
            for i, ligne in enumerate(lignes):
                retrait = len(ligne) - len(ligne.lstrip(" "))
                self.assertEqual(retrait % 2, 0, ligne)          # indentation par 2 espaces
                if ligne.rstrip().endswith("run: |"):
                    corps = lignes[i + 1]
                    self.assertGreater(len(corps) - len(corps.lstrip(" ")), retrait, corps)
            blocs = TestDeclencheurs.jobs(texte)
            for job in blocs:
                self.assertRegex(job, r"^[A-Za-z_][A-Za-z0-9_-]*$")
            for besoin in re.findall(r"needs: \[([^\]]*)\]", texte):
                for nom in besoin.split(","):
                    self.assertIn(nom.strip(), blocs)
            # le nom publié est celui que `deporter` télécharge : le `produit` du catalogue
            for job, bloc in blocs.items():
                if "upload-artifact" in bloc:
                    nom = re.search(r"upload-artifact@v4\n\s+with:\n\s+name: (\S+)", bloc).group(1)
                    self.assertEqual(nom, catalogue[job]["produit"])

    def test_aller_retour_pyyaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML absent")
        for texte, _ in self.textes():
            v = yaml.safe_load(texte)
            self.assertIn("jobs", v)
            self.assertNotIn("push", v.get(True, v.get("on")) or {})


class TestGradle(unittest.TestCase):
    """Contrôleur (essai réel) : `gradlew` sans bit exécutable dans un dépôt créé sous Windows, JDK 17 exigé."""

    def etapes(self, bloc):
        """Les étapes d'un job, dans l'ordre : `uses` ou `run` de chacune."""
        noms = []
        for ligne in bloc.splitlines():
            s = ligne.strip()
            if s.startswith("- uses: "):
                noms.append(s[len("- uses: "):])
            elif s.startswith("- run: "):
                noms.append(s[len("- run: "):])
            elif s.startswith("- name: "):
                noms.append("commande")
        return noms

    def test_ordre_checkout_java_cache_gradle_chmod_commande(self):
        from bureau.deport_types import CATALOGUES
        texte = wf.generer("p", ["apk", "tests"], {}, catalogue=CATALOGUES["application-mobile-android"])
        for job, bloc in TestDeclencheurs.jobs(texte).items():
            e = self.etapes(bloc)
            self.assertEqual(e[:5], ["actions/checkout@v4", "actions/setup-java@v4", "gradle/actions/setup-gradle@v4",
                                       "chmod +x gradlew", "commande"], job)
            self.assertIn("distribution: temurin", bloc)
            self.assertIn("java-version: '17'", bloc)

    def test_sans_gradlew_ni_java_ni_chmod(self):
        texte = wf.generer("p", ["apk", "tests"], COMMANDES)
        blocs = TestDeclencheurs.jobs(texte)
        self.assertNotIn("setup-java", blocs["tests"])
        self.assertNotIn("setup-gradle", blocs["tests"])
        self.assertNotIn("chmod", blocs["tests"])
        self.assertIn("setup-java", blocs["apk"])          # ./gradlew assembleDebug
        self.assertIn("gradle/actions/setup-gradle@v4", blocs["apk"])
        self.assertIn("chmod +x gradlew", blocs["apk"])
