"""La boucle du moteur : un passage, plusieurs projets, la reprise. Aucun appel réel à `claude`, aucun push."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from moteur import agents, appel, boucle, detache, jugement, regles
from tests.orch_aide import AvecProjet, factory_minimale

FICHE_REMI = ("Clé : rel-1\nPrénom : Rémi\nRôle : relecteur\nService : dev\nModèle : Sonnet\nLieu : local\n\n"
              "Relit.\n\n## Leçons\n")
CONSEIL_RIEN = {"action": "rien", "parametres": {}, "reponse": "Rien à faire."}
USAGE = {"modele": "claude-haiku-5-5", "entree": 100, "sortie": 20, "cache_lecture": 5, "cache_ecriture": 7}
RAPPORT_FAIT = '```json\n{"statut": "fait", "message": {"texte": "Voilà.", "attend": true}}\n```'


class Appels:
    """Un faux `appeler` de jugement : rend la réponse JSON donnée."""

    def __init__(self, objet=CONSEIL_RIEN):
        self.objet, self.recus = objet, []

    def __call__(self, consigne, dossier, modele, **options):
        self.recus.append((modele, dossier))
        return appel.Reponse(json.dumps(self.objet), [dict(USAGE)])


class Agents:
    """Un faux `executer_agent` : garde ce qu'il a lancé et rend un rapport."""

    def __init__(self, rapport=RAPPORT_FAIT):
        self.rapport, self.lances = rapport, []

    def __call__(self, depart, matiere, *, agent, modele, dossier_projet, tache=None, lot=None, **plus):
        self.lances.append({"agent": agent["cle"], "tache": tache, "modele": modele, "depart": depart,
                            "matiere": matiere, "dossier": dossier_projet, "fiche": agent, **plus})
        from moteur import rapport
        return agents.Execution(tache, agent["cle"], lot, rapport=rapport.lire(self.rapport) if self.rapport else None,
                                usages=[dict(USAGE, modele="claude-opus-5-5")], erreur=None if self.rapport else "x",
                                session="s-1" if self.rapport else None)


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        (self.dossier / "fiches" / "remi.md").write_text(FICHE_REMI, encoding="utf-8")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True)
        self.appels, self.agents, self.commits = Appels(), Agents(), []
        self.moteur = self.fabriquer([self.projet])

    def fabriquer(self, projets, **kw):
        return boucle.Moteur(projets, appeler=self.appels, executer_agent=self.agents, synchrone=True,
                             commit=lambda d, m: self.commits.append((str(d), m)), **kw)

    def suivi(self, dossier=None):
        return json.loads(((dossier or self.dossier) / "suivi.json").read_text(encoding="utf-8"))

    def demande(self, factory=None, **champs):
        code, objet = self.outil("actions", entree=champs, factory=factory)
        self.assertEqual(code, 0, objet)
        return objet["id"]

    def statut(self, i, dossier=None):
        return next(d for d in self.suivi(dossier)["demandes"] if d["id"] == i)


