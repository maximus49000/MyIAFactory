"""Le découpage des étapes selon le poste, de bout en bout dans le moteur (conception 2026-11-13-etapes-locales-design.md) :
« Proposer le découpage » → jugement `decouper_lieux` (Sonnet) → décision de projet `decoupage_lieux` avec l'avant/après ;
« Valider » applique, « Refuser » ne change rien ; le lieu d'une étape se règle tout de suite (`lieu_etape`).
Aucun appel réel : les jugements sont joués par un faux `appeler`."""
import json

from bureau import demandes, releve
from moteur import jugement, regles
from orchestrateur import lieux
from tests.test_moteur_jugement import Appels, reponse
from tests.test_moteur_polyvalents import FLUX, Base

# La proposition type sur FLUX (dev, val, qa, archi, livraison) : le dev découpé, la recette locale.
PROPOSITION = [dict(FLUX[0], nom="Développement : code", lieu="indifférent"),
               {"id": "dev-local", "nom": "Développement : mise en place et tests", "role": "dev", "service": "dev",
                "lieu": "local"},
               FLUX[1], dict(FLUX[2], lieu="local"), *FLUX[3:]]
OBJET = {"flux": PROPOSITION, "message": "Le code part dans le cloud ; sa mise en place et la recette restent au poste."}


