"""Claude autonome : Claude réfléchit aux décisions du Directeur (jamais aux validations), le moteur en tire des leçons,
des améliorations et des réponses qu'il donnera seul ensuite."""
import json
import unittest
from unittest import mock

from moteur import jugement, regles
from tests import test_moteur_regles as tmr
from tests import test_moteur_serie_reprise as tsr

ELEMENTS = tsr.ELEMENTS


def objet(**champs):
    return {"raison": "Débloque la tâche sans sortir de la demande.", "verdict": "accepter", "texte": None,
            "generalisable": False, "lecon": None, "amelioration": None, **champs}


class Reponses(unittest.TestCase):
    """La réponse mécanique de repli."""

    def test_un_accord_prend_le_premier_choix_les_premieres_reponses_ou_accepte(self):
        r = regles._reponse_autonome
        self.assertEqual(r({"id": "d1", "genre": "accord_agent", "choix": ["A", "B"]}),
                         {"type": "accord_agent", "verdict": "choisir", "choix": "A", "decision": "d1"})
        d = r({"id": "d2", "genre": "accord_agent", "questions": [{"texte": "?", "choix": ["x", "y"]}]})
        self.assertEqual((d["verdict"], d["reponses"]), ("repondre", [["x"]]))
        self.assertEqual(r({"id": "d3", "genre": "accord_agent"})["verdict"], "accepter")

    def test_outil_serie_et_blocage(self):
        r = regles._reponse_autonome
        self.assertEqual(r({"id": "d1", "genre": "outil_agent", "programme": "flutter"})["verdict"], "autoriser")
        self.assertEqual(r({"id": "d1", "genre": "outil_agent"})["verdict"], "relancer")
        self.assertEqual(r({"id": "d2", "genre": "serie_arretee"})["verdict"], "relancer")
        self.assertEqual(r({"id": "d3", "genre": "blocage_analyse", "recommandation": "Refais"})["verdict"], "suivre")
        self.assertIsNone(r({"id": "d3", "genre": "blocage_analyse", "recommandation": ""}))

    def test_jamais_une_validation_ni_une_decision_qui_depense(self):
        for genre in ("valider_etape", "valider_methode", "fable_tache", "decoupage_lieux", "environnement"):
            self.assertIsNone(regles._reponse_autonome({"id": "d1", "genre": genre}), genre)
            self.assertNotIn(genre, regles.VERDICTS_AUTONOMES)


class Validation(unittest.TestCase):
    D = {"verdicts": ["accepter", "choisir", "repondre", "refuser"], "choix": ["A", "B"],
         "questions": [{"texte": "?", "choix": ["x", "y"]}], "mots_interdits": ["Secret"]}

    def erreur(self, **champs):
        return jugement.valider("decider_autonome", objet(**champs), self.D)

    def test_une_reponse_valable(self):
        self.assertIsNone(self.erreur())
        self.assertIsNone(self.erreur(verdict="choisir", choix="B"))
        self.assertIsNone(self.erreur(verdict="repondre", reponses=[["y"]]))
        self.assertIsNone(self.erreur(lecon={"portee": "metier", "texte": "Demande l'outil avant."},
                                      amelioration={"titre": "Ouvrir flutter d'office", "description": "Le profil."}))

    def test_refus_des_reponses_inventees(self):
        self.assertIn("verdict", self.erreur(verdict="valider"))
        self.assertIn("choix", self.erreur(verdict="choisir", choix="Z"))
        self.assertIn("reponses", self.erreur(verdict="repondre", reponses=[["z"]]))
        self.assertIn("texte", self.erreur(verdict="refuser"))
        self.assertIn("Fable", self.erreur(texte="Passe sur Fable."))
        self.assertIn("raison", self.erreur(raison=""))
        self.assertIn("généraux", self.erreur(lecon={"portee": "genre", "texte": "Le Secret du projet."}))
        self.assertIn("generalisable", self.erreur(generalisable="oui"))


