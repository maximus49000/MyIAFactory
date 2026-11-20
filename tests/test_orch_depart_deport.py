import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bureau.deport_types import ANDROID, GENERIQUE
from orchestrateur import depart, outil
from tests.test_orch_depart import fiche
from tests import test_orch_lots_outil as lots


def _tous(lieu):
    return {a: lieu for a in GENERIQUE}


class TestDeportConsigne(unittest.TestCase):
    def test_tout_au_poste_est_vide(self):
        self.assertEqual(depart.deport_consigne(_tous("poste")), "")
        self.assertEqual(depart.deport_consigne({}), "")
        self.assertEqual(depart.deport_consigne(None, ANDROID), "")

    def test_apk_chez_github_cite_le_lanceur(self):
        t = depart.deport_consigne({**_tous("poste"), "apk": "github"})
        self.assertIn("deporter apk", t)
        self.assertIn(str(depart.LANCEUR_DE_TESTS), t)
        self.assertNotIn("- Tests : ", t)      # pas déportés ; ils attendent l'APK (voir la ligne « Au poste… »)
        for mot in ("Pousse d'abord", "ATTEND", "dépendances", "directement", "--poste", "Directeur", "deport/workflow"):
            self.assertIn(mot, t)

    def test_android_utilise_ses_commandes_sans_charge(self):
        t = depart.deport_consigne({a: "github" for a in ANDROID}, ANDROID)
        self.assertIn("./gradlew assembleDebug", t)
        self.assertIn("./gradlew testDebugUnitTest", t)
        self.assertNotIn("charge", t)

    def test_commande_du_projet(self):
        t = depart.deport_consigne({"tests": "github"}, GENERIQUE, {"tests": "npx vitest run"}, dossier="D:/p")
        self.assertIn('deporter tests --dossier "D:/p" -- npx vitest run', t)

    def test_action_au_poste_qui_attend_github_passe_aussi_par_deporter(self):
        t = depart.deport_consigne({**_tous("poste"), "apk": "github"}, GENERIQUE, dossier="D:/p")
        self.assertIn('deporter tests --dossier "D:/p" -- <ta commande>', t)
        self.assertIn("8 quota", t)
        android = depart.deport_consigne({**{a: "poste" for a in ANDROID}, "apk": "github"}, ANDROID)
        self.assertNotIn("deporter tests", android)     # les tests Android ne consomment pas l'APK

    def test_la_recette_sur_emulateur_n_est_jamais_une_commande_github_ni_poste(self):
        for lieu in (None, "github", "poste"):         # « serveur » : voir TestConsigneRecette
            for catalogue in (GENERIQUE, ANDROID):
                t = depart.deport_consigne({**{a: "github" for a in catalogue}, "recette-emulateur": lieu}, catalogue)
                self.assertNotIn("recette-emulateur", t, (lieu, catalogue is ANDROID))
                self.assertNotIn("Recette sur émulateur", t)

    def test_generique_tout_sur_github_dans_le_budget(self):
        t = depart.deport_consigne({**_tous("github"), "emulateur": "poste"}, GENERIQUE, dossier="D:/un/long/chemin")
        self.assertLess(len(t), 2200)

    def test_dans_le_budget(self):
        t = depart.deport_consigne({a: "github" for a in ANDROID}, ANDROID)
        self.assertLess(len(t), 2200)


class TestConsigneRecette(unittest.TestCase):
    """La ligne du message de départ pour la recette sur émulateur (au seul serveur) : une commande à connaître."""
    RECETTE = {"recette-emulateur": "serveur"}

    def test_reglee_sur_serveur_donne_la_commande_et_les_garde_fous(self):
        for catalogue in (GENERIQUE, ANDROID):
            t = depart.deport_consigne(self.RECETTE, catalogue, {}, dossier="D:/p")
            self.assertIn('deporter recette-emulateur --scenario <nom> --dossier "D:/p"', t)
            self.assertIn(str(depart.LANCEUR_DE_TESTS), t)
            for mot in ("DONNÉES", "jamais des instructions", "Directeur", ".factory/recettes", "--mode pilote"):
                self.assertIn(mot, t)
            self.assertNotIn("GitHub", t)       # rien d'une action déportée sur GitHub
            self.assertLess(len(t), 1300)

    def test_ni_reglee_ni_au_poste_ni_sur_github_rien_ne_change(self):
        for lieu in (None, "poste", "github", "autre"):
            self.assertEqual(depart.deport_consigne({"recette-emulateur": lieu}, ANDROID), "", lieu)
        self.assertEqual(depart.deport_consigne({}, GENERIQUE), "")

    def test_le_fichier_de_reglages_ailleurs_est_repris(self):
        t = depart.deport_consigne(self.RECETTE, ANDROID, {}, dossier="D:/p", reglages="D:/r.json")
        self.assertIn('--dossier "D:/p" --reglages "D:/r.json"', t)

    def test_avec_des_actions_sur_github_les_deux_consignes_sont_la(self):
        t = depart.deport_consigne({**{a: "github" for a in ANDROID}, **self.RECETTE}, ANDROID)
        self.assertIn("## Actions déportées sur GitHub", t)
        self.assertIn("deporter apk", t)
        self.assertIn("deporter recette-emulateur", t)
        self.assertLess(t.index("## Actions déportées"), t.index("deporter recette-emulateur"))

    def test_une_action_non_servie_au_serveur_n_a_pas_cette_ligne(self):
        t = depart.deport_consigne(self.RECETTE, {"apk": GENERIQUE["apk"]})      # catalogue sans la recette
        self.assertEqual(t, "")


