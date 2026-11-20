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

    def test_un_jugement_refuse_est_dit_dans_la_discussion(self):
        """Essai réel : la création d'une fonctionnalité refusée après son classement ; le bureau montrait l'agent de
        cadrage « en train d'écrire » sans fin. Le refus est dit dans la discussion de la fonctionnalité."""
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("demande-traitee", entree={"id": "r1"})
        self.moteur._signaler(self.projet, ("juger", "classer_genre", {}, {"demande": "r1", "fonctionnalite": "f1"}),
                              regles.Refus("organisation : Organisation refusée : Aucun agent pour le rôle « dev »."))
        f = next(x for x in self.suivi()["fonctionnalites"] if x["id"] == "f1")
        self.assertIn("Je n'ai pas pu aller au bout", f["discussion"][-1]["texte"])
        self.assertNotEqual(f["discussion"][-1]["auteur"], "utilisateur")

    def test_un_jugement_en_echec_n_est_jamais_laisse_en_attente(self):
        """Essai réel : l'écriture d'une méthode validée a échoué (appel au modèle) ; la demande restait « en attente »
        sans fin et le bureau semblait bloqué. L'échec est dit sur la demande et dans la discussion."""
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("demande-traitee", entree={"id": "r1"})
        i = self.demande(type="message", fonctionnalite="f1", texte="Bonjour")
        with mock.patch.object(self.moteur, "_juger", side_effect=RuntimeError("délai dépassé")):
            self.moteur._executer(self.projet, [("juger", "ecrire_methode", {}, {"demande": i, "fonctionnalite": "f1"})])
        d = self.statut(i)
        self.assertEqual(d["statut"], "traitée")
        self.assertIn("délai dépassé", d["reponse"])
        f = next(x for x in self.suivi()["fonctionnalites"] if x["id"] == "f1")
        self.assertIn("renvoyer votre réponse", f["discussion"][-1]["texte"])

    def test_le_chef_au_travail_est_dit_pendant_un_jugement(self):
        from bureau import attente
        vu = []

        def juger(type_, dossier, **kw):
            vu.append(attente.chef_au_travail(self.dossier))
            raise RuntimeError("fin de l'essai")
        with mock.patch.object(boucle.jugement, "juger", side_effect=juger):
            self.moteur._executer(self.projet, [("juger", "ecrire_methode", {}, {"fonctionnalite": "f1"})])
        self.assertEqual((vu[0]["texte"], vu[0]["fonctionnalite"]), ("Le Chef est en train d'écrire la méthode", "f1"))
        self.assertIsNone(attente.chef_au_travail(self.dossier))        # effacé après, même en échec

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

    def test_un_rapport_qui_fait_echouer_le_moteur_n_est_jamais_perdu_en_silence(self):
        """Essai réel : le rapport d'une livraison n'a jamais été appliqué ; la tâche restait « active » sans agent et
        le bureau semblait bloqué. Toute erreur : la tâche est bloquée et dit pourquoi."""
        self.demande(type="fonctionnalite", texte="Des écrans")
        with mock.patch.object(regles, "traiter_retour", side_effect=KeyError("element")):
            self.moteur.tour()                      # en essai, le rapport de l'agent est lu dans le même passage
        t = self.suivi()["taches"][0]
        self.assertFalse(t["active"])
        self.assertIn("n'a pas pu appliquer tout le rapport", t["bloquee"])

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

    def test_une_reprise_promise_survit_au_redemarrage(self):
        """La reprise demandée (`a_lancer`) est gardée dans `attente-reprises.json` : le moteur redémarré la relance."""
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        t = self.ok("tache", entree={"titre": "Correction : Accueil", "fonctionnalite": "f1", "role": "dev",
                                     "colonne": "dev", "etape": "correction", "agent": "dev-1"})["id"]
        fichier = boucle.Moteur._fichier_reprises(self.moteur.projets[0])
        fichier.write_text(json.dumps({"a_lancer": [t], "supplements": {t: "Reprends sur le poste."}}),
                           encoding="utf-8")
        self.moteur.tour()
        self.assertEqual([(x["agent"], x["tache"]) for x in self.agents.lances], [("dev-1", t)])
        self.assertFalse(fichier.exists())             # partie : plus rien à garder

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

    def suivi_du_retour(self, i):
        return next(d for d in self.suivi()["demandes"] if d["id"] == i).get("suivi")

    def test_un_retour_transmis_est_suivi_jusqu_a_la_reponse(self):
        """Essai réel (2026-11-18) : « Question transmise à Hugo » restait la seule trace du retour sur la tâche."""
        self.agent_en_cours()
        self.vivants.add(4242)
        self.moteur.synchrone = False
        fini = __import__("threading").Event()
        vrai = self.agents.__call__

        def lent(*a, **k):
            fini.wait(10)
            return vrai(*a, **k)
        self.moteur.executer_agent = lent
        self.moteur.tour()
        i = self.demande(type="retour", tache=self.tache, texte="Le téléchargement échoue")
        self.moteur.tour()
        s = self.suivi_du_retour(i)
        self.assertEqual((s["etat"], s["tache"]), ("transmis", self.tache))
        self.assertIn("Léa travaille encore", s["texte"])
        (r,) = next(t for t in self.ok("releve")["taches"] if t["id"] == self.tache)["retours"]
        self.assertEqual(r["suivi"]["etat"], "transmis")      # le bureau le voit sous le retour
        self.moteur.synchrone = True
        self.moteur.executer_agent = self.agents
        fini.set()
        for _ in range(100):
            if not self.moteur.retours.empty():
                break
            __import__("time").sleep(0.05)
        with mock.patch.object(regles, "suivre_demande", wraps=regles.suivre_demande) as suivre:
            self.moteur.tour()                    # la tâche finie : l'agent rédige sa réponse, puis la rend
            self.moteur.tour()
        self.assertEqual([c.args[2] for c in suivre.call_args_list], ["reponse_en_cours", "repondu"])
        s = self.suivi_du_retour(i)
        self.assertEqual((s["etat"], s["texte"]), ("repondu", "Réponse de Léa : Voilà."))

    def test_le_bureau_compte_la_reponse_jusqu_a_pris_en_compte(self):
        from bureau import etat as bureau_etat
        taches = [{"id": "t1", "retours": [{"id": "r1", "t": "x", "texte": "y", "suivi": {"etat": "repondu"}},
                                           {"id": "r2", "t": "x", "texte": "y", "suivi": {"etat": "transmis"}}]}]
        self.assertEqual([x["id"] for _, x in bureau_etat.retours_repondus_non_vus(taches, [])], ["r1"])
        self.assertEqual(bureau_etat.retours_repondus_non_vus(taches, ["retour:r1"]), [])
        self.assertEqual([bureau_etat.retour_sans_reponse(x) for x in taches[0]["retours"]], [False, True])

    def test_un_retour_repris_dans_le_nouvel_essai(self):
        self.agents.rapport = None
        self.agent_en_cours()
        self.vivants.add(4242)
        i = self.demande(type="retour", tache=self.tache, texte="Et le menu ?")
        self.ok("demande-traitee", entree={"id": i, "reponse": "transmise"})
        detache.ajouter_question(self.dossier, self.tache, "Et le menu ?", demande=i)
        self.moteur.tour()
        self.moteur.tour()
        self.assertEqual(self.suivi_du_retour(i)["etat"], "repris")

    def test_les_anciennes_questions_sans_demande_se_lisent_encore(self):
        self.registre.mkdir(exist_ok=True)
        (self.registre / f"{self.tache}.questions.json").write_text('["Ancienne"]', encoding="utf-8")
        detache.ajouter_question(self.dossier, self.tache, "Nouvelle", demande="r9")
        self.assertEqual(detache.prendre_questions_et_demandes(self.dossier, self.tache),
                         (["Ancienne", "Nouvelle"], ["r9"]))

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


