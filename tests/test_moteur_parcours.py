"""Le parcours d'une nouvelle fonctionnalité : classer le genre, proposer son workflow, recruter, puis cadrer.

Une ligne du parcours (conception, section 5), un test. Appels d'IA et agents simulés : aucun appel réel.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from moteur import jugement, regles
from orchestrateur import outil
from tests.orch_aide import factory_minimale
from tests.test_moteur_regles import Base

GENRE = "# Genre : {}\nDomaine : {}\nLivrable : des fichiers\nOutils : aucun\n"
CLASSER_MEME = {"verdict": "meme", "genre": "badges", "nouveau": None, "raison": "Même genre que le projet."}
CLASSER_PROCHE = {"verdict": "proche", "genre": "stickers", "nouveau": None, "raison": "Mêmes outils, même livrable."}
CLASSER_AUTRE = {"verdict": "autre", "genre": None, "raison": "Un jeu n'est pas un badge.",
                 "nouveau": {"id": "jeu-mobile", "description": "Jeux pour téléphone"}}
CLASSER_INCERTAIN = {"verdict": "incertain", "genre": None, "nouveau": None, "raison": "Peu clair."}
PROPOSITION = {
    "flux": [{"etape": "dev", "nom": "Développement du badge", "role": "dev", "service": "dev"},
             {"etape": "livraison", "nom": "Livraison des badges", "role": "livreur", "service": "livraison"}],
    "services": [{"id": "livraison", "nom": "Livraison"}],
    "agents": [{"cle": "liv-1", "prenom": "Paul", "role": "livreur", "service": "livraison", "modele": "Haiku",
                "justification": "Tâche mécanique.", "fable_suggere": False, "texte": "Livre les badges."}],
    "briefs": {"livreur": "Livre les fichiers dans les livrables."},
    "livrable": "Les badges en PNG", "environnement": [], "outils_installation": []}
SANS_NOUVEAU = {**PROPOSITION, "services": [], "agents": [], "briefs": {},
                "flux": [{"etape": "dev", "nom": "Développement du badge", "role": "dev", "service": "dev"},
                         {"etape": "livraison", "nom": "Livraison des badges", "role": "dev", "service": "dev"}]}


class AvecParcours(Base):
    """Un projet de genre « badges » et de quoi mener une demande de fonctionnalité jusqu'à son workflow proposé."""

    def setUp(self):
        super().setUp()
        self.reecrire(genre="badges", description="Des badges pour une chaîne de streaming", mots_interdits=["Secret"])
        for genre in ("badges", "stickers"):
            self.ecrire(self.dossier / "memoire" / "genres" / f"{genre}.md", GENRE.format(genre, f"Genre {genre}"))
        self.ecrire(self.dossier / "fiches" / "briefs" / "dev.md", "Brief des développeurs.")

    def ecrire(self, chemin, texte):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")

    def lire_factory(self):
        return json.loads(self.factory.read_text(encoding="utf-8"))

    def reecrire(self, **champs):
        d = self.lire_factory()
        d.update(champs)
        self.factory.write_text(json.dumps(d), encoding="utf-8")

    def decisions(self, genre=None):
        return [d for d in self.ok("etat")["decisions"] if genre is None or d["genre"] == genre]

    def demander(self, juges, texte="Un badge pour le chat YouTube", **champs):
        """La demande de fonctionnalité, jusqu'au bout de ses jugements. Rend (demande, actions vues)."""
        d, actions = self.traiter(type="fonctionnalite", texte=texte, **champs)
        return d, self.piloter(actions, juges=juges)

    def vers_l_organisation(self, proposition=PROPOSITION, classer=CLASSER_MEME):
        d, vus = self.demander({"classer_genre": classer, "proposer_organisation": proposition})
        return d, self.decisions("organisation")[0]

    def accepter(self, decision, **champs):
        return self.traiter(type="organisation", decision=decision["id"], verdict="accepter", **champs)