class Boucle(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)

    prendre, tache, serie_arretee = (tsr.Reprise.__dict__[n] for n in ("prendre", "tache", "serie_arretee"))

    def decision_serie(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        self.prendre("e1", "e2")
        self.tache("e1", "flux:ancienne", journal="Fait.", colonne="dev")
        self.tache("e2", "prototype")
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        (d,) = self.serie_arretee()
        return d

    def appliquer(self, action, o=None, question=None):
        _, type_, _, suite = action
        decision = jugement.Decision(question=question) if question else jugement.Decision(objet=o)
        return regles.appliquer_jugement(self.projet, type_, decision, suite, self.etat)

    def test_desactive_rien_n_est_fait(self):
        self.decision_serie()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_active_claude_recoit_un_dossier_sur_la_decision_et_les_etapes_de_validation(self):
        d = self.decision_serie()
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        _, type_, dossier, suite = action
        self.assertEqual((type_, suite["decision"]), ("decider_autonome", d["id"]))
        self.assertEqual(dossier["decision"]["genre"], "serie_arretee")
        self.assertEqual(dossier["verdicts"], ["relancer", "laisser"])
        self.assertTrue(any(x["validation"] for x in dossier["fonctionnalite"]["flux"]))       # le but : la validation
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])        # une seule tentative

    def test_la_reponse_reflechie_est_deposee_avec_sa_raison_sa_lecon_et_son_amelioration(self):
        d = self.decision_serie()
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, objet(verdict="relancer", raison="Une étape retirée du flux bloquait la série.",
                                     lecon={"portee": "metier", "texte": "Garde des étapes du workflow actuel."},
                                     amelioration={"titre": "Étape retirée", "description": "Migrer les tâches."}))
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "serie_arretee"]
        self.assertEqual((demande["decision"], demande["verdict"], demande["claude_autonome"]), (d["id"], "relancer", True))
        self.assertIn("étape retirée", demande["raison"])
        regles.traiter_demande(self.projet, demande, self.etat)
        self.assertEqual(self.serie_arretee(), [])
        (lecon,) = self.suivi()["lecons"]
        self.assertEqual((lecon["texte"], lecon["etat"]), ("Garde des étapes du workflow actuel.", "validée"))
        titres = [a["titre"] for a in self.ok("anomalies")["anomalies"]]
        self.assertEqual(titres, ["Amélioration : Étape retirée"])

    def test_si_claude_ne_peut_pas_reflechir_la_reponse_mecanique_debloque_quand_meme(self):
        self.decision_serie()
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, question="Deux essais sans réponse utilisable.")
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "serie_arretee"]
        self.assertEqual(demande["verdict"], "relancer")
        self.assertIn("pas pu réfléchir", demande["raison"])
        self.assertEqual(len(self.suivi()["lecons"]), 1)      # la leçon mécanique

    def test_une_serie_qui_se_rebloque_revient_au_directeur_apres_trois_reponses(self):
        self.decision_serie()
        self.projet.claude_autonome = True
        self.etat["autonome_reprises"] = {("serie_arretee", "f1"): regles.AUTONOME_MAX_REPRISES}
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        self.assertEqual(len(self.serie_arretee()), 1)


CHEF = ("Analyse du Chef (l'agent n'a pas pu finir) : cause probable.", "Retour du Chef : refais la recette.")
BLOQUEE = "Le service en ligne n'a pas le correctif."


