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

    def test_apres_une_maquette_validee_la_correction_va_au_developpeur(self):
        """Essai réel 2026-11-23 : la correction partait chez le maquettiste et se terminait sans code ni livrable."""
        fac = json.loads(self.factory.read_text(encoding="utf-8"))
        fac["flux"] = ([{"id": "maquette", "nom": "Maquette", "role": "maquettiste", "service": "dev"},
                        {"id": "valid-maquette", "nom": "Validation", "validation": True}] + fac["flux"])
        self.factory.write_text(json.dumps(fac), encoding="utf-8")
        (self.dossier / "fiches" / "briefs" / "maquettiste.md").write_text(
            "# Brief du rôle : maquettiste\n\nMaquette.\n", encoding="utf-8")
        self.corriger()
        w = wf.de_la_fonctionnalite(fa.lire(self.factory), self.fonc())
        self.assertEqual(w["flux"][0]["role"], "dev")
        self.assertEqual(w["flux"][-1]["role"], "dev")

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

    def test_correctif_sans_doit_marcher_pose_la_validation_avec_l_attendu_de_la_fiche(self):
        """Essai réel (RoadmapReborn, 4 fois) : l'agent du correctif, jugeant l'anomalie déjà corrigée, rendait sa preuve
        sans `doit_marcher` ; l'étape était refaite pour rien. Pour une correction, ce qui doit marcher est connu : le
        résultat attendu de la fiche. La validation est posée sans relancer d'agent."""
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score", "fiche_correction": FICHE})
        preuve = self.dossier / "pieces" / "f1" / "preuve.md"
        preuve.parent.mkdir(parents=True, exist_ok=True)
        preuve.write_text("# Preuve\n\nLe test passe.\n", encoding="utf-8")
        muet = {"statut": "fait", "message": {"texte": "Déjà corrigé : rien à changer, le test passe."},
                "nature": "mecanique",
                "fichiers": [{"chemin": "pieces/f1/preuve.md", "titre": "Preuve", "element": "correction"}]}
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[muet])
        self.assertEqual(len(self.taches(etape="flux:f1-correctif")), 1)        # pas de relance
        (d,) = self.decisions("valider_etape")
        self.assertIn("revient à 0", d["doit_marcher"])
        self.assertLessEqual(len(d["doit_marcher"]), 480)

    def test_le_correctif_demande_le_rapport_complet_meme_sans_changement(self):
        matiere = regles._matiere(self.projet, self.etat, self.en_serie())
        self.assertIn("Même si tu ne changes rien", matiere)
        for c in ("doit_marcher", "pas_encore", "conclusion", "points_a_verifier", "nature"):
            self.assertIn(f'"{c}"', matiere)

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


PUBSPEC_FLUTTER = "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n"
APK = "build/app/outputs/flutter-apk/app-release.apk"


