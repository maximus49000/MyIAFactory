"""Le parcours court d'une correction : ni genre, ni workflow proposé, ni cahier."""
import json
import os
import time
import unittest
from pathlib import Path
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

    def test_fonctionnalite_creee_garde_captures(self):
        self.corriger(captures=True)
        self.assertIs(self.fonc()["captures"], True)

    def test_sans_champ_captures_vaut_non(self):
        self.corriger()
        self.assertIs(self.fonc()["captures"], False)

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

    def test_un_rapport_de_cadrage_sans_nom_est_applique(self):
        # Essai réel (FM_Stats, f7) : un « en clair » sans « nom » levait KeyError 'nom' ; le diagnostic restait sans
        # restitution au Directeur.
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {"en_clair": "Rien à corriger.", "fiche_correction": FICHE})
        self.assertEqual(self.fonc()["etape"], "serie")
        self.assertEqual(self.fonc()["en_clair"], "Rien à corriger.")

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

    def dater(self, chemin, decalage):
        """Date un fichier du projet : `decalage` secondes par rapport à maintenant (le moteur écrit son suivi pendant
        le test : un APK « récent » doit donc être daté dans le futur pour l'être vraiment)."""
        t = time.time() + decalage
        os.utime(self.dossier / chemin, (t, t))

    def source(self, nom="lib/main.dart", decalage=0):
        s = self.dossier / nom
        s.parent.mkdir(parents=True, exist_ok=True)
        s.write_text("void main() {}\n", encoding="utf-8")
        self.dater(nom, decalage)

    def test_un_apk_plus_ancien_que_le_code_n_est_pas_montre_au_directeur(self):
        """Essai réel FM_Stats (2026-11-25, deux fois) : l'APK transmis datait d'avant les corrections fusionnées ; le
        Directeur l'installait et ne voyait rien de changé. Un APK construit avant la dernière modification du code est
        refusé : l'étape est refaite, avec la consigne de le reconstruire."""
        rendu = {"statut": "fait", "message": {"texte": "Corrigé ; APK joint."}, "nature": "mecanique",
                 "fichiers": [self.preuve(), self.apk()], "doit_marcher": "La comparaison suit l'onglet."}
        self.source()
        self.dater(APK, -3600)                      # l'APK date d'il y a une heure, le code d'à l'instant
        self.rendre(rendu)
        self.assertEqual(self.decisions("valider_etape"), [])
        correctifs = self.taches(etape="flux:f1-correctif")
        self.assertEqual(len(correctifs), 2)
        consigne = " ".join(j["texte"] for j in correctifs[-1]["journal"])
        self.assertIn("construire-apk", consigne)
        self.assertIn("plus ancien", consigne)

    def test_un_apk_construit_apres_le_code_est_montre(self):
        rendu = {"statut": "fait", "message": {"texte": "Corrigé ; APK joint."}, "nature": "mecanique",
                 "fichiers": [self.preuve(), self.apk()], "doit_marcher": "La comparaison suit l'onglet."}
        self.source()
        self.dater(APK, 7200)                       # construit après toutes les écritures du test
        self.rendre(rendu)
        self.assertEqual(len(self.decisions("valider_etape")), 1)

    def test_les_dossiers_de_sortie_et_les_documents_ne_comptent_pas_comme_du_code(self):
        rendu = {"statut": "fait", "message": {"texte": "Corrigé ; APK joint."}, "nature": "mecanique",
                 "fichiers": [self.preuve(), self.apk()], "doit_marcher": "La comparaison suit l'onglet."}
        for nom in ("build/intermediates/x.class", ".dart_tool/package_config.json", "CHANGELOG.md",
                    ".factory/suivi.json", "Livrables/FM_Stats_1.apk"):
            self.source(nom, decalage=10800)        # plus récents que l'APK, et pourtant ignorés
        self.dater(APK, 7200)
        self.rendre(rendu)
        self.assertEqual(len(self.decisions("valider_etape")), 1)

    def test_un_projet_sans_livrable_n_exige_pas_d_apk(self):
        (self.dossier / "pubspec.yaml").unlink()
        rendu = {"statut": "fait", "message": {"texte": "Corrigé."}, "nature": "mecanique",
                 "fichiers": [self.preuve()], "doit_marcher": "Le score revient à 0."}
        self.rendre(rendu)
        self.assertEqual(len(self.decisions("valider_etape")), 1)

    # --- Les captures de validation (conception 2026-11-25-captures-de-validation, §5.2, §5.4, §6 bis).

    def rendu_frais(self, texte="Corrigé ; APK joint."):
        """Le rapport du correctif avec un APK construit après le code (à jour)."""
        rendu = {"statut": "fait", "message": {"texte": texte}, "nature": "mecanique",
                 "fichiers": [self.preuve(), self.apk()], "doit_marcher": "La comparaison suit l'onglet.",
                 "points_a_verifier": ["Le score revient à 0 après une défaite"]}
        self.source()
        self.dater(APK, 7200)
        return rendu

    def image(self, nom):
        chemin = f"pieces/f1/captures/{nom}.png"
        p = self.dossier / chemin
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        return {"chemin": chemin, "legende": f"Écran {nom} : le score revient à 0"}

    def capture(self, images, texte="Captures prises sur l'émulateur."):
        return {"statut": "fait", "message": {"texte": texte, "images": images}}

    def equipe_au_serveur(self, places=1, hors_ligne=None, polyvalent=False):
        """Le projet a un agent du serveur (dev-9), `places` places serveur, et un serveur en ligne (sinon la raison) :
        sans cela, une capture ne peut pas partir et la validation est posée sans capture."""
        from tests.orch_aide import FICHE_LEA
        fiche = (FICHE_LEA.replace("Clé : dev-1", "Clé : dev-9").replace("Prénom : Léa", "Prénom : Sam")
                 .replace("Lieu : local", "Lieu : serveur"))
        if polyvalent:
            fiche = "Clé : dev-9\nPrénom : Sam\nLieu : serveur\n"      # le modèle polyvalent (test_moteur_polyvalents)
        (self.dossier / "fiches" / "sam.md").write_text(fiche, encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["agents_serveur_max"] = places
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        from orchestrateur import outil
        p = mock.patch.object(outil, "raison_serveur", return_value=hors_ligne)
        p.start()
        self.addCleanup(p.stop)

    def cadrer_la_correction(self, captures=True, serveur=True):
        if serveur and not (self.dossier / "fiches" / "sam.md").exists():
            self.equipe_au_serveur()
        self.corriger(captures=captures)
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {"nom": "Corriger : score", "fiche_correction": FICHE})

    def jusqu_aux_captures(self):
        """Le correctif rendu avec un APK à jour : l'agent de capture est parti, son rapport n'est pas encore revenu."""
        self.cadrer_la_correction()
        actions = regles.avancer(self.projet, self.etat)
        self.assertEqual([a[0] for a in actions], ["agent"])
        self.piloter(actions, rapports=[self.rendu_frais()], limite=1)
        (t,) = self.taches(etape="captures:f1-validation")
        return t

    def retour(self, tid, rapport=None, erreur=None, **drapeaux):
        from moteur import agents
        from tests.test_moteur_regles import _lu
        e = agents.Execution(tid, "dev-1", rapport=_lu(rapport) if rapport else None, erreur=erreur)
        for k, val in drapeaux.items():
            setattr(e, k, val)
        return regles.traiter_retour(self.projet, e, self.etat)

    def test_captures_demandees_lance_la_tache_avant_la_validation(self):
        t = self.jusqu_aux_captures()
        self.assertEqual(self.decisions("valider_etape"), [])
        self.assertTrue(t["active"])
        self.assertEqual(t["element"], "correction")
        self.assertEqual(self.etat["elements"]["f1/correction"]["phase"], "captures")
        self.assertEqual(self.taches(etape="validation:f1-validation"), [])

    def test_rapport_de_capture_est_fusionne_et_la_validation_posee(self):
        self.cadrer_la_correction()
        images = [self.image(n) for n in ("menu", "partie", "score")]
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais(), self.capture(images)])
        (d,) = self.decisions("valider_etape")
        self.assertEqual([c["chemin"] for c in d["captures"]], [x["chemin"] for x in images])
        self.assertEqual(d["captures"][0]["legende"], "Écran menu : le score revient à 0")
        self.assertNotIn("sans_capture", d)
        chemins = [x["chemin"] for x in d["fichiers"]]
        self.assertIn(APK, chemins)
        self.assertIn("pieces/f1/preuve.md", chemins)
        self.assertEqual(d["doit_marcher"], "La comparaison suit l'onglet.")
        self.assertEqual(d["points"], ["Le score revient à 0 après une défaite"])
        (t,) = self.taches(etape="captures:f1-validation")
        self.assertEqual(t["colonne"], "fait")
        self.assertEqual(self.etat["elements"]["f1/correction"]["phase"], "validation")

    def test_plus_de_huit_captures_sont_tronquees_a_huit(self):
        self.cadrer_la_correction()
        images = [self.image(f"etape-{k:02d}") for k in range(1, 11)]
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais(), self.capture(images)])
        (d,) = self.decisions("valider_etape")
        self.assertEqual(regles.CAPTURES_MAX, 8)
        self.assertEqual([c["chemin"] for c in d["captures"]], [x["chemin"] for x in images[:8]])

    def test_zero_capture_pose_la_validation_avec_ecran_introuvable(self):
        self.cadrer_la_correction()
        muet = self.capture([], texte="écran introuvable : le menu Statistiques n'existe pas dans cet APK.")
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais(), muet])
        (d,) = self.decisions("valider_etape")
        self.assertEqual(d["captures"], [])
        self.assertTrue(d["sans_capture"].startswith("écran introuvable :"), d["sans_capture"])
        self.assertIn("Statistiques", d["sans_capture"])
        self.assertIn(APK, [x["chemin"] for x in d["fichiers"]])

    def test_zero_capture_sans_raison_dite_reste_ecran_introuvable(self):
        self.cadrer_la_correction()
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[self.rendu_frais(), self.capture([], texte="Rien trouvé.")])
        (d,) = self.decisions("valider_etape")
        self.assertTrue(d["sans_capture"].startswith("écran introuvable :"), d["sans_capture"])

    def test_sans_oui_aucune_tache_de_capture(self):
        self.cadrer_la_correction(captures=False)
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais()])
        self.assertEqual(self.taches(etape="captures:f1-validation"), [])
        (d,) = self.decisions("valider_etape")
        self.assertNotIn("captures", d)
        self.assertNotIn("sans_capture", d)

    def test_apk_perime_ne_lance_pas_la_capture(self):
        """Le rapport du correctif arrivé pendant l'arrêt du moteur (relu dans le suivi) : la validation est posée avec ce
        qu'il y a à vérifier, même avec un APK plus ancien que le code ; jamais de capture sur cet APK."""
        self.cadrer_la_correction()
        regles.avancer(self.projet, self.etat)
        (flux,) = self.taches(etape="flux:f1-correctif")
        for x in (self.preuve(), self.apk()):
            regles.lancer(self.projet, "document", {"fonctionnalite": "f1", "chemin": x["chemin"], "titre": x["titre"],
                                                    "agent": "dev-1", "etape": "flux:f1-correctif", "tache": flux["id"],
                                                    "element": "correction",
                                                    **({"livrable": True} if x.get("livrable") else {})})
        self.source()
        self.dater(APK, -3600)
        regles.lancer(self.projet, "tache", {"id": flux["id"], "colonne": "fait", "active": False,
                                             "journal": ["Corrigé ; APK joint."]})
        self.etat = regles.nouvel_etat()          # le moteur relancé
        regles.reprendre_la_serie(self.projet, self.etat, "f1")
        self.assertEqual(self.taches(etape="captures:f1-validation"), [])
        (d,) = self.decisions("valider_etape")
        self.assertEqual(d["sans_capture"], "APK absent ou périmé")
        self.assertEqual(d["captures"], [])

    def test_captures_demandees_dit_pourquoi_s_en_passer(self):
        self.cadrer_la_correction()
        regles.avancer(self.projet, self.etat)
        v = self.etat["elements"]["f1/correction"]
        v["dernier_rapport"] = {"fichiers": [self.preuve()]}
        self.assertEqual(regles._captures_demandees(self.projet, v), "APK absent ou périmé")
        v["dernier_rapport"] = {"fichiers": [self.preuve(), self.apk()]}
        self.source()
        self.dater(APK, 7200)
        self.assertIsNone(regles._captures_demandees(self.projet, v))
        self.projet.pilote_possible = lambda: "aucun serveur avec l'image de l'émulateur"
        self.assertEqual(regles._captures_demandees(self.projet, v),
                         "émulateur indisponible : aucun serveur avec l'image de l'émulateur")
        self.projet.pilote_possible = lambda: None
        self.assertIsNone(regles._captures_demandees(self.projet, v))

    def test_emulateur_indisponible_pose_la_validation_sans_capture(self):
        self.projet.pilote_possible = lambda: "accord recette-emulateur absent"
        self.cadrer_la_correction()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais()])
        self.assertEqual(self.taches(etape="captures:f1-validation"), [])
        (d,) = self.decisions("valider_etape")
        self.assertEqual(d["sans_capture"], "émulateur indisponible : accord recette-emulateur absent")

    def test_agent_en_echec_ou_hors_delai_pose_la_validation_sans_capture(self):
        t = self.jusqu_aux_captures()
        self.retour(t["id"], erreur="l'appel a échoué : durée maximale", echeance=True)
        (d,) = self.decisions("valider_etape")
        self.assertEqual(d["captures"], [])
        self.assertIn("hors délai", d["sans_capture"])
        self.assertIn("15 minutes", d["sans_capture"])
        self.assertIn(APK, [x["chemin"] for x in d["fichiers"]])
        (t,) = self.taches(etape="captures:f1-validation")
        self.assertEqual(t["colonne"], "fait")
        self.assertFalse(t.get("bloquee"))

    def test_rapport_en_echec_de_l_agent_de_capture_pose_la_validation(self):
        self.cadrer_la_correction()
        echec = {"statut": "echec", "message": {"texte": "L'émulateur ne démarre pas."}}
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais(), echec])
        (d,) = self.decisions("valider_etape")
        self.assertIn("L'émulateur ne démarre pas.", d["sans_capture"])
        (t,) = self.taches(etape="captures:f1-validation")
        self.assertFalse(t.get("bloquee"))

    def test_creneau_pris_trop_longtemps_pose_la_validation_sans_capture(self):
        t = self.jusqu_aux_captures()
        self.retour(t["id"], erreur="l'appel a échoué : Aucune place d'agent libre après 1200 s : lancement abandonné")
        (d,) = self.decisions("valider_etape")
        self.assertIn("20 minutes", d["sans_capture"])
        self.assertEqual(len(self.taches(etape="captures:f1-validation")), 1)      # pas de nouvel essai

    def test_capture_non_lancee_faute_de_pilote_pose_la_validation_avec_la_raison(self):
        """Le moteur n'a pas lancé l'agent de capture (pilote impossible au départ) : la validation est posée sans
        capture, avec la raison qu'il donne ; aucun nouvel essai."""
        t = self.jusqu_aux_captures()
        self.retour(t["id"], erreur="x", sans_capture="émulateur indisponible : accord recette-emulateur absent")
        (d,) = self.decisions("valider_etape")
        self.assertEqual((d["captures"], d["sans_capture"]),
                         ([], "émulateur indisponible : accord recette-emulateur absent"))
        self.assertIn(APK, [x["chemin"] for x in d["fichiers"]])
        self.assertEqual(len(self.taches(etape="captures:f1-validation")), 1)

    def test_la_capture_part_chez_un_agent_du_serveur(self):
        """Un projet à places serveur : l'agent de capture est un agent du serveur (le pilote y conduit l'émulateur),
        jamais l'agent du poste qui a fait l'étape d'avant."""
        t = self.jusqu_aux_captures()
        self.assertEqual(t["agent"], "dev-9")

    def capture_close_sans_depart(self, raison):
        """Le correctif rendu : la capture, qui ne peut pas partir, est close aussitôt (jamais confiée à un agent) et la
        validation posée sans capture avec `raison`."""
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais()])
        (t,) = self.taches(etape="captures:f1-validation")
        self.assertEqual(t["colonne"], "fait")
        self.assertFalse(t.get("debut"))                       # jamais partie
        (d,) = self.decisions("valider_etape")
        self.assertEqual((d["captures"], d["sans_capture"]), ([], raison))
        self.assertIn(APK, [x["chemin"] for x in d["fichiers"]])

    def test_serveur_hors_ligne_la_capture_est_close_aussitot(self):
        self.equipe_au_serveur(hors_ligne="hors ligne")
        self.cadrer_la_correction()
        self.capture_close_sans_depart("émulateur indisponible : serveur hors ligne")

    def test_sans_place_serveur_la_capture_est_close_aussitot(self):
        """Le poste seul (aucune place serveur), ses places occupées ou non : la validation n'attend pas un agent du
        poste qui serait de toute façon refusé."""
        self.equipe_au_serveur(places=0)
        self.cadrer_la_correction()
        self.capture_close_sans_depart("émulateur indisponible : aucune place d'agent serveur réglée pour ce projet")

    def test_sans_agent_du_serveur_la_capture_ne_peut_pas_partir(self):
        """(Le flux d'un tel projet n'atteint pas la capture aujourd'hui : la règle est vérifiée directement.)"""
        from orchestrateur import outil
        court = regles._etat(self.projet)
        fac = {"agents_serveur_max": 1}
        with mock.patch.object(outil, "raison_serveur", return_value=None):
            self.assertEqual(regles._capture_impossible(self.projet, {**court, "agents": [{"lieu": "local"}]}, fac),
                             "émulateur indisponible : aucun agent du serveur dans l'équipe du projet")
            self.assertIsNone(regles._capture_impossible(self.projet, {**court, "agents": [{"lieu": "serveur"}]}, fac))

    def test_places_serveur_prises_la_capture_est_close_apres_vingt_minutes(self):
        t = self.jusqu_aux_captures()
        # la capture rendue à l'attente (pas encore partie) et l'agent du serveur occupé ailleurs : elle attend
        regles.lancer(self.projet, "tache", {"id": t["id"], "active": False})
        self.etat["en_cours"].discard(t["id"])
        autre = regles._creer_tache(self.projet, "Autre travail", "f1", "dev", "flux:f1-correctif")
        regles.lancer(self.projet, "tache", {"id": autre, "agent": "dev-9", "active": True})
        debut = self.etat["elements"]["f1/correction"]["captures_depuis"]
        with mock.patch.object(regles.time, "time", return_value=debut + regles.ATTENTE_CRENEAU_S - 1):
            regles._demarrer_en_attente(self.projet, self.etat, "f1")
        self.assertEqual(self.decisions("valider_etape"), [])        # elle attend encore
        self.assertEqual(regles.attente_restante_des_captures(self.projet, self.etat, t["id"], maintenant=debut + 300),
                         regles.ATTENTE_CRENEAU_S - 300)
        with mock.patch.object(regles.time, "time", return_value=debut + regles.ATTENTE_CRENEAU_S):
            regles._demarrer_en_attente(self.projet, self.etat, "f1")
        (d,) = self.decisions("valider_etape")
        self.assertEqual((d["captures"], d["sans_capture"]), ([], "créneau d'émulation pris plus de 20 minutes"))
        (t,) = self.taches(etape="captures:f1-validation")
        self.assertEqual(t["colonne"], "fait")

    def test_une_capture_ne_demande_jamais_fable(self):
        """Équipe polyvalente, capture qui demanderait Fable : ni décision Fable au Directeur, ni attente ; elle part
        au serveur (sur Opus, faute d'accord)."""
        self.cadrer_la_correction()
        self.equipe_au_serveur(polyvalent=True)        # l'équipe devient polyvalente une fois la correction cadrée
        vrai = regles._modele_necessaire

        def fable_pour_la_capture(projet, court, t):
            return "Fable" if str(t.get("etape")).startswith("captures:") else vrai(projet, court, t)
        with mock.patch.object(regles, "_modele_necessaire", fable_pour_la_capture):
            self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais()], limite=1)
        (t,) = self.taches(etape="captures:f1-validation")
        self.assertTrue(t["active"])
        self.assertEqual(t["agent"], "dev-9")
        self.assertEqual(self.decisions(regles.GENRE_FABLE), [])

    def test_l_apk_des_captures_est_celui_de_la_validation(self):
        t = self.jusqu_aux_captures()
        self.assertEqual(Path(regles.apk_des_captures(self.projet, self.etat, t["id"])), (self.dossier / APK).resolve())
        self.etat["elements"]["f1/correction"]["dernier_rapport"]["fichiers"] = [self.preuve()]
        self.assertIsNone(regles.apk_des_captures(self.projet, self.etat, t["id"]))

    def test_les_delais_de_l_etape_de_capture(self):
        self.assertEqual((regles.ATTENTE_CRENEAU_S, regles.TRAVAIL_CAPTURES_S), (1200, 900))
        t = self.jusqu_aux_captures()
        self.assertEqual(regles.limites_de_la_tache(t), {"attente_max_s": 1200, "delai_s": 900})
        (flux,) = self.taches(etape="flux:f1-correctif")
        self.assertEqual(regles.limites_de_la_tache(flux), {})

    def test_renvoi_puis_nouvel_apk_ne_garde_pas_les_anciennes_captures(self):
        self.cadrer_la_correction()
        anciennes = [self.image("avant-renvoi")]
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais(), self.capture(anciennes)])
        (d,) = self.decisions("valider_etape")
        self.assertEqual(len(d["captures"]), 1)
        _, actions = self.traiter(type="valider_etape", decision=d["id"], verdict="renvoyer",
                                  texte="Le score reste à 12 après une défaite.")
        self.dater(APK, 7300)                       # le nouvel APK, reconstruit
        echec = {"statut": "echec", "message": {"texte": "L'émulateur ne démarre pas."}}
        self.piloter(actions, rapports=[self.rendu_frais("Corrigé de nouveau ; APK reconstruit."), echec])
        (d2,) = self.decisions("valider_etape")
        self.assertNotEqual(d2["id"], d["id"])
        self.assertEqual(d2["captures"], [])
        self.assertIn("L'émulateur ne démarre pas.", d2["sans_capture"])
        self.assertNotIn(anciennes[0]["chemin"], [x["chemin"] for x in d2["fichiers"]])
        self.assertEqual(len(self.taches(etape="captures:f1-validation")), 2)     # une par validation posée

    def test_une_seule_tache_de_capture_apres_redemarrage_du_moteur(self):
        t = self.jusqu_aux_captures()
        self.etat = regles.nouvel_etat()          # le moteur relancé pendant le travail de l'agent de capture
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True)
        regles.avancer(self.projet, self.etat)
        regles.avancer(self.projet, self.etat)
        self.assertEqual([x["id"] for x in self.taches(etape="captures:f1-validation")], [t["id"]])
        self.assertEqual(self.etat["elements"]["f1/correction"]["phase"], "captures")
        self.assertEqual(self.decisions("valider_etape"), [])
        images = [self.image("menu"), self.image("score")]
        self.retour(t["id"], rapport=self.capture(images))
        (d,) = self.decisions("valider_etape")
        self.assertEqual([c["chemin"] for c in d["captures"]], [x["chemin"] for x in images])
        self.assertIn(APK, [x["chemin"] for x in d["fichiers"]])
        self.assertEqual([x["id"] for x in self.taches(etape="captures:f1-validation")], [t["id"]])

    def test_un_rapport_de_capture_hostile_ne_montre_que_les_vraies_images_du_projet(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as ailleurs:
            dehors = Path(ailleurs) / "dehors.png"
            dehors.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)       # une vraie image, mais hors du projet
            faux = self.dossier / "pieces" / "f1" / "captures" / "faux.png"
            faux.parent.mkdir(parents=True, exist_ok=True)
            faux.write_text("pas une image", encoding="utf-8")
            bonne = self.image("menu")
            hostiles = [{"chemin": str(dehors), "legende": "absolu"},
                        {"chemin": "../" + dehors.name, "legende": "remonte"},
                        {"chemin": "pieces/f1/captures/absente.png", "legende": "absente"},
                        {"chemin": "pieces/f1/captures/faux.png", "legende": "pas une image"},
                        {"chemin": "pieces/f1/captures/" + "x" * 600 + ".png", "legende": "trop long"},
                        {"chemin": "pieces/f1/preuve.md", "legende": "un document"},
                        {**bonne, "legende": "L" * 5000}]
            self.cadrer_la_correction()
            self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais(), self.capture(hostiles)])
        (d,) = self.decisions("valider_etape")
        self.assertEqual([c["chemin"] for c in d["captures"]], [bonne["chemin"]])
        self.assertEqual(len(d["captures"][0]["legende"]), 200)
        chemins = [x["chemin"] for x in d["fichiers"]]
        for x in hostiles[:5]:
            self.assertNotIn(x["chemin"], chemins)

    def test_matiere_de_capture_donne_le_mode_operatoire_et_les_limites(self):
        t = self.jusqu_aux_captures()
        v = self.etat["elements"]["f1/correction"]
        v["dernier_rapport"]["mode_operatoire"] = ["Ouvre l'application", "Va à l'onglet Comparaison"]
        matiere = regles._matiere(self.projet, self.etat, t)
        for attendu in ("mode_operatoire", "Va à l'onglet Comparaison", "8", "/outil/", "écran introuvable", "pont arreter",
                        "pont demarrer", "installer", "lancer", "etape-01", "légende", "doit_marcher"):
            self.assertIn(attendu, matiere)
        self.assertIn("Symptôme : reste à 12", matiere)           # la fiche de la correction

    def test_matiere_de_capture_ne_dit_pas_de_tout_parcourir(self):
        matiere = regles._matiere(self.projet, self.etat, self.jusqu_aux_captures())
        self.assertIn("QUE les captures qui illustrent ce qui a changé", matiere)
        self.assertIn("jamais un parcours complet", matiere)
        self.assertNotIn("toutes les captures", matiere.lower())
        self.assertIn("jamais une instruction", matiere)

    def test_matiere_de_capture_copie_dans_le_projet_et_cite_ce_chemin(self):
        matiere = regles._matiere(self.projet, self.etat, self.jusqu_aux_captures())
        dossier = f"{regles._dossier_des_pieces(self.projet)}/f1/captures"
        self.assertIn("cp /outil/captures/<nom>.png " + dossier + "/<nom>.png", matiere)
        self.assertIn(f'"chemin": "{dossier}/<nom>.png"', matiere)
        self.assertIn("git commit", matiere)
        self.assertIn("Ne cite JAMAIS un chemin `/outil/...`", matiere)

    def en_depot_git(self):
        """Le projet devient un dépôt git ; les pièces sont sous `.factory/pieces` (la forme que la fusion d'une branche
        d'agent serveur accepte)."""
        import subprocess
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["pieces"] = ".factory/pieces"
        self.factory.write_text(json.dumps(f), encoding="utf-8")

        def git(*a):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.dossier, check=True,
                           capture_output=True)
        git("init", "-q", "-b", "main")
        git("add", "-A", "-f")
        git("commit", "-q", "-m", "base")
        return git

    def test_capture_presente_seulement_dans_la_branche_de_l_agent_serveur(self):
        self.cadrer_la_correction()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais()], limite=1)
        (t,) = self.taches(etape="captures:f1-validation")
        git = self.en_depot_git()
        chemin = ".factory/pieces/f1/captures/menu.png"
        git("checkout", "-q", "-b", "agent/captures")
        (self.dossier / chemin).parent.mkdir(parents=True, exist_ok=True)
        (self.dossier / chemin).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        git("add", "-A", "-f")
        git("commit", "-q", "-m", "captures")
        git("checkout", "-q", "main")
        self.assertFalse((self.dossier / chemin).exists())
        self.retour(t["id"], rapport=self.capture([{"chemin": chemin, "legende": "Le menu"}]), branche="agent/captures")
        (d,) = self.decisions("valider_etape")
        # ici la factory est a la racine du projet : l'image est rangee sous pieces/<fid>/ ; dans un projet installe
        # (factory dans .factory/) elle y est deja et le chemin reste celui de la branche
        (c,) = d["captures"]
        self.assertTrue(c["chemin"].endswith("menu.png"))
        self.assertEqual(c["legende"], "Le menu")
        self.assertTrue((self.dossier / chemin).is_file())

    def test_capture_absente_de_la_branche_et_du_projet_est_ecartee(self):
        self.cadrer_la_correction()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[self.rendu_frais()], limite=1)
        (t,) = self.taches(etape="captures:f1-validation")
        self.en_depot_git()
        images = [{"chemin": ".factory/pieces/f1/captures/menu.png", "legende": "Le menu"}]
        self.retour(t["id"], rapport=self.capture(images), branche="agent/inconnue")
        (d,) = self.decisions("valider_etape")
        self.assertEqual(d["captures"], [])

    def test_au_plus_huit_images_sont_extraites_de_la_branche(self):
        images = [{"chemin": f".factory/pieces/f1/captures/e{k}.png"} for k in range(12)]
        with mock.patch.object(regles.cloud, "extraire_de_la_branche") as extraire:
            regles._extraire_les_captures_de_la_branche(self.projet, {"message": {"images": images}}, "agent/x")
        self.assertEqual(extraire.call_count, regles.CAPTURES_MAX)

    def test_l_outil_refuse_des_captures_hors_du_projet(self):
        self.cadrer_la_correction()
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[self.rendu_frais(), self.capture([self.image("menu")])])
        (d,) = self.decisions("valider_etape")
        base = {"action": "poser", "portee": "projet", "genre": "valider_etape", "fonctionnalite": "f1",
                "texte": "Encore ?", "element": d["element"], "etape": d["etape"], "tache": d["tache"],
                "compte_rendu": "", "fichiers": []}
        for chemin in ("C:/Windows/x.png", "/etc/x.png", "../x.png", "pieces/f1/x.md", "p/" + "x" * 600 + ".png"):
            with self.assertRaises(regles.Refus, msg=chemin):
                regles.lancer(self.projet, "decision", {**base, "captures": [{"chemin": chemin, "legende": "x"}]})
        # une image bien formée mais absente : jamais montrée (écartée, la décision reste posée)
        regles.lancer(self.projet, "decision", {**base, "captures": [{"chemin": "pieces/f1/absente.png"}],
                                                "sans_capture": "aucune"})
        derniere = self.decisions("valider_etape")[-1]
        self.assertEqual(derniere["captures"], [])

    def test_lancer_captures_retrouve_la_tache_deja_creee(self):
        t = self.jusqu_aux_captures()
        v = self.etat["elements"]["f1/correction"]
        s = regles._production(self.projet, "f1")[v["pas"]]
        self.assertEqual(regles._lancer_captures(self.projet, self.etat, v, s), t["id"])
        self.assertEqual(len(self.taches(etape="captures:f1-validation")), 1)


