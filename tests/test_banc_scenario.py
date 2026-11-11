"""Le scénario du banc et son rejoueur. Le scénario synthétique ne contient rien d'un essai réel ; aucun appel réel."""
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path

from banc import jouer, rejoueur, scenario
from moteur import appel, jugement

SYNTHETIQUE = Path(__file__).resolve().parent.parent / "banc" / "exemples" / "synthetique.json"

DECOUPAGE = {"elements": [{"id": "e1", "nom": "Accueil", "groupe": "écrans"},
                          {"id": "e2", "nom": "Profil", "groupe": "écrans"}],
             "prototype": "e1", "depend_de": {}, "reprendre_methode": None, "message": "Deux écrans, l'accueil d'abord."}
METHODE = {"document": "# Méthode\n\n1. Faire l'écran comme la maquette.", "briefs": {"dev": "Fais l'écran selon la méthode."},
           "controles": [{"texte": "Le titre fait au moins 24 px.", "origine": "prototype"}]}
APRES_REFUS = {"suite": "corriger", "consigne": "Agrandir le titre du profil.", "raison": "Titre trop petit."}
USAGE_JUGEMENT = {"modele": "claude-haiku-5-5", "entree": 1500, "sortie": 200, "cache_lecture": 0, "cache_ecriture": 0}


class Jugements:
    """Un faux `appeler` de jugement : la réponse du type d'appel reconnu à sa consigne."""

    def __init__(self, **reponses):
        self.reponses = {"decouper": DECOUPAGE, "ecrire_methode": METHODE, "apres_refus": APRES_REFUS, **reponses}
        self.types = []

    def __call__(self, consigne, dossier, modele, **options):
        type_ = next(t for t in jugement.TYPES if jugement.consigne(t) == consigne)
        self.types.append(type_)
        return appel.Reponse(json.dumps(self.reponses[type_], ensure_ascii=False), [dict(USAGE_JUGEMENT)])


def donnees():
    return json.loads(SYNTHETIQUE.read_text(encoding="utf-8"))


class Format(unittest.TestCase):
    def test_synthetique_charge(self):
        s = scenario.charger(SYNTHETIQUE)
        self.assertEqual(len(s.gestes), 5)
        self.assertEqual(len(s.rapports), 9)
        self.assertEqual(len(s.attendu), 5)
        self.assertEqual(s.restants, 5)
        self.assertEqual({r["etape"] for r in s.rapports},
                         {"cadrage", "prototype", "flux:dev", "relecture", "correction"})

    def test_synthetique_sans_rien_d_un_essai_reel(self):
        # un projet fabriqué : aucun chemin de machine, aucun nom propre, aucune adresse
        texte = SYNTHETIQUE.read_text(encoding="utf-8")
        for motif in ("C:\\\\", "C:/", "/home/", "/Users/", "http", "@", "Downloads"):
            self.assertNotIn(motif, texte, motif)

    def test_format_refuse(self):
        d = donnees()
        for nom, abime in (("version", lambda x: x.update(version=2)),
                           ("geste", lambda x: x["gestes"][0].update(apres="un jour")),
                           ("type de demande", lambda x: x["gestes"][0]["demande"].pop("type")),
                           ("étape", lambda x: x["rapports"][0].update(etape="inconnue")),
                           ("rang", lambda x: x["rapports"][0].update(rang=-1)),
                           ("usage", lambda x: x["rapports"][0]["usage"].pop("entree")),
                           ("fichier", lambda x: x["rapports"][1]["fichiers"][0].pop("contenu_base64")),
                           ("attendu", lambda x: x.update(attendu="tout")),
                           ("fiches", lambda x: x["projet"].update(fiches={}))):
            x = copy.deepcopy(d)
            abime(x)
            with self.subTest(nom), self.assertRaises(scenario.ScenarioInvalide):
                scenario.Scenario(x)
        with self.assertRaises(scenario.ScenarioInvalide):
            scenario.charger(SYNTHETIQUE.with_name("absent.json"))

    def test_prochain_geste_attend_le_moteur(self):
        s = scenario.charger(SYNTHETIQUE)
        occupe = {"taches": [{"id": "t1", "active": True, "colonne": "dev"}]}
        attente = {"taches": [{"id": "t2", "active": False, "colonne": "dev", "debut": None, "lot": None}]}
        calme = {"taches": [{"id": "t3", "active": False, "colonne": "fait"},
                            {"id": "t4", "active": False, "colonne": "cadrage", "debut": "2026-11-11T10:00:00+01:00"},
                            {"id": "t5", "active": False, "colonne": "dev", "bloquee": "x"}]}
        self.assertEqual(s.prochain_geste(occupe)["type"], "fonctionnalite")      # « immediat » : sans attendre
        for etat in (occupe, attente):
            self.assertIsNone(s.prochain_geste(etat))                              # le moteur travaille encore
        self.assertEqual(s.prochain_geste(calme)["type"], "message")
        self.assertEqual(s.restants, 3)
        etat_vide = {"taches": []}
        self.assertEqual([s.prochain_geste(etat_vide)["type"] for _ in range(3)], ["cahier", "cahier", "methode"])
        self.assertIsNone(s.prochain_geste(etat_vide))

    def test_materialiser_ecrit_une_factory_lisible(self):
        from orchestrateur import factory, fiches
        s = scenario.charger(SYNTHETIQUE)
        with tempfile.TemporaryDirectory() as d:
            chemin = s.materialiser(d)
            f = factory.lire(chemin)
            self.assertEqual([x["id"] for x in f["flux"]], ["dev", "relecture"])
            self.assertEqual(sorted(x["cle"] for x in fiches.lire_toutes(f["fiches"])),
                             ["dev-1", "metier-1", "rel-1", "rel-2"])
            self.assertTrue((Path(d) / "fiches" / "briefs" / "dev.md").is_file())