class TestCorrectionAvecApk(Base):
    """Essai réel FM_Stats (2026-11-24) : le code de la correction était fusionné, mais aucun APK n'était construit avant
    la validation du Directeur (la livraison, qui le construit, vient après elle) : « Rien à valider », série close à
    vide, et « correctif déjà présent » ne livrait rien. Dans un projet à livrable (APK), le correctif rend l'APK de sa
    branche avant la validation, même sans changement ; sans lui, l'étape est refaite."""
    corriger, decisions, en_serie = TestCorrection.corriger, TestCorrection.decisions, TestCorrection.en_serie

    def setUp(self):
        super().setUp()
        briefs = self.dossier / "fiches" / "briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        (briefs / "dev.md").write_text("# Brief du rôle : dev\n\nFait son métier.\n", encoding="utf-8")
        (self.dossier / "pubspec.yaml").write_text(PUBSPEC_FLUTTER, encoding="utf-8")

    def preuve(self):
        p = self.dossier / "pieces" / "f1" / "preuve.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Preuve\n\nLe test passe.\n", encoding="utf-8")
        return {"chemin": "pieces/f1/preuve.md", "titre": "Preuve", "element": "correction"}

    def apk(self):
        p = self.dossier / APK
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"PK\x03\x04apk")
        return {"chemin": APK, "titre": "APK", "element": "correction", "livrable": True}

    def test_la_matiere_du_correctif_demande_l_apk_par_construire_apk(self):
        matiere = regles._matiere(self.projet, self.etat, self.en_serie())
        self.assertIn("construire-apk", matiere)
        self.assertIn("même si tu n'as rien modifié", matiere)
        self.assertIn("jamais `flutter build`", matiere)
        tid = regles._creer_tache(self.projet, "Livraison", "f1", "dev", "flux:f1-livraison", element="correction")
        self.assertIn("construire-apk", regles._matiere(self.projet, self.etat, regles._tache(self.projet, tid)))

    def rendre(self, rapport):
        """Le rapport du correctif d'une correction cadrée, piloté jusqu'au bout."""
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score", "fiche_correction": FICHE})
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[rapport])

    def test_deja_present_sans_apk_refait_l_etape_avec_la_consigne(self):
        muet = {"statut": "fait", "message": {"texte": "Correctif déjà présent : rien à changer."},
                "nature": "mecanique", "fichiers": [self.preuve()], "doit_marcher": "La comparaison suit l'onglet."}
        self.rendre(muet)
        self.assertEqual(self.decisions("valider_etape"), [])
        correctifs = self.taches(etape="flux:f1-correctif")
        self.assertEqual(len(correctifs), 2)
        self.assertIn("construire-apk", " ".join(j["texte"] for j in correctifs[-1]["journal"]))

    def test_avec_l_apk_la_validation_le_montre_meme_pour_une_mecanique(self):
        rendu = {"statut": "fait", "message": {"texte": "Correctif déjà présent ; APK de la branche construit."},
                 "nature": "mecanique", "fichiers": [self.preuve(), self.apk()],
                 "doit_marcher": "La comparaison suit l'onglet."}
        self.rendre(rendu)
        (d,) = self.decisions("valider_etape")
        self.assertIn(APK, [x["chemin"] for x in d["fichiers"]])

    def test_un_projet_sans_livrable_n_exige_pas_d_apk(self):
        (self.dossier / "pubspec.yaml").unlink()
        rendu = {"statut": "fait", "message": {"texte": "Corrigé."}, "nature": "mecanique",
                 "fichiers": [self.preuve()], "doit_marcher": "Le score revient à 0."}
        self.rendre(rendu)
        self.assertEqual(len(self.decisions("valider_etape")), 1)