class FauxExecuteurServeur:
    """L'exécuteur distant des essais : garde ce qu'il a reçu ; `arreter` réveille l'agent qui l'attend."""

    def __init__(self, projet, tache, mode, demande_base, apk=None, **kw):
        self.projet, self.tache, self.mode, self.demande_base, self.apk = projet, tache, mode, demande_base, apk
        self.autres_noms = kw.get("autres_noms", ())
        self.branche, self.arrets = None, 0
        self.arret = __import__("threading").Event()

    def arreter(self):
        self.arrets += 1
        self.arret.set()
        return {"etat": "arretee"}


class FauxFusion:
    def __init__(self):
        self.fusions = []

    def fusionner(self, dossier, branche, **kw):
        self.fusions.append((dossier, branche, kw))
        return None


class Serveur(Base):
    """Le lieu `serveur` : un agent ordinaire dont l'exécuteur est distant (`ExecuteurServeur`)."""

    def setUp(self):
        super().setUp()
        from tests.orch_aide import FICHE_LEA
        (self.dossier / "fiches" / "lea.md").write_text(FICHE_LEA.replace("Lieu : local", "Lieu : serveur"),
                                                        encoding="utf-8")
        from moteur import executeur_serveur
        from bureau import deport_types
        self.executeurs, self.accord, self.accords, self.actives = [], False, [], []

        def fabrique(*a, **kw):
            ex = FauxExecuteurServeur(*a, **kw)
            self.executeurs.append(ex)
            return ex

        def accord(racine, action, *a, **kw):
            self.accords.append((racine, action))
            return self.accord
        for cible, nom, valeur in ((executeur_serveur, "ExecuteurServeur", fabrique),
                                   (deport_types, "accord_serveur", accord)):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(boucle.Moteur, "_taches_serveur_actives",
                              lambda moteur: None if self.actives is None else list(self.actives), create=True)
        p.start()
        self.addCleanup(p.stop)
        self.cloud = FauxFusion()
        self.moteur = self.fabriquer([self.projet], session_cloud=self.cloud)
        self.ok("demande-traitee", entree={"id": self.demande(type="fonctionnalite", texte="Des écrans")})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        self.tache = self.ok("tache", entree={"titre": "Développement : Accueil", "fonctionnalite": "f1", "role": "dev",
                                              "colonne": "dev", "etape": "flux:dev", "element": "e1", "agent": "dev-1",
                                              "active": True})["id"]

    def tache_suivie(self):
        return next(x for x in self.suivi()["taches"] if x["id"] == self.tache)

    def journal(self):
        return [j["texte"] for j in self.tache_suivie()["journal"]]

    def lances(self):
        return [x for x in self.agents.lances if x["agent"] == "dev-1"]

    def partir(self, matiere="Matière."):
        """Le départ tel que `regles` le donne : la tâche en cours, son départ noté, puis l'action `agent`."""
        etat = self.moteur._etat(self.projet)
        etat["repris"] = True
        etat["en_cours"].add(self.tache)
        etat["departs"][self.tache] = {"agent": "dev-1", "taches": [self.tache], "matiere": matiere, "modele": "sonnet",
                                       "lot": None, "suite": None}
        self.moteur._partir(self.projet, ("agent", "dev-1", [self.tache], matiere))

    def test_partir_serveur_utilise_l_executeur_distant(self):
        self.partir()
        (lance,) = self.lances()
        (ex,) = self.executeurs
        self.assertIs(lance["executeur"], ex)
        self.assertEqual((Path(ex.projet), ex.tache, ex.mode, ex.demande_base, ex.apk),
                         (self.dossier, self.tache, "seul", {"projet": self.projet.nom}, None))
        self.assertEqual((lance["tache"], lance["matiere"], lance["dossier"]), (self.tache, "Matière.", str(self.dossier)))
        self.assertIn(f"`agent/{self.tache}`", lance["depart"])
        self.assertIn("commite", lance["depart"])
        self.assertNotIn("lancer.py\" tests --", lance["depart"])     # pas le lanceur de tests du poste
        self.assertNotIn("reprendre", lance)
        self.assertFalse(any(detache.dossier(self.dossier).glob("*.json")))   # aucun agent détaché sur le poste
        self.moteur.tour()
        self.assertEqual(self.tache_suivie()["colonne"], "fait")
        self.assertEqual(self.cloud.fusions, [])          # sans commit rapatrié : rien à fusionner

    def test_mode_pilote_seulement_avec_accord_et_apk(self):
        sorties = self.dossier / "app" / "build" / "outputs" / "apk"
        (sorties / "androidTest" / "debug").mkdir(parents=True)
        (sorties / "androidTest" / "debug" / "app-debug-androidTest.apk").write_bytes(b"PK")
        cas = []
        for accord, apk in ((False, False), (True, False), (True, True), (False, True)):
            self.accord = accord
            if apk:
                (sorties / "debug").mkdir(parents=True, exist_ok=True)
                (sorties / "debug" / "app-debug.apk").write_bytes(b"PK")
            self.partir()
            ex = self.executeurs[-1]
            cas.append((accord, apk, ex.mode, ex.apk and Path(ex.apk).name))
            depart = self.lances()[-1]["depart"]
            self.assertEqual("`pont <verbe> [arguments]`" in depart, ex.mode == "pilote")
        self.assertEqual(cas, [(False, False, "seul", None), (True, False, "seul", None),
                               (True, True, "pilote", "app-debug.apk"), (False, True, "seul", None)])
        self.assertEqual(set(self.accords), {(str(self.dossier), "recette-emulateur")})

    def test_redemarrage_rattache_sans_relancer(self):
        self.actives = [{"id": "20261120-101010-abcdef", "type": "agent", "etat": "en_cours", "projet": self.projet.nom,
                         "tache": self.tache}]
        self.moteur.tour()                  # premier passage : la tâche active tenue par l'agent serveur est retrouvée
        (lance,) = self.lances()
        (ex,) = self.executeurs
        self.assertIs(lance["executeur"], ex)
        self.assertEqual((ex.tache, lance["tache"]), (self.tache, self.tache))
        self.assertTrue(any("travaille encore sur le serveur" in j for j in self.journal()))
        self.assertFalse(any("avait disparu" in j for j in self.journal()))     # jamais relancée par `orphelines`
        self.moteur.tour()
        self.assertEqual(len(self.lances()), 1)
        self.assertEqual(self.tache_suivie()["colonne"], "fait")

    def active(self, tache, genre="tache"):
        return {"id": "t20261120-101010-abcd", "type": "agent", "etat": "en_cours", "projet": self.projet.nom,
                "tache": tache, "genre": genre}

    def test_redemarrage_tache_plus_active_laissee_a_orphelines(self):
        self.actives = []                   # l'index se lit : la tâche n'y est plus active
        self.moteur.tour()
        (lance,) = self.lances()            # relancée une fois, par `orphelines`
        self.assertIs(lance["executeur"], self.executeurs[0])
        self.assertTrue(any("avait disparu" in j for j in self.journal()))
        self.assertFalse(any("n'est plus actif" in j for j in self.journal()))

    def test_redemarrage_projet_en_pause_ne_lance_rien(self):
        self.actives = []
        self.ok("actions", entree={"type": "bouton", "id": "pause"})
        self.moteur.tour()
        self.assertEqual(self.lances(), [])
        self.assertEqual(self.executeurs, [])

    def test_redemarrage_amont_pas_pret_ne_lance_rien(self):
        self.actives = []
        avant = self.ok("tache", entree={"titre": "Maquette", "fonctionnalite": "f1", "colonne": "dev"})["id"]
        self.ok("tache", entree={"id": self.tache, "depend_de": [avant]})
        self.moteur.tour()
        self.assertEqual(self.lances(), [])
        self.assertFalse(self.tache_suivie()["active"])
        self.assertTrue(any("amont" in j for j in self.journal()))

    def test_redemarrage_index_illisible(self):
        self.actives = None
        self.moteur.tour()
        (lance,) = self.lances()            # rattachée par son exécuteur (qui relit l'index), jamais en double
        self.assertIs(lance["executeur"], self.executeurs[0])
        self.assertTrue(any("illisible" in j for j in self.journal()))
        self.assertFalse(any("n'est plus actif" in j for j in self.journal()))
        self.assertFalse(any("avait disparu" in j for j in self.journal()))

    def test_redemarrage_lot_rattache_par_l_identifiant_actif(self):
        suivante = self.ok("tache", entree={"titre": "Développement : Menu", "fonctionnalite": "f1", "role": "dev",
                                            "colonne": "dev", "etape": "flux:dev", "element": "e2",
                                            "lot": {"id": "L1", "rang": 2}})["id"]
        self.ok("tache", entree={"id": self.tache, "lot": {"id": "L1", "rang": 1}})
        self.actives = [self.active(suivante.upper())]       # la tâche serveur porte l'autre identifiant du lot
        self.moteur.tour()
        (lance,) = self.lances()
        (ex,) = self.executeurs
        self.assertEqual(lance["tache"], self.tache)            # le départ du moteur : la première du lot
        self.assertEqual(ex.tache, suivante)                     # l'exécuteur : la tâche serveur active
        self.assertIn(f"`agent/{suivante}`", lance["depart"])
        self.assertTrue(any("travaille encore sur le serveur" in j for j in self.journal()))

    def test_redemarrage_lot_index_illisible_rattache_par_tous_ses_noms(self):
        suivante = self.ok("tache", entree={"titre": "Développement : Menu", "fonctionnalite": "f1", "role": "dev",
                                            "colonne": "dev", "etape": "flux:dev", "element": "e2",
                                            "lot": {"id": "L1", "rang": 2}})["id"]
        self.ok("tache", entree={"id": self.tache, "lot": {"id": "L1", "rang": 1}})
        self.actives = None
        self.moteur.tour()
        (ex,) = self.executeurs
        self.assertEqual(ex.tache, self.tache)
        self.assertEqual(set(ex.autres_noms), {self.tache, suivante})   # l'exécuteur cherche le lot sous tous ses noms

    def test_marque_d_arret_du_lot_sous_le_nom_de_la_tache_serveur(self):
        """Un lot rattaché par un autre de ses identifiants : le bureau marque l'arrêt sous le nom de la tâche SERVEUR ;
        le moteur l'entend, et la marque est prise (elle n'arrêtera pas le lancement suivant)."""
        ex = FauxExecuteurServeur(self.dossier, "lot-suivante", "seul", {"projet": self.projet.nom})
        self.moteur._serveurs[(str(self.projet.factory), self.tache)] = ex
        detache.demander_arret(self.dossier, "lot-suivante")
        self.moteur._arreter_les_agents_serveur(self.projet)
        self.assertEqual(ex.arrets, 1)
        self.assertFalse((detache.dossier(self.dossier) / "lot-suivante.arrete").exists())

    def test_reponse_en_echec_n_arrete_pas_les_suivantes_et_reste_gardee(self):
        dossier = detache.dossier(self.dossier)
        dossier.mkdir(parents=True, exist_ok=True)
        for tid in ("a-1", "b-2"):
            (dossier / f"{tid}.reponse-serveur").write_text(json.dumps(
                {"tache": tid, "agent": "dev-1", "modele": "sonnet", "session": "s-1", "questions": ["Où ?"],
                 "demandes": []}), encoding="utf-8")
        self.actives = []                                # finies sans être lues : redemandées
        vues = []

        def repondre(projet, etat, tid, *a, **k):
            vues.append(tid)
            if tid == "a-1":
                raise RuntimeError("panne")
        self.moteur._repondre = repondre
        self.moteur._rattacher_les_reponses_serveur(self.projet, self.moteur._etat(self.projet))
        self.assertEqual(vues, ["a-1", "b-2"])                       # la panne de la première n'arrête pas la suivante
        self.assertTrue((dossier / "a-1.reponse-serveur").exists())  # remise : redemandée au prochain démarrage

    def test_apk_par_un_lien_ou_hors_du_projet_refuse(self):
        import os
        import tempfile
        dehors = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, dehors, ignore_errors=True)
        (dehors / "pirate.apk").write_bytes(b"PK")
        sortie = self.dossier / "app" / "build" / "outputs" / "apk" / "debug"
        sortie.mkdir(parents=True)
        try:
            os.symlink(dehors / "pirate.apk", sortie / "app-debug.apk")
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        self.assertIsNone(boucle.apk_pour_le_pilote(self.dossier))
        (sortie / "app-debug.apk").unlink()
        try:
            os.symlink(dehors, sortie / "lien", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        (dehors / "app-release.apk").write_bytes(b"PK")
        self.assertIsNone(boucle.apk_pour_le_pilote(self.dossier))   # un dossier lié qui sort du projet
        (sortie / "vrai.apk").write_bytes(b"PK")
        self.assertEqual(Path(boucle.apk_pour_le_pilote(self.dossier)).name, "vrai.apk")

    def lancer_une_reponse_en_cours(self):
        """Une réponse aux questions lancée (dans un fil) puis le moteur « coupé » : rend l'évènement qui la libère."""
        detache.ajouter_question(self.dossier, self.tache, "Où en es-tu ?")
        self.partir()
        libere = __import__("threading").Event()
        self.addCleanup(libere.set)
        vrai = self.agents.__call__

        def bloque_la_reponse(*a, **k):
            if k.get("reprendre"):
                libere.wait(10)
            return vrai(*a, **k)
        self.moteur.executer_agent = bloque_la_reponse
        self.moteur.synchrone = False
        self.moteur.tour()                    # la tâche finie : la réponse part (et reste en cours)
        self.assertEqual(len(self.executeurs), 2)
        self.moteur = self.fabriquer([self.projet], session_cloud=self.cloud)     # le moteur redémarre
        self.agents.lances.clear()
        self.executeurs.clear()

    def test_redemarrage_pendant_une_reponse_rattachee(self):
        self.lancer_une_reponse_en_cours()
        self.actives = [self.active(self.tache, "reponse")]
        self.moteur.tour()
        (reponse,) = self.lances()
        (ex,) = self.executeurs
        self.assertIs(reponse["executeur"], ex)
        self.assertEqual(ex.demande_base, {"projet": self.projet.nom, "genre": "reponse"})
        self.assertEqual(reponse["reprendre"], "s-1")
        self.moteur.tour()
        f = self.ok("detail", entree={"fonctionnalite": "f1"})
        self.assertEqual((f["discussion"][-1]["auteur"], f["discussion"][-1]["texte"]), ("dev-1", "Voilà."))
        self.assertEqual(list(detache.dossier(self.dossier).glob("*.reponse-serveur")), [])

    def test_redemarrage_reponse_plus_active_redemandee(self):
        self.lancer_une_reponse_en_cours()
        self.actives = []
        self.moteur.tour()
        (reponse,) = self.lances()            # la réponse repart (sa session reprise), jamais oubliée
        self.assertEqual(reponse["reprendre"], "s-1")
        self.assertEqual(self.executeurs[0].demande_base["genre"], "reponse")
        self.moteur.tour()
        f = self.ok("detail", entree={"fonctionnalite": "f1"})
        self.assertEqual(f["discussion"][-1]["texte"], "Voilà.")

    def test_reponse_orpheline_arretee_au_redemarrage(self):
        """Une réponse active sur le serveur dont le moteur ne sait plus rien : arrêtée, jamais prise pour la tâche."""
        self.ok("tache", entree={"id": self.tache, "active": False})
        self.ok("tache", entree={"id": self.tache, "colonne": "fait"})
        self.actives = [self.active(self.tache, "reponse")]
        self.moteur.tour()
        self.assertEqual(self.lances(), [])
        (ex,) = self.executeurs
        self.assertEqual((ex.tache, ex.demande_base, ex.arrets), (self.tache, {"projet": self.projet.nom,
                                                                                "genre": "reponse"}, 1))

    def test_arret_garde_la_branche_rapatriee(self):
        def arrete(depart, matiere, *, agent, tache=None, lot=None, executeur=None, **k):
            self.agents.lances.append({"agent": agent["cle"], "tache": tache})
            executeur.branche = f"agent/{tache}"
            e = agents.Execution(tache, agent["cle"], lot, erreur="l'appel a échoué : " + detache.ARRET)
            e.arrete = True
            return e
        self.moteur.executer_agent = arrete
        self.partir()
        self.moteur.tour()
        bloquee = self.tache_suivie()["bloquee"]
        self.assertTrue(bloquee.startswith(regles.ARRET_DEPUIS_LE_BUREAU))
        self.assertIn(f"agent/{self.tache}", bloquee)
        self.assertEqual((len(self.lances()), self.cloud.fusions), (1, []))

    def test_arret_du_bureau_arrete_la_tache_serveur(self):
        self.moteur.synchrone = False

        def attend_l_arret(depart, matiere, *, agent, tache=None, lot=None, executeur=None, **k):
            self.agents.lances.append({"agent": agent["cle"], "tache": tache, "executeur": executeur})
            executeur.arret.wait(10)
            e = agents.Execution(tache, agent["cle"], lot, erreur="l'appel a échoué : " + detache.ARRET)
            e.arrete = True
            return e
        self.moteur.executer_agent = attend_l_arret
        self.partir()
        (ex,) = self.executeurs
        self.assertEqual(ex.arrets, 0)
        detache.demander_arret(self.dossier, self.tache)     # le bouton « Arrêter » du bureau
        self.moteur.tour()
        self.assertTrue(ex.arret.wait(10))
        for _ in range(200):          # le retour arrive dans la file (ou a déjà été lu par ce passage)
            if not self.moteur.retours.empty() or self.tache_suivie().get("bloquee"):
                break
            __import__("time").sleep(0.05)
        self.moteur.synchrone = True
        self.moteur.tour()
        self.assertEqual(ex.arrets, 1)
        self.assertEqual(self.tache_suivie()["bloquee"], regles.ARRET_DEPUIS_LE_BUREAU)
        self.assertEqual(len(self.lances()), 1)              # ni nouvel essai ni relance
        self.assertFalse((detache.dossier(self.dossier) / f"{self.tache}.arrete").exists())
        self.moteur.tour()
        self.assertEqual((ex.arrets, len(self.lances())), (1, 1))

    def test_rapport_fait_fusionne_agent_tache(self):
        vrai = self.agents.__call__

        def avec_commit(depart, matiere, *, executeur=None, tache=None, **k):
            executeur.branche = f"agent/{tache}"
            return vrai(depart, matiere, executeur=executeur, tache=tache, **k)
        self.moteur.executer_agent = avec_commit
        self.partir()
        self.moteur.tour()
        self.assertEqual(self.cloud.fusions, [(str(self.dossier), f"agent/{self.tache}", {"distante": False})])
        self.assertEqual(self.tache_suivie()["colonne"], "fait")
        self.assertTrue(self.commits)                    # le commit du rapport, avant la fusion

    def test_echeance_dite_sans_nouvel_essai(self):
        from moteur import executeur_serveur

        def echeance(depart, matiere, *, agent, tache=None, lot=None, executeur=None, **k):
            self.agents.lances.append({"agent": agent["cle"], "tache": tache})
            executeur.branche = f"agent/{tache}"
            e = agents.Execution(tache, agent["cle"], lot, erreur="l'appel a échoué : " + executeur_serveur.ECHEANCE)
            e.echeance = True
            return e
        self.moteur.executer_agent = echeance
        self.partir()
        self.moteur.tour()
        self.moteur.tour()
        self.assertEqual(len(self.lances()), 1)                     # pas de nouvel essai
        bloquee = self.tache_suivie()["bloquee"]
        self.assertIn("durée maximale", bloquee)
        self.assertIn(f"agent/{self.tache}", bloquee)               # le travail rapatrié est gardé sur sa branche
        self.assertEqual(self.cloud.fusions, [])
        f = self.ok("detail", entree={"fonctionnalite": "f1"})
        self.assertIn("durée maximale", f["discussion"][-1]["texte"])

    def test_question_puis_reponse_reprend_la_session(self):
        detache.ajouter_question(self.dossier, self.tache, "Où en es-tu ?")
        self.partir()
        self.moteur.tour()                 # la tâche finie : l'agent reprend sa session (sur le serveur) pour répondre
        premier, reponse = self.lances()
        self.assertNotIn("reprendre", premier)
        self.assertEqual(reponse["reprendre"], "s-1")
        self.assertEqual(len(self.executeurs), 2)
        self.assertIs(reponse["executeur"], self.executeurs[-1])
        self.assertEqual(self.executeurs[-1].mode, "seul")
        self.assertEqual(reponse["fiche"]["outils"], "Read, Grep, Glob")
        self.assertIn("Où en es-tu ?", reponse["depart"])
        self.assertEqual(detache.questions(self.dossier, self.tache), [])
        self.moteur.tour()
        f = self.ok("detail", entree={"fonctionnalite": "f1"})
        self.assertEqual((f["discussion"][-1]["auteur"], f["discussion"][-1]["texte"]), ("dev-1", "Voilà."))
        self.assertEqual(self.cloud.fusions, [])


class Lecteur(Base):
    """L'agent lecteur d'une question : Read, Grep, Glob seulement, sur Sonnet, dans le dossier du projet."""
    PREMIERE = {"reponse": "D'après les documents, la sauvegarde est automatique.", "sur": False, "suggestion": None}
    LUE = {"reponse": "Elle écrit `sauvegarde.json` à chaque niveau.", "sur": True, "suggestion": None,
           "fichiers_lus": ["jeu/sauvegarde.py:12"]}

    def fils(self):
        return self.ok("lancer", "questions", entree={"action": "lister"})["questions"]

    def test_lecture_avec_les_seuls_outils_de_lecture(self):
        vus = []

        def appeler(consigne, dossier, modele, **kw):
            vus.append((modele, kw.get("outils"), kw.get("dossier_travail"), kw.get("couche")))
            return appel.Reponse(json.dumps(self.LUE if kw.get("outils") else self.PREMIERE), [dict(USAGE)])
        self.moteur.appeler = appeler
        self.projet.couche = "api"     # les jugements passent par l'API ; le lecteur, lui, a besoin de claude -p
        self.demande(type="question", texte="Que fait la sauvegarde ?")
        self.moteur.tour()          # synchrone : jugée, escaladée, lue et la lecture appliquée dans le même passage
        self.assertEqual(len(vus), 2)
        self.assertEqual(vus[-1], ("sonnet", ["Read", "Grep", "Glob"], str(self.projet.dossier), "claude"))
        (fil,) = self.fils()
        dernier = fil["messages"][-1]
        self.assertEqual((fil["etat"], dernier["niveau"], dernier["fichiers_lus"]),
                         ("repondue", "code", ["jeu/sauvegarde.py:12"]))
        etapes = [u.get("etape") for u in self.suivi()["usage"] if u.get("agent") == "orchestrateur"]
        self.assertEqual(etapes, ["questions", "questions"])      # le jugement et la lecture : ligne « Questions »
        self.assertEqual(self.moteur.journal, [])

    def test_le_dossier_nomme_les_agents_par_leur_prenom_avec_leurs_taches(self):
        """« Où en est Rémi ? » : le dossier de la question porte l'équipe (prénom et tâches pas faites)."""
        self.demande(type="fonctionnalite", texte="Des écrans")
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        t = self.ok("tache", entree={"titre": "Relecture : Accueil", "fonctionnalite": "f1", "role": "relecteur",
                                     "colonne": "relecture", "etape": "flux:relecture", "agent": "rel-1"})["id"]
        recus = []

        def appeler(consigne, dossier, modele, **kw):
            recus.append(json.loads(dossier))
            return appel.Reponse(json.dumps({**self.PREMIERE, "sur": True}), [dict(USAGE)])
        self.moteur.appeler = appeler
        self.demande(type="question", texte="Où en est Rémi ?")
        self.moteur.tour()
        equipe = next(d for d in recus if "equipe" in d)["equipe"]
        (remi,) = [a for a in equipe if a["cle"] == "rel-1"]
        self.assertEqual((remi["prenom"], [x["id"] for x in remi["taches"]]), ("Rémi", [t]))

    def test_un_appel_en_echec_ne_laisse_jamais_le_fil_en_lecture(self):
        def appeler(consigne, dossier, modele, **kw):
            if kw.get("outils"):
                raise appel.ErreurAppel("délai dépassé")
            return appel.Reponse(json.dumps(self.PREMIERE), [dict(USAGE)])
        self.moteur.appeler = appeler
        self.demande(type="question", texte="Que fait la sauvegarde ?")
        self.moteur.tour()
        (fil,) = self.fils()
        self.assertEqual((fil["etat"], fil["messages"][-1]["texte"]),
                         ("repondue", "Je n'ai pas pu lire le code jusqu'au bout."))
        self.assertEqual(fil["messages"][-1]["niveau"], "documents")    # « Chercher dans le code » reste possible
        self.assertTrue(any("délai dépassé" in j for j in self.moteur.journal))

    def test_au_demarrage_une_lecture_laissee_est_dite_interrompue(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("lancer", "questions", entree={"action": "marquer", "id": "q1", "etat": "en_lecture"})
        self.moteur.tour()
        (fil,) = self.fils()
        self.assertEqual(fil["etat"], "repondue")
        self.assertIn("Lecture interrompue", fil["messages"][-1]["texte"])


if __name__ == "__main__":
    unittest.main()