class Passage(Base):
    def test_tour_ecrit_la_presence(self):
        self.moteur.tour()
        p = json.loads((self.dossier / "presence.json").read_text(encoding="utf-8"))
        self.assertIn("pid", p)
        self.assertEqual(self.moteur.journal, [])

    def test_premier_passage_propose_le_genre_d_un_projet_cree_au_bureau(self):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        self.factory.write_text(json.dumps({**f, "genre": None, "description": "Un site d'une page pour un café."}),
                                encoding="utf-8")
        self.appels.objet = {"verdict": "autre", "genre": None, "raison": "Un site web.",
                             "nouveau": {"id": "site-vitrine", "description": "Sites web d'une page"}}
        self.moteur.tour()
        self.assertEqual([json.loads(x)["demande"]["texte"] for _, x in self.appels.recus],
                         ["Un site d'une page pour un café."])
        (c,) = self.suivi()["decisions_projet"]
        self.assertEqual((c["genre"], c["propose"]), ("confirmer_genre", "site-vitrine"))
        self.moteur.tour()
        self.assertEqual(len(self.appels.recus), 1)                 # une seule fois

    def test_tour_traite_les_messages_d_abord(self):
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Une leçon.", "etage_propose": "projet",
                                 "roles": ["dev"]})
        a = self.demande(type="lecon", id="dev-1:L1", verdict="valider")
        b = self.demande(type="bouton", id="exporter")
        c = self.demande(type="message", fonctionnalite="f1", texte="Bonjour")
        vus = []
        vrai = regles.traiter_demande
        with mock.patch.object(regles, "traiter_demande", side_effect=lambda p, d, e: vus.append(d["id"]) or vrai(p, d, e)):
            self.moteur.tour()
        self.assertEqual(vus, [c, a, b])

    def test_usage_de_chaque_jugement_note(self):
        i = self.demande(type="bouton", id="exporter")
        self.moteur.tour()
        usages = [u for u in self.suivi()["usage"] if u.get("agent") == "orchestrateur"]
        self.assertEqual(len(usages), 1)
        u = usages[0]
        self.assertEqual((u["etape"], u["modele"], u["entree"], u["sortie"], u["cache_lecture"], u["cache_ecriture"]),
                         ("orchestration", "claude-haiku-5-5", 100, 20, 5, 7))
        self.assertEqual(self.statut(i)["reponse"], "Rien à faire.")

    def test_l_instantane_d_abonnement_suit_l_usage_du_jugement(self):
        ab = {"seven_day": {"pourcent": 43.0, "remise": 1794639600}, "t": 1794480000}
        self.moteur.appeler = lambda c, d, m, **o: appel.Reponse(json.dumps(CONSEIL_RIEN), [dict(USAGE, abonnement=ab)])
        self.demande(type="bouton", id="exporter")
        self.moteur.tour()
        [u] = [u for u in self.suivi()["usage"] if u.get("agent") == "orchestrateur"]
        self.assertEqual(u["abonnement"], ab)

    def test_usage_d_un_agent_note_sur_sa_tache(self):
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.moteur.tour()
        self.moteur.tour()      # le retour de l'agent est lu au passage suivant
        usages = [u for u in self.suivi()["usage"] if u.get("agent") == "metier-1"]
        self.assertEqual(len(usages), 1)
        self.assertEqual(usages[0]["modele"], "claude-opus-5-5")
        self.assertEqual(usages[0]["tache"], self.suivi()["taches"][0]["id"])
        self.assertEqual(len(self.agents.lances), 1)
        self.assertIn("Discussion", self.agents.lances[0]["matiere"])
        self.assertEqual(self.agents.lances[0]["dossier"], str(self.projet.dossier))

    def test_agent_en_echec_usage_note_quand_meme(self):
        self.agents.rapport = None
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.moteur.tour()
        self.assertTrue(any(u.get("agent") == "metier-1" for u in self.suivi()["usage"]))

    def test_demande_traitee_pas_rejouee(self):
        i = self.demande(type="bouton", id="exporter")
        vrai = regles.traiter_demande
        with mock.patch.object(regles, "traiter_demande", side_effect=vrai) as m:
            self.moteur.tour()
            self.moteur.tour()
        self.assertEqual(m.call_count, 1)
        self.assertEqual(self.statut(i)["statut"], "traitée")
        # même une demande qui attend encore un agent n'est prise qu'une fois
        self.appels.objet = {"action": "transmettre_agent", "parametres": {"consigne": "Exporte."}, "reponse": ""}
        j = self.demande(type="bouton", id="autre")
        self.agents.rapport = None
        self.agents.lances.clear()
        with mock.patch.object(regles, "traiter_demande", side_effect=vrai) as m:
            self.moteur.tour()
            self.moteur.tour()
            self.moteur.tour()
        self.assertEqual(m.call_count, 1)
        self.assertEqual(len(self.agents.lances), 2)                   # l'agent sans rapport est relancé une fois
        self.assertEqual(self.statut(j)["statut"], "traitée")          # puis la demande dit pourquoi elle s'arrête

    def test_feu_vert_faux_ne_lance_rien(self):
        self.projet._feu_vert = lambda: False
        i = self.demande(type="fonctionnalite", texte="Des écrans")
        self.moteur.tour()
        self.moteur.tour()
        self.assertEqual(self.agents.lances, [])
        self.assertEqual(self.statut(i)["statut"], "traitée")
        self.projet._feu_vert = lambda: True      # la charge baisse : l'agent part au passage suivant
        self.moteur.tour()
        self.assertEqual(len(self.agents.lances), 1)

    def test_pause_par_projet(self):
        with tempfile.TemporaryDirectory() as autre_dossier:
            autre = Path(autre_dossier)
            (autre / "fiches").mkdir()
            factory_b = factory_minimale(autre)
            (autre / "fiches" / "hugo.md").write_text((self.dossier / "fiches" / "hugo.md").read_text(encoding="utf-8").replace("metier-1", "metier-9"), encoding="utf-8")
            projet_b = regles.Projet(factory_b, feu_vert=lambda: True)
            moteur = self.fabriquer([self.projet, projet_b])
            self.demande(type="bouton", id="pause")                 # le projet A est en pause
            a = self.demande(type="fonctionnalite", texte="Pour A")
            b = self.demande(factory=factory_b, type="fonctionnalite", texte="Pour B")
            moteur.tour()
            moteur.tour()
            self.assertEqual(self.statut(a)["statut"], "traitée")   # ses demandes sont quand même traitées
            self.assertEqual(self.statut(b, autre)["statut"], "traitée")
            self.assertEqual([x["agent"] for x in self.agents.lances], ["metier-9"])    # seul B a démarré
            self.assertEqual([t for t in self.suivi()["taches"] if t.get("active")], [])

    def test_reprise_relance_tache_orpheline(self):
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        t = self.ok("tache", entree={"titre": "Développement : Accueil", "fonctionnalite": "f1", "role": "dev",
                                     "colonne": "dev", "etape": "flux:dev", "element": "e1", "agent": "dev-1",
                                     "active": True})["id"]
        self.moteur.tour()
        self.assertEqual([(x["agent"], x["tache"]) for x in self.agents.lances], [("dev-1", t)])
        journal = [j["texte"] for j in next(x for x in self.suivi()["taches"] if x["id"] == t)["journal"]]
        self.assertTrue(any("repris" in j for j in journal))
        self.moteur.tour()
        self.assertEqual(len(self.agents.lances), 1)        # une seule fois

    def test_le_depart_d_un_lot_ne_demande_aucune_commande(self):
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        ids = [self.ok("tache", entree={"titre": f"Développement : {n}", "fonctionnalite": "f1", "role": "dev",
                                        "colonne": "dev", "etape": "flux:dev", "element": n})["id"] for n in ("e1", "e2")]
        self.moteur._partir(self.projet, ("agent", "dev-1", ids, "Matière."))
        depart = self.agents.lances[0]["depart"]
        self.assertIn("un seul rapport", depart)
        self.assertNotIn("lancer tache", depart)

    def test_ligne_couche_dite_une_fois(self):
        (self.dossier / "reglages.json").write_text(json.dumps({"images": {"racines": ["pieces"]},
                                                                "moteur": {"couche": "api"}}), encoding="utf-8")
        projet = boucle.ouvrir_projet(self.dossier / "reglages.json", environ={})
        self.assertEqual(projet.couche, "claude")
        self.assertEqual(projet.ligne_a_dire, appel.LIGNE_SANS_CLE)
        moteur = self.fabriquer([projet])
        a = self.demande(type="bouton", id="x")
        b = self.demande(type="bouton", id="y")
        moteur.tour()
        self.assertIn(appel.LIGNE_SANS_CLE, self.statut(a)["reponse"])
        self.assertNotIn(appel.LIGNE_SANS_CLE, self.statut(b)["reponse"])
        self.assertIsNone(projet.ligne_a_dire)

    def test_couche_api_avec_cle(self):
        (self.dossier / "reglages.json").write_text(json.dumps({"moteur": {"couche": "api"}}), encoding="utf-8")
        projet = boucle.ouvrir_projet(self.dossier / "reglages.json", environ={"ANTHROPIC_API_KEY": "x"})
        self.assertEqual((projet.couche, projet.ligne_a_dire), ("api", None))

    def test_projet_ajoute_au_bureau_pris_sans_redemarrer(self):
        with tempfile.TemporaryDirectory() as racine:
            racine = Path(racine)
            premier, second = racine / "a", racine / "b"
            for d in (premier, second):
                d.mkdir()
                factory_minimale(d)
            bureau = racine / "bureau.json"
            bureau.write_text(json.dumps({"projets": ["a/reglages.json"]}), encoding="utf-8")
            moteur = self.fabriquer([], bureau=bureau)
            moteur.tour()
            self.assertTrue((premier / "presence.json").exists())
            self.assertFalse((second / "presence.json").exists())
            bureau.write_text(json.dumps({"projets": ["a/reglages.json", "b/reglages.json"]}), encoding="utf-8")
            moteur.tour()
            self.assertTrue((second / "presence.json").exists())
            self.assertEqual(len(moteur.projets), 2)

    def test_commit_apres_une_etape_qui_produit(self):
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.moteur.tour()
        self.moteur.tour()
        self.assertEqual(self.commits, [(str(self.projet.dossier), "Factory : Voilà.")])

    def test_le_projet_connait_le_bureau_pour_estimer(self):
        bureau = self.dossier / "bureau.json"
        moteur = self.fabriquer([], bureau=bureau)
        moteur._ajouter(self.projet)
        self.assertEqual(self.projet.bureau, bureau)

    def test_erreur_d_un_projet_n_arrete_pas_la_boucle(self):
        with mock.patch.object(regles, "avancer", side_effect=RuntimeError("boum")):
            self.moteur.tour()
        self.assertTrue(any("boum" in ligne for ligne in self.moteur.journal))