class TestCorrectionsDuMemeSujet(Base):
    """Essai réel FM_Stats (2026-11-24) : une nouvelle correction sur le sujet d'une chaîne encore ouverte (f5, bloquée)
    a lancé une chaîne concurrente (f6) qui modifiait les mêmes fichiers : conflits de fusion en cascade. Une correction
    qui recoupe une correction encore ouverte du projet (même fonctionnalité concernée, ou même titre) attend sa fin ;
    une demande indépendante part aussitôt, et le Directeur peut toujours lancer la correction en file tout de suite."""
    def corriger(self, texte="Le score ne se remet pas à zéro", **plus):
        return self.traiter(type="fonctionnalite", texte=texte, nature="correction", **plus)

    def setUp(self):
        super().setUp()
        briefs = self.dossier / "fiches" / "briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        (briefs / "dev.md").write_text("# Brief du rôle : dev\n\nFait son métier.\n", encoding="utf-8")
        self.fonctionnalite(etape="terminee")         # f1 : la fonctionnalité que les corrections concernent

    def en_file(self, fid):
        f = self.fonc(fid)
        return f.get("en_file_derriere"), f.get("workflow")

    def test_une_correction_du_meme_sujet_attend_la_fin_de_la_premiere(self):
        self.corriger(concerne="f1")                                         # f2 : part
        d, actions = self.corriger(concerne="f1", texte="La comparaison doit suivre l'onglet actif")    # f3
        self.assertEqual(actions, [])
        self.assertEqual(self.en_file("f2"), (None, "w-f2"))
        self.assertEqual(self.en_file("f3"), ("f2", None))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        dit = self.fonc("f3")["discussion"][-1]
        self.assertIn("f2", dit["texte"])
        self.assertIn(regles.LANCER_LA_CORRECTION_MAINTENANT, dit["questions"][0]["choix"])
        regles.avancer(self.projet, self.etat)
        self.assertEqual(self.en_file("f3"), ("f2", None))                # rien ne part tant que f2 est ouverte
        self.ok("fonctionnalite", entree={"id": "f2", "etape": "terminee"})
        regles.avancer(regles.Projet(self.factory, feu_vert=lambda: True), regles.nouvel_etat())   # moteur relancé
        self.assertEqual(self.en_file("f3"), (None, "w-f3"))

    def test_meme_titre_sans_fonctionnalite_concernee(self):
        self.corriger()
        _, actions = self.corriger()
        self.assertEqual(self.en_file("f3"), ("f2", None))

    def test_une_correction_independante_part_aussitot(self):
        self.corriger(concerne="f1")
        self.corriger(texte="Le bouton Partager ne fait rien")
        self.assertEqual(self.en_file("f3"), (None, "w-f3"))

    def test_le_directeur_peut_la_lancer_tout_de_suite(self):
        self.corriger(concerne="f1")
        self.corriger(concerne="f1", texte="Autre chose sur l'écran")
        self.traiter(type="message", fonctionnalite="f3", texte="Plus tard")
        self.assertEqual(self.en_file("f3"), ("f2", None))                # un autre message ne la débloque pas
        self.traiter(type="message", fonctionnalite="f3", texte=regles.LANCER_LA_CORRECTION_MAINTENANT)
        self.assertEqual(self.en_file("f3"), (None, "w-f3"))

    def test_les_corrections_en_file_partent_l_une_apres_l_autre(self):
        self.corriger(concerne="f1")
        self.corriger(concerne="f1", texte="Deuxième")
        self.corriger(concerne="f1", texte="Troisième")
        self.assertEqual(self.en_file("f4")[0], "f2")
        self.ok("fonctionnalite", entree={"id": "f2", "etape": "terminee"})
        regles.avancer(self.projet, self.etat)
        self.assertEqual(self.en_file("f3"), (None, "w-f3"))
        self.assertEqual(self.en_file("f4"), ("f3", None))               # derrière celle qui vient de partir

    def test_l_outil_refuse_une_file_vers_une_fonctionnalite_inconnue(self):
        code, objet = self.outil("lancer", "fonctionnalite", entree={"id": "f1", "en_file_derriere": "f9"})
        self.assertEqual(code, 1)
        code, objet = self.outil("lancer", "fonctionnalite", entree={"id": "f1", "en_file_derriere": "f1"})
        self.assertEqual(code, 1)


