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


def outil_genres(test):
    from orchestrateur import memoire
    return memoire.genres(test.dossier / "memoire")


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

    def test_nom_de_la_fonctionnalite_l_intitule_du_jugement(self):
        longue = "Je voudrais un petit jeu de casse-briques pour Android, avec des niveaux et un score"
        d, vus = self.demander({"classer_genre": dict(CLASSER_AUTRE, intitule="Casse-briques Android"),
                                "proposer_organisation": PROPOSITION}, texte=longue)
        self.assertEqual(self.fonc()["nom"], "Casse-briques Android")
        self.assertEqual(self.fonc()["discussion"][0]["texte"], longue)       # la demande reste dite telle quelle

    def test_nom_de_la_fonctionnalite_sans_intitule_resume_aux_mots(self):
        longue = "Je voudrais un petit jeu de casse-briques pour Android, avec des niveaux et un score."
        self.demander({"classer_genre": CLASSER_MEME, "proposer_organisation": PROPOSITION}, texte=longue)
        nom = self.fonc()["nom"]
        self.assertEqual(nom, "Je voudrais un petit jeu de casse-briques pour Android")
        self.assertFalse(nom[-1] in ",;:.-", nom)
        # une demande courte garde son texte, sans point final
        self.demander({"classer_genre": CLASSER_MEME, "proposer_organisation": PROPOSITION}, texte="Un badge pour le chat.")
        self.assertEqual(self.fonc("f2")["nom"], "Un badge pour le chat")

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

    # --- Cohérence avec le projet (2026-11-12).

    def test_incoherente_previent_quel_que_soit_le_genre(self):
        for i, classer in enumerate((CLASSER_MEME, CLASSER_PROCHE, CLASSER_AUTRE, CLASSER_INCERTAIN), 1):
            c = dict(classer, coherente=False, raison="Un logo Twitch n'a rien à faire dans un jeu roguelike.")
            d, vus = self.demander({"classer_genre": c}, texte="Un logo Twitch")
            self.assertEqual([(a[0], a[1]) for a in vus], [("juger", "classer_genre")])    # rien ne démarre
            (q,) = [x for x in self.decisions("genre_fonctionnalite") if x["portee"] == f"f{i}"]
            self.assertIn("ne semble pas cohérente avec le projet", q["texte"])
            self.assertIn("Un logo Twitch n'a rien à faire", q["texte"])
            self.assertIn("nouveau projet", q["texte"])
            self.assertEqual(q["incertain"], classer["verdict"] != "autre")    # « même genre » seulement s'il a un sens
            self.assertIsNone(self.fonc(f"f{i}")["genre"])
            self.assertEqual(self.decisions("organisation"), [])

    def test_incoherente_propose_la_piste_de_genre(self):
        self.demander({"classer_genre": dict(CLASSER_AUTRE, coherente=False)})
        (q,) = self.decisions("genre_fonctionnalite")
        self.assertEqual((q["propose"], q["nouveau"]["id"]), ("jeu-mobile", "jeu-mobile"))

    def test_coherente_d_un_autre_genre_reste_dans_le_projet(self):
        d, vus = self.demander({"classer_genre": dict(CLASSER_AUTRE, coherente=True),
                                "proposer_organisation": PROPOSITION}, texte="Un casse-briques pour Android")
        self.assertEqual([(a[0], a[1]) for a in vus], [("juger", "classer_genre"), ("juger", "proposer_organisation")])
        self.assertEqual(self.decisions("genre_fonctionnalite"), [])           # aucune question de projet
        self.assertEqual(self.fonc()["genre"], "jeu-mobile")
        w = self.decisions("organisation")[0]["organisation"]["workflow"]
        self.assertEqual((w["genre"], w["genre_nouveau"]), ("jeu-mobile", {"description": "Jeux pour téléphone"}))
        self.assertTrue(any("a sa place dans ce projet" in m["texte"] for m in self.fonc()["discussion"]))

    def test_coherente_meme_ou_proche_comme_avant(self):
        self.demander({"classer_genre": dict(CLASSER_PROCHE, coherente=True), "proposer_organisation": PROPOSITION})
        self.assertEqual(self.fonc()["genre"], "stickers")
        self.assertEqual(self.decisions("genre_fonctionnalite"), [])

    def test_coherente_incertain_pose_la_question(self):
        self.demander({"classer_genre": dict(CLASSER_INCERTAIN, coherente=True)})
        (q,) = self.decisions("genre_fonctionnalite")
        self.assertTrue(q["incertain"])
        self.assertNotIn("cohérente", q["texte"])

    def test_coherence_inconnue_comme_avant(self):
        for i, coherente in enumerate((None, "absent"), 1):
            c = dict(CLASSER_AUTRE) if coherente == "absent" else dict(CLASSER_AUTRE, coherente=None)
            self.demander({"classer_genre": c})
            (q,) = [x for x in self.decisions("genre_fonctionnalite") if x["portee"] == f"f{i}"]
            self.assertIn("n'est pas du genre du projet", q["texte"])

    # --- La phrase d'un genre nouveau est proposée d'avance (2026-11-12).

    def test_genre_du_projet_propose_avec_sa_phrase_et_valide_sans_la_retaper(self):
        self.reecrire(genre=None)
        self.demander({"classer_genre": CLASSER_AUTRE})
        (c,) = self.decisions("confirmer_genre")
        self.assertEqual((c["propose"], c["description"]), ("jeu-mobile", "Jeux pour téléphone"))
        with mock.patch.object(outil, "GIT", lambda args, cwd: (0, "")):
            d, actions = self.traiter(type="genre", decision=c["id"], genre="jeu-mobile")     # aucune description tapée
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertIn("Jeux pour téléphone", (self.dossier / "memoire" / "genres" / "jeu-mobile.md").read_text(encoding="utf-8"))
        self.assertEqual(self.lire_factory()["genre"], "jeu-mobile")

    # --- Garder une demande dans un genre existant : sa description s'élargit, avec l'accord du Directeur.

    def elargissements(self):
        return self.decisions("elargir_genre")

    def description_du_genre(self, genre="badges"):
        return {g["id"]: g for g in outil_genres(self)}[genre]["domaine"]

    def test_meme_genre_propose_d_elargir_la_description_sans_bloquer(self):
        c = dict(CLASSER_INCERTAIN, elargissement="Genre badges, et aussi logos de chaîne")
        self.demander({"classer_genre": c}, texte="Un logo de chaîne")
        (q,) = self.decisions("genre_fonctionnalite")
        self.assertEqual(q["elargissement"], "Genre badges, et aussi logos de chaîne")
        self.assertEqual(self.elargissements(), [])                       # rien tant que le Directeur n'a pas choisi
        d, actions = self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="meme")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "proposer_organisation")])     # la fonctionnalité avance
        (e,) = self.elargissements()
        self.assertEqual((e["portee"], e["cible"], e["ancienne"], e["propose"], e["fonctionnalite"]),
                         ("projet", "badges", "Genre badges", "Genre badges, et aussi logos de chaîne", "f1"))
        self.assertIn("Genre badges, et aussi logos de chaîne", self.fonc()["discussion"][-1]["texte"])
        self.assertEqual(self.description_du_genre(), "Genre badges")      # pas appliquée avant la validation

    def test_elargissement_sans_phrase_du_jugement_est_deterministe(self):
        self.demander({"classer_genre": CLASSER_INCERTAIN}, texte="Un logo de chaîne")
        (q,) = self.decisions("genre_fonctionnalite")
        self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="meme")
        (e,) = self.elargissements()
        self.assertEqual(e["propose"], f"Genre badges, et aussi {self.fonc()['nom'][:1].lower()}{self.fonc()['nom'][1:]}")

    def test_valider_l_elargissement_modifie_le_genre(self):
        c = dict(CLASSER_INCERTAIN, elargissement="Genre badges, et aussi logos de chaîne")
        self.demander({"classer_genre": c})
        (q,) = self.decisions("genre_fonctionnalite")
        self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="meme")
        (e,) = self.elargissements()
        appels = []
        with mock.patch.object(outil, "GIT", lambda args, cwd: appels.append(args[0]) or (0, "")):
            d, _ = self.traiter(type="elargir_genre", decision=e["id"], verdict="valider",
                                description="Genre badges, et aussi logos")           # corrigée par l'utilisateur
        self.assertEqual(self.description_du_genre(), "Genre badges, et aussi logos")
        self.assertIn("commit", appels)
        self.assertEqual(self.elargissements(), [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_valider_sans_correction_applique_la_phrase_proposee(self):
        c = dict(CLASSER_INCERTAIN, elargissement="Genre badges, et aussi logos de chaîne")
        self.demander({"classer_genre": c})
        (q,) = self.decisions("genre_fonctionnalite")
        self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="meme")
        (e,) = self.elargissements()
        with mock.patch.object(outil, "GIT", lambda args, cwd: (0, "")):
            self.traiter(type="elargir_genre", decision=e["id"], verdict="valider")
        self.assertEqual(self.description_du_genre(), "Genre badges, et aussi logos de chaîne")

    def test_refuser_l_elargissement_garde_la_description_et_la_fonctionnalite(self):
        self.demander({"classer_genre": CLASSER_INCERTAIN})
        (q,) = self.decisions("genre_fonctionnalite")
        self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="meme")
        (e,) = self.elargissements()
        d, _ = self.traiter(type="elargir_genre", decision=e["id"], verdict="refuser")
        self.assertEqual(self.description_du_genre(), "Genre badges")
        self.assertEqual(self.elargissements(), [])
        self.assertEqual(self.fonc()["genre"], "badges")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_ici_avec_un_genre_connu_corrige_elargit_celui_ci(self):
        self.demander({"classer_genre": CLASSER_AUTRE}, texte="Un sticker animé")
        (q,) = self.decisions("genre_fonctionnalite")
        self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="ici", genre="stickers")
        (e,) = self.elargissements()
        self.assertEqual((e["cible"], e["ancienne"]), ("stickers", "Genre stickers"))

    def test_ici_avec_la_piste_ou_un_genre_nouveau_n_elargit_rien(self):
        self.demander({"classer_genre": CLASSER_AUTRE}, texte="Un casse-briques")
        (q,) = self.decisions("genre_fonctionnalite")
        self.traiter(type="genre_fonctionnalite", decision=q["id"], fonctionnalite="f1", choix="ici")
        self.assertEqual(self.elargissements(), [])

    def test_coherente_d_un_autre_genre_n_elargit_rien(self):
        self.demander({"classer_genre": dict(CLASSER_AUTRE, coherente=True), "proposer_organisation": PROPOSITION})
        self.assertEqual(self.elargissements(), [])

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
        # un projet créé depuis une demande déplacée : la demande porte son genre (choisi par le Directeur), aucune
        # proposition de genre du projet en plus
        self.traiter(type="fonctionnalite", texte="Un jeu", genre="jeu-mobile", description="Jeux pour téléphone")
        self.assertEqual(regles.genre_a_proposer(self.projet, self.etat), [])
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