class Detaches(Base):
    """Les agents locaux détachés : le moteur relancé les retrouve ; une question de l'utilisateur leur est transmise."""

    def setUp(self):
        super().setUp()
        self.vivants = set()
        self.moteur = self.fabriquer([self.projet], registre=lambda d: detache.Registre(
            d, vivant=lambda e: e.get("pid") in self.vivants, noter_abonnement=False))
        self.ok("demande-traitee", entree={"id": self.demande(type="fonctionnalite", texte="Des écrans")})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        self.tache = self.ok("tache", entree={"titre": "Développement : Accueil", "fonctionnalite": "f1", "role": "dev",
                                              "colonne": "dev", "etape": "flux:dev", "element": "e1", "agent": "dev-1",
                                              "active": True})["id"]
        self.registre = detache.dossier(self.dossier)

    def agent_en_cours(self, pid=4242, resultat=False):
        self.registre.mkdir(exist_ok=True)
        (self.registre / f"{self.tache}.json").write_text(json.dumps(
            {"genre": "tache", "tache": self.tache, "taches": [self.tache], "agent": "dev-1", "modele": "sonnet",
             "lot": None, "matiere": "Matière d'avant", "pid": pid, "debut": 1.0}), encoding="utf-8")
        (self.registre / f"{self.tache}.jsonl").write_text(
            '{"type": "result", "result": "x"}\n' if resultat else '{"type": "system"}\n', encoding="utf-8")

    def journal(self):
        return [j["texte"] for j in next(x for x in self.suivi()["taches"] if x["id"] == self.tache)["journal"]]

    def tache_suivie(self):
        return next(x for x in self.suivi()["taches"] if x["id"] == self.tache)

    def test_un_agent_vivant_est_attendu_au_lieu_d_etre_relance(self):
        self.agent_en_cours()
        self.vivants.add(4242)
        self.moteur.tour()
        (lance,) = self.agents.lances
        self.assertEqual((lance["tache"], lance["agent"], lance["matiere"]), (self.tache, "dev-1", "Matière d'avant"))
        self.assertTrue(lance["executeur"].rattacher)
        self.assertFalse(any("avait disparu" in j for j in self.journal()))
        self.assertTrue(any("travaille encore" in j for j in self.journal()))
        self.moteur.tour()                        # son résultat lu : la tâche est finie, l'agent oublié
        self.assertEqual(self.tache_suivie()["colonne"], "fait")
        self.assertFalse((self.registre / f"{self.tache}.json").exists())
        self.assertEqual(len(self.agents.lances), 1)

    def test_un_agent_mort_avec_son_resultat_est_lu(self):
        self.agent_en_cours(resultat=True)
        self.moteur.tour()
        (lance,) = self.agents.lances
        self.assertTrue(lance["executeur"].rattacher)
        self.assertTrue(any("avait fini" in j for j in self.journal()))

    def test_un_agent_mort_sans_resultat_nouvel_essai(self):
        self.agent_en_cours()
        self.moteur.tour()
        (lance,) = self.agents.lances
        self.assertFalse(lance["executeur"].rattacher)
        self.assertTrue(any("avait disparu" in j for j in self.journal()))

    def test_un_agent_arrete_depuis_le_bureau_moteur_coupe_ne_repart_pas(self):
        self.agent_en_cours()
        detache.demander_arret(self.dossier, self.tache)
        self.moteur.tour()
        self.assertEqual(self.agents.lances, [])
        self.assertEqual(self.tache_suivie()["bloquee"], regles.ARRET_DEPUIS_LE_BUREAU)
        self.assertFalse((self.registre / f"{self.tache}.arrete").exists())

    def test_le_depart_passe_par_le_registre_du_projet(self):
        self.moteur.tour()
        (lance,) = self.agents.lances          # la tâche orpheline (aucun agent connu) repart
        self.assertFalse(lance["executeur"].rattacher)
        self.assertEqual(lance["executeur"].registre.dossier, self.registre)

    def test_une_question_pendant_le_travail_est_transmise_a_l_agent(self):
        self.agent_en_cours()
        self.vivants.add(4242)
        self.moteur.synchrone = False
        fini = __import__("threading").Event()
        vrai = self.agents.__call__

        def lent(*a, **k):
            fini.wait(10)
            return vrai(*a, **k)
        self.moteur.executer_agent = lent
        self.moteur.tour()                        # l'agent est attendu (dans un fil)
        i = self.demande(type="message", fonctionnalite="f1", texte="Où en es-tu ?")
        self.moteur.tour()
        self.assertEqual(self.statut(i)["statut"], "traitée")
        self.assertEqual([t["titre"] for t in self.suivi()["taches"] if t["titre"].startswith("Retour")], [])
        dit = "Question transmise à Léa : il répondra à la fin de sa tâche en cours."
        f = self.ok("detail", entree={"fonctionnalite": "f1"})
        self.assertEqual(f["discussion"][-1]["texte"], dit)
        self.assertEqual(detache.questions(self.dossier, self.tache), ["Où en es-tu ?"])
        self.moteur.synchrone = True
        self.moteur.executer_agent = self.agents
        fini.set()
        for _ in range(100):
            if not self.moteur.retours.empty():
                break
            __import__("time").sleep(0.05)
        self.moteur.tour()                        # la tâche finie : l'agent reprend sa session pour répondre
        reponse = self.agents.lances[-1]
        self.assertEqual(reponse["reprendre"], "s-1")
        self.assertIn("Où en es-tu ?", reponse["depart"])
        self.assertEqual(reponse["fiche"]["outils"], "Read, Grep, Glob")      # il répond, il ne travaille plus
        self.assertEqual(detache.questions(self.dossier, self.tache), [])
        self.moteur.tour()
        f = self.ok("detail", entree={"fonctionnalite": "f1"})
        self.assertEqual((f["discussion"][-1]["auteur"], f["discussion"][-1]["texte"]), ("dev-1", "Voilà."))
        self.assertEqual(self.tache_suivie()["colonne"], "fait")

    def test_la_question_suit_la_tache_relancee(self):
        """L'agent rend sans rapport : la tâche repart, la question va dans la matière de ce nouvel essai."""
        self.agents.rapport = None
        self.agent_en_cours()
        self.vivants.add(4242)
        detache.ajouter_question(self.dossier, self.tache, "Et le menu ?")
        self.moteur.tour()
        self.moteur.tour()
        relance = self.agents.lances[-1]
        self.assertEqual(relance["tache"], self.tache)
        self.assertIn("Et le menu ?", relance["matiere"])
        self.assertNotIn("reprendre", relance)

    def test_sans_agent_au_travail_le_message_suit_son_cours(self):
        self.ok("tache", entree={"id": self.tache, "active": False})
        self.ok("tache", entree={"id": self.tache, "colonne": "fait"})
        with mock.patch.object(regles, "_conseil", return_value=("lancer", "etat", None)) as conseil:
            self.demande(type="message", fonctionnalite="f1", texte="Une idée")
            self.moteur.tour()
        self.assertEqual(conseil.call_count, 1)


