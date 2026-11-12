"""Les règles du projet : le fichier `.factory/regles-projet.json`, la commande `lancer regles`, leur transmission aux
agents et aux jugements, le rappel au Directeur, les demandes du bureau et le relevé."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bureau import demandes, equipe, etat, releve
from orchestrateur import depart, regles_projet as rp
from tests.orch_aide import AvecProjet
from tests.test_demandes import R4
from tests.test_orch_lots_outil import AvecTaches

APPAREIL = ("Pas d'installation ni de test sur un appareil physique : tests automatiques sur émulateur, validation de "
            "version par la fenêtre de validation.")


class TestModule(unittest.TestCase):
    def test_correspondance_par_mots_cles(self):
        regles = [{"id": "r1", "texte": APPAREIL}, {"id": "r2", "texte": "Pas de Docker."},
                  {"id": "r3", "texte": "Les textes du jeu restent en français."}]
        sur = lambda *t: [x["id"] for x in rp.touchees(regles, *t)]      # noqa: E731
        self.assertEqual(sur("adb install de l'apk", "Je veux tester sur le téléphone branché"), ["r1"])
        self.assertEqual(sur("Installer Docker pour lancer le serveur"), ["r2"])    # une règle d'un seul mot : un mot
        self.assertEqual(sur("Générer 5 images", "Il me faut un accord."), [])
        self.assertEqual(sur("Mettre les textes du jeu en français et en anglais"), ["r3"])
        self.assertEqual(sur("Écrire les textes du jeu en anglais"), [])      # un seul mot en commun : pas de rappel
        self.assertEqual(sur(None, 3), [])
        self.assertEqual(rp.touchees([], "installation"), [])

    def test_au_plus_trois_regles_rappelees(self):
        regles = [{"id": f"r{i}", "texte": "Pas de serveur local réseau"} for i in range(1, 6)]
        self.assertEqual(len(rp.touchees(regles, "un serveur local")), rp.MAX_TOUCHEES)

    def test_en_tete(self):
        self.assertEqual(rp.en_tete([]), "")
        t = rp.en_tete([{"texte": "Une."}, "Deux."])
        self.assertTrue(t.startswith("## Règles du projet, à respecter :\n"))
        self.assertIn("- Une.\n- Deux.", t)
        long = rp.en_tete(["x" * 500] * 40)
        self.assertLessEqual(len(long), rp.MAX_EN_TETE + 60)
        self.assertEqual(long.count("- x"), rp.MAX_EN_TETE // 503)


class TestCommande(AvecProjet):
    def regles(self, **entree):
        return self.ok("lancer", "regles", entree=entree)

    def fichier(self):
        return self.dossier / "regles-projet.json"      # à côté du fichier de factory

    def test_ajouter_modifier_supprimer(self):
        self.assertEqual(self.regles(action="lister"), {"regles": []})
        r = self.regles(action="ajouter", texte="  Pas  de   Docker. ", origine={"decision": "d3", "agent": "dev-1"})
        self.assertEqual(r["regle"]["id"], "r1")
        self.assertEqual(r["regle"]["texte"], "Pas de Docker.")
        self.assertEqual(r["regle"]["origine"], {"decision": "d3", "agent": "dev-1"})
        self.assertTrue(r["regle"]["cree_le"])
        self.assertEqual(self.regles(action="ajouter", texte="pas de docker.")["deja"], True)   # pas de doublon
        self.regles(action="ajouter", texte="Textes en français.")
        self.assertEqual([x["id"] for x in self.regles(action="lister")["regles"]], ["r1", "r2"])
        m = self.regles(action="modifier", id="r2", texte="Textes en français et courts.")
        self.assertEqual(m["regle"]["texte"], "Textes en français et courts.")
        self.assertIn("modifie_le", m["regle"])
        self.regles(action="supprimer", id="r1")
        self.assertEqual([x["id"] for x in self.regles(action="lister")["regles"]], ["r2"])
        self.assertEqual(self.regles(action="ajouter", texte="Autre.")["regle"]["id"], "r3")      # les ids ne reviennent pas
        self.assertEqual(json.loads(self.fichier().read_text(encoding="utf-8"))[0]["id"], "r2")

    def test_refus(self):
        for e in ({}, {"action": "effacer"}, {"action": "ajouter"}, {"action": "ajouter", "texte": "   "},
                  {"action": "ajouter", "texte": 3}, {"action": "ajouter", "texte": "x" * 501},
                  {"action": "ajouter", "texte": "ok", "origine": {"decision": "d1"}},
                  {"action": "modifier", "id": "r9", "texte": "x"}, {"action": "supprimer", "id": "r9"},
                  {"action": "modifier", "texte": "x"}):
            self.assertEqual(self.outil("lancer", "regles", entree=e)[0], 1, e)
        self.ok("lancer", "regles", entree={"action": "ajouter", "texte": "x" * 500})
        self.assertFalse(self.fichier().with_name("regles-projet.json.tmp").exists())

    def test_au_plus_quarante_regles(self):
        for i in range(rp.MAX_REGLES):
            self.regles(action="ajouter", texte=f"Règle numéro {i}.")
        code, objet = self.outil("lancer", "regles", entree={"action": "ajouter", "texte": "De trop."})
        self.assertEqual(code, 1)
        self.assertIn("supprimez-en une", objet["erreur"])

    def test_fichier_abime_ou_entrees_invalides_ignores(self):
        self.fichier().write_text("pas du json", encoding="utf-8")
        self.assertEqual(self.regles(action="lister"), {"regles": []})
        self.fichier().write_text(json.dumps([{"id": "r1", "texte": "Bonne."}, {"id": "x", "texte": "Mauvais id."},
                                              {"id": "r2", "texte": ""}, 3]), encoding="utf-8")
        self.assertEqual([x["id"] for x in self.regles(action="lister")["regles"]], ["r1"])

    def test_releve_porte_les_regles(self):
        self.assertEqual(self.ok("releve")["regles_projet"], [])
        self.regles(action="ajouter", texte="Pas de Docker.")
        r = self.ok("releve")
        self.assertEqual(r["regles_projet"][0]["texte"], "Pas de Docker.")
        self.assertEqual(releve.valider(r), [])

    def test_un_agent_ne_conseille_pas_les_regles(self):
        from moteur import jugement
        self.assertIn("regles", jugement.COMMANDES_INTERDITES_AU_CONSEIL)


class TestTransmission(AvecTaches):
    def test_depart_d_un_agent_et_d_un_lot_portent_les_regles(self):
        a, b = self.nt("Écrire le menu"), self.nt("Composer le son du menu", "son")
        sans = self.ok("depart", entree={"agent": "dev-1", "tache": a})["message"]
        self.assertNotIn("Règles du projet", sans)
        self.ok("lancer", "regles", entree={"action": "ajouter", "texte": "Pas de Docker."})
        self.ok("lancer", "regles", entree={"action": "ajouter", "texte": "Textes en français."})
        for message in (self.ok("depart", entree={"agent": "dev-1", "tache": a})["message"],
                        self.ok("depart", entree={"agent": "dev-1", "taches": [a, b]})["message"],
                        self.ok("depart", entree={"agent": "dev-1", "taches": [a, b], "moteur": True})["message"]):
            self.assertIn("## Règles du projet, à respecter :\n- Pas de Docker.\n- Textes en français.", message)
            self.assertLess(message.index("Règles du projet"), message.index("## Ta fiche"))      # en tête
            self.assertLess(message.index("# Projet :"), message.index("Règles du projet"))
        self.assertLess(len(self.ok("depart", entree={"agent": "dev-1", "tache": a})["message"]) - len(sans), 200)

    def test_depart_cloud_porte_les_regles_apres_le_rappel_de_depart(self):
        m = depart.message({"nom": "P", "genre": None},
                           {"cle": "c", "role": "dev", "modele": "Sonnet", "lieu": "cloud", "texte": "T", "lecons": []},
                           {"id": "t1", "titre": "T"}, None, {"skill": [], "genre": []}, regles_projet=[{"texte": "R."}])
        self.assertTrue(m.startswith("Tu repars de zéro."))
        self.assertIn("## Règles du projet, à respecter :\n- R.", m)


def releve_avec(regles, decisions):
    return releve.normaliser({**R4, "regles_projet": regles, "decisions_projet": decisions})


REGLES = [{"id": "r1", "texte": APPAREIL, "cree_le": "2026-11-12T10:00:00+01:00"}]
ACCORD = {"id": "a1", "genre": "accord_agent", "texte": "Accord ?", "agent": "d1", "tache": "t1", "quoi": "adb install"}


class TestDemandes(unittest.TestCase):
    R = releve_avec(REGLES, [ACCORD])

    def ok(self, d):
        self.assertIsNone(demandes.verifier(d, self.R, frozenset()), d)

    def refus(self, d, r=None):
        self.assertTrue(demandes.verifier(d, r or self.R, frozenset()), d)

    def test_regle_projet(self):
        self.ok({"type": "regle_projet", "operation": "ajouter", "texte": "Pas de Docker."})
        self.ok({"type": "regle_projet", "operation": "ajouter", "texte": "x" * 500})
        self.ok({"type": "regle_projet", "operation": "modifier", "id": "r1", "texte": "Autre."})
        self.ok({"type": "regle_projet", "operation": "supprimer", "id": "r1"})
        for d in ({"type": "regle_projet"}, {"type": "regle_projet", "operation": "effacer"},
                  {"type": "regle_projet", "operation": "ajouter"},
                  {"type": "regle_projet", "operation": "ajouter", "texte": "  "},
                  {"type": "regle_projet", "operation": "ajouter", "texte": 4},
                  {"type": "regle_projet", "operation": "ajouter", "texte": "x" * 501},
                  {"type": "regle_projet", "operation": "modifier", "texte": "Autre."},
                  {"type": "regle_projet", "operation": "modifier", "id": "r9", "texte": "Autre."},
                  {"type": "regle_projet", "operation": "modifier", "id": "r1"},
                  {"type": "regle_projet", "operation": "supprimer", "id": "r9"}):
            self.refus(d)
        self.assertEqual(demandes.nettoyer({"type": "regle_projet", "operation": "supprimer", "id": "r1", "autre": 1}),
                        {"type": "regle_projet", "operation": "supprimer", "id": "r1"})

    def test_relevé_sans_regles_les_refuse(self):
        self.refus({"type": "regle_projet", "operation": "ajouter", "texte": "R"}, R4)
        self.refus({"type": "accord_agent", "decision": "a1", "verdict": "accepter", "regle": "R"},
                   releve.normaliser({**R4, "decisions_projet": [ACCORD]}))

    def test_accord_agent_choisir(self):
        r = releve_avec(REGLES, [{**ACCORD, "choix": ["Oui, je branche", "Non"]}])
        base = {"type": "accord_agent", "decision": "a1", "verdict": "choisir"}
        self.assertIsNone(demandes.verifier({**base, "choix": "Non", "texte": "t", "regle": "R"}, r, frozenset()))
        for mauvaise in ({}, {"choix": "Autre"}, {"choix": 3}):
            self.assertTrue(demandes.verifier({**base, **mauvaise}, r, frozenset()), mauvaise)
        self.assertTrue(demandes.verifier({**base, "choix": "Non"}, self.R, frozenset()))      # la décision n'a pas de choix
        self.assertEqual(demandes.nettoyer({**base, "choix": "Non", "autre": 1}), {**base, "choix": "Non"})
        self.assertEqual(releve.valider(r), [])
        for mauvais in ("Non", [], [""], ["x" * 121], ["a"] * 7):
            self.assertTrue(releve.valider(releve_avec(REGLES, [{**ACCORD, "choix": mauvais}])), mauvais)

    def test_accord_agent_retenir_comme_regle(self):
        base = {"type": "accord_agent", "decision": "a1", "verdict": "refuser"}
        self.ok({**base, "regle": "Pas d'appareil physique.", "texte": "Utilise l'émulateur."})
        self.ok({**base, "regle": "x" * 500})
        self.refus({**base, "regle": "  "})
        self.refus({**base, "regle": "x" * 501})
        self.refus({**base, "regle": 3})
        self.assertEqual(demandes.nettoyer({**base, "regle": "R", "autre": 1}), {**base, "regle": "R"})


class TestReleve(unittest.TestCase):
    def test_regles_du_releve(self):
        self.assertEqual(releve.valider(releve_avec(REGLES, [])), [])
        for mauvaise in ("x", [{"id": "r1"}], [{"id": "r1", "texte": "x" * 501}], [{"id": "r1", "texte": "a"}, {"id": "r1", "texte": "b"}],
                         [{"id": "r1", "texte": "a", "origine": {"decision": "d"}}], [{"id": "r1", "texte": "a", "cree_le": "hier"}]):
            r = copy.deepcopy(R4)
            r["regles_projet"] = mauvaise
            self.assertTrue(releve.valider(r), mauvaise)

    def test_decision_accord_regle_proposee_et_touchees(self):
        ok = {**ACCORD, "regle_proposee": APPAREIL, "regles_touchees": [{"id": "r1", "texte": APPAREIL}]}
        self.assertEqual(releve.valider(releve_avec(REGLES, [ok])), [])
        for mauvaise in ({"regle_proposee": 3}, {"regle_proposee": "x" * 501}, {"regles_touchees": "r1"},
                         {"regles_touchees": [{"id": "r1"}]}):
            self.assertTrue(releve.valider(releve_avec(REGLES, [{**ACCORD, **mauvaise}])), mauvaise)

    def test_l_etat_du_bureau_porte_les_regles(self):
        with tempfile.TemporaryDirectory() as t:
            eq = equipe.Equipe(Path(t) / "equipe.json")
            e = etat.construire(releve_avec(REGLES, []), eq, datetime(2026, 11, 12, tzinfo=timezone.utc), 30)
            self.assertEqual(e["regles_projet"], REGLES)
            e = etat.construire(releve.normaliser({**R4, "regles_projet": None}), eq,
                                datetime(2026, 11, 12, tzinfo=timezone.utc), 30)
            self.assertNotIn("regles_projet", e)


if __name__ == "__main__":
    unittest.main()
