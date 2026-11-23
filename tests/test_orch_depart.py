import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from orchestrateur import depart, factory, fiches, memoire, outil
from tests.orch_aide import AvecProjet


def fiche(cle, role, modele="Sonnet", lieu="local", session=None, prenom=None):
    return {"cle": cle, "prenom": prenom or cle.title(), "role": role, "service": "dev", "modele": modele,
            "lieu": lieu, "session": session, "specialite": None, "texte": f"Texte de {cle}.", "lecons": []}


class TestDepart(unittest.TestCase):
    def test_monter(self):
        self.assertEqual(depart.monter("Haiku"), "Sonnet")
        self.assertEqual(depart.monter("Sonnet"), "Opus")
        self.assertEqual(depart.monter("Opus"), "Opus")   # on ne monte pas plus haut
        self.assertEqual(depart.monter("Inconnu"), "Inconnu")
        self.assertEqual(depart.monter("Fable"), "Fable")   # jamais choisi, jamais atteint par une montée

    def test_jamais_fable(self):
        for modele in ("Haiku", "Sonnet", "Opus", "Fable", "autre", ""):
            self.assertNotEqual(depart.monter(modele), "Fable" if modele != "Fable" else "")
        self.assertNotIn("Fable", depart.ECHELLE)
        # un outil ne choisit jamais Fable, même si une fiche le demandait : la fiche est refusée à la lecture
        with self.assertRaises(fiches.FicheInvalide):
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as t:
                p = Path(t) / "x.md"
                p.write_text("Clé : x\nRôle : dev\nModèle : Fable\nLieu : local\n", encoding="utf-8")
                fiches.lire_fiche(p)

    def test_agent_libre_occupe(self):
        liste = [fiche("dev-1", "dev"), fiche("dev-2", "dev"), fiche("qa-1", "qa")]
        taches = [{"agent": "dev-1", "active": True}, {"agent": "dev-2", "active": False}]
        self.assertEqual(depart.agent_libre(liste, taches, "dev")[0], "dev-2")   # dev-1 est pris
        cle, raison = depart.agent_libre(liste, taches + [{"agent": "dev-2", "active": True}], "dev")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun dev libre")
        self.assertEqual(depart.agent_libre(liste, [], "design")[1], "aucun design libre")
        self.assertEqual(depart.agent_libre(liste, taches, "qa")[0], "qa-1")

    def test_agent_libre_modele_et_lieu(self):
        liste = [fiche("dev-1", "dev", "Sonnet"), fiche("dev-2", "dev", "Opus")]
        self.assertEqual(depart.agent_libre(liste, [], "dev", modele="Opus")[0], "dev-2")
        # le modèle de la fiche est un plafond : une tâche Haiku va au plus petit plafond suffisant (Sonnet)
        self.assertEqual(depart.agent_libre(liste, [], "dev", modele="Haiku")[0], "dev-1")
        self.assertEqual(depart.agent_libre(liste[::-1], [], "dev", modele="Haiku")[0], "dev-1")
        self.assertEqual(depart.agent_libre(liste, [{"agent": "dev-1", "active": True}], "dev", modele="Haiku")[0],
                         "dev-2")
        self.assertEqual(depart.agent_libre(liste[:1], [], "dev", modele="Opus"), (None, "aucun dev libre sur Opus"))

    def test_limite_agents_locaux(self):
        liste = [fiche("dev-1", "dev"), fiche("dev-2", "dev")]
        taches = [{"agent": "dev-1", "active": True}]
        self.assertEqual(depart.agent_libre(liste, taches, "dev", agents_locaux_max=1),
                         (None, "limite de 1 agents locaux atteinte"))
        self.assertEqual(depart.agent_libre(liste, taches, "dev", agents_locaux_max=2)[0], "dev-2")
        self.assertEqual(depart.agent_libre(liste, taches, "dev")[0], "dev-2")   # sans limite donnée, comme avant

    def test_limite_ne_compte_pas_le_cloud(self):
        liste = [fiche("dev-1", "dev"), fiche("cl-1", "dev", "Sonnet", "cloud", "Session cl")]
        taches = [{"agent": "cl-1", "active": True}]
        self.assertEqual(depart.agent_libre(liste, taches, "dev", lieu="local", agents_locaux_max=1)[0], "dev-1")
        # la limite ne bloque pas non plus un agent cloud libre
        taches = [{"agent": "dev-1", "active": True}]
        self.assertEqual(depart.agent_libre(liste, taches, "dev", lieu="cloud", agents_locaux_max=1)[0], "cl-1")

    def test_agent_libre_cloud_manquant(self):
        liste = [fiche("prep-1", "preparateur", "Sonnet", "cloud", "Session prep"), fiche("prep-2", "preparateur", "Opus", "cloud")]
        self.assertEqual(depart.agent_libre(liste, [], "preparateur", "Sonnet", "cloud")[0], "prep-1")
        # Une tâche Haiku : le plafond Sonnet de prep-1 suffit.
        self.assertEqual(depart.agent_libre(liste, [], "preparateur", "Haiku", "cloud")[0], "prep-1")
        # Aucune fiche de ce rôle au plafond suffisant : il faut d'abord en écrire une (pas de session à demander).
        cle, raison = depart.agent_libre(liste[:1], [], "preparateur", "Opus", "cloud")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucune fiche cloud preparateur sur Opus : ajoutez-en une")
        self.assertIsNone(depart.sans_session(liste[:1], "preparateur", "Opus"))
        # La fiche existe, sans session : c'est elle qui attend sa session (la décision la nomme).
        cle, raison = depart.agent_libre(liste, [], "preparateur", "Opus", "cloud")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun agent cloud preparateur sur Opus : session à créer pour prep-2")
        self.assertEqual(depart.sans_session(liste, "preparateur", "Opus"), "prep-2")
        # Occupé n'est pas « sans session » : on attend, on ne redemande pas une session qui existe.
        seul = liste[:1]
        cle, raison = depart.agent_libre(seul, [{"agent": "prep-1", "active": True}], "preparateur", "Sonnet", "cloud")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun agent cloud preparateur libre sur Sonnet")
        self.assertIsNone(depart.sans_session(seul, "preparateur", "Sonnet"))
        # prep-1 occupé, prep-2 (plafond Opus) pourrait prendre la tâche Sonnet : c'est sa session qui manque.
        self.assertEqual(depart.sans_session(liste, "preparateur", "Sonnet"), "prep-2")

    def test_agent_libre_local_ignore_le_cloud(self):
        liste = [fiche("prep-1", "preparateur", "Sonnet", "cloud", "S")]
        self.assertIsNone(depart.agent_libre(liste, [], "preparateur", lieu="local")[0])

    def message(self, lieu="local", lecons=None, brief="Brief du rôle dev.", tache=None):
        f = {"nom": "Projet démo", "genre": "vitrine"}
        t = tache or {"id": "t4", "titre": "Développer l'écran", "fonctionnalite": "f1", "element": "e2", "etape": "Mise en page"}
        return depart.message(f, fiche("dev-1", "dev", lieu=lieu), t, brief,
                              lecons or {"skill": [{"id": "S1", "titre": "Relire", "texte": "Relire avant de rendre."}],
                                         "genre": [{"id": "G1", "titre": "Textes", "texte": "Textes courts."}]})

    def test_message_contient_tout(self):
        m = self.message()
        for attendu in ("Projet démo", "vitrine", "Texte de dev-1.", "Relire avant de rendre.", "Textes courts.",
                        "Brief du rôle dev.", "Développer l'écran", "t4", "e2", "Mise en page", "leçons", "étage"):
            self.assertIn(attendu, m)
        self.assertNotIn("Tu repars de zéro.", m)
        self.assertLess(m.index("Texte de dev-1."), m.index("Brief du rôle dev."))   # fiche, puis brief, puis tâche
        self.assertLess(m.index("Brief du rôle dev."), m.index("Développer l'écran"))

    def test_message_sobre(self):
        # Les leçons « à valider » ne sont pas encore la règle : elles restent hors du message de départ ; et le message
        # demande de ne lire que ce que la tâche demande (le coût d'un agent vient surtout de ce qu'il relit).
        f = fiche("dev-1", "dev")
        f["lecons"] = [{"etat": "validée", "id": "dev-1:L1", "texte": "Règle sûre."},
                       {"etat": "à valider", "id": "dev-1:L2", "texte": "Idée pas encore validée."}]
        m = depart.message({"nom": "P", "genre": None}, f, {"id": "t1", "titre": "T"}, None, {"skill": [], "genre": []})
        self.assertIn("Règle sûre.", m)
        self.assertNotIn("Idée pas encore validée.", m)
        self.assertIn("Sobriété", m)
        # Une fiche écrite sur disque : ses lignes « à valider » sont retirées aussi.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "dev.md"
            chemin.write_text("\n".join(["Clé : dev-1", "Rôle : dev", "Modèle : Sonnet", "Lieu : local", "", "Texte.", "",
                                         "## Leçons", "- [validée] dev-1:L1 : Règle sûre.",
                                         "- [à valider] dev-1:L2 : Idée pas encore validée.", ""]), encoding="utf-8")
            m = depart.message({"nom": "P", "genre": None}, {**f, "chemin": str(chemin)}, {"id": "t1", "titre": "T"},
                               None, {"skill": [], "genre": []})
        self.assertIn("Règle sûre.", m)
        self.assertNotIn("Idée pas encore validée.", m)

    def test_message_sans_genre_ni_brief(self):
        m = depart.message({"nom": "P", "genre": None}, fiche("dev-1", "dev"), {"id": "t1", "titre": "T"}, None,
                           {"skill": [], "genre": []})
        self.assertIn("Texte de dev-1.", m)
        self.assertIn("T", m)

    def test_un_agent_local_passe_ses_tests_par_le_verrou_du_poste(self):
        """Une seule campagne de tests à la fois sur le poste, pour les agents des projets aussi (2026-11-17)."""
        m = self.message()
        self.assertIn("lancer.py\" tests --", m)
        self.assertIn("une seule campagne de tests à la fois", m.lower())
        self.assertIn("seulement les tests touchés", m)
        self.assertNotIn("lancer.py\" tests --", self.message("cloud"))      # un agent cloud a sa propre machine


    def test_message_cloud_repart_de_zero(self):
        self.assertTrue(self.message("cloud").startswith("Tu repars de zéro."))

    def test_verbes_du_pont_concordent_avec_serveur_tache(self):
        """R2 : la consigne nomme exactement la liste fermée du pont, avec le bon nombre d'arguments."""
        import sys
        outils = str(Path(__file__).resolve().parent.parent / "outils")
        if outils not in sys.path:
            sys.path.append(outils)
        import serveur_tache as st
        noms = [v.split()[0] for v in depart.VERBES_DU_PONT]
        self.assertEqual(len(noms), len(set(noms)))
        self.assertEqual(set(noms), set(st.VERBES))
        for v in depart.VERBES_DU_PONT:
            nom, *args = v.split()
            self.assertEqual(len(args), len(st.VERBES[nom]), v)
            facultatifs = [a for a in args if a.startswith("[")]
            self.assertEqual(len(facultatifs), st.FACULTATIFS.get(nom, 0), v)
            self.assertEqual(args[len(args) - len(facultatifs):], facultatifs, v)     # les facultatifs à la fin

    def test_consigne_serveur_seul_et_pilote(self):
        seul, pilote = depart.consigne_serveur("seul", "t7"), depart.consigne_serveur("pilote", "t7")
        for c in (seul, pilote):
            self.assertIn("`agent/t7`", c)
            self.assertIn("commite", c)
            self.assertIn("donnée", c)
            self.assertIn("message.questions", c)
            self.assertIn("attend: true", c)
            self.assertIn("GitHub", c)
            self.assertNotIn("lancer.py", c)                 # ni lanceur de tests du poste, ni deporter
        self.assertIn("`pont <verbe> [arguments]`", pilote)
        self.assertIn("/outil/", pilote)
        self.assertNotIn("pont", seul)
        with self.assertRaises(ValueError):
            depart.consigne_serveur("scenario", "t7")
        # les valeurs admises de `touche` sont dites (celles du pont, `serveur_tache.MOTIF_TOUCHE`)
        import re
        import sys
        outils = str(Path(__file__).resolve().parent.parent / "outils")
        if outils not in sys.path:
            sys.path.append(outils)
        import serveur_tache
        touches = re.fullmatch(r"\((.*)\)", serveur_tache.MOTIF_TOUCHE).group(1).split("|")
        self.assertIn("`touche` : " + ", ".join(f"`{t}`" for t in touches), pilote)
        # le message d'un agent serveur : ni la section du lanceur de tests du poste, ni les actions déportées
        f = {"nom": "P", "genre": None}
        t = {"id": "t7", "titre": "T"}
        m = depart.message(f, fiche("dev-1", "dev", lieu="serveur"), t, None, {"skill": [], "genre": []},
                           deport="## Actions déportées sur GitHub\nx")
        self.assertNotIn("lancer.py\" tests --", m)
        self.assertNotIn("Actions déportées", m)
        self.assertNotIn("Tu repars de zéro.", m)
        lot = depart.message_lot(f, fiche("dev-1", "dev", lieu="serveur"), [t], [("dev", None)],
                                 {"skill": [], "genre": []}, deport="## Actions déportées sur GitHub\nx")
        self.assertNotIn("lancer.py\" tests --", lot)
        self.assertNotIn("Actions déportées", lot)
        # local : inchangé (la section des tests et le déport restent)
        m = depart.message(f, fiche("dev-1", "dev"), t, None, {"skill": [], "genre": []},
                           deport="## Actions déportées sur GitHub\nx")
        self.assertIn("lancer.py\" tests --", m)
        self.assertIn("Actions déportées", m)