class Parcours(AvecParcours):
    # --- Classer la demande.

    def test_demande_du_meme_genre_propose_son_workflow(self):
        d, vus = self.demander({"classer_genre": CLASSER_MEME, "proposer_organisation": PROPOSITION})
        self.assertEqual([(a[0], a[1]) for a in vus], [("juger", "classer_genre"), ("juger", "proposer_organisation")])
        dossier = vus[0][2]
        self.assertEqual(dossier["demande"]["texte"], "Un badge pour le chat YouTube")
        self.assertEqual([g["id"] for g in dossier["genres_du_projet"]], ["badges"])
        self.assertEqual(sorted(g["id"] for g in dossier["genres_connus"]), ["badges", "stickers"])
        self.assertEqual(dossier["mots_interdits"], ["Secret"])
        self.assertEqual(vus[1][2]["fonctionnalite"], "f1")
        self.assertEqual(self.fonc()["genre"], "badges")
        (decision,) = self.decisions("organisation")
        o = decision["organisation"]
        self.assertEqual([e["id"] for e in o["flux"]], ["f1-dev", "f1-livraison"])
        self.assertEqual(o["workflow"], {"id": "w-f1", "genre": "badges", "flux": o["flux"]})
        self.assertEqual(o["fonctionnalite"], "f1")
        self.assertEqual([s["id"] for s in o["services"]], ["metier", "dev", "livraison"])
        self.assertEqual([(a["cle"], a["lieu"]) for a in o["agents"]], [("liv-1", "local")])
        self.assertEqual(o["livrable"], "Les badges en PNG")
        self.assertEqual(len(o["cout"]["tokens"]), 2)
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.taches(etape="cadrage"), [])          # le cadrage attend la validation du workflow
        self.assertEqual(self.demande_en_attente(), [])

    def test_texte_de_la_proposition_sans_double_point(self):
        _, decision = self.vers_l_organisation({**PROPOSITION, "livrable": "Les badges en PNG."})
        self.assertIn("Livrable : Les badges en PNG. ", decision["texte"])
        self.assertNotIn("..", decision["texte"])

    def test_demande_proche_rattachee(self):
        d, vus = self.demander({"classer_genre": CLASSER_PROCHE, "proposer_organisation": PROPOSITION})
        self.assertEqual(self.fonc()["genre"], "stickers")
        self.assertEqual(self.decisions("genre_fonctionnalite"), [])    # aucune question : le genre est rattaché
        self.assertEqual(len(self.decisions("organisation")), 1)
        self.assertEqual(self.decisions("organisation")[0]["organisation"]["workflow"]["genre"], "stickers")
        self.assertIn("stickers", self.fonc()["discussion"][-2]["texte"])      # le moteur le dit
        self.assertEqual(vus[1][2]["genre"], "stickers")

    def test_demande_d_un_autre_genre_avertit(self):
        d, vus = self.demander({"classer_genre": CLASSER_AUTRE}, texte="Un casse-briques pour Android")
        self.assertEqual([(a[0], a[1]) for a in vus], [("juger", "classer_genre")])    # pas de proposition tout de suite
        (q,) = self.decisions("genre_fonctionnalite")
        self.assertEqual(q["portee"], "f1")
        self.assertEqual((q["propose"], q["incertain"]), ("jeu-mobile", False))
        self.assertEqual(q["nouveau"], {"id": "jeu-mobile", "description": "Jeux pour téléphone"})
        self.assertEqual(sorted(q["genres_connus"]), ["badges", "stickers"])
        self.assertIn("nouveau projet", q["texte"])
        self.assertIn("badges", q["texte"])
        self.assertEqual(self.decisions("organisation"), [])
        self.assertIsNone(self.fonc()["genre"])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertIn(q["texte"], [m["texte"] for m in self.fonc()["discussion"]])
        self.assertEqual(self.taches(etape="cadrage"), [])

    def test_incertain_demande_a_l_utilisateur(self):
        self.demander({"classer_genre": CLASSER_INCERTAIN}, texte="Quelque chose de visuel")
        (q,) = self.decisions("genre_fonctionnalite")
        self.assertEqual((q["incertain"], q["propose"]), (True, "badges"))     # sans piste : le genre du projet
        self.assertNotIn("nouveau", q)
        self.assertIn("même genre", q["texte"])
        # « C'est le même genre » : le genre du projet, puis la proposition de workflow
        d, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="meme")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])
        self.assertEqual(self.fonc()["genre"], "badges")
        self.assertEqual(self.decisions("genre_fonctionnalite"), [])

    # --- Les trois issues de l'avertissement.

    def avertie(self):
        self.demander({"classer_genre": CLASSER_AUTRE}, texte="Un casse-briques pour Android")
        return self.decisions("genre_fonctionnalite")[0]

    def test_choix_ici_propose_le_workflow(self):
        q = self.avertie()
        d, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="ici")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])
        self.assertEqual(actions[0][2]["genre"], "jeu-mobile")
        self.assertEqual(actions[0][2]["demande"]["texte"], "Un casse-briques pour Android")
        self.piloter(actions, juges={"proposer_organisation": PROPOSITION})
        self.assertEqual(self.decisions("genre_fonctionnalite"), [])
        self.assertEqual(self.fonc()["genre"], "jeu-mobile")
        w = self.decisions("organisation")[0]["organisation"]["workflow"]
        self.assertEqual((w["genre"], w["genre_nouveau"]), ("jeu-mobile", {"description": "Jeux pour téléphone"}))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_choix_ici_avec_un_genre_corrige(self):
        q = self.avertie()
        _, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="ici",
                                  genre="stickers")
        self.assertEqual(actions[0][2]["genre"], "stickers")
        self.assertEqual(self.fonc()["genre"], "stickers")
        # un genre nouveau demande une description
        q = self.avertie_encore()
        d, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f2", choix="ici",
                                  genre="jeu-de-role")
        self.assertEqual(actions, [])
        self.assertIn("description", self.statut(d["id"])["reponse"])
        self.assertEqual(len(self.decisions("genre_fonctionnalite")), 1)

    def avertie_encore(self):
        self.demander({"classer_genre": CLASSER_AUTRE}, texte="Un autre jeu")
        return self.decisions("genre_fonctionnalite")[0]

    def autre_projet(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        autre = Path(t.name) / "casse-briques"
        autre.mkdir()
        factory_minimale(autre)
        return autre

    def test_choix_nouveau_projet_deplace_la_demande(self):
        q = self.avertie()
        autre = self.autre_projet()
        d, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1",
                                  choix="nouveau_projet", projet_cree=str(autre / "reglages.json"))
        self.assertEqual(actions, [])
        f = self.fonc()
        self.assertEqual((f["etape"], f["deplacee_vers"]), ("deplacee", "casse-briques"))
        self.assertIn("Partie dans le projet casse-briques", [m["texte"] for m in f["discussion"]])
        self.assertEqual(self.decisions("genre_fonctionnalite"), [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        # la demande d'origine, recréée dans le nouveau projet par sa commande `actions`, avec son genre
        suivi = json.loads((autre / "suivi.json").read_text(encoding="utf-8"))
        (recreee,) = suivi["demandes"]
        self.assertEqual((recreee["type"], recreee["texte"], recreee["genre"], recreee["description"]),
                         ("fonctionnalite", "Un casse-briques pour Android", "jeu-mobile", "Jeux pour téléphone"))
        self.assertEqual(suivi["fonctionnalites"][0]["discussion"][0]["texte"], "Un casse-briques pour Android")
        self.assertEqual(self.ok("etat")["fonctionnalites"][0]["etape"], "deplacee")
        self.assertEqual(self.taches(), [])

    def test_nouveau_projet_impossible_reste_ici(self):
        q = self.avertie()
        for champs in ({"projet_cree": str(self.dossier / "inexistant" / "reglages.json")}, {}):
            d, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1",
                                      choix="nouveau_projet", **champs)
            self.assertEqual(actions, [])
            self.assertEqual(self.fonc()["etape"], "cadrage")                 # rien n'a bougé
            self.assertEqual(len(self.decisions("genre_fonctionnalite")), 1)
            self.assertIn("Dans ce projet", self.statut(d["id"])["reponse"])
        # « Dans ce projet » reste possible
        _, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="ici")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])

    def test_projet_sans_genre_confirme_d_apres_la_description(self):
        self.reecrire(genre=None)
        d, vus = self.demander({"classer_genre": CLASSER_PROCHE})
        self.assertEqual(vus[0][2]["demande"]["texte"], "Des badges pour une chaîne de streaming")
        self.assertEqual(vus[0][2]["genres_du_projet"], [])
        (c,) = self.decisions("confirmer_genre")
        self.assertEqual((c["portee"], c["propose"], c["fonctionnalite"]), ("projet", "stickers", "f1"))
        self.assertIn("badges", c["genres_connus"])
        self.assertEqual(self.decisions("organisation"), [])
        self.assertEqual(self.taches(etape="cadrage"), [])
        # le genre confirmé fixe celui du projet et de la fonctionnalité, puis le workflow est proposé
        d2, actions = self.traiter(type="genre", decision=c["id"], genre="stickers")
        self.assertEqual(self.lire_factory()["genre"], "stickers")
        self.assertEqual(self.fonc()["genre"], "stickers")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])
        self.assertEqual(self.decisions("confirmer_genre"), [])
        self.assertEqual(self.statut(d2["id"])["statut"], "traitée")

    def test_projet_cree_sans_genre_propose_son_genre_au_demarrage(self):
        """Un projet créé au bureau avec une description : dès le premier passage du moteur, sans attendre une demande,
        son genre est proposé (« Le genre vous sera proposé dans un instant »)."""
        self.reecrire(genre=None)
        actions = regles.genre_a_proposer(self.projet, self.etat)
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "classer_genre")])
        self.assertEqual(actions[0][2]["demande"]["texte"], "Des badges pour une chaîne de streaming")
        self.piloter(actions, juges={"classer_genre": CLASSER_PROCHE})
        (c,) = self.decisions("confirmer_genre")
        self.assertEqual((c["portee"], c["propose"], c.get("fonctionnalite")), ("projet", "stickers", None))
        self.assertIn("stickers", c["texte"])
        self.assertEqual(regles.genre_a_proposer(self.projet, self.etat), [])        # déjà proposé : rien de plus
        d, actions = self.traiter(type="genre", decision=c["id"], genre="stickers")
        self.assertEqual(actions, [])
        self.assertEqual(self.lire_factory()["genre"], "stickers")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(regles.genre_a_proposer(self.projet, self.etat), [])

    def test_genre_propose_sans_point_avant_la_parenthese(self):
        self.reecrire(genre=None)
        classer = {**CLASSER_AUTRE, "nouveau": {"id": "jeu-mobile", "description": "Jeux pour téléphone."}}
        self.piloter(regles.genre_a_proposer(self.projet, self.etat), juges={"classer_genre": classer})
        (c,) = self.decisions("confirmer_genre")
        self.assertIn("« jeu-mobile » (Jeux pour téléphone).", c["texte"])

    def test_rien_a_proposer_au_demarrage(self):
        self.assertEqual(regles.genre_a_proposer(self.projet, self.etat), [])           # le projet a un genre
        self.reecrire(genre=None, description=None)
        self.assertEqual(regles.genre_a_proposer(self.projet, self.etat), [])           # ni genre ni description
        self.reecrire(description="Des badges")
        regles.appliquer_jugement(self.projet, "classer_genre", jugement.Decision(question="Raté."),
                                  {"sans_genre": True}, self.etat)                       # un classement raté : silence
        self.assertEqual(self.decisions(), [])

    def test_demande_pendant_la_proposition_du_genre_l_attend(self):
        """Une demande arrive alors que le genre du projet est déjà proposé : pas de second classement, la décision
        porte désormais la fonctionnalité, et la confirmer propose son workflow."""
        self.reecrire(genre=None)
        self.piloter(regles.genre_a_proposer(self.projet, self.etat), juges={"classer_genre": CLASSER_PROCHE})
        d, vus = self.demander({})
        self.assertEqual(vus, [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        (c,) = self.decisions("confirmer_genre")
        self.assertEqual((c["propose"], c["fonctionnalite"]), ("stickers", "f1"))
        self.assertEqual(self.taches(etape="cadrage"), [])
        _, actions = self.traiter(type="genre", decision=c["id"], genre="stickers")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])

    # --- Valider le workflow proposé.

    def test_organisation_acceptee_recrute_et_lance_le_cadrage(self):
        _, decision = self.vers_l_organisation()
        d, actions = self.accepter(decision)
        f = self.lire_factory()
        (w,) = f["workflows"]
        self.assertEqual((w["id"], w["fonctionnalite"], w["genre"]), ("w-f1", "f1", "badges"))
        self.assertEqual([e["id"] for e in w["flux"]], ["f1-dev", "f1-livraison"])
        self.assertEqual([s["id"] for s in f["services"]], ["metier", "dev", "livraison"])
        self.assertEqual(f["flux"][0]["id"], "dev")                          # le flux du projet n'est pas touché
        fiche = (self.dossier / "fiches" / "liv-1.md").read_text(encoding="utf-8")
        self.assertIn("Modèle : Haiku", fiche)
        self.assertNotIn("Fable", fiche)
        self.assertTrue((self.dossier / "fiches" / "briefs" / "livreur.md").is_file())
        self.assertEqual((self.fonc()["genre"], self.fonc()["workflow"]), ("badges", "w-f1"))
        self.assertEqual(self.decisions("organisation"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])      # le cadrage démarre
        self.assertEqual(self.taches(etape="cadrage")[0]["agent"], "metier-1")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        # une tâche de cette fonctionnalité, créée sans colonne, part de la première étape de son workflow
        self.assertEqual(self.ok("tache", entree={"titre": "Un badge", "fonctionnalite": "f1"})["colonne"], "f1-dev")

    def test_agent_existant_reutilise(self):
        _, decision = self.vers_l_organisation(SANS_NOUVEAU)
        self.assertEqual(decision["organisation"]["agents"], [])
        avant = sorted(p.name for p in (self.dossier / "fiches").glob("*.md"))
        _, actions = self.accepter(decision)
        self.assertEqual(sorted(p.name for p in (self.dossier / "fiches").glob("*.md")), avant)
        self.assertEqual([s["id"] for s in self.lire_factory()["services"]], ["metier", "dev"])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])

    def test_genre_nouveau_cree_a_l_acceptation(self):
        q = self.avertie()
        _, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="ici")
        self.piloter(actions, juges={"proposer_organisation": PROPOSITION})
        decision = self.decisions("organisation")[0]
        appels = []
        with mock.patch.object(outil, "GIT", lambda args, cwd: appels.append(args[0]) or (0, "")):
            self.accepter(decision)
        genre = self.dossier / "memoire" / "genres" / "jeu-mobile.md"
        self.assertIn("Jeux pour téléphone", genre.read_text(encoding="utf-8"))
        self.assertIn("commit", appels)
        self.assertEqual(self.lire_factory()["workflows"][0]["genre"], "jeu-mobile")

    def test_refus_avec_texte_nouvelle_proposition(self):
        _, decision = self.vers_l_organisation()
        d, actions = self.traiter(type="organisation", decision=decision["id"], verdict="refuser",
                                  texte="Pas de service de livraison, le dev livre.")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])
        self.assertEqual(actions[0][2]["refus"], "Pas de service de livraison, le dev livre.")
        self.assertEqual(self.decisions("organisation"), [])
        self.piloter(actions, juges={"proposer_organisation": SANS_NOUVEAU})
        (nouvelle,) = self.decisions("organisation")
        self.assertNotEqual(nouvelle["id"], decision["id"])
        self.assertEqual(nouvelle["organisation"]["agents"], [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.lire_factory().get("workflows"), None)

    def test_refus_sans_texte_reprend_le_workflow_du_genre(self):
        etapes = [{"id": "f0-dev", "nom": "Dev", "role": "dev", "service": "dev"}]
        self.reecrire(workflows=[{"id": "w-f0", "fonctionnalite": "f0", "genre": "stickers", "flux": etapes},
                                 {"id": "w-f00", "fonctionnalite": "f00", "genre": "badges",
                                  "flux": [{"id": "f00-dev", "nom": "Dev", "role": "dev", "service": "dev"}]}])
        _, decision = self.vers_l_organisation()
        d, actions = self.traiter(type="organisation", decision=decision["id"], verdict="refuser")
        self.assertEqual((self.fonc()["workflow"], self.fonc()["genre"]), ("w-f00", "badges"))   # le plus récent du genre
        self.assertEqual(self.decisions("organisation"), [])
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])
        self.assertTrue(any("workflow existant" in m["texte"] for m in self.fonc()["discussion"]))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_refus_sans_texte_sans_workflow_du_genre_reprend_le_principal(self):
        _, decision = self.vers_l_organisation()
        self.traiter(type="organisation", decision=decision["id"], verdict="refuser")
        self.assertEqual(self.fonc()["workflow"], "principal")
        self.assertEqual(self.taches(etape="cadrage")[0]["agent"], "metier-1")

    def test_projet_sans_workflow_refus_reste_pose(self):
        self.reecrire(flux=[])
        _, decision = self.vers_l_organisation(SANS_NOUVEAU)
        d, actions = self.traiter(type="organisation", decision=decision["id"], verdict="refuser")
        self.assertEqual(actions, [])
        self.assertEqual([x["id"] for x in self.decisions("organisation")], [decision["id"]])     # toujours posée
        self.assertIsNone(self.fonc()["workflow"])
        self.assertIn("aucun workflow", self.statut(d["id"])["reponse"])
        self.assertEqual(self.taches(etape="cadrage"), [])
        # l'issue « abandonner » existe
        d2, _ = self.traiter(type="organisation", decision=decision["id"], verdict="abandonner")
        self.assertEqual(self.decisions("organisation"), [])
        self.assertEqual(self.fonc()["etape"], "deplacee")
        self.assertEqual(self.statut(d2["id"])["statut"], "traitée")

    def test_fable_coche_recrute_sur_fable(self):
        proposition = {**PROPOSITION, "agents": [dict(PROPOSITION["agents"][0], modele="Opus", fable_suggere=True)]}
        _, decision = self.vers_l_organisation(proposition)
        # non coché : Opus, sans accord
        self.assertEqual(decision["organisation"]["agents"][0]["fable_suggere"], True)
        d, _ = self.traiter(type="organisation", decision=decision["id"], verdict="accepter", fable=["dev-1"])
        self.assertIn("Fable n'a pas été suggéré", self.statut(d["id"])["reponse"])      # un autre agent : refusé
        self.assertEqual(len(self.decisions("organisation")), 1)
        self.assertFalse((self.dossier / "fiches" / "liv-1.md").exists())
        _, actions = self.accepter(decision, fable=["liv-1"])
        fiche = (self.dossier / "fiches" / "liv-1.md").read_text(encoding="utf-8")
        self.assertIn("Modèle : Fable", fiche)
        self.assertRegex(fiche, r"Fable : accordé par le Directeur le \d{4}-\d{2}-\d{2}")
        from orchestrateur import fiches
        self.assertTrue(fiches.fable_accorde(fiches.lire_fiche(self.dossier / "fiches" / "liv-1.md")))

    def test_fable_non_coche_reste_sur_opus(self):
        proposition = {**PROPOSITION, "agents": [dict(PROPOSITION["agents"][0], modele="Opus", fable_suggere=True)]}
        _, decision = self.vers_l_organisation(proposition)
        self.accepter(decision)
        fiche = (self.dossier / "fiches" / "liv-1.md").read_text(encoding="utf-8")
        self.assertIn("Modèle : Opus", fiche)
        self.assertNotIn("Fable", fiche)

    # --- Quand un jugement échoue : ne jamais bloquer.

    def test_classer_rate_continue_avec_le_genre_du_projet(self):
        d, actions = self.traiter(type="fonctionnalite", texte="Un badge")
        suite = actions[0][3]
        actions = regles.appliquer_jugement(self.projet, "classer_genre", jugement.Decision(question="Raté."), suite,
                                            self.etat)
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])       # le cadrage démarre
        self.assertEqual(self.fonc()["genre"], "badges")
        self.assertIn("badges", self.fonc()["discussion"][-1]["texte"])                  # une phrase le dit
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.decisions(), [])

    def proposition_ratee(self):
        d, actions = self.traiter(type="fonctionnalite", texte="Un badge")
        regles.appliquer_jugement(self.projet, "classer_genre", jugement.Decision(objet=CLASSER_MEME), actions[0][3],
                                  self.etat)
        return d, regles.appliquer_jugement(self.projet, "proposer_organisation",
                                            jugement.Decision(question="Je n'ai pas réussi à proposer."),
                                            {"demande": d["id"], "fonctionnalite": "f1"}, self.etat)

    def test_proposer_rate_question_au_directeur(self):
        d, actions = self.proposition_ratee()
        self.assertEqual(actions, [])
        message = self.fonc()["discussion"][-1]
        self.assertEqual(message["questions"][0]["choix"], [regles.CONTINUER, regles.JE_PRECISE])
        self.assertTrue(message["attend"])
        self.assertEqual(self.taches(), [])                                  # le cadrage attend la réponse
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        # « continuer avec le workflow actuel » : le principal (aucun autre workflow), puis le cadrage
        _, actions = self.traiter(type="message", fonctionnalite="f1", texte=regles.CONTINUER)
        self.assertEqual(self.fonc()["workflow"], "principal")
        self.assertEqual([(a[0], a[1]) for a in actions], [("agent", "metier-1")])

    def test_proposer_rate_puis_precisions_relancent_la_proposition(self):
        self.proposition_ratee()
        _, actions = self.traiter(type="message", fonctionnalite="f1", texte="Sans service de livraison")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])
        self.assertEqual(actions[0][2]["refus"], "Sans service de livraison")

    def test_un_message_pendant_la_question_n_ouvre_pas_le_cadrage(self):
        self.avertie()
        d, actions = self.traiter(type="message", fonctionnalite="f1", texte="Alors ?")
        self.assertEqual(actions, [])
        self.assertEqual(self.taches(etape="cadrage"), [])
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_workflows_du_genre_donnes_sans_prefixe(self):
        self.reecrire(workflows=[{"id": "w-f0", "fonctionnalite": "f0", "genre": "badges", "flux": [
            {"id": "f0-dev", "nom": "Dev", "role": "dev", "service": "dev"}]}])
        _, vus = self.demander({"classer_genre": CLASSER_MEME, "proposer_organisation": PROPOSITION})
        self.assertEqual(vus[1][2]["workflows_du_genre"][0]["id"], "w-f0")
        self.assertEqual(vus[1][2]["workflows_du_genre"][0]["flux"][0]["etape"], "dev")
        self.assertEqual(sorted(a["cle"] for a in vus[1][2]["agents"]), ["dev-1", "metier-1", "rel-1", "rel-2"])


if __name__ == "__main__":
    unittest.main()
