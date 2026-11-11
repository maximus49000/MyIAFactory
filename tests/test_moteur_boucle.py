"""La boucle du moteur : un passage, plusieurs projets, la reprise. Aucun appel réel à `claude`, aucun push."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from moteur import agents, appel, boucle, jugement, regles
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
                            "matiere": matiere, "dossier": dossier_projet})
        from moteur import rapport
        return agents.Execution(tache, agent["cle"], lot, rapport=rapport.lire(self.rapport) if self.rapport else None,
                                usages=[dict(USAGE, modele="claude-opus-5-5")], erreur=None if self.rapport else "x")


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

    def test_erreur_d_un_projet_n_arrete_pas_la_boucle(self):
        with mock.patch.object(regles, "avancer", side_effect=RuntimeError("boum")):
            self.moteur.tour()
        self.assertTrue(any("boum" in ligne for ligne in self.moteur.journal))


if __name__ == "__main__":
    unittest.main()