class TestPetiteCorrection(TestCorrection):
    """Essai réel (2026-11-17) : deux lignes de CSS ont payé diagnostic, correctif et livraison, trois agents et 0,94 €.
    Une petite correction, jugée au diagnostic, fait le correctif dans la même tâche ; la livraison est faite par
    l'outil."""
    PETITE = {**FICHE, "taille": "petite"}
    CORRECTIF = {"doit_marcher": "Le score revient à 0.", "en_clair": "Le score repart de zéro.",
                 "conclusion": "Validez si le test passe.", "points_a_verifier": ["a", "b", "c"]}

    def diagnostic(self, fiche, **plus):
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        r = {"nom": "Corriger : score", "fiche_correction": fiche,
             "message": {"texte": "Fait.", "images": [{"chemin": "pieces/f1/apres.png", "legende": "Après"}]}, **plus}
        return regles._suite_cadrage(self.projet, self.etat, t, r)

    def test_le_diagnostic_demande_la_taille(self):
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        matiere = regles._matiere(self.projet, self.etat, t)
        self.assertIn("**Juge la taille**", matiere)
        self.assertIn("Petite correction : fais le correctif tout de suite", matiere)

    def test_le_correctif_fait_au_diagnostic_va_droit_a_la_validation(self):
        preuve = self.dossier / "pieces" / "f1" / "preuve.md"     # la preuve la plus simple : le test avant / après
        preuve.parent.mkdir(parents=True, exist_ok=True)
        preuve.write_text("# Preuve\n\nLe test échouait avant, passe après.\n", encoding="utf-8")
        actions = self.diagnostic(self.PETITE, nature="mecanique",
                                  fichiers=[{"chemin": "pieces/f1/preuve.md", "titre": "Preuve"}], **self.CORRECTIF)
        self.assertFalse(any(a[0] == "agent" for a in actions))
        (c,) = self.taches(etape="flux:f1-correctif")
        self.assertEqual(c["colonne"], "fait")
        self.assertIn(regles.JOURNAL_CORRECTIF_AU_DIAGNOSTIC, [j["texte"] for j in c["journal"]])
        self.assertEqual(self.fonc()["cahier"]["parcours"], regles.PARCOURS_CORRECTION_COURTE)
        (d,) = self.decisions("valider_etape")
        # le Directeur valide : la livraison est faite par l'outil, sans agent, et l'élément est fini
        _, actions = self.traiter(type="valider_etape", decision=d["id"], verdict="valider")
        self.assertFalse(any(a[0] == "agent" for a in actions))
        (liv,) = self.taches(etape="flux:f1-livraison")
        self.assertEqual(liv["colonne"], "fait")
        self.assertIn(regles.JOURNAL_LIVREE_PAR_L_OUTIL, [j["texte"] for j in liv["journal"]])
        self.assertEqual(self.etat["elements"]["f1/correction"]["phase"], "fait")
        regles.avancer(self.projet, self.etat)
        ouvertes = [t["etape"] for t in self.taches(fonctionnalite="f1") if t["colonne"] != "fait"]
        self.assertEqual(ouvertes, ["cadrage"])     # ni relecture ni agent après la validation (le cadrage : appel direct)

    def test_une_petite_correction_sans_preuve_passe_par_le_correctif(self):
        self.diagnostic(self.PETITE)       # ni `doit_marcher` : le correctif n'est pas fait, un agent le fera
        regles.avancer(self.projet, self.etat)
        (c,) = self.taches(etape="flux:f1-correctif")
        self.assertNotEqual(c["colonne"], "fait")
        self.assertEqual(self.fonc()["cahier"]["parcours"], regles.PARCOURS_CORRECTION_COURTE)

    def test_une_correction_normale_garde_le_parcours_complet(self):
        self.diagnostic({**FICHE, "taille": "normale"}, **self.CORRECTIF)
        regles.avancer(self.projet, self.etat)
        (c,) = self.taches(etape="flux:f1-correctif")
        self.assertNotEqual(c["colonne"], "fait")
        self.assertNotIn("parcours", self.fonc()["cahier"])
        v = self.etat["elements"]["f1/correction"]
        s = regles._production(self.projet, "f1")[2]
        self.assertFalse(regles._livree_par_l_outil(self.projet, v, s))

    def test_une_legende_trop_longue_est_raccourcie_pas_refusee(self):
        from bureau import releve as rel
        from orchestrateur import outil
        (x,) = outil.liste_d_images([{"chemin": "a.png", "legende": "mot " * 80}], "images")
        self.assertLessEqual(len(x["legende"]), rel.MAX_LEGENDE)
        self.assertTrue(x["legende"].endswith("…"))

    def test_un_refus_redonne_le_rapport_entier(self):
        s = regles._supplement_de_refus("légende trop longue.", {"texte": "m"},
                                        {"fiche_correction": FICHE, "message": {"texte": "m"}})
        self.assertIn("en entier", s)
        self.assertIn("fiche_correction", s)


if __name__ == "__main__":
    unittest.main()