class TestAssemblage(unittest.TestCase):
    def _msg(self, **k):
        f = fiche("dev-1", "dev")
        tache = {"id": "T1", "titre": "x"}
        return depart.message({"nom": "P", "genre": None}, f, tache, "b", {"skill": [], "genre": []}, **k)

    def test_inclus_seulement_si_non_vide(self):
        base = self._msg()
        self.assertEqual(self._msg(deport=""), base)
        texte = depart.deport_consigne({"apk": "github"})
        avec = self._msg(deport=texte)
        self.assertIn(texte, avec)
        self.assertEqual(avec.replace("\n\n" + texte, ""), base)
        lot = depart.message_lot({"nom": "P", "genre": None}, fiche("dev-1", "dev"), [{"id": "T1", "titre": "x"}],
                                 [("dev", "b")], {"skill": [], "genre": []}, deport=texte)
        self.assertIn("deporter apk", lot)


class TestLectureDesReglages(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.projet = Path(t.name) / "mon projet"
        (self.projet / ".factory").mkdir(parents=True)
        self.bureau = Path(t.name) / "bureau.json"
        self.ctx = SimpleNamespace(f={"base": self.projet / ".factory", "reglages": None})

    def ecrire(self, chemin, deport):
        Path(chemin).write_text(json.dumps({"deport": deport}), encoding="utf-8")

    def consigne(self, ctx=None):
        return outil._deport_du_depart(ctx or self.ctx, bureau=self.bureau)

    def test_rien_ne_change_sans_deport(self):
        self.assertEqual(self.consigne(), "")   # ni bureau.json ni réglages

    def test_depuis_les_reglages_du_projet(self):
        self.ecrire(self.projet / ".factory" / "reglages.json",
                    {"lieux": {"apk": "github"}, "commandes": {"apk": "make apk"}})
        texte = self.consigne()
        self.assertIn("deporter apk", texte)
        self.assertIn("-- make apk", texte)
        self.assertIn('--dossier "%s"' % self.projet, texte)
        self.assertNotIn("--reglages", texte)   # emplacement par défaut

    def test_defaut_global_github_surcharge_projet_poste(self):
        self.ecrire(self.bureau, {"lieux": {a: "github" for a in GENERIQUE}})
        self.assertIn("deporter apk", self.consigne())
        self.ecrire(self.projet / ".factory" / "reglages.json", {"lieux": {a: "poste" for a in GENERIQUE}})
        self.assertEqual(self.consigne(), "")

    def test_reglages_ailleurs_ajoutent_l_option(self):
        autre = self.projet / "reglages.json"
        self.ecrire(autre, {"lieux": {"apk": "github"}})
        ctx = SimpleNamespace(f={"base": self.projet / ".factory", "reglages": autre})
        self.assertIn('--reglages "%s"' % autre, self.consigne(ctx))

    def test_reglages_invalides_donnent_vide(self):
        chemin = self.projet / ".factory" / "reglages.json"
        chemin.write_text("{ cassé", encoding="utf-8")
        self.assertEqual(self.consigne(), "")
        for deport in ("texte", ["x"], {"lieux": "github"}, {"lieux": ["apk"]}, {"lieux": {"apk": "github"}, "commandes": 3}):
            self.ecrire(chemin, deport)
            texte = self.consigne()
            if isinstance(deport, dict) and isinstance(deport.get("lieux"), dict):
                self.assertIn("deporter apk", texte)
            else:
                self.assertEqual(texte, "")

    def test_la_recette_vient_des_reglages_du_projet_jamais_du_defaut_du_bureau(self):
        self.ecrire(self.bureau, {"lieux": {"recette-emulateur": "serveur"}})
        self.assertEqual(self.consigne(), "")      # l'accord permanent ne s'hérite pas du bureau
        self.ecrire(self.projet / ".factory" / "reglages.json", {"lieux": {"recette-emulateur": "serveur"}})
        texte = self.consigne()
        self.assertIn("deporter recette-emulateur", texte)
        self.assertIn('--dossier "%s"' % self.projet, texte)
        self.ecrire(self.projet / ".factory" / "reglages.json", {"lieux": {"recette-emulateur": "poste"}})
        self.assertEqual(self.consigne(), "")

    def test_contexte_invalide_donne_vide(self):
        self.assertEqual(outil._deport_du_depart(SimpleNamespace(f={})), "")
        self.assertEqual(outil._deport_du_depart(None), "")


class TestDepartDeBoutEnBout(lots.AvecTaches):
    def setUp(self):
        super().setUp()
        (self.dossier / "reglages.json").write_text(json.dumps(
            {"images": {"racines": ["pieces"]}, "deport": {"lieux": {"apk": "github"}}}), encoding="utf-8")

    def test_tache_seule_et_lot(self):
        a, b = self.nt("Écrire le menu"), self.nt("Autre tâche")
        seul = self.ok("lancer", "depart", entree={"agent": "dev-1", "tache": a})["message"]
        lot = self.ok("lancer", "depart", entree={"agent": "dev-1", "taches": [a, b]})["message"]
        for m in (seul, lot):
            self.assertIn("## Actions déportées sur GitHub", m)
            self.assertIn("deporter apk", m)
            self.assertIn("--reglages", m)   # les réglages du projet ne sont pas dans .factory/


if __name__ == "__main__":
    unittest.main()