class TacheBloquee(tsr.AvecValidation):
    """Une tâche restée bloquée sans décision, après l'essai automatique du Chef : Claude autonome la prend."""

    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.dev = self.ok("tache", entree={"titre": "Index et /sante", "fonctionnalite": "f1", "role": "dev",
                                            "etape": "flux:dev", "colonne": "dev", "active": False})["id"]
        self.ok("tache", entree={"id": self.dev, "colonne": "fait", "journal": ["Livré."]})
        self.recette = self.ok("tache", entree={
            "titre": "Recette du service", "fonctionnalite": "f1", "role": "testeur", "etape": "flux:essai",
            "colonne": "dev", "active": False, "bloquee": BLOQUEE, "journal": list(CHEF)})["id"]
        self.etat = regles.nouvel_etat()

    def bloquer(self, activer=True):
        self.projet.claude_autonome, self.projet.analyse_blocages = activer, True
        self.assertEqual(regles._analyser_le_blocage(self.projet, self.etat, self.recette, "echec"), [])

    def juger(self):
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        return action

    def appliquer(self, action, o=None, question=None):
        _, type_, _, suite = action
        decision = jugement.Decision(question=question) if question else jugement.Decision(objet=o)
        return regles.appliquer_jugement(self.projet, type_, decision, suite, self.etat)

    def traiter_la_reponse(self):
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "tache_bloquee"]
        self.assertTrue(demande["claude_autonome"])
        return demande, regles.traiter_demande(self.projet, demande, self.etat)

    def la(self, tid):
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    # --- Cas 1 : la tâche bloquée sans décision.

    def test_reglage_decoche_rien_n_est_fait(self):
        self.bloquer(activer=False)
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_claude_recoit_le_dossier_de_la_tache_bloquee(self):
        self.bloquer()
        _, type_, dossier, _ = self.juger()
        self.assertEqual((type_, dossier["decision"]["genre"], dossier["tache"]["id"]),
                         ("decider_autonome", "tache_bloquee", self.recette))
        self.assertEqual([x["id"] for x in dossier["taches_dev"]], [self.dev])
        self.assertEqual(sorted(dossier["verdicts"]), ["laisser", "relancer", "renvoyer"])    # pas de service déclaré
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])      # une seule tentative

    def test_relancer_reprend_la_tache_avec_une_consigne_et_garde_la_raison(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="relancer", texte="Refais la recette quand /sante répond.",
                                           raison="Le service est prêt, la recette peut être refaite."))
        demande, _ = self.traiter_la_reponse()
        self.assertIn("recette peut être refaite", demande["raison"])
        self.assertFalse(self.la(self.recette).get("bloquee"))
        self.assertTrue(any("Reprise sur votre retour" in str(j.get("texte")) for j in self.la(self.recette)["journal"]))

    def test_relancer_sans_texte_est_refuse(self):
        self.bloquer()
        _, _, dossier, _ = self.juger()
        self.assertIn("texte", jugement.valider("decider_autonome", objet(verdict="relancer"), dossier))

    def test_laisser_garde_la_tache_bloquee(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="laisser", raison="Il faut une clé que seul le Directeur a."))
        self.traiter_la_reponse()
        self.assertTrue(self.la(self.recette)["bloquee"])

    def test_une_meme_cause_n_est_tentee_qu_une_fois(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="relancer", texte="Refais la recette."))
        self.traiter_la_reponse()
        self.ok("tache", entree={"id": self.recette, "bloquee": BLOQUEE})
        self.assertEqual(regles._analyser_le_blocage(self.projet, self.etat, self.recette, "echec"), [])
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        self.assertTrue(any("déjà essayé" in str(j.get("texte")) for j in self.la(self.recette)["journal"]))

    def test_une_cause_nouvelle_a_sa_propre_tentative(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="relancer", texte="Refais la recette."))
        self.traiter_la_reponse()
        self.ok("tache", entree={"id": self.recette, "bloquee": "Autre cause : la page /equipe/77 est vide."})
        self.assertEqual(regles._analyser_le_blocage(self.projet, self.etat, self.recette, "echec"), [])
        self.assertEqual(len(regles.repondre_en_autonome(self.projet, self.etat)), 1)

    def test_jamais_une_validation_du_directeur(self):
        self.projet.claude_autonome = self.projet.analyse_blocages = True
        regles._analyser_le_blocage(self.projet, self.etat, self.recette, "validation")
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_si_claude_ne_peut_pas_reflechir_la_tache_reste_au_directeur(self):
        self.bloquer()
        self.appliquer(self.juger(), question="Deux essais sans réponse utilisable.")
        self.assertEqual([x for x in self.demande_en_attente() if x["type"] == "tache_bloquee"], [])
        self.assertTrue(self.la(self.recette)["bloquee"])
        self.assertTrue(any("revient au Directeur" in str(j.get("texte")) for j in self.la(self.recette)["journal"]))

    def test_la_lecon_de_la_reponse_est_retenue(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="relancer", texte="Refais la recette.",
                                           lecon={"portee": "metier", "texte": "Vérifie /sante avant la recette."}))
        (lecon,) = self.suivi()["lecons"]
        self.assertEqual((lecon["texte"], lecon["etat"]), ("Vérifie /sante avant la recette.", "validée"))

    # --- Cas 2 : le défaut du code livré est renvoyé au dev, avec diagnostic.

    def test_renvoyer_le_defaut_au_dev_cree_un_retour_et_la_recette_l_attend(self):
        self.bloquer()
        diag = "Les index sont créés avant l'écoute du port : /sante reste muet. Écris un test d'abord."
        self.appliquer(self.juger(), objet(verdict="renvoyer", tache_dev=self.dev, texte=diag))
        self.traiter_la_reponse()
        (retour,) = [t for t in self.suivi()["taches"] if t["titre"].startswith("Retour : ")]
        self.assertIn("/sante reste muet", json.dumps(retour["journal"], ensure_ascii=False))
        self.assertEqual(retour["role"], "dev")
        recette = self.la(self.recette)
        self.assertFalse(recette.get("bloquee"))
        self.assertIn(retour["id"], recette["depend_de"])

    def test_renvoyer_exige_une_tache_de_dev_connue(self):
        self.bloquer()
        _, _, dossier, _ = self.juger()
        self.assertIn("tache_dev", jugement.valider("decider_autonome",
                                                    objet(verdict="renvoyer", texte="X.", tache_dev="t999"), dossier))
        self.assertIsNone(jugement.valider("decider_autonome",
                                           objet(verdict="renvoyer", texte="X.", tache_dev=self.dev), dossier))

    # --- Cas 3 : le service tourne sans la correction : redéploiement, puis la recette repart une fois sain.

    def avec_service(self, statuts, sante=((True, "HTTP 200"),) * 5):
        s = regles.service_permanent
        patchs = [mock.patch.object(s, "sante_repond", side_effect=list(sante)),
                  mock.patch.object(s, "raison_de_ne_pas_deployer", return_value=None),
                  mock.patch.object(s, "_commit_du_depot", return_value="a" * 40),
                  mock.patch.object(s, "declencher", return_value="Service permanent : lancé."),
                  mock.patch.object(s, "statut_du_serveur", side_effect=statuts)]
        mocks = [p.start() for p in patchs]
        for p in patchs:
            self.addCleanup(p.stop)
        return mocks[2]

    def test_sans_service_le_redeploiement_n_est_pas_propose(self):
        with mock.patch.object(regles.service_permanent, "raison_de_ne_pas_deployer", return_value=""):
            self.bloquer()
            _, _, dossier, _ = self.juger()
        self.assertNotIn("redeployer", dossier["verdicts"])

    def test_redeployer_le_service_puis_relancer_la_recette_une_fois_sain(self):
        declencher = self.avec_service([("attente", "en cours"), ("a_jour", "version livrée en ligne")])
        self.bloquer()
        action = self.juger()
        self.assertIn("redeployer", action[2]["verdicts"])
        self.appliquer(action, objet(verdict="redeployer", texte="Refais la recette contre le service à jour.",
                                     raison="Le service tourne sans le correctif fusionné."))
        self.traiter_la_reponse()
        declencher.assert_called_once()
        self.assertTrue(self.la(self.recette)["bloquee"])          # pas relancée avant que le service soit sain
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])     # « attente » : on patiente
        self.assertTrue(self.la(self.recette)["bloquee"])
        regles.repondre_en_autonome(self.projet, self.etat)          # « a_jour » : la recette repart
        self.assertFalse(self.la(self.recette).get("bloquee"))
        self.assertTrue(any("le service est à jour" in str(j.get("texte")) for j in self.la(self.recette)["journal"]))
        declencher.assert_called_once()                              # un seul redéploiement

    def test_un_redeploiement_en_echec_revient_au_directeur(self):
        self.avec_service([("echec", "retour arrière : /sante muet")])
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="redeployer"))
        self.traiter_la_reponse()
        regles.repondre_en_autonome(self.projet, self.etat)
        self.assertTrue(self.la(self.recette)["bloquee"])
        self.assertTrue(any("revient au Directeur" in str(j.get("texte")) for j in self.la(self.recette)["journal"]))

    # --- Cas 5 : attendre que le service réponde 200 avant de relancer la recette.

    def test_la_recette_attend_que_le_service_reponde(self):
        declencher = self.avec_service([("a_jour", "ok")] * 3, sante=[(False, "HTTP 503"), (True, "HTTP 200")])
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="redeployer"))
        self.traiter_la_reponse()
        regles.repondre_en_autonome(self.projet, self.etat)           # déployé mais 503 : on attend
        self.assertTrue(self.la(self.recette)["bloquee"])
        regles.repondre_en_autonome(self.projet, self.etat)           # 200 : la recette repart
        self.assertFalse(self.la(self.recette).get("bloquee"))

    def test_la_sante_se_lit_sur_l_adresse_du_service(self):
        class Reponse:
            status = 503
            def __enter__(self): return self
            def __exit__(self, *a): return False
        m = mock.Mock()
        m.lire_cache.return_value = {"p": {"adresse": "https://service.test"}}
        m.identifiant.return_value = "p"
        m.lire_declaration.return_value = {"sante": "/sante"}
        vus = []
        self.assertEqual(regles.service_permanent.sante_repond(
            self.dossier, module=m, ouvrir=lambda url, timeout: vus.append(url) or Reponse()), (False, "HTTP 503"))
        self.assertEqual(vus, ["https://service.test/sante"])

    # --- Cas 4 : l'anomalie du logiciel désignée par la cause est fermée.

    def test_une_anomalie_corrigee_depuis_est_marquee_reglee(self):
        a = self.ok("anomalies", entree={"action": "ajouter", "titre": "Lancement refusé : --tools",
                                         "description": "Valeur invalide pour --tools."})["anomalie"]["id"]
        self.bloquer()
        action = self.juger()
        self.assertEqual([x["id"] for x in action[2]["anomalies"]], [a])
        self.assertIn("anomalies", jugement.valider("decider_autonome", objet(verdict="laisser",
                                                    anomalies=[{"id": "a99", "etat": "reglee"}]), action[2]))
        self.appliquer(action, objet(verdict="relancer", texte="Refais la tâche.", anomalies=[{"id": a, "etat": "reglee"}]))
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "anomalie"]
        self.assertEqual((demande["etat"], demande["claude_autonome"]), ("reglee", True))
        regles.traiter_demande(self.projet, demande, self.etat)
        self.assertEqual(self.ok("anomalies")["anomalies"][0]["etat"], "reglee")

    # --- Cas 6 et 7 : les moyens du projet sont donnés à Claude.

    def test_le_dossier_donne_l_adresse_du_service_et_les_anomalies(self):
        self.bloquer()
        with mock.patch.object(regles, "_adresse_du_service", return_value="https://service.test"):
            _, _, dossier, _ = self.juger()
        self.assertEqual(dossier["service"]["adresse"], "https://service.test")
        self.assertEqual(dossier["anomalies"], [])

    # --- Les faits lus sur le service réel et le rapport de la tâche, dans le dossier de Claude (lecture seule).

    def test_le_dossier_porte_les_faits_du_service_et_le_rapport_de_la_tache(self):
        faits = {"commit": "b" * 40, "etat": "actif", "journal": ["FileNotFoundError: /app/docs/style.json"],
                 "pages": [{"chemin": "/sante", "code": 503, "ms": 12}], "erreur": None}
        (self.projet.dossier / "docs").mkdir(exist_ok=True)
        (self.projet.dossier / "docs" / "recette.md").write_text("Défaut : jeton: abc123 visible.", encoding="utf-8")
        self.ok("tache", entree={"id": self.recette, "journal": ["Rapport dans docs/recette.md, page /equipe/77."]})
        self.avec_service([("attente", "")])
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits) as lire:
            self.bloquer()
            _, _, dossier, _ = self.juger()
        self.assertEqual(dossier["faits_du_service"], faits)
        self.assertIn("/sante", lire.call_args[0][1])
        self.assertIn("/equipe/77", lire.call_args[0][1])
        self.assertEqual(dossier["rapport_de_la_tache"]["chemin"], "docs/recette.md")
        self.assertNotIn("abc123", dossier["rapport_de_la_tache"]["texte"])      # jamais un secret lu

    def test_faits_du_service_en_lecture_seule_secrets_masques(self):
        class Reponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        m = mock.Mock()
        m.lire_cache.return_value = {"p": {"adresse": "https://service.test", "etat": {"commit": "c" * 40, "etat": "actif"}}}
        m.identifiant.return_value = "p"
        m.gerer.return_value = (0, {"lignes": ["Traceback...", "Authorization: Bearer abc123", "jeton: zzz"]})
        vus = []
        faits = regles.service_permanent.faits_du_service(
            self.dossier, ["/sante", "/equipe/77", "http://autre.test/x"], module=m,
            ouvrir=lambda url, timeout: vus.append(url) or Reponse())
        self.assertEqual(m.gerer.call_args[0][1], "journal")                   # jamais redémarrer ni autre commande
        self.assertEqual(faits["commit"], "c" * 40)
        self.assertEqual([(x["chemin"], x["code"]) for x in faits["pages"]], [("/sante", 200), ("/equipe/77", 200)])
        self.assertEqual(vus, ["https://service.test/sante", "https://service.test/equipe/77"])
        texte = " ".join(faits["journal"])
        self.assertNotIn("abc123", texte)
        self.assertNotIn("zzz", texte)
        self.assertIn("Traceback", texte)

    # --- Une décision qui parle du service : l'état réel d'abord (essai FM_Stats : « oui, déployer » sur un service déjà sain).

    def accord_de_deploiement(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "accord_agent", "agent": "chef", "texte": "Un agent demande votre accord.",
                                    "tache": self.recette, "quoi": "Déployer le service fm-donnees et poser le secret API",
                                    "pourquoi": "La recette exige le service en ligne."})
        self.projet.claude_autonome = True

    def faits_sains(self):
        return {"commit": "2b0ad4a" + "0" * 33, "etat": "actif", "sante_ok": True, "secrets": {"API_FOOTBALL_KEY": True},
                "journal": [], "pages": [{"chemin": "/sante", "code": 200, "ms": 20}], "erreur": None}

    def test_un_accord_de_deploiement_recoit_les_faits_du_service(self):
        self.accord_de_deploiement()
        self.avec_service([("a_jour", "ok")])
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=self.faits_sains()) as lire:
            (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        dossier = action[2]
        self.assertEqual(dossier["faits_du_service"]["secrets"], {"API_FOOTBALL_KEY": True})      # des noms, jamais des valeurs
        self.assertTrue(dossier["deja_fait"])
        self.assertEqual(lire.call_args.kwargs["lignes"], 0)        # sans le journal : pas d'appel au serveur

    def test_deja_fait_la_reponse_oui_est_refusee_et_refuser_avec_deja_fait_passe(self):
        self.accord_de_deploiement()
        self.avec_service([("a_jour", "ok")])
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=self.faits_sains()):
            (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        dossier = action[2]
        self.assertIn("déjà faite", jugement.valider("decider_autonome", objet(verdict="accepter"), dossier))
        self.assertIsNone(jugement.valider("decider_autonome", objet(
            verdict="refuser", texte="Déjà fait : le service est en ligne et sain ; vérifie les pages et rends."), dossier))

    def test_service_pas_a_jour_l_accord_reste_possible(self):
        self.accord_de_deploiement()
        self.avec_service([("attente", "pas encore")])
        faits = dict(self.faits_sains(), sante_ok=False)
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits):
            (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertFalse(action[2]["deja_fait"])
        self.assertIsNone(jugement.valider("decider_autonome", objet(verdict="accepter"), action[2]))

    def test_une_serie_arretee_recoit_aussi_les_faits_du_service(self):
        self.avec_service([("a_jour", "ok")])
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=self.faits_sains()):
            dossier = regles._dossier_autonome(self.projet, self.etat, {"id": "d9", "genre": "serie_arretee",
                                                                       "fonctionnalite": "f1", "texte": "Série arrêtée."})
        self.assertEqual(dossier["faits_du_service"]["etat"], "actif")
        self.assertFalse(dossier["deja_fait"])      # le garde « déjà fait » ne vaut que pour un accord

    def test_une_decision_sans_rapport_avec_le_service_n_a_pas_de_faits(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "accord_agent", "agent": "chef", "texte": "Un agent demande votre accord.",
                                    "tache": self.recette, "quoi": "Générer 5 images"})
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertNotIn("faits_du_service", action[2])

    # --- Étape 4 : le résultat de l'action est vérifié aux passages suivants.

    def relancer(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="relancer", texte="Refais la recette."))
        self.traiter_la_reponse()
        self.assertFalse(self.la(self.recette).get("bloquee"))

    def test_suivi_la_tache_terminee_est_dite(self):
        self.relancer()
        self.ok("tache", entree={"id": self.recette, "colonne": "fait", "journal": ["Recette passée."]})
        avant = len(self.paroles())
        regles.repondre_en_autonome(self.projet, self.etat)
        (parole,) = self.paroles()[avant:]
        self.assertIn("est terminée", parole)
        regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(len(self.paroles()), avant + 1)             # une seule fois

    def test_suivi_meme_cause_pas_de_nouvelle_tentative_et_le_chef_le_dit(self):
        self.relancer()
        self.ok("tache", entree={"id": self.recette, "bloquee": BLOQUEE})
        avant = len(self.paroles())
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        (parole,) = self.paroles()[avant:]
        self.assertIn("même raison", parole)
        self.assertIn("c'est à vous de décider", parole)

    def test_suivi_une_autre_cause_a_sa_tentative(self):
        self.relancer()
        self.ok("tache", entree={"id": self.recette, "bloquee": "Autre cause : /equipe/77 renvoie 500."})
        avant = len(self.paroles())
        actions = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][2]["decision"]["genre"], "tache_bloquee")
        self.assertIn("autre raison", self.paroles()[avant:][0])

    def test_trois_tentatives_au_plus_puis_le_chef_le_dit_une_fois(self):
        self.etat["autonome_reprises"] = {("tache_bloquee", self.recette): regles.AUTONOME_MAX_REPRISES}
        self.bloquer()
        avant = len(self.paroles())
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        (parole,) = self.paroles()[avant:]
        self.assertIn("trois tentatives", parole)

    def test_suivi_pendant_l_attente_du_service_rien_n_est_dit(self):
        self.avec_service([("attente", "en cours")] * 3)
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="redeployer"))
        self.traiter_la_reponse()
        avant = len(self.paroles())
        regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(len(self.paroles()), avant)

    # --- Étape 5 : un défaut du moteur lui-même devient une fiche, jamais un correctif appliqué seul.

    def test_un_defaut_du_moteur_devient_une_fiche_dite_par_le_chef(self):
        self.bloquer()
        avant = len(self.paroles())
        a = {"titre": "Index créés avant l'écoute du port", "description": "Vu sur la recette.", "defaut_moteur": True,
             "diagnostic": "Les index bloquent le démarrage.", "correction": "Les créer en arrière-plan.",
             "test": "Le port répond avant la fin des index."}
        self.appliquer(self.juger(), objet(verdict="laisser", amelioration=a))
        (fiche,) = self.ok("anomalies")["anomalies"]
        self.assertTrue(fiche["titre"].startswith("Défaut du moteur : "))
        for mot in ("Diagnostic", "Correction attendue", "Test à écrire"):
            self.assertIn(mot, fiche["description"])
        (parole,) = self.paroles()[avant:]
        self.assertIn("défaut du moteur lui-même", parole)
        self.assertIn("je ne le corrige pas seul", parole)

    def test_defaut_du_moteur_sans_diagnostic_ni_test_est_refuse(self):
        self.bloquer()
        _, _, dossier, _ = self.juger()
        a = {"titre": "Défaut", "description": "x", "defaut_moteur": True}
        self.assertIn("diagnostic", jugement.valider("decider_autonome", objet(verdict="laisser", amelioration=a), dossier))

    def test_une_amelioration_simple_reste_une_amelioration(self):
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="laisser", amelioration={"titre": "Idée", "description": "Un réglage."}))
        (fiche,) = self.ok("anomalies")["anomalies"]
        self.assertTrue(fiche["titre"].startswith("Amélioration : "))

    # --- Une tâche bloquée par un chemin qui ne passe pas par l'analyse du Chef est prise aussi (FM_Stats t279).

    CADRAGE = "L'agent a rendu deux fois son cadrage sans le cahier des charges ni question : rien ne peut suivre."

    def bloquer_sans_analyse(self, texte=CADRAGE, tid=None):
        tid = tid or self.recette
        self.ok("tache", entree={"id": tid, "bloquee": texte})
        self.projet.claude_autonome = True
        return tid

    def vieillir(self):
        for k in list(self.etat.get("autonome_bloquees_vues", {})):
            self.etat["autonome_bloquees_vues"][k] -= regles.DELAI_BLOCAGE_SANS_ANALYSE_S + 1

    def test_orphelin_pas_avant_le_delai_de_l_analyse_du_chef(self):
        self.bloquer_sans_analyse()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        self.vieillir()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(action[2]["decision"]["genre"], "tache_bloquee")
        self.assertIn("cahier", action[2]["decision"]["texte"])

    def test_orphelin_une_meme_cause_une_seule_fois(self):
        self.bloquer_sans_analyse()
        regles.repondre_en_autonome(self.projet, self.etat)
        self.vieillir()
        self.appliquer(self.juger(), objet(verdict="relancer", texte="Rends le cahier OU une question, pas un troisième diagnostic."))
        self.traiter_la_reponse()
        self.bloquer_sans_analyse()                                  # rebloquée pour la même cause
        regles.repondre_en_autonome(self.projet, self.etat)
        self.vieillir()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_orphelin_jamais_avec_une_decision_ouverte_ni_une_validation_ni_sans_le_reglage(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "accord_agent", "agent": "chef",
                                    "texte": "Un agent demande votre accord.", "tache": self.recette, "quoi": "Générer 5 images"})
        self.bloquer_sans_analyse()
        regles.repondre_en_autonome(self.projet, self.etat)
        self.vieillir()
        actions = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual([a for a in actions if a[2]["decision"]["genre"] == "tache_bloquee"], [])   # l'accord seul, répondu
        etat2 = regles.nouvel_etat()
        self.projet.claude_autonome = False
        self.assertEqual(regles.repondre_en_autonome(self.projet, etat2), [])
        self.assertEqual(etat2.get("autonome_bloquees_vues"), None)

    def test_le_laisser_bloquee_du_directeur_est_respecte(self):
        self.projet.claude_autonome = True
        self.ok("tache", entree={"id": self.recette, "bloquee": BLOQUEE})
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "blocage_analyse", "tache": self.recette,
                                    "texte": "Bloquée.", "analyse": "x", "question": "q ?", "recommandation": "r",
                                    "motif": "echec"})
        d = next(x for x in self.ok("etat")["decisions"] if x["genre"] == "blocage_analyse")
        self.traiter(type="blocage_analyse", decision=d["id"], verdict="laisser")
        regles.repondre_en_autonome(self.projet, self.etat)
        self.vieillir()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    # --- Une série qui attend volontairement une autre n'est pas relancée ; une anomalie par cause.

    def serie_en_file(self):
        chemin = self.dossier / "suivi.json"
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        next(f for f in donnees["fonctionnalites"] if f["id"] == "f1")["en_file_derriere"] = "f9"
        chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        self.ok("message", entree={"fonctionnalite": "f1", "auteur": "chef",
                                   "texte": "Cette fonctionnalité attend f9 : elle démarrera dès que celle-ci sera terminée."})
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "serie_arretee", "fonctionnalite": "f1",
                                    "texte": "« f1 » ne progresse plus."})
        self.projet.claude_autonome = True

    def test_la_serie_arretee_recoit_ce_qu_elle_attend(self):
        self.serie_en_file()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        dossier = action[2]
        self.assertEqual(dossier["en_file_derriere"], "f9")
        self.assertIn("attend f9", dossier["dernier_message_du_chef"])
        self.assertEqual(sorted(dossier["verdicts"]), ["laisser", "relancer"])

    def test_laisser_une_serie_n_est_pas_la_relancer_et_le_chef_le_dit(self):
        self.serie_en_file()
        action = self.juger()
        avant = len(self.paroles())
        self.appliquer(action, objet(verdict="laisser", raison="Elle attend f9 exprès."))
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "serie_arretee"]
        self.assertEqual(demande["verdict"], "laisser")
        regles.traiter_demande(self.projet, demande, self.etat)
        self.assertEqual(len([d for d in self.ok("etat")["decisions"] if d["genre"] == "serie_arretee"]), 1)   # rien de levé
        (parole,) = self.paroles()[avant:]
        self.assertIn("Elle attend f9 exprès", parole)

    def test_une_seule_anomalie_par_cause_avec_un_compteur(self):
        self.bloquer()
        a = {"titre": "Fausse alerte de série", "description": "La série attend une autre."}
        for _ in range(3):
            regles._noter_une_anomalie(self.projet, self.etat, self.recette, "Recette", "Amélioration : " + a["titre"], a["description"])
        self.assertEqual(len(self.ok("anomalies")["anomalies"]), 1)
        self.assertEqual(self.etat["anomalies_vues"]["Amélioration : " + a["titre"]], 3)
        self.assertTrue(any("revenue 3 fois" in str(j["texte"]) for j in self.la(self.recette)["journal"]))

    # --- Cas 8 : une relance par changement de cause, jamais sans changement.

    def passer(self, signature):
        with mock.patch.object(regles, "_signature_des_causes", return_value=signature):
            regles.repondre_en_autonome(self.projet, self.etat)
        return [x for x in self.demande_en_attente() if x["type"] == "retour"]

    def test_une_relance_par_changement_de_cause_pas_sans_changement(self):
        self.projet.claude_autonome = True
        self.assertEqual(self.passer(("c1", ())), [])                 # première vue : rien
        self.assertEqual(self.passer(("c1", ())), [])                 # aucun changement : rien
        (relance,) = self.passer(("c2", ()))                          # le service a une nouvelle version
        self.assertTrue(relance["claude_autonome"] and relance["texte"].startswith("Relance demandée"))
        regles.traiter_demande(self.projet, relance, self.etat)
        self.assertFalse(self.la(self.recette).get("bloquee"))
        self.ok("tache", entree={"id": self.recette, "bloquee": BLOQUEE})
        self.assertEqual(self.passer(("c2", ())), [])                 # même cause : pas de seconde relance
        self.assertEqual(len(self.passer(("c2", ("a1",)))), 1)        # une anomalie réglée : une relance de plus

    def test_sans_le_reglage_aucune_relance(self):
        self.assertEqual(self.passer(("c1", ())), [])
        self.assertEqual(self.passer(("c2", ())), [])

    # --- Cas 9 : le Chef dit chaque action, une phrase, jamais deux ; rien sans le réglage.

    def paroles(self):
        return [m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"] if m["auteur"] == "chef"]

    def test_chaque_reponse_laisse_exactement_un_message_du_chef(self):
        self.bloquer()
        avant = len(self.paroles())
        self.appliquer(self.juger(), objet(verdict="renvoyer", tache_dev=self.dev, texte="Corrige /sante.",
                                           raison="Le défaut vient du code livré.",
                                           lecon={"portee": "metier", "texte": "Teste /sante avant de livrer."}))
        nouveaux = self.paroles()[avant:]
        self.assertEqual(len(nouveaux), 1)
        self.assertIn("J'ai renvoyé le défaut", nouveaux[0])
        self.assertIn("Le défaut vient du code livré.", nouveaux[0])
        self.assertIn("leçon", nouveaux[0])
        self.traiter_la_reponse()
        self.assertEqual(len(self.paroles()[avant:]), 1)             # le traitement n'en ajoute pas

    def test_la_relance_apres_le_redeploiement_est_dite_une_fois(self):
        self.avec_service([("a_jour", "ok")])
        self.bloquer()
        self.appliquer(self.juger(), objet(verdict="redeployer"))
        self.traiter_la_reponse()
        avant = len(self.paroles())
        regles.repondre_en_autonome(self.projet, self.etat)
        (parole,) = self.paroles()[avant:]
        self.assertIn("le service est redéployé et répond", parole)

    def test_sans_le_reglage_le_chef_ne_dit_rien(self):
        avant = len(self.paroles())
        self.bloquer(activer=False)
        regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(len(self.paroles()), avant)


class Apprentissage(tmr.Arrets):
    """Une réponse généralisable est apprise : la fois d'après, le moteur répond seul, sans appel à Claude."""

    def appliquer(self, action, o):
        _, type_, _, suite = action
        return regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet=o), suite, self.etat)

    def ouvrir_un_accord(self):
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        self.projet.claude_autonome = True
        return self.decisions_accord()[0]

    def test_claude_accepte_puis_le_moteur_repond_seul(self):
        d = self.ouvrir_un_accord()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(action[2]["decision"]["quoi"], "Générer 5 images")
        self.appliquer(action, objet(generalisable=True, lecon={"portee": "metier", "texte": "Génère sans demander."}))
        fichier = regles._fichier_appris(self.projet)
        appris = json.loads(fichier.read_text(encoding="utf-8"))
        self.assertEqual(list(appris), ["accord_agent|générer 5 images"])
        # même demande plus tard : aucun jugement, la réponse apprise est déposée et comptée
        self.etat["autonome_faites"].discard(d["id"])
        self.etat["autonome_reprises"].clear()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        reponses = [x for x in self.demande_en_attente() if x["type"] == "accord_agent"]
        self.assertTrue(any(x["raison"].startswith("Réponse apprise") for x in reponses))
        self.assertEqual(json.loads(fichier.read_text(encoding="utf-8"))["accord_agent|générer 5 images"]["emplois"], 1)

    def test_une_reponse_non_generalisable_n_est_pas_apprise(self):
        self.ouvrir_un_accord()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, objet(generalisable=False))
        self.assertFalse(regles._fichier_appris(self.projet).exists())

    def test_la_decision_levee_pendant_la_reflexion_ne_fait_rien(self):
        d = self.ouvrir_un_accord()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.traiter(type="accord_agent", decision=d["id"], verdict="accepter")      # le Directeur a répondu
        self.assertEqual(self.appliquer(action, objet()), [])


if __name__ == "__main__":
    unittest.main()