class Decoupage(Base):
    def setUp(self):
        super().setUp()
        self.agent("agent-1")

    def suivi(self):
        return json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))

    def demande(self, type_, **champs):
        rid = self.ok("actions", entree={"type": type_, **champs})["id"]
        return next(d for d in self.suivi()["demandes"] if d["id"] == rid)

    def reponse_de(self, demande):
        return next(d for d in self.suivi()["demandes"] if d["id"] == demande["id"])["reponse"]

    def decisions(self):
        return [d for d in self.suivi()["decisions_projet"] if d["genre"] == "decoupage_lieux"]

    def juger(self, objet, *, rate=False):
        """Demande le découpage, puis rend le jugement (`objet`, ou deux réponses invalides si `rate`)."""
        d = self.demande("proposer_decoupage")
        actions = regles.traiter_demande(self.projet, d, regles.nouvel_etat())
        self.assertEqual([a[:2] for a in actions], [("juger", "decouper_lieux")])
        _, type_, dossier, suite = actions[0]
        appels = Appels(*([reponse(objet)] * (2 if rate else 1)))
        decision = jugement.juger(type_, dossier, couche="claude", appeler=appels)
        regles.appliquer_jugement(self.projet, type_, decision, suite)
        return d, dossier, appels

    def flux(self):
        return json.loads(self.factory.read_text(encoding="utf-8"))["flux"]

    def test_le_dossier_porte_le_flux_de_reference_et_l_environnement(self):
        d = self.demande("proposer_decoupage")
        _, _, dossier, suite = regles.traiter_demande(self.projet, d, regles.nouvel_etat())[0]
        self.assertEqual(dossier["flux"], lieux.flux_de_reference({"flux": FLUX, "workflows": []}))
        for cle in ("environnement", "suggerees", "metiers"):
            self.assertIsInstance(dossier[cle], list, cle)
        self.assertEqual(suite["demande"], d["id"])

    def test_jugement_valide_pose_la_decision_avec_avant_apres(self):
        avant = self.factory.read_bytes()
        d, _, appels = self.juger(OBJET)
        self.assertEqual(len(appels.recus), 1)
        self.assertEqual(appels.recus[0]["modele"], "sonnet")
        [decision] = self.decisions()
        self.assertEqual([e["id"] for e in decision["avant"]], [e["id"] for e in FLUX])
        self.assertEqual(decision["apres"], PROPOSITION)
        self.assertEqual(decision["message"], OBJET["message"])
        self.assertEqual(self.factory.read_bytes(), avant)       # rien n'est appliqué avant la décision
        self.assertTrue(self.reponse_de(d))

    def test_jugement_redemande_une_fois_puis_pas_de_decision(self):
        avant = self.factory.read_bytes()
        invalide = {**OBJET, "flux": PROPOSITION[:-1]}          # la livraison a disparu : refusée
        d, _, appels = self.juger(invalide, rate=True)
        self.assertEqual(len(appels.recus), 2)
        self.assertIn(jugement.CLE_ERREUR, appels.recus[1]["dossier"])
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.factory.read_bytes(), avant)
        self.assertIn("rien n'a changé", self.reponse_de(d))

    def test_une_seule_proposition_en_attente(self):
        self.juger(OBJET)
        d = self.demande("proposer_decoupage")
        self.assertEqual(regles.traiter_demande(self.projet, d, regles.nouvel_etat()), [])
        self.assertIn("attend déjà", self.reponse_de(d))
        self.assertEqual(len(self.decisions()), 1)

    def test_valider_applique(self):
        self.juger(OBJET)
        [decision] = self.decisions()
        d = self.demande("decoupage_lieux", decision=decision["id"], verdict="valider")
        regles.traiter_demande(self.projet, d, regles.nouvel_etat())
        flux = self.flux()
        self.assertEqual([e["id"] for e in flux], ["dev", "dev-local", "val", "qa", "archi", "livraison"])
        self.assertEqual((flux[0]["lieu"], flux[1]["lieu"], flux[3]["lieu"]), ("indifférent", "local", "local"))
        self.assertEqual(self.decisions(), [])
        self.assertTrue(self.reponse_de(d))

    def test_refuser_ne_change_rien(self):
        self.juger(OBJET)
        avant = self.factory.read_bytes()
        [decision] = self.decisions()
        d = self.demande("decoupage_lieux", decision=decision["id"], verdict="refuser")
        regles.traiter_demande(self.projet, d, regles.nouvel_etat())
        self.assertEqual(self.factory.read_bytes(), avant)
        self.assertEqual(self.decisions(), [])
        self.assertTrue(self.reponse_de(d))

    def test_aucune_tache_touchee(self):
        t = self.tache("flux:qa")
        self.faite(t)          # une tâche finie : rien ne la fait repartir, le découpage seul pourrait la toucher
        self.juger(OBJET)
        avant = [x for x in self.suivi()["taches"] if x["id"] == t]
        [decision] = self.decisions()
        regles.traiter_demande(self.projet, self.demande("decoupage_lieux", decision=decision["id"], verdict="valider"),
                               regles.nouvel_etat())
        self.assertEqual([x for x in self.suivi()["taches"] if x["id"] == t], avant)

    def test_un_element_en_cours_garde_son_etape(self):
        """L'élément à la recette (« qa ») y reste quand une étape d'avant est découpée ; l'élément au dev continue sur
        sa partie code puis enchaîne sur la partie locale."""
        self.juger(OBJET)
        etat = regles.nouvel_etat()
        production = [e["id"] for e in regles._production(self.projet, "f1")]
        etat["elements"]["f1/e1"] = {"fid": "f1", "element": {"id": "e1", "nom": "e1"}, "phase": "flux",
                                     "pas": production.index("qa"), "taches": []}
        etat["elements"]["f1/e2"] = {"fid": "f1", "element": {"id": "e2", "nom": "e2"}, "phase": "flux",
                                     "pas": production.index("dev"), "taches": []}
        [decision] = self.decisions()
        regles.traiter_demande(self.projet, self.demande("decoupage_lieux", decision=decision["id"], verdict="valider"),
                               etat)
        apres = [e["id"] for e in regles._production(self.projet, "f1")]
        self.assertEqual(apres[etat["elements"]["f1/e1"]["pas"]], "qa")
        self.assertEqual(apres[etat["elements"]["f1/e2"]["pas"]], "dev")
        self.assertEqual(apres[etat["elements"]["f1/e2"]["pas"] + 1], "dev-local")

    def test_la_partie_locale_recoit_sa_consigne(self):
        """La tâche de la partie locale dit de récupérer le code, compiler, tester, capturer, sans le réécrire."""
        self.juger(OBJET)
        [decision] = self.decisions()
        regles.traiter_demande(self.projet, self.demande("decoupage_lieux", decision=decision["id"], verdict="valider"),
                               regles.nouvel_etat())
        production = [e["id"] for e in regles._production(self.projet, "f1")]
        etat = regles.nouvel_etat()
        for etape in ("dev-local", "dev"):
            v = {"fid": "f1", "element": {"id": f"e-{etape}", "nom": "Écran"}, "phase": "flux",
                 "pas": production.index(etape), "taches": []}
            tid = regles._tache_de_flux(self.projet, etat, v)
            journal = " ".join(j["texte"] for t in self.suivi()["taches"] if t["id"] == tid for j in t["journal"])
            if etape == "dev-local":
                self.assertIn(lieux.CONSIGNE_PARTIE_LOCALE, journal)
            else:
                self.assertNotIn(lieux.CONSIGNE_PARTIE_LOCALE, journal)
        for mot in ("récupère", "compile", "teste", "capture", "réécris pas"):
            self.assertIn(mot, lieux.CONSIGNE_PARTIE_LOCALE)
        self.assertLess(len(lieux.CONSIGNE_PARTIE_LOCALE), 600)

    def test_lieu_etape_immediat(self):
        d = self.demande("lieu_etape", etape="qa", lieu="local")
        regles.traiter_demande(self.projet, d, regles.nouvel_etat())
        self.assertEqual(next(e for e in self.flux() if e["id"] == "qa")["lieu"], "local")
        self.assertEqual(self.decisions(), [])
        self.assertTrue(self.reponse_de(d))
        d = self.demande("lieu_etape", etape="qa", lieu=None)
        regles.traiter_demande(self.projet, d, regles.nouvel_etat())
        self.assertNotIn("lieu", next(e for e in self.flux() if e["id"] == "qa"))

    def test_lieu_etape_refuse_sur_une_validation(self):
        avant = self.factory.read_bytes()
        d = self.demande("lieu_etape", etape="val", lieu="local")
        regles.traiter_demande(self.projet, d, regles.nouvel_etat())
        self.assertEqual(self.factory.read_bytes(), avant)
        self.assertIn("pas pu", self.reponse_de(d))


