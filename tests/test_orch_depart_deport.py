import unittest

from bureau.deport_types import ANDROID, GENERIQUE
from orchestrateur import depart
from tests.test_orch_depart import fiche


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
        self.assertNotIn("deporter tests", t)
        for mot in ("Pousse d'abord", "ATTEND", "dépendances", "directement", "--poste", "Directeur", "deport/workflow"):
            self.assertIn(mot, t)

    def test_android_utilise_ses_commandes_sans_charge(self):
        t = depart.deport_consigne({a: "github" for a in ANDROID}, ANDROID)
        self.assertIn("./gradlew assembleDebug", t)
        self.assertIn("./gradlew testDebugUnitTest", t)
        self.assertNotIn("charge", t)

    def test_commande_du_projet(self):
        t = depart.deport_consigne({"tests": "github"}, GENERIQUE, {"tests": "npx vitest run"}, dossier="D:/p")
        self.assertIn("deporter tests --dossier D:/p -- npx vitest run", t)

    def test_dans_le_budget(self):
        t = depart.deport_consigne({a: "github" for a in ANDROID}, ANDROID)
        self.assertLess(len(t), 2200)


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
    def test_depuis_les_reglages_du_projet(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from orchestrateur import outil
        with tempfile.TemporaryDirectory() as t:
            projet = Path(t)
            (projet / ".factory").mkdir()
            ctx = SimpleNamespace(f={"base": projet / ".factory", "reglages": None})
            self.assertEqual(outil._deport_du_depart(ctx), "") if not Path("~/MyIAFactory/bureau.json").expanduser().exists() else None
            (projet / ".factory" / "reglages.json").write_text(json.dumps(
                {"deport": {"lieux": {"apk": "github"}, "commandes": {"apk": "make apk"}}}), encoding="utf-8")
            texte = outil._deport_du_depart(ctx)
        self.assertIn("deporter apk", texte)
        self.assertIn("-- make apk", texte)


if __name__ == "__main__":
    unittest.main()