class Lecons(Base):
    """Les verdicts sur des leçons : « Valider toutes » est un lot, et une écriture en attente se réessaie seule."""

    def noter(self, texte):
        return self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": texte, "etage_propose": "projet",
                                        "roles": ["dev"]})["id"]

    def espionner(self, **faux):
        """Note chaque `lancer lecon` ; `faux[nom]` remplace la réponse de l'outil (nom : valeur ou fonction)."""
        vus, vrai = [], regles.lancer

        def lancer(projet, nom, entree=None):
            if nom == "lecon":
                vus.append(entree)
            if nom == "lecon" and "lecon" in faux:
                return faux["lecon"](entree)
            return vrai(projet, nom, entree)

        return vus, mock.patch.object(regles, "lancer", lancer)

    def test_plusieurs_verdicts_un_seul_appel_en_lot(self):
        ids = [self.noter(f"Leçon {n}.") for n in range(3)]
        demandes = [self.demande(type="lecon", id=i, verdict="valider") for i in ids]
        vus, patch = self.espionner()
        with patch:
            self.moteur.tour()
        appliques = [e for e in vus if e.get("action") == "appliquer"]
        self.assertEqual(len(appliques), 1)
        self.assertEqual([x["id"] for x in appliques[0]["lot"]], ids)
        for d in demandes:
            self.assertEqual((self.statut(d)["statut"], self.statut(d)["reponse"]), ("traitée", "La leçon est retenue."))
        self.assertEqual(self.ok("etat")["lecons"], [])

    def test_chaque_demande_du_lot_garde_son_resultat(self):
        i = self.noter("Une leçon.")
        bonne = self.demande(type="lecon", id=i, verdict="valider")
        inconnue = self.demande(type="lecon", id="dev-1:L99", verdict="valider")
        self.moteur.tour()
        self.assertEqual(self.statut(bonne)["reponse"], "La leçon est retenue.")
        self.assertTrue(self.statut(inconnue)["reponse"].startswith("Je n'ai pas pu le faire"))

    def test_une_seule_demande_reste_un_appel_simple(self):
        i = self.noter("Une leçon.")
        d = self.demande(type="lecon", id=i, verdict="invalider")
        self.moteur.tour()
        self.assertEqual(self.statut(d)["reponse"], "La leçon est écartée.")

    def test_ecriture_en_attente_dite_dans_la_reponse(self):
        a, b = self.noter("Une."), self.noter("Deux.")
        da, db = (self.demande(type="lecon", id=i, verdict="valider") for i in (a, b))
        faux = lambda e: {"resultats": [  # noqa: E731
            {"id": a, "ok": True, "etage": "skill", "en_attente": True, "raison": "le dépôt est occupé."},
            {"id": b, "ok": True, "etage": "projet"}]}
        _, patch = self.espionner(lecon=faux)
        with patch:
            self.moteur.tour()
        self.assertIn("en attente", self.statut(da)["reponse"])
        self.assertIn("le dépôt est occupé.", self.statut(da)["reponse"])
        self.assertEqual(self.statut(db)["reponse"], "La leçon est retenue.")

    def test_les_ecritures_en_attente_sont_reessayees_toutes_les_cinq_minutes(self):
        heure = [1000.0]
        self.moteur = self.fabriquer([self.projet], horloge=lambda: heure[0])
        vus, patch = self.espionner()
        with patch:
            self.moteur.tour()
            self.moteur.tour()
            self.assertEqual([e["action"] for e in vus], ["reessayer"])    # au premier passage, une fois
            heure[0] += boucle.ECRITURE_LECONS_TOUS_LES_S - 1
            self.moteur.tour()
            self.assertEqual(len(vus), 1)
            heure[0] += 2
            self.moteur.tour()
            self.assertEqual([e["action"] for e in vus], ["reessayer", "reessayer"])
        self.assertEqual(self.moteur.journal, [])

    def etats(self):
        return {x["id"]: x["etat"] for x in self.suivi()["lecons"]}

    def test_decoche_la_lecon_reste_a_valider(self):
        i = self.noter("Une leçon.")
        vus, patch = self.espionner()
        with patch:
            self.moteur.tour()
        self.assertEqual(self.etats(), {i: "à valider"})
        self.assertFalse([e for e in vus if e.get("action") == "appliquer"])

    def test_coche_la_lecon_proposee_passe_validee_au_passage_suivant(self):
        self.projet.lecons_auto = True
        i = self.noter("Une leçon.")
        self.moteur.tour()
        self.assertEqual(self.etats(), {i: "validée"})
        self.assertEqual(next(x for x in self.suivi()["lecons"] if x["id"] == i)["etage_applique"], "projet")
        self.assertEqual(self.ok("etat")["lecons"], [])

    def test_coche_les_lecons_deja_en_attente_sont_validees_au_niveau_propose(self):
        a, b = self.noter("Une."), self.noter("Deux.")
        self.moteur.tour()
        self.assertEqual(self.etats(), {a: "à valider", b: "à valider"})
        self.projet.lecons_auto = True
        vus, patch = self.espionner()
        with patch:
            self.moteur.tour()
        (lot,) = [e["lot"] for e in vus if e.get("action") == "appliquer"]
        self.assertEqual(lot, [{"id": a, "verdict": "valider", "etage": "projet"},
                               {"id": b, "verdict": "valider", "etage": "projet"}])
        self.assertEqual(self.etats(), {a: "validée", b: "validée"})

    def test_l_etage_propose_est_celui_de_la_validation(self):
        self.projet.lecons_auto = True
        a = self.noter("Une.")
        faux = lambda e: {"resultats": [{"id": a, "ok": True, "etage": "skill"}]}  # noqa: E731
        vus, patch = self.espionner(lecon=faux)
        s = self.suivi()
        s["lecons"][0].update(etage_propose="skill", texte_general="Une règle générale.")
        (self.dossier / "suivi.json").write_text(json.dumps(s), encoding="utf-8")
        with patch:
            self.moteur.tour()
        (lot,) = [e["lot"] for e in vus if e.get("action") == "appliquer"]
        self.assertEqual(lot, [{"id": a, "verdict": "valider", "etage": "skill"}])

    def test_une_lecon_refusee_reste_a_valider_sans_etre_reessayee_ni_bloquer_les_autres(self):
        self.projet.lecons_auto = True
        a, b = self.noter("Une."), self.noter("Deux.")
        faux = lambda e: {"resultats": [  # noqa: E731
            {"id": a, "ok": False, "refus": "texte invalide"}, {"id": b, "ok": True, "etage": "projet"}]}
        vus, patch = self.espionner(lecon=faux)
        with patch:
            self.moteur.tour()
            self.moteur.tour()
        self.assertEqual(len([e for e in vus if e.get("action") == "appliquer"]), 1)
        self.assertTrue(any("texte invalide" in x for x in self.moteur.journal))

    def test_le_reglage_est_relu_a_chaque_passage_et_a_l_ouverture(self):
        reglages = self.dossier / "reglages.json"
        reglages.write_text("{}", encoding="utf-8")
        ouvert = boucle.ouvrir_projet(reglages)
        self.assertEqual((ouvert.lecons_auto, ouvert.fichier_reglages), (False, reglages))
        self.projet.fichier_reglages = ouvert.fichier_reglages
        i = self.noter("Une leçon.")
        self.moteur.tour()
        self.assertEqual(self.etats(), {i: "à valider"})
        reglages.write_text(json.dumps({"lecons_auto": True}), encoding="utf-8")
        self.moteur.tour()
        self.assertEqual(self.etats(), {i: "validée"})
        self.assertTrue(boucle.ouvrir_projet(reglages).lecons_auto)


if __name__ == "__main__":
    unittest.main()