class Bureau(Base):
    """Le relevé publie le lieu des étapes et la décision ; le bureau vérifie les trois demandes."""

    def setUp(self):
        super().setUp()
        self.agent("agent-1")

    def releve(self):
        return self.ok("releve")

    def test_releve_publie_les_etapes_et_leurs_lieux(self):
        self.ok("lieux", entree={"action": "regler", "etape": "qa", "lieu": "local"})
        r = self.releve()
        self.assertEqual(releve.valider(r), [])
        etapes = {e["id"]: e for e in r["etapes_lieux"]}
        self.assertEqual(etapes["qa"]["lieu"], "local")
        self.assertIsNone(etapes["dev"]["lieu"])
        self.assertTrue(etapes["val"]["validation"])
        self.assertEqual(next(c for c in r["colonnes"] if c["id"] == "qa")["lieu"], "local")

    def test_tache_sur_le_poste_local_au_releve(self):
        self.ok("lieux", entree={"action": "regler", "etape": "qa", "lieu": "local"})
        locale, ailleurs = self.tache("flux:qa"), self.tache("flux:dev", element="e2")
        r = self.releve()
        self.assertEqual(releve.valider(r), [])
        par_id = {t["id"]: t for t in r["taches"]}
        self.assertEqual(par_id[locale]["lieu"], "local")
        self.assertNotIn("lieu", par_id[ailleurs])
        self.assertIn("lieu", releve.valider({**r, "taches": [{**par_id[locale], "lieu": "cloud"}]})[0])

    def test_releve_valide_avec_la_decision(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "decoupage_lieux",
                                    "texte": "Découper les étapes selon le poste ?", "apres": PROPOSITION,
                                    "message": OBJET["message"]})
        r = self.releve()
        self.assertEqual(releve.valider(r), [])
        [d] = [x for x in r["decisions_projet"] if x["genre"] == "decoupage_lieux"]
        self.assertEqual(d["apres"], PROPOSITION)
        self.assertEqual([e["id"] for e in d["avant"]], [e["id"] for e in FLUX])

    def test_la_decision_refuse_une_proposition_invalide(self):
        code, _ = self.outil("decision", entree={"action": "poser", "portee": "projet", "genre": "decoupage_lieux",
                                                 "texte": "?", "apres": PROPOSITION[:-1], "message": "x"})
        self.assertNotEqual(code, 0)

    def test_demandes_verifiees(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "decoupage_lieux",
                                    "texte": "Découper ?", "apres": PROPOSITION, "message": "x"})
        r = self.releve()
        did = next(x["id"] for x in r["decisions_projet"] if x["genre"] == "decoupage_lieux")
        verifier = lambda d: demandes.verifier(d, r)   # noqa: E731
        self.assertIsNone(verifier({"type": "decoupage_lieux", "decision": did, "verdict": "valider"}))
        self.assertIsNone(verifier({"type": "decoupage_lieux", "decision": did, "verdict": "refuser"}))
        self.assertIsNotNone(verifier({"type": "decoupage_lieux", "decision": did, "verdict": "peut-être"}))
        self.assertIsNotNone(verifier({"type": "decoupage_lieux", "decision": "d999", "verdict": "valider"}))
        self.assertIsNone(verifier({"type": "lieu_etape", "etape": "qa", "lieu": "local"}))
        self.assertIsNone(verifier({"type": "lieu_etape", "etape": "qa", "lieu": "indifférent"}))
        self.assertIsNone(verifier({"type": "lieu_etape", "etape": "qa", "lieu": None}))
        self.assertIsNotNone(verifier({"type": "lieu_etape", "etape": "qa", "lieu": "cloud"}))
        self.assertIsNotNone(verifier({"type": "lieu_etape", "etape": "val", "lieu": "local"}))
        self.assertIsNotNone(verifier({"type": "lieu_etape", "etape": "inconnue", "lieu": "local"}))
        self.assertIsNotNone(verifier({"type": "lieu_etape", "etape": "qa"}))
        # une proposition attend déjà : pas de seconde demande
        self.assertIsNotNone(verifier({"type": "proposer_decoupage"}))

    def test_proposer_decoupage_verifie(self):
        r = self.releve()
        self.assertIsNone(demandes.verifier({"type": "proposer_decoupage"}, r))
        self.assertIsNotNone(demandes.verifier({"type": "proposer_decoupage"}, {**r, "etapes_lieux": []}))
