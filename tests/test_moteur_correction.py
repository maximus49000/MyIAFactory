"""Le parcours court d'une correction : ni genre, ni workflow proposé, ni cahier."""
import json
import unittest
from unittest import mock

from moteur import regles
from orchestrateur import factory as fa
from orchestrateur import workflows as wf
from tests.test_moteur_regles import Base

FICHE_TOM = ("Clé : qa-1\nPrénom : Tom\nRôle : testeur\nService : dev\nModèle : Sonnet\nLieu : local\n\n"
             "Vérifie.\n\n## Leçons\n")
FICHE = {"symptome": "reste à 12", "reproduction": ["perdre"], "attendu": "revient à 0", "piste": None}


class TestCorrection(Base):
    def setUp(self):
        super().setUp()
        briefs = self.dossier / "fiches" / "briefs"      # un projet installé a le brief de chaque rôle de son flux
        briefs.mkdir(parents=True, exist_ok=True)
        for role in ("dev", "testeur"):
            (briefs / f"{role}.md").write_text(f"# Brief du rôle : {role}\n\nFait son métier.\n", encoding="utf-8")

    def corriger(self, **plus):
        return self.traiter(type="fonctionnalite", texte="Le score ne se remet pas à zéro", nature="correction",
                            **plus)

    def decisions(self, genre=None):
        return [d for d in self.ok("etat")["decisions"] if genre is None or d["genre"] == genre]

    def flux_de(self, fid="f1"):
        return [s["id"] for s in wf.de_la_fonctionnalite(fa.lire(self.factory), self.fonc(fid))["flux"]]

    def test_aucun_jugement_de_genre_ni_de_workflow(self):
        d, actions = self.corriger()
        self.assertFalse(any(a[0] == "juger" for a in actions))
        f = self.fonc()
        self.assertEqual((f["nature"], f["workflow"], f["etape"]), ("correction", "w-f1", "cadrage"))
        self.assertEqual(self.decisions("organisation"), [])
        (t,) = self.taches(etape="cadrage")
        self.assertTrue(t["titre"].startswith("Diagnostic : "), t["titre"])     # pas « Cadrage » pour une anomalie
        self.assertEqual(self.flux_de(), ["f1-correctif", "f1-validation", "f1-livraison"])     # sans rôle QA : pas de vérification
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def recette(self, agent=True):
        """Le projet a un métier de vérification (`testeur`), avec ou sans agent pour le tenir."""
        fac = json.loads(self.factory.read_text(encoding="utf-8"))
        fac["flux"].insert(1, {"id": "recette", "nom": "Recette", "role": "testeur", "service": "dev"})
        self.factory.write_text(json.dumps(fac), encoding="utf-8")
        if agent:
            (self.dossier / "fiches" / "tom.md").write_text(FICHE_TOM, encoding="utf-8")
        return mock.patch.object(regles, "_metiers_du_projet", return_value={"dev": {}, "testeur": {}})

    def test_le_role_qa_du_projet_ajoute_la_verification(self):
        with self.recette():
            self.corriger()
        self.assertEqual(self.flux_de(), ["f1-correctif", "f1-verification", "f1-validation", "f1-livraison"])

    def test_un_role_qa_sans_agent_n_empeche_pas_la_correction(self):
        with self.recette(agent=False):
            self.corriger()
        self.assertEqual(self.flux_de(), ["f1-correctif", "f1-validation", "f1-livraison"])
        self.assertIn("sans vérification", " ".join(m["texte"] for m in self.fonc()["discussion"]))

    def test_un_metier_introuvable_pose_la_question_au_directeur(self):
        with mock.patch.object(regles, "_role_production", return_value="peintre"):
            d, actions = self.corriger()
        self.assertEqual(actions, [])
        f = self.fonc()
        self.assertIsNone(f.get("workflow"))
        self.assertEqual(self.taches(etape="cadrage"), [])
        question = f["discussion"][-1]
        self.assertTrue(question["attend"])
        self.assertIn("quel métier", question["texte"])
        self.assertEqual(question["questions"][0]["choix"], ["dev", "Plus tard"])     # ni le relecteur
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(regles.avancer(self.projet, self.etat), [])     # rien ne démarre avant la réponse
        self.assertEqual(self.taches(etape="cadrage"), [])
        self.traiter(type="message", fonctionnalite="f1", texte="devops")     # pas un des métiers : « dev » ≠ « devops »
        self.assertIsNone(self.fonc().get("workflow"))
        # la réponse du Directeur : le métier choisi corrige, le cadrage court démarre
        self.traiter(type="message", fonctionnalite="f1", texte="dev")
        self.assertEqual(self.fonc()["workflow"], "w-f1")
        self.assertEqual(len(self.taches(etape="cadrage")), 1)

    def test_fiche_de_cadrage_lance_la_serie_d_un_seul_element(self):
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score", "fiche_correction": FICHE})
        f = self.fonc()
        self.assertEqual(f["etape"], "serie")
        self.assertEqual([x["id"] for x in f["file"]], ["correction"])
        self.assertEqual(self.decisions("valider_cahier"), [])
        self.assertIn("Attendu : revient à 0", f["cahier"]["etapes"])
        regles.avancer(self.projet, self.etat)       # la série prend son seul élément, sans méthode ni prototype
        (flux,) = self.taches(etape="flux:f1-correctif")
        self.assertEqual(flux["element"], "correction")

    def test_la_fiche_se_lit_en_clair_puis_en_detail(self):
        # Double lecture demandée par le Directeur : une vulgarisation pour n'importe qui, puis la description complète.
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        en_clair = "Le score ne repart pas de zéro quand on recommence une partie."
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score",
                                                           "fiche_correction": {**FICHE, "en_clair": en_clair}})
        f = self.fonc()
        self.assertEqual(f["cahier"]["etapes"][0], "En clair : " + en_clair)
        self.assertTrue(f["cahier"]["etapes"][1].startswith("Symptôme : "))
        self.assertIn(en_clair, f["discussion"][-1]["texte"])
        self.assertEqual(f["en_clair"], en_clair)          # en tête du panneau de la tâche
        # une fiche sans « en clair » reste acceptée (rien ne bloque) : elle commence au symptôme

    def test_la_validation_reprend_l_en_clair_de_la_fiche(self):
        # Le Directeur lit d'abord, sans jargon, le problème et ce qu'on fait : en tête de sa fenêtre de validation.
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        en_clair = "Le score ne repart pas de zéro quand on recommence une partie."
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score",
                                                           "fiche_correction": {**FICHE, "en_clair": en_clair}})
        self.assertEqual(regles._en_clair_de_la_fiche(self.projet, "f1"), en_clair)
        self.fonctionnalite()                       # une fonctionnalité ordinaire : pas de lecture de fiche
        self.assertIsNone(regles._en_clair_de_la_fiche(self.projet, "f2"))

    def test_en_clair_est_un_champ_de_la_validation(self):
        from bureau import releve as rel
        from moteur import rapport
        self.assertIn("en_clair", [c for c, _, _ in rel.CHAMPS_DIT])
        import json
        brut = {"statut": "fait", "en_clair": "  Le test  oubliait Zendesk. ", "doit_marcher": "x"}
        r = rapport.lire("```json\n" + json.dumps(brut, ensure_ascii=False) + "\n```")
        self.assertEqual(r.get("en_clair"), "Le test oubliait Zendesk.")

    def test_le_rapport_de_cadrage_avec_fiche_ferme_la_tache(self):
        _, actions = self.corriger()
        self.piloter(actions, rapports=[{"statut": "fait", "message": {"texte": "Je reproduis."},
                                         "nom": "Corriger : score", "fiche_correction": FICHE}], limite=1)
        (t,) = self.taches(etape="cadrage")
        self.assertEqual(t["colonne"], "fait")
        self.assertEqual(self.fonc()["etape"], "serie")

    def en_serie(self):
        """Une correction cadrée, en série : rend la tâche du correctif."""
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score", "fiche_correction": FICHE})
        regles.avancer(self.projet, self.etat)
        (flux,) = self.taches(etape="flux:f1-correctif")
        return flux

    def test_la_matiere_du_correctif_et_de_la_livraison(self):
        matiere = regles._matiere(self.projet, self.etat, self.en_serie())
        self.assertIn("Symptôme : reste à 12", matiere)
        self.assertIn("## Correctif", matiere)
        self.assertNotIn("## Livraison", matiere)
        self.assertNotIn("Méthode validée", matiere)
        tid = regles._creer_tache(self.projet, "Livraison", "f1", "dev", "flux:f1-livraison", element="correction")
        matiere = regles._matiere(self.projet, self.etat, regles._tache(self.projet, tid))
        self.assertIn("Symptôme : reste à 12", matiere)
        self.assertIn("## Livraison", matiere)
        self.assertNotIn("## Correctif", matiere)

    def test_la_matiere_d_une_fonctionnalite_ordinaire_ne_change_pas(self):
        self.serie(n=1)
        regles.avancer(self.projet, self.etat)
        (t,) = self.taches(etape="flux:dev")
        matiere = regles._matiere(self.projet, self.etat, t)
        self.assertIn("Méthode validée : pieces/f1/methode-v1.md", matiere)
        self.assertNotIn("correction**", matiere)
        self.assertNotIn("Symptôme", matiere)

    def test_trop_de_tours_laisse_la_correction_de_cote_sans_parler_de_methode(self):
        self.en_serie()
        v = self.etat["elements"]["f1/correction"]
        regles._methode_a_revoir(self.projet, self.etat, v, "cet élément a déjà eu 3 tours de corrections")
        self.assertEqual(self.decisions("methode_a_revoir"), [])
        (t,) = self.taches(etape="flux:f1-correctif")
        self.assertIn("correction qui n'aboutit pas", t["bloquee"])
        dernier = self.fonc()["discussion"][-1]["texte"]
        self.assertIn("La correction n'aboutit pas", dernier)
        self.assertNotIn("méthode", dernier)

    def test_une_fiche_sans_attendu_laisse_le_cadrage_ouvert(self):
        _, actions = self.corriger()
        self.piloter(actions, rapports=[{"statut": "fait", "message": {"texte": "Je cherche."},
                                         "fiche_correction": {**FICHE, "attendu": " "}}], limite=1)
        (t,) = self.taches(etape="cadrage")
        self.assertNotEqual(t["colonne"], "fait")
        self.assertEqual(self.fonc()["etape"], "cadrage")

    def test_une_fonctionnalite_concernee_disparue_est_ignoree(self):
        self.assertEqual(regles._contexte_concerne(self.projet, {"concerne": "f9"}), [])

    def test_la_fonctionnalite_concernee_est_dans_la_matiere(self):
        self.fonctionnalite(etape="serie")       # f1 : une fonctionnalité existante
        self.corriger(concerne="f1")
        (t,) = self.taches(etape="cadrage", fonctionnalite="f2")
        matiere = regles._matiere(self.projet, self.etat, t)
        self.assertIn("Fonctionnalité concernée", matiere)
        self.assertIn("fiche_correction", matiere)
        self.assertNotIn("cahier des charges", matiere)

    def test_l_outil_refuse_une_fonctionnalite_ordinaire(self):
        self.fonctionnalite()
        code, objet = self.outil("lancer", "organisation", entree={"action": "correction", "fonctionnalite": "f1",
                                                                   "role_production": "dev"})
        self.assertEqual(code, 1)
        self.assertIn("n'est pas une correction", objet["erreur"])


if __name__ == "__main__":
    unittest.main()