PLACES = {"local": 2, "serveur": 2, "cloud": 3}
ORDRE = ["local", "serveur", "cloud"]


class TestBasculeLieux(unittest.TestCase):
    """Le lieu où part une tâche libre : le premier de l'ordre qui a une place, jamais ailleurs en silence."""

    def pour(self, ordre=None, places=None, occupes=None, hors=frozenset(), actifs=0, plafond=None):
        return depart.lieu_pour(ordre or ORDRE, places or PLACES, occupes or {}, hors, actifs, plafond)

    def test_premier_lieu_libre_dans_l_ordre(self):
        self.assertEqual(self.pour()[0], "local")
        self.assertEqual(self.pour(occupes={"local": 2})[0], "serveur")
        self.assertEqual(self.pour(occupes={"local": 2, "serveur": 2})[0], "cloud")
        self.assertEqual(self.pour(occupes={"local": 1})[0], "local")      # une place reste
        self.assertEqual(self.pour(ordre=["cloud", "local"])[0], "cloud")
        self.assertEqual(self.pour(ordre=["serveur"], occupes={"local": 2})[0], "serveur")

    def test_lieu_hors_ligne_saute(self):
        self.assertEqual(self.pour(occupes={"local": 2}, hors=frozenset({"serveur"}))[0], "cloud")
        self.assertEqual(self.pour(ordre=["serveur", "local"], hors=frozenset({"serveur"}))[0], "local")

    def test_tout_plein_raison_nomme_chaque_lieu(self):
        self.assertEqual(self.pour(places={"local": 2, "serveur": 2, "cloud": 0}, occupes={"local": 2},
                                   hors=frozenset({"serveur"})),
                         (None, "local : 2/2 occupés ; serveur : hors ligne ; cloud : 0 place"))
        cle, raison = self.pour(occupes={"local": 2, "serveur": 1, "cloud": 3}, places={"local": 2, "serveur": 1, "cloud": 3})
        self.assertIsNone(cle)
        self.assertEqual(raison, "local : 2/2 occupés ; serveur : 1/1 occupés ; cloud : 3/3 occupés")
        # un lieu absent des places n'a aucune place ; l'ordre des lieux est celui de l'ordre donné
        self.assertEqual(self.pour(ordre=["cloud", "serveur"], places={"local": 2}),
                         (None, "cloud : 0 place ; serveur : 0 place"))

    def test_plafond_d_abonnement_au_dessus_des_places(self):
        self.assertEqual(self.pour(actifs=4, plafond=4), (None, "plafond d'abonnement atteint (4/4)"))
        self.assertEqual(self.pour(actifs=5, plafond=4), (None, "plafond d'abonnement atteint (5/4)"))
        self.assertEqual(self.pour(actifs=3, plafond=4)[0], "local")
        self.assertEqual(self.pour(actifs=99, plafond=None)[0], "local")      # sans plafond : rien ne limite

    def test_ordre_par_metier_l_emporte(self):
        f = {"ordre_lieux": ORDRE, "ordre_lieux_par_metier": {"qa": ["cloud", "local"]}}
        self.assertEqual(depart.ordre_du_metier(f, "qa"), ["cloud", "local"])
        self.assertEqual(depart.ordre_du_metier(f, "dev"), ORDRE)
        self.assertEqual(depart.ordre_du_metier({}, "dev"), ORDRE)           # défaut : local, serveur, cloud

    def test_lieu_impose_par_l_etape_l_emporte_sur_l_ordre(self):
        liste = [fiche("dev-1", "dev"), fiche("srv-1", "dev", lieu="serveur"),
                 fiche("cl-1", "dev", lieu="cloud", session="S")]
        occupe = [{"agent": "dev-1", "active": True}]
        # l'étape exige le poste : local plein, la tâche attend ; elle ne part ni sur le serveur ni dans le cloud
        cle, raison = depart.agent_libre(liste, occupe, "dev", lieu_etape="local", ordre_lieux=ORDRE, places=PLACES,
                                         agents_locaux_max=1)
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun agent local libre : la tâche attend le poste local")
        # le plafond d'abonnement lie aussi les tâches dont le lieu est imposé (étape, métier, lieu donné, sans ordre)
        plafond = (4, 4)
        for kw in ({"lieu_etape": "local"}, {"lieu_reserve": "cloud"}, {"lieu": "serveur"}, {"lieu": "local"},
                   {"lieu_etape": "cloud"}):
            self.assertEqual(depart.agent_libre(liste, [], "dev", ordre_lieux=ORDRE, places=PLACES, abonnement=plafond, **kw),
                             (None, "plafond d'abonnement atteint (4/4)"), kw)
            self.assertEqual(depart.agent_libre(liste, [], "dev", abonnement=plafond, **kw),
                             (None, "plafond d'abonnement atteint (4/4)"), kw)      # même sans ordre des lieux
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu_etape="local", abonnement=(3, 4))[0], "dev-1")
        # un lieu serveur demandé : hors ligne ou sans place, la tâche attend, elle ne part pas
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu="serveur", ordre_lieux=ORDRE, places=PLACES,
                                            hors_ligne=frozenset({"serveur"})), (None, "serveur : hors ligne"))
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu="serveur", ordre_lieux=ORDRE,
                                            places={"local": 2, "serveur": 0}), (None, "serveur : 0 place"))
        self.assertEqual(depart.agent_libre(liste, [{"agent": "srv-1", "active": True}], "dev", lieu="serveur",
                                            ordre_lieux=ORDRE, places={"serveur": 1}), (None, "serveur : 1/1 occupés"))
        # un métier réservé au serveur passe par la même garde qu'un lieu serveur donné (place et serveur en ligne)
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu_reserve="serveur", ordre_lieux=ORDRE, places=PLACES,
                                            hors_ligne=frozenset({"serveur"})), (None, "serveur : hors ligne"))
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu_reserve="serveur", ordre_lieux=ORDRE,
                                            places=PLACES)[0], "srv-1")
        # un réglage de plafond illisible : la tâche attend avec sa raison, quel que soit le lieu
        refus = "plafond d'abonnement : réglage illisible"
        for kw in ({}, {"lieu_etape": "local"}, {"lieu": "serveur"}):
            self.assertEqual(depart.agent_libre(liste, [], "dev", abonnement_refus=refus, **kw), (None, refus), kw)
        # le métier réservé au cloud : l'ordre n'y change rien
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu_reserve="cloud", ordre_lieux=ORDRE, places=PLACES)[0], "cl-1")
        # un lieu donné explicitement l'emporte aussi
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu="serveur", ordre_lieux=ORDRE, places=PLACES)[0], "srv-1")
        # `indifférent` n'impose rien : l'ordre décide
        self.assertEqual(depart.agent_libre(liste, [], "dev", lieu_etape="indifférent", ordre_lieux=["serveur", "local"],
                                            places=PLACES)[0], "srv-1")

    def test_agent_libre_suit_l_ordre_et_passe_au_suivant(self):
        liste = [fiche("dev-1", "dev"), fiche("srv-1", "dev", lieu="serveur"),
                 fiche("cl-1", "dev", lieu="cloud", session="S")]
        places = {"local": 1, "serveur": 1, "cloud": 1}
        suivre = lambda taches, **k: depart.agent_libre(liste, taches, "dev", ordre_lieux=ORDRE, places=places,
                                                        agents_locaux_max=1, **k)
        self.assertEqual(suivre([])[0], "dev-1")
        self.assertEqual(suivre([{"agent": "dev-1", "active": True}])[0], "srv-1")
        self.assertEqual(suivre([{"agent": "dev-1", "active": True}, {"agent": "srv-1", "active": True}])[0], "cl-1")
        self.assertEqual(suivre([], hors_ligne=frozenset({"local"}))[0], "srv-1")
        # un lieu qui a une place mais aucune fiche libre passe au suivant
        sans_serveur = [f for f in liste if f["lieu"] != "serveur"]
        self.assertEqual(depart.agent_libre(sans_serveur, [{"agent": "dev-1", "active": True}], "dev", ordre_lieux=ORDRE,
                                            places=places, agents_locaux_max=1)[0], "cl-1")

    def test_agent_libre_cloud_sans_session_le_dit(self):
        liste = [fiche("dev-1", "dev"), fiche("cl-1", "dev", lieu="cloud")]            # la fiche cloud n'a pas de session
        cle, raison = depart.agent_libre(liste, [{"agent": "dev-1", "active": True}], "dev", ordre_lieux=ORDRE,
                                         places={"local": 1, "serveur": 0, "cloud": 2}, agents_locaux_max=1)
        self.assertIsNone(cle)
        self.assertEqual(raison, "local : 1/1 occupés ; serveur : 0 place ; cloud : session à créer pour cl-1")

    def test_agent_libre_tout_plein_nomme_chaque_lieu(self):
        liste = [fiche("dev-1", "dev"), fiche("srv-1", "dev", lieu="serveur")]
        cle, raison = depart.agent_libre(liste, [{"agent": "dev-1", "active": True}], "dev", ordre_lieux=ORDRE,
                                         places={"local": 1, "serveur": 1, "cloud": 0}, agents_locaux_max=1,
                                         hors_ligne=frozenset({"serveur"}))
        self.assertIsNone(cle)
        self.assertEqual(raison, "local : 1/1 occupés ; serveur : hors ligne ; cloud : 0 place")
        # des places, mais aucune fiche libre : la raison le dit pour ce lieu, sans en oublier un
        cle, raison = depart.agent_libre([fiche("dev-1", "dev")], [{"agent": "dev-1", "active": True}], "dev",
                                         ordre_lieux=ORDRE, places={"local": 2, "serveur": 2, "cloud": 2})
        self.assertIsNone(cle)
        for lieu in ORDRE:
            self.assertIn(lieu, raison)
        # le plafond d'abonnement l'emporte sur des places libres et une fiche libre
        self.assertEqual(depart.agent_libre([fiche("dev-1", "dev")], [{"agent": "x", "active": True}], "dev", ordre_lieux=ORDRE,
                                            places=PLACES, abonnement=(1, 1)),
                         (None, "plafond d'abonnement atteint (1/1)"))

    def test_sans_ordre_comportement_inchange(self):
        liste = [fiche("dev-1", "dev"), fiche("srv-1", "dev", lieu="serveur")]
        taches = [{"agent": "dev-1", "active": True}]
        # même résultat que sans les nouveaux paramètres (la suite actuelle l'éprouve par ailleurs)
        for kw in ({}, {"agents_locaux_max": 1}, {"lieu": "local"}, {"modele": "Opus"}):
            self.assertEqual(depart.agent_libre(liste, taches, "dev", ordre_lieux=None, places=PLACES,
                                                hors_ligne=frozenset({"local"}), **kw),
                             depart.agent_libre(liste, taches, "dev", **kw))


