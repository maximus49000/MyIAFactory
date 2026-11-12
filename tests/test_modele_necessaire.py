"""Le modèle nécessaire d'une tâche et le plafond d'un agent (conception 2026-11-12-modele-par-tache-design.md)."""
import unittest

from orchestrateur import modele_necessaire as mn


def fiche(cle, role, modele="Opus", lieu="local"):
    return {"cle": cle, "role": role, "modele": modele, "lieu": lieu}


FLUX = [{"id": "f1-conception", "nom": "Conception", "role": "dev", "service": "dev"},
        {"id": "f1-dev", "nom": "Développement", "role": "dev", "service": "dev",
         "modele": "Haiku", "justification": "Petits écrans répétitifs."},
        {"id": "f1-essai", "nom": "Essai par le Directeur", "validation": True},
        {"id": "f1-tests", "nom": "Tests", "role": "qa", "service": "dev"},
        {"id": "f1-poesie", "nom": "Poésie", "role": "barde", "service": "dev"}]
FACTORY = {"flux": [], "workflows": [{"id": "w-f1", "fonctionnalite": "f1", "genre": "jeu", "flux": FLUX}]}
FONCS = [{"id": "f1", "workflow": "w-f1"}]


class Etape(unittest.TestCase):
    def test_modele_fixe_par_le_workflow(self):
        m = mn.de_l_etape(FLUX[1])
        self.assertEqual((m["modele"], m["source"]), ("Haiku", "workflow"))
        self.assertIn("Petits écrans", m["raison"])

    def test_deduit_de_la_nature(self):
        self.assertEqual(mn.de_l_etape(FLUX[0])["modele"], "Opus")
        m = mn.de_l_etape(FLUX[3])
        self.assertEqual((m["modele"], m["source"]), ("Haiku", "deduit"))
        self.assertIn("tests", m["raison"])
        # le rôle, à défaut du nom de l'étape
        self.assertEqual(mn.de_l_etape({"id": "x", "nom": "Étape", "role": "testeur"})["modele"], "Haiku")

    def test_nature_inconnue_prend_le_modele_du_role(self):
        self.assertEqual(mn.de_l_etape(FLUX[4], [fiche("b", "barde", "Haiku")])["modele"], "Haiku")
        self.assertEqual(mn.de_l_etape(FLUX[4], [fiche("b", "barde", "Fable")])["modele"], "Opus")
        m = mn.de_l_etape(FLUX[4])
        self.assertEqual((m["modele"], m["source"]), ("Sonnet", "role"))

    def test_modele_invalide_ignore_et_jamais_fable(self):
        for mauvais in ("Fable", "GPT", "", None, 3):
            self.assertNotEqual(mn.de_l_etape(dict(FLUX[0], modele=mauvais))["source"], "workflow")
        self.assertIsNone(mn.de_l_etape(FLUX[2]))        # une validation du Directeur n'a pas de modèle

    def test_rang_plafonne_et_nom(self):
        self.assertEqual([mn.rang(m) for m in ("haiku", "Sonnet", "claude-opus-5-5", "Fable", "?")], [0, 1, 2, 3, 1])
        self.assertEqual(mn.plafonne("Opus", "Sonnet"), "Sonnet")
        self.assertEqual(mn.plafonne("Haiku", "Opus"), "Haiku")
        self.assertEqual(mn.plafonne("Opus", "Fable"), "Opus")
        self.assertEqual(mn.nom("sonnet"), "Sonnet")