class Rejoue(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)
        self.scenario = scenario.charger(SYNTHETIQUE)
        self.taches = {}
        self.rejoueur = rejoueur.Rejoueur(self.scenario, lambda t: self.taches[t])

    def jouer(self, tache, etape, role, element=None):
        self.taches[tache] = {"etape": etape, "role": role, "element": element}
        return self.rejoueur("départ", "matière", agent={"cle": "a-1", "role": role}, modele="sonnet",
                             dossier_projet=str(self.dossier), tache=tache)

    def test_rejoueur_rend_le_rapport_par_rang(self):
        e = self.jouer("t1", "prototype", "dev", "e1")                     # rang 0 : le prototype
        self.assertEqual(e.rapport["methode_prete"], True)
        self.assertIsNone(e.erreur)
        self.assertEqual(e.usage["entree"], 2500)
        e = self.jouer("t2", "flux:dev", "dev", "e2")                      # rang 1 : le premier élément de la série
        self.assertEqual(e.rapport["lecons"][0]["etage_propose"], "projet")
        self.assertEqual(e.rapport["lignes"], 42)
        self.assertEqual([f["chemin"] for f in e.rapport["fichiers"]], ["pieces/f1/profil.png"])
        # les fichiers sont écrits dans le projet du banc
        self.assertTrue((self.dossier / "pieces" / "f1" / "profil.png").read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(self.rejoueur.ecarts, [])

    def test_rapports_de_meme_cle_dans_l_ordre(self):
        premier = self.jouer("t1", "relecture", "relecteur", "e1")
        self.jouer("t0", "prototype", "dev", "e1")
        self.jouer("t2", "flux:dev", "dev", "e2")
        a = self.jouer("t3", "relecture", "relecteur", "e2")
        b = self.jouer("t4", "relecture", "relecteur", "e2")
        c = self.jouer("t5", "relecture", "relecteur", "e2")
        self.assertEqual([x.rapport["verdicts"][0]["conforme"] for x in (a, b, c)], [False, True, True])
        self.assertTrue(premier.rapport["message"]["texte"].startswith("Rien à rejouer"))   # e1 est le rang 0 : aucun

    def test_verdicts_rendus_aux_elements_du_moteur(self):
        """Le découpage du moteur nomme ses éléments à sa façon : un verdict rejoué désigne l'élément du même rang."""
        rel = next(r for r in self.scenario.rapports if r["etape"] == "relecture" and r["rang"] == 1)
        rel["rapport"]["verdicts"] = [{"element": "badge-essai", "rang": 1, "conforme": False, "points": ["Décalé"]},
                                      {"element": "autre-essai", "rang": 4, "conforme": True, "points": []}]
        self.jouer("t0", "prototype", "dev", "e1")
        self.jouer("t2", "flux:dev", "dev", "e2")
        e = self.jouer("t3", "relecture", "relecteur", "e2")
        self.assertEqual([(v["element"], v["conforme"]) for v in e.rapport["verdicts"]],
                         [("e2", False), ("autre-essai", True)])        # rang 4 : pas encore vu par le moteur
        self.assertNotIn("rang", e.rapport["verdicts"][0])

    def test_un_lot_donne_leur_rang_a_tous_ses_elements(self):
        self.jouer("t0", "prototype", "dev", "e1")
        self.taches["t2"] = {"etape": "flux:dev", "role": "dev", "element": "e2", "elements": ["e2", "e3"]}
        self.rejoueur("départ", "matière", agent={"cle": "a-1", "role": "dev"}, modele="sonnet",
                      dossier_projet=str(self.dossier), tache="t2", lot="L1")
        self.assertEqual(self.rejoueur.rangs, {"e1": 0, "e2": 1, "e3": 2})

    def test_cadrage_toujours_au_rang_zero(self):
        for k in range(3):
            e = self.jouer(f"t{k}", "cadrage", "cadrage")
            self.assertIn("message", e.rapport)
        self.assertEqual(self.rejoueur.ecarts, [])

    def test_rejoueur_note_un_ecart(self):
        e = self.jouer("t9", "flux:dev", "dev", "e7")      # le rang 0 n'a pas de dev en série : un écart, pas un échec
        self.assertIsNone(e.erreur)
        self.assertEqual(e.rapport["statut"], "fait")
        self.assertEqual(e.usages, [])
        self.assertIn("Rien à rejouer", e.rapport["message"]["texte"])
        self.assertEqual(len(self.rejoueur.ecarts), 1)
        self.assertIn("flux:dev / dev / rang 0", self.rejoueur.ecarts[0])
        self.jouer("t1", "cadrage", "cadrage")
        for k in range(3):
            self.jouer(f"c{k}", "cadrage", "cadrage")
        self.assertEqual(len(self.rejoueur.ecarts), 2)                    # un quatrième tour de cadrage : encore un écart

    def test_fichier_hors_du_projet_refuse(self):
        d = donnees()
        d["rapports"][3]["fichiers"][0]["chemin"] = "../dehors.png"
        r = rejoueur.Rejoueur(scenario.Scenario(d), lambda t: {"etape": "prototype", "role": "dev", "element": "e1"})
        r("d", "m", agent={"cle": "a", "role": "dev"}, modele="sonnet", dossier_projet=str(self.dossier), tache="t1")
        self.assertFalse((self.dossier.parent / "dehors.png").exists())
        self.assertTrue(any("hors du projet" in e for e in r.ecarts))
        r2 = rejoueur.Rejoueur(scenario.Scenario(d), lambda t: {"etape": "cadrage", "role": "cadrage", "element": None})
        self.assertEqual(r2.ecarts, [])


class Passage(unittest.TestCase):
    def test_vrais_agents_a_la_place_du_rejoueur(self):
        from moteur import agents, rapport as rap
        s, vus = scenario.charger(SYNTHETIQUE), []

        def agent(depart, matiere, *, agent, modele, dossier_projet, tache=None, lot=None, **plus):
            vus.append((tache, dossier_projet))
            r = rap.lire('```json\n{"statut": "fait", "message": {"texte": "Fait par un vrai agent."}}\n```')
            return agents.Execution(tache, agent["cle"], lot, rapport=r, modele=modele, usages=[
                {"modele": "claude-sonnet-5-5", "entree": 5, "sortie": 5, "cache_lecture": 0, "cache_ecriture": 0}])

        with tempfile.TemporaryDirectory() as d:
            r = jouer.jouer_moteur(s, d, Jugements(), executer_agent=agent, max_tours=40)
            self.assertTrue(vus and all(p == str(Path(d)) for _, p in vus))      # les agents travaillent dans le projet
            self.assertEqual(r["ecarts"], [])
            self.assertTrue(r["usages_production"])
            textes = [m["texte"] for f in r["suivi"]["fonctionnalites"] for m in f["discussion"]]
            self.assertIn("Fait par un vrai agent.", textes)
            self.assertFalse(any(t.startswith("Rien à rejouer") for t in textes))

    def test_le_banc_ne_valide_jamais_une_lecon(self):
        """Valider une leçon de genre ou de skill écrirait dans la skill (ce dépôt) : le geste est sauté."""
        s = scenario.charger(SYNTHETIQUE)
        s.gestes.append({"apres": "attente_utilisateur", "demande": {"type": "lecon", "verdict": "valider",
                                                                       "id": "dev-1:L1"}})
        with tempfile.TemporaryDirectory() as d:
            r = jouer.jouer_moteur(s, d, Jugements())
            self.assertFalse(any(x["type"] == "lecon" for x in r["suivi"]["demandes"]))
            self.assertEqual(r["gestes_restants"], 0)

    def test_un_passage_en_vrai_demande_un_dossier_vide(self):
        from banc import __main__ as banc_main
        from banc.construire import ErreurBanc
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(banc_main.projet_vide(Path(d), "projet-moteur").is_dir())
            (Path(d) / "projet-moteur" / "x.txt").write_text("déjà joué", encoding="utf-8")
            with self.assertRaises(ErreurBanc):
                banc_main.projet_vide(Path(d), "projet-moteur")

    def test_moteur_va_au_bout_du_synthetique(self):
        s = scenario.charger(SYNTHETIQUE)
        jugements = Jugements()
        with tempfile.TemporaryDirectory() as d:
            r = jouer.jouer_moteur(s, d, jugements)
            suivi = r["suivi"]
            f = next(x for x in suivi["fonctionnalites"] if x["id"] == "f1")
            self.assertEqual(f["etape"], "terminee")
            self.assertEqual(r["demandes_en_attente"], [])
            self.assertEqual(r["gestes_restants"], 0)
            self.assertEqual(r["ecarts"], [])
            self.assertEqual([x["statut"] for x in suivi["demandes"]], ["traitée"] * 5)
            self.assertEqual(f["nom"], "Application de démonstration")
            self.assertEqual(f["methode"]["version"], 1)
            self.assertTrue(f["cahier"]["valide_le"])
            self.assertEqual(f["decisions"], [])
            self.assertEqual(len(f["file"]), 0)
            # le jugement : un découpage, une méthode, un refus ; rien d'autre (aucun appel de conseil)
            self.assertEqual(sorted(jugements.types), ["apres_refus", "decouper", "ecrire_methode"])
            self.assertEqual(len(r["usages_jugement"]), 3)
            self.assertTrue(all(u["agent"] == "orchestrateur" for u in r["usages_jugement"]))
            # la production est celle de l'essai, rejouée
            self.assertGreaterEqual(len(r["usages_production"]), 9)
            self.assertTrue(any(l.get("texte") for l in suivi["lecons"]) and len(suivi["lecons"]) == 1)
            controles = (Path(d) / "controles.md").read_text(encoding="utf-8")
            self.assertIn("Le titre du profil est trop petit", controles)
            self.assertIn("Le titre fait au moins 24 px.", controles)
            self.assertTrue((Path(d) / "pieces" / "f1" / "methode-v1.md").is_file())
            self.assertTrue(all(t["colonne"] == "fait" for t in suivi["taches"]))
            self.assertEqual(s.restants, 0)


if __name__ == "__main__":
    unittest.main()