class TestDepartCommandes(AvecProjet):
    def preparer(self):
        (self.dossier / "fiches" / "briefs").mkdir()
        (self.dossier / "fiches" / "briefs" / "dev.md").write_text("Brief propre aux développeurs.", encoding="utf-8")
        mem = self.dossier / "memoire"
        (mem / "genres").mkdir(parents=True)
        (mem / "skill.md").write_text("# Mémoire\n\n## S1 — Pour les dev\nRôles : dev\nDate : 2026-11-01\n\nLeçon des dev.\n\n"
                                      "## S2 — Pour les qa\nRôles : qa\nDate : 2026-11-01\n\nLeçon des qa.\n", encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["genre"] = "vitrine"
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        (mem / "genres" / "vitrine.md").write_text("# Genre : vitrine\nDomaine : d\nLivrable : l\nOutils : o\n\n"
                                                    "## G1 — Général\nRôles : tous\nDate : 2026-11-02\n\nLeçon de genre.\n", encoding="utf-8")

    def test_commande_agent_libre(self):
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"}), {"agent": None, "raison": "aucun dev libre"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "cadrage"})["agent"], "metier-1")
        self.assertEqual(self.outil("agent-libre", entree={"modele": "Opus"})[0], 1)   # le rôle est obligatoire

    # --- la bascule entre lieux : le serveur sondé, l'abonnement du bureau, l'ordre du projet

    def serveur(self, caps, maj=None):
        """Un serveur déclaré dans un dossier de plateforme de test, avec ces capacités à la dernière sonde."""
        plateforme = self.dossier / "plateforme"
        plateforme.mkdir(exist_ok=True)
        (plateforme / "serveurs.json").write_text(json.dumps([{
            "id": "ovh1", "nom": "ovh1", "hote": "ovh1.exemple.net", "utilisateur": "ubuntu", "cle": "C:/cles/id"}]),
            encoding="utf-8")
        (plateforme / "serveurs-etat.json").write_text(json.dumps({"ovh1": {
            "capacites": {k: {"statut": v, **({"maj": maj} if maj else {})} for k, v in caps.items()},
            "installation": {"en_cours": False}}}),
            encoding="utf-8")
        patch = mock.patch.object(outil, "DOSSIER_PLATEFORME", plateforme)
        patch.start()
        self.addCleanup(patch.stop)
        return plateforme

    def test_serveur_hors_ligne_si_sonde_ancienne_ou_sans_abonnement(self):
        self.assertTrue(outil.serveur_hors_ligne(self.dossier / "vide"))          # aucun serveur déclaré
        self.serveur({"agent": "presente", "agent-abonnement": "presente"})
        self.assertFalse(outil.serveur_hors_ligne())
        self.serveur({"agent": "presente", "agent-abonnement": "absente"})        # sans connexion à l'abonnement
        self.assertTrue(outil.serveur_hors_ligne())
        self.serveur({"agent": "presente"})                                        # capacité jamais constatée
        self.assertTrue(outil.serveur_hors_ligne())
        self.serveur({"agent": "inconnue", "agent-abonnement": "inconnue"})       # sonde ancienne ou injoignable
        self.assertTrue(outil.serveur_hors_ligne())
        self.serveur({})                                                           # jamais sondé
        self.assertTrue(outil.serveur_hors_ligne())
        prets = {"agent": "presente", "agent-abonnement": "presente"}
        maintenant = datetime.now(timezone.utc)
        self.serveur(prets, maj=(maintenant - timedelta(hours=2)).isoformat(timespec="seconds"))
        self.assertFalse(outil.serveur_hors_ligne())                               # sondé il y a 2 h
        self.serveur(prets, maj=(maintenant - timedelta(hours=25)).isoformat(timespec="seconds"))
        self.assertTrue(outil.serveur_hors_ligne())                                # sonde de plus de 24 h : hors ligne
        self.serveur(prets, maj="pas une date")                                    # date illisible : on ne peut le dire prêt
        self.assertTrue(outil.serveur_hors_ligne())

    def regler(self, **cles):
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d.update(cles)
        self.factory.write_text(json.dumps(d), encoding="utf-8")

    def fiche_serveur(self):
        (self.dossier / "fiches" / "srv.md").write_text(
            "Clé : srv-1\nRôle : dev\nService : dev\nModèle : Sonnet\nLieu : serveur\n\n## Leçons\n", encoding="utf-8")

    def test_commande_ordre_serveur_puis_local(self):
        self.fiche_serveur()
        self.regler(agents_serveur_max=1, ordre_lieux=["serveur", "local", "cloud"])
        self.serveur({"agent": "presente", "agent-abonnement": "presente"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "srv-1")
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "srv-1"})   # la place serveur est prise
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")

    def test_commande_serveur_hors_ligne_saute_et_raison_nomme_chaque_lieu(self):
        self.fiche_serveur()
        self.regler(agents_serveur_max=1, ordre_lieux=["serveur", "local", "cloud"])
        self.serveur({"agent": "presente", "agent-abonnement": "absente"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        r = self.ok("agent-libre", entree={"role": "dev"})
        self.assertIsNone(r["agent"])
        self.assertIn("serveur : hors ligne", r["raison"])
        self.assertEqual(r["raison"], "serveur : hors ligne ; local : aucune fiche libre ; cloud : 0 place")

    def flutter(self):
        """Ce projet devient un projet Flutter (pubspec.yaml d'un sous-dossier qui dépend de flutter)."""
        chemin = self.factory.resolve()
        projet = chemin.parent.parent if chemin.parent.name == ".factory" else chemin.parent
        (projet / "android_app").mkdir(exist_ok=True)
        (projet / "android_app" / "pubspec.yaml").write_text("name: x\ndependencies:\n  flutter:\n    sdk: flutter\n",
                                                            encoding="utf-8")

    def test_projet_flutter_sans_flutter_sdk_retombe_au_poste_avec_la_raison(self):
        self.fiche_serveur()
        self.regler(agents_serveur_max=1, ordre_lieux=["serveur", "local", "cloud"])
        self.serveur({"agent": "presente", "agent-abonnement": "presente"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "srv-1")     # non Flutter : inchangé
        self.flutter()
        self.assertTrue(outil.serveur_hors_ligne(besoin="agent-flutter"))
        self.assertFalse(outil.serveur_hors_ligne())
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")     # le lieu suivant
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        r = self.ok("agent-libre", entree={"role": "dev"})
        self.assertIsNone(r["agent"])
        self.assertIn("serveur : flutter-sdk absent du serveur", r["raison"])
        self.serveur({"agent": "presente", "agent-abonnement": "presente", "flutter-sdk": "presente"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "srv-1")

    def test_commande_ordre_par_metier_l_emporte(self):
        self.fiche_serveur()
        self.regler(agents_serveur_max=1, ordre_lieux=["serveur", "local", "cloud"],
                    ordre_lieux_par_metier={"dev": ["local", "serveur"]})
        self.serveur({"agent": "presente", "agent-abonnement": "presente"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")

    def bureau_avec_autre(self, plafond=2, suivi=None, factory_autre=True, brut=None):
        """Un bureau à deux projets (celui-ci et `autre`, qui tient 1 tâche d'agent active) et ce plafond d'abonnement."""
        bureau = self.dossier / "bureau.json"
        autre = self.dossier / "autre"
        (autre / ".factory").mkdir(parents=True, exist_ok=True)
        (autre / ".factory" / "reglages.json").write_text("{}", encoding="utf-8")
        if factory_autre:
            (autre / ".factory" / "factory.json").write_text(json.dumps({"skill": "s", "suivi": "suivi.json"}), encoding="utf-8")
        else:
            (autre / ".factory" / "factory.json").unlink(missing_ok=True)
        (autre / ".factory" / "suivi.json").write_text(suivi if suivi is not None else json.dumps({"taches": [
            {"id": "t1", "agent": "x-1", "active": True}, {"id": "t2", "agent": "x-2", "active": False},
            {"id": "t3", "agent": None, "active": True}]}), encoding="utf-8")
        (self.dossier / "reglages.json").write_text("{}", encoding="utf-8")
        contenu = {"projets": ["reglages.json", "autre/.factory/reglages.json"]}
        if plafond is not None:
            contenu["agents_abonnement_max"] = plafond
        bureau.write_text(brut if brut is not None else json.dumps(contenu), encoding="utf-8")
        if not getattr(self, "_bureau_patch", False):
            self._bureau_patch = True
            patch = mock.patch.object(outil, "BUREAU_DEPORT", str(bureau))
            patch.start()
            self.addCleanup(patch.stop)
        return bureau

    def test_commande_plafond_d_abonnement_du_bureau(self):
        self.regler(agents_serveur_max=1)
        self.bureau_avec_autre(2)
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        r = self.ok("agent-libre", entree={"role": "dev"})                       # 2 actives (ici et ailleurs) : plafond
        self.assertEqual((r["agent"], r["raison"]), (None, "plafond d'abonnement atteint (2/2)"))
        # le plafond lie aussi un lieu imposé : un lieu donné
        r = self.ok("agent-libre", entree={"role": "dev", "lieu": "local"})
        self.assertEqual((r["agent"], r["raison"]), (None, "plafond d'abonnement atteint (2/2)"))

    def test_commande_plafond_invalide_ou_bureau_illisible_garde_la_porte_fermee(self):
        refus = f"plafond d'abonnement : réglage illisible ({self.dossier / 'bureau.json'})"     # le fichier nommé
        for mauvais in (0, 33, "4", True, None, 2.5):
            bureau = self.bureau_avec_autre(1)
            contenu = json.loads(bureau.read_text(encoding="utf-8"))
            contenu["agents_abonnement_max"] = mauvais
            bureau.write_text(json.dumps(contenu), encoding="utf-8")
            r = self.ok("agent-libre", entree={"role": "dev"})
            self.assertEqual((r["agent"], r["raison"]), (None, refus), repr(mauvais))
        self.bureau_avec_autre(brut="{pas du json")                               # bureau illisible
        r = self.ok("agent-libre", entree={"role": "dev"})
        self.assertEqual((r["agent"], r["raison"]), (None, refus))
        self.bureau_avec_autre(brut="[1, 2]")
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["raison"], refus)
        with mock.patch.object(Path, "exists", side_effect=PermissionError("refusé")):     # existence illisible
            self.assertEqual(outil.plafond_abonnement(self.dossier / "bureau.json"), (None, refus))
        # sans plafond réglé, ou sans fichier du bureau : rien ne limite
        self.bureau_avec_autre(None)
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")
        (self.dossier / "bureau.json").unlink()
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"})["agent"], "dev-1")

    def test_commande_suivi_d_un_autre_projet_illisible_garde_la_porte_fermee(self):
        self.bureau_avec_autre(5, suivi="{abime")
        r = self.ok("agent-libre", entree={"role": "dev"})
        self.assertIsNone(r["agent"])
        self.assertIn("plafond d'abonnement", r["raison"])
        self.assertIn("autre", r["raison"])                                       # le projet illisible est nommé
        self.bureau_avec_autre(5, factory_autre=False)
        r = self.ok("agent-libre", entree={"role": "dev"})
        self.assertIsNone(r["agent"])
        self.assertIn("autre", r["raison"])

    def test_commande_cloud_sans_session_en_bascule(self):
        (self.dossier / "fiches" / "cl.md").write_text(
            "Clé : cl-1\nRôle : dev\nService : dev\nModèle : Sonnet\nLieu : cloud\n\n## Leçons\n", encoding="utf-8")
        self.regler(agents_serveur_max=1, agents_cloud_max=2, agents_locaux_max=1)
        self.serveur({"agent": "presente", "agent-abonnement": "absente"})
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        r = self.ok("agent-libre", entree={"role": "dev"})
        self.assertIsNone(r["agent"])
        self.assertEqual(r["raison"], "local : 1/1 occupés ; serveur : hors ligne ; cloud : session à créer pour cl-1")
        self.assertEqual(r["sans_session"], "cl-1")

    def test_agent_libre_voit_la_session_de_la_table(self):
        (self.dossier / "fiches" / "prep.md").write_text(
            "Clé : prep-1\nRôle : preparateur\nService : dev\nModèle : Sonnet\nLieu : cloud\n\n## Leçons\n", encoding="utf-8")
        entree = {"role": "preparateur", "modele": "Sonnet", "lieu": "cloud"}
        self.assertIsNone(self.ok("agent-libre", entree=entree)["agent"])
        self.ok("session", entree={"agent": "prep-1", "session": "Session prép"})
        self.assertEqual(self.ok("agent-libre", entree=entree)["agent"], "prep-1")

    def test_commande_depart(self):
        self.preparer()
        t = self.ok("tache", entree={"titre": "Développer l'écran", "role": "dev", "colonne": "dev"})
        m = self.ok("depart", entree={"agent": "dev-1", "tache": t["id"]})["message"]
        for attendu in ("Développer l'écran", "Brief propre aux développeurs.", "Leçon des dev.", "Leçon de genre.",
                        "Développe les écrans.", "Nommer les écrans"):
            self.assertIn(attendu, m)
        self.assertNotIn("Leçon des qa.", m)   # pas les leçons d'un autre rôle
        self.assertEqual(self.outil("depart", entree={"agent": "inconnu", "tache": t["id"]})[0], 1)
        self.assertEqual(self.outil("depart", entree={"agent": "dev-1", "tache": "t99"})[0], 1)

    def test_message_cloud_par_la_commande(self):
        (self.dossier / "fiches" / "prep.md").write_text(
            "Clé : prep-1\nRôle : preparateur\nService : dev\nModèle : Sonnet\nLieu : cloud\nSession : S\n\n## Leçons\n",
            encoding="utf-8")
        t = self.ok("tache", entree={"titre": "Préparer"})
        m = self.ok("depart", entree={"agent": "prep-1", "tache": t["id"]})["message"]
        self.assertTrue(m.startswith("Tu repars de zéro."))

    def test_message_montre_le_modele_de_la_tache_montee(self):
        t = self.ok("tache", entree={"titre": "Écran", "montee": {"de": "Haiku", "a": "Sonnet", "raison": "complexe"}})
        m = self.ok("depart", entree={"agent": "dev-1", "tache": t["id"]})["message"]
        self.assertIn("Sonnet", m)
        self.assertIn("Haiku", m)