class Tache(unittest.TestCase):
    def tache(self, etape, role="dev", **plus):
        return {"id": "t1", "etape": etape, "role": role, "fonctionnalite": "f1", **plus}

    def test_tache_de_flux(self):
        m = mn.de_la_tache(FACTORY, self.tache("flux:f1-dev"), [fiche("dev-1", "dev")], FONCS)
        self.assertEqual((m["modele"], m["ramene"]), ("Haiku", False))
        self.assertEqual(mn.de_la_tache(FACTORY, self.tache("flux:f1-conception"), [fiche("d", "dev")], FONCS)["modele"],
                         "Opus")

    def test_relecture_correction_retour_suivent_l_etape_du_role(self):
        for etape in ("correction", "retour", "demande", "relecture"):
            role = "qa" if etape == "relecture" else "dev"
            m = mn.de_la_tache(FACTORY, self.tache(etape, role), [fiche("x", role)], FONCS)
            self.assertEqual(m["modele"], "Haiku" if role == "qa" else "Opus", etape)   # la première étape du rôle

    def test_cadrage_prototype_installation_gardent_la_fiche(self):
        for etape in ("cadrage", "prototype", "environnement", ""):
            self.assertIsNone(mn.de_la_tache(FACTORY, self.tache(etape), [fiche("d", "dev")], FONCS), etape)

    def test_montee_s_applique_a_la_tache(self):
        t = self.tache("flux:f1-dev", montee={"de": "Haiku", "a": "Sonnet", "raison": "deux échecs"})
        m = mn.de_la_tache(FACTORY, t, [fiche("d", "dev")], FONCS)
        self.assertEqual((m["modele"], m["source"]), ("Sonnet", "montee"))
        self.assertIn("deux échecs", m["raison"])

    def test_ramene_au_plus_haut_plafond_du_role(self):
        """Un projet existant : ses agents en Sonnet, une étape déduite en Opus ; la tâche part en Sonnet."""
        t = self.tache("flux:f1-conception")
        m = mn.de_la_tache(FACTORY, t, [fiche("d1", "dev", "Haiku"), fiche("d2", "dev", "Sonnet")], FONCS)
        self.assertEqual((m["modele"], m["ramene"]), ("Sonnet", True))
        self.assertIn("plafond", m["raison"])
        # sans agent du rôle, rien n'est ramené
        self.assertEqual(mn.de_la_tache(FACTORY, t, [], FONCS)["modele"], "Opus")

    def test_etape_inconnue(self):
        self.assertIsNone(mn.de_la_tache(FACTORY, self.tache("flux:f9-x"), [], FONCS))


class Proposition(unittest.TestCase):
    def test_agents_au_plafond_opus_et_modeles_sur_les_etapes(self):
        flux = [{"id": "dev", "nom": "Dev", "role": "dev", "service": "s"},
                {"id": "qa", "nom": "Contrôle", "role": "qa", "service": "s", "modele": "Sonnet", "justification": "J"},
                {"id": "val", "nom": "Essai", "validation": True}]
        agents = [{"cle": "dev-1", "role": "dev", "modele": "Haiku", "justification": "Mécanique."},
                  {"cle": "qa-1", "role": "qa", "modele": "Haiku", "justification": "Vérifie."},
                  {"cle": "x-1", "role": "x"}]
        etapes, recrues = mn.modeles_sur_les_etapes(flux, agents)
        self.assertEqual((etapes[0]["modele"], etapes[0]["justification"]), ("Haiku", "Mécanique."))
        self.assertEqual(etapes[1]["modele"], "Sonnet")          # l'étape avait le sien
        self.assertNotIn("modele", etapes[2])
        self.assertEqual({a["modele"] for a in recrues}, {"Opus"})
        self.assertEqual(agents[0]["modele"], "Haiku")           # rien n'est modifié en place
        self.assertNotIn("modele", flux[0])


class Plafond(unittest.TestCase):
    def test_plus_petit_plafond_suffisant_d_abord(self):
        liste = [fiche("o", "dev", "Opus"), fiche("f", "dev", "Fable"), fiche("s", "dev", "Sonnet"),
                 fiche("h", "dev", "Haiku"), fiche("q", "qa", "Sonnet")]
        self.assertEqual([x["cle"] for x in mn.possibles(liste, "dev", "Sonnet")], ["s", "o", "f"])
        self.assertEqual([x["cle"] for x in mn.possibles(liste, "dev", "Opus")], ["o", "f"])
        self.assertEqual([x["cle"] for x in mn.possibles(liste, "dev", None)], ["o", "f", "s", "h"])   # ordre des fiches


if __name__ == "__main__":
    unittest.main()