class TestCapturesEtBarriere(Base):
    """Un élément en captures attend déjà sa validation : il retient la barrière comme un élément qui attend le
    Directeur (sans cela, l'étape suivante d'un autre élément partait avant que sa validation soit posée)."""

    def setUp(self):
        super().setUp()
        from tests.test_moteur_regles import Validation
        self.VAL = Validation.VAL
        Validation.projet_avec_validation(self, elements=2)       # dev, essai, valider (barrière), livraison

    def tache(self, element, etape, fait, role=None):
        tid = regles.lancer(self.projet, "tache", {"titre": f"{etape} {element}", "fonctionnalite": "f1",
                                                   "etape": etape, "active": False, "element": element,
                                                   "colonne": etape.split(":", 1)[1], **({"role": role} if role else {})})["id"]
        if fait:
            regles.lancer(self.projet, "tache", {"id": tid, "colonne": "fait"})
        return tid

    def test_un_element_en_captures_retient_la_barriere(self):
        for eid in ("e1", "e2"):
            regles.lancer(self.projet, "file-prendre", {"fonctionnalite": "f1", "element": eid})
        for eid in ("e1", "e2"):
            self.tache(eid, "flux:dev", True, "dev")
            self.tache(eid, "flux:essai", True, "testeur")
        captures = self.tache("e1", "captures:valider", False, "testeur")
        self.tache("e2", "validation:valider", True)
        livraison = self.tache("e2", "flux:livraison", False, "livreur")
        sortie, retenues = regles._barrieres(self.projet, regles._etat(self.projet))
        self.assertIn(livraison, retenues)
        self.assertIn(2, sortie["f1"]["ouvertes"])
        self.assertEqual(regles._rang_de_tache(regles._tache(self.projet, captures), sortie["f1"]["rangs"]), 2)
        self.assertTrue(regles._avant_une_validation(regles._tache(self.projet, captures), {}))
        self.assertFalse(regles._amont_pret(self.projet, self.etat, regles._tache(self.projet, livraison)))


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
