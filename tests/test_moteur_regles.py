"""La table de règles du moteur : une ligne de la conception, un test. Appels d'IA et agents simulés."""
import json
import unittest

from moteur import agents, appel, jugement, regles
from tests.orch_aide import AvecProjet

FICHE_REMI = ("Clé : rel-1\nPrénom : Rémi\nRôle : relecteur\nService : dev\nModèle : Sonnet\nLieu : local\n\n"
              "Relit.\n\n## Leçons\n")
FICHE_ZOE = FICHE_REMI.replace("rel-1", "rel-2").replace("Rémi", "Zoé")
PNG = "pieces/f1/maquette.png"

DECOUPAGE = {"elements": [{"id": "e1", "nom": "Accueil", "groupe": "écrans"},
                          {"id": "e2", "nom": "Profil", "groupe": "écrans"},
                          {"id": "e3", "nom": "Réglages", "groupe": "écrans"}],
             "prototype": "e1", "depend_de": {}, "reprendre_methode": None, "message": "Trois écrans, e1 d'abord."}
METHODE = {"document": "# Méthode\n\n1. Faire l'écran.", "briefs": {"dev": "Fais l'écran selon la méthode."},
           "controles": [{"texte": "Le titre fait 24 px.", "origine": "prototype"}]}


def usage():
    return {"modele": "claude-haiku-5-5", "entree": 1, "sortie": 1, "cache_lecture": 0, "cache_ecriture": 0}


def decision(objet):
    return jugement.Decision(objet=objet, usages=[usage()])


def verdict(element, points=()):
    return {"statut": "fait", "message": {"texte": "Relu."},
            "verdicts": [{"element": element, "conforme": not points, "points": list(points)}]}


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        (self.dossier / "fiches" / "remi.md").write_text(FICHE_REMI, encoding="utf-8")
        (self.dossier / "fiches" / "zoe.md").write_text(FICHE_ZOE, encoding="utf-8")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True)
        self.etat = regles.nouvel_etat()

    # --- Le suivi, vu par les tests.
    def suivi(self):
        return json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))

    def fonc(self, fid="f1"):
        return next(f for f in self.suivi()["fonctionnalites"] if f["id"] == fid)

    def taches(self, **filtre):
        return [t for t in self.suivi()["taches"] if all(t.get(k) == v for k, v in filtre.items())]

    def demande_en_attente(self):
        return self.ok("demandes")["demandes"]

    def demande(self, **champs):
        i = self.ok("actions", entree=champs)["id"]
        return next(d for d in self.demande_en_attente() if d["id"] == i)

    def traiter(self, **champs):
        d = self.demande(**champs)
        return d, regles.traiter_demande(self.projet, d, self.etat)

    def statut(self, i):
        return next(d for d in self.suivi()["demandes"] if d["id"] == i)

    # --- Des états de départ.
    def fonctionnalite(self, etape="cadrage", **extra):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans pour l'appli"})
        for d in self.demande_en_attente():     # la demande de création n'est pas ce qu'on teste ici
            self.ok("demande-traitee", entree={"id": d["id"]})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": etape, "agent_cadrage": "metier-1", **extra})

    def cahier_a_valider(self):
        self.fonctionnalite("cahier", cahier={"maquette": [PNG], "etapes": ["Faire les écrans"]})
        self.ok("decision", entree={"action": "poser", "portee": "f1", "genre": "valider_cahier", "texte": "ok ?"})

    def serie(self, n=3, methode=True):
        """Une fonctionnalité en série : n éléments dans la file, une méthode écrite."""
        self.fonctionnalite("serie", methode={"version": 1, "chemin": "pieces/f1/methode-v1.md"} if methode else None)
        self.ok("file", entree={"fonctionnalite": "f1", "elements": DECOUPAGE["elements"][:n]})

    # --- Piloter les actions qui restent, comme le fera la boucle.
    def piloter(self, actions, rapports=None, juges=None, limite=60):
        rapports, juges, actions = list(rapports or []), dict(juges or {}), list(actions)
        vus = []
        while actions and limite:
            limite -= 1
            action = actions.pop(0)
            vus.append(action)
            if action[0] == "agent":
                rap = rapports.pop(0) if rapports else {"statut": "fait", "message": {"texte": "Fait."}}
                e = agents.Execution(action[2][0], action[1], rapport=_lu(rap), usages=[usage()])
                actions += regles.traiter_retour(self.projet, e, self.etat)
            elif action[0] == "juger":
                _, type_, _, suite = action
                actions += regles.appliquer_jugement(self.projet, type_, decision(juges[type_]), suite, self.etat)
            else:
                regles.lancer(self.projet, action[1], action[2])
        return vus


def _lu(r):
    from moteur import rapport
    return rapport.lire("```json\n" + json.dumps(r) + "\n```")


class Demandes(Base):
    def test_fonctionnalite_lance_le_cadrage(self):
        d, actions = self.traiter(type="fonctionnalite", texte="Des écrans pour l'appli")
        self.assertEqual([a[0] for a in actions], ["agent"])
        self.assertEqual(actions[0][1], "metier-1")
        self.assertIn("Discussion", actions[0][3])
        t = self.taches(etape="cadrage")[0]
        self.assertTrue(t["active"])
        self.assertEqual((t["agent"], t["colonne"]), ("metier-1", "cadrage"))
        self.assertEqual(self.fonc()["agent_cadrage"], "metier-1")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_sans_agent_de_cadrage_le_specialiste_de_la_premiere_etape_cadre(self):
        """Un projet installé sans rôle `cadrage` ni service Métier (l'essai de référence) : le cadrage revient à
        l'agent de la première étape de production, comme le faisait l'orchestrateur actuel."""
        (self.dossier / "fiches" / "hugo.md").unlink()
        _, actions = self.traiter(type="fonctionnalite", texte="Des écrans pour l'appli")
        self.assertEqual([a[0] for a in actions], ["agent"])
        self.assertEqual(actions[0][1], "dev-1")
        t = self.taches(etape="cadrage")[0]
        self.assertEqual((t["agent"], t["colonne"], t["role"]), ("dev-1", "cadrage", "dev"))

    def test_chemins_rendus_ramenes_au_dossier_de_la_factory(self):
        """L'agent travaille dans le dossier du projet (le parent de `.factory`) ; le suivi et le bureau comptent depuis
        `.factory`. Vu en vrai : `.factory/pieces/f2/maquette.png` dans le cahier, image introuvable au bureau."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            projet = regles.Projet(Path(d) / "jeu" / ".factory" / "factory.json")
            absolu = str(Path(d) / "jeu" / ".factory" / "pieces" / "f2" / "b.png")
            r = {"statut": "fait", "message": {"texte": "Voici.", "images": [".factory/pieces/f2/a.png", absolu]},
                 "cahier": {"maquette": [".factory\\pieces\\f2\\a.png"], "etapes": ["Faire"]},
                 "fichiers": [{"chemin": ".factory/pieces/f2/x.md", "titre": "x"},
                              {"chemin": "pieces/f2/y.md", "titre": "y"},     # déjà relatif à la factory : gardé
                              {"chemin": "src/main.kt", "titre": "code"}]}    # hors de la factory : gardé tel quel
            n = regles._chemins_du_projet(projet, r)
            self.assertEqual(n["message"]["images"], ["pieces/f2/a.png", "pieces/f2/b.png"])
            self.assertEqual(n["cahier"]["maquette"], ["pieces/f2/a.png"])
            self.assertEqual([x["chemin"] for x in n["fichiers"]], ["pieces/f2/x.md", "pieces/f2/y.md", "src/main.kt"])
            self.assertEqual(r["cahier"]["maquette"], [".factory\\pieces\\f2\\a.png"])     # le rapport lu n'est pas modifié

    def test_le_cadrage_pose_une_seule_serie_de_questions(self):
        """Au passage en vrai, l'agent de cadrage reposait des questions à chaque tour et n'écrivait jamais le cahier."""
        _, actions = self.traiter(type="fonctionnalite", texte="Des écrans pour l'appli")
        matiere = actions[0][3]
        self.assertIn("Une seule série de questions", matiere)
        self.assertIn("rends le cahier corrigé", matiere)

    def test_methode_validee_sans_prototype_n_ecrit_rien(self):
        """Valider une méthode avant tout prototype (la fonctionnalité est encore en cadrage) : rien à écrire."""
        self.fonctionnalite("cadrage")
        d, actions = self.traiter(type="methode", fonctionnalite="f1", verdict="valider")
        self.assertEqual(actions, [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertIn("prototype", self.statut(d["id"])["reponse"])
        self.assertEqual(self.fonc()["etape"], "cadrage")

    def test_cahier_valider_juge_decouper(self):
        self.cahier_a_valider()
        d, actions = self.traiter(type="cahier", fonctionnalite="f1", verdict="valider")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "decouper")])
        dossier = actions[0][2]
        self.assertEqual(dossier["fonctionnalite"]["cahier"]["etapes"], ["Faire les écrans"])
        self.assertEqual([s["role"] for s in dossier["flux"]], ["dev"])
        f = self.fonc()
        self.assertEqual(f["etape"], "decoupage")
        self.assertTrue(f["cahier"]["valide_le"])
        self.assertEqual(f["decisions"], [])
        self.assertEqual(self.statut(d["id"])["statut"], "en attente")   # finie avec le jugement

    def test_decoupage_ecrit_file_et_prototype(self):
        self.cahier_a_valider()
        d, actions = self.traiter(type="cahier", fonctionnalite="f1", verdict="valider")
        suite = self.piloter(actions, juges={"decouper": DECOUPAGE})
        f = self.fonc()
        self.assertEqual([q["id"] for q in f["file"]], ["e2", "e3"])        # le prototype est pris
        self.assertEqual(f["etape"], "prototype")
        self.assertIn("Trois écrans, e1 d'abord.", [m["texte"] for m in f["discussion"]])
        self.assertEqual(self.etat["prototype"]["f1"]["id"], "e1")
        proto = self.taches(etape="prototype")
        self.assertEqual([t["element"] for t in proto], ["e1"])
        self.assertIn("agent", [a[0] for a in suite])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_cahier_corriger_rouvre_cadrage(self):
        self.cahier_a_valider()
        d, actions = self.traiter(type="cahier", fonctionnalite="f1", verdict="corriger", texte="Ajoutez un écran")
        f = self.fonc()
        self.assertEqual(f["etape"], "cadrage")
        self.assertEqual(f["decisions"], [])
        self.assertIn("Ajoutez un écran", f["discussion"][-1]["texte"])
        self.assertEqual([a[0] for a in actions], ["agent"])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_message_prototype_traduit_puis_transmet(self):
        self.fonctionnalite("prototype")
        self.etat["prototype"]["f1"] = {"id": "e1", "nom": "Accueil"}
        d, actions = self.traiter(type="message", fonctionnalite="f1", texte="Le titre est trop petit")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "traduire_retour")])
        self.assertEqual(actions[0][2]["message"]["texte"], "Le titre est trop petit")
        suite = self.piloter(actions, juges={"traduire_retour": {"validation": False, "consigne": "Agrandir le titre."}},
                             rapports=[{"statut": "fait", "message": {"texte": "Voici.", "attend": True}}])
        agent = next(a for a in suite if a[0] == "agent")
        self.assertIn("Agrandir le titre.", agent[3])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_prototype_valide_pose_valider_methode(self):
        self.fonctionnalite("prototype")
        d, actions = self.traiter(type="message", fonctionnalite="f1", texte="Parfait")
        self.piloter(actions, juges={"traduire_retour": {"validation": True, "consigne": None}})
        self.assertEqual([x["genre"] for x in self.fonc()["decisions"]], ["valider_methode"])

    def test_methode_valider_ecrit_methode_briefs_controles(self):
        self.fonctionnalite("prototype")
        self.etat["prototype"]["f1"] = {"id": "e1", "nom": "Accueil"}
        self.ok("decision", entree={"action": "poser", "portee": "f1", "genre": "valider_methode", "texte": "ok ?"})
        d, actions = self.traiter(type="methode", fonctionnalite="f1", verdict="valider")
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "ecrire_methode")])
        self.piloter(actions, juges={"ecrire_methode": METHODE})
        f = self.fonc()
        self.assertEqual((f["etape"], f["methode"]["version"]), ("serie", 1))
        self.assertEqual(f["decisions"], [])
        doc = self.dossier / f["methode"]["chemin"]
        self.assertIn("Faire l'écran", doc.read_text(encoding="utf-8"))
        self.assertIn("Fais l'écran selon la méthode.", (self.dossier / "fiches" / "briefs" / "dev.md").read_text(encoding="utf-8"))
        self.assertIn("Le titre fait 24 px.", (self.dossier / "controles.md").read_text(encoding="utf-8"))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_lecon_appliquee_sans_ia(self):
        self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Relancer les tests.",
                                 "etage_propose": "projet", "roles": ["dev"]})
        d, actions = self.traiter(type="lecon", id="dev-1:L1", verdict="valider")
        self.assertEqual(actions, [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        fiche = (self.dossier / "fiches" / "lea.md").read_text(encoding="utf-8")
        self.assertIn("[validée] dev-1:L1", fiche)

    def test_refus_de_l_outil_devient_la_reponse(self):
        d, actions = self.traiter(type="lecon", id="dev-1:L9", verdict="valider")
        self.assertEqual(actions, [])
        s = self.statut(d["id"])
        self.assertEqual(s["statut"], "traitée")
        self.assertIn("Je n'ai pas pu", s["reponse"])

    def test_type_inconnu_demande_conseil(self):
        for champs in ({"type": "bouton", "id": "exporter"}, {"type": "solution", "challenge": "c1", "texte": "x"}):
            d, actions = self.traiter(**champs)
            self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "conseil")], champs)
            self.assertIn("evenement", actions[0][2])
            self.assertNotIn("lecon", actions[0][2]["commandes"])
            self.assertNotIn("actions", actions[0][2]["commandes"])
            self.piloter(actions, juges={"conseil": {"action": "repondre", "parametres": {}, "reponse": "Noté."}})
            self.assertEqual(self.statut(d["id"])["reponse"], "Noté.")

    def test_conseil_lancer_et_agent(self):
        self.fonctionnalite("serie")
        d, actions = self.traiter(type="bouton", id="exporter")
        suite = self.piloter(actions, juges={"conseil": {"action": "transmettre_agent", "reponse": "Je m'en occupe.",
                                                           "parametres": {"consigne": "Exporte les écrans."}}})
        self.assertEqual([a[0] for a in suite], ["juger", "agent"])
        self.assertEqual(self.statut(d["id"])["reponse"], "Fait.")   # la réponse de l'agent clôt la demande

    def test_aucune_demande_sans_reponse(self):
        """Pour chaque type de demande, la demande finit traitée (tout de suite, ou à la fin de son jugement)."""
        self.cahier_a_valider()
        self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Une leçon.", "etage_propose": "projet",
                                 "roles": ["dev"]})
        tache = self.ok("tache", entree={"titre": "Écran", "role": "dev", "colonne": "dev", "active": False})["id"]
        cas = [({"type": "fonctionnalite", "texte": "Autre chose"}, {}),
               ({"type": "message", "fonctionnalite": "f1", "texte": "Bonjour"}, {}),
               ({"type": "cahier", "fonctionnalite": "f1", "verdict": "corriger", "texte": "Plus court"}, {}),
               ({"type": "lecon", "id": "dev-1:L1", "verdict": "invalider"}, {}),
               ({"type": "retour", "tache": tache, "texte": "À revoir"}, {}),
               ({"type": "deplacer", "tache": tache, "colonne": "fait"}, {}),
               ({"type": "partenaires_actualiser"}, {}),
               ({"type": "bouton", "id": "x"}, {"conseil": {"action": "rien", "parametres": {}, "reponse": ""}}),
               ({"type": "genre", "decision": "d9", "genre": "jeu"}, {})]
        for champs, juges in cas:
            with self.subTest(champs["type"]):
                d, actions = self.traiter(**champs)
                self.piloter(actions, juges=juges)
                self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.demande_en_attente(), [])


class Ecrire(Base):
    def test_ecrire_brief_document_et_refus(self):
        self.fonctionnalite("serie")
        r = self.ok("ecrire", entree={"brief": "dev", "texte": "Brief A"})
        self.ok("ecrire", entree={"brief": "dev", "texte": "Brief A"})        # déjà là : rien n'est ajouté
        self.assertEqual((self.dossier / r["chemin"]).read_text(encoding="utf-8"), "Brief A" + chr(10))
        r = self.ok("ecrire", entree={"fonctionnalite": "f1", "nom": "m.md", "texte": "Doc", "titre": "Méthode"})
        self.assertEqual((self.dossier / r["chemin"]).read_text(encoding="utf-8"), "Doc" + chr(10))
        self.assertIn(r["chemin"], [d["chemin"] for d in self.fonc()["documents"]])
        for entree in ({"fonctionnalite": "f1", "nom": "../x.md", "texte": "t"}, {"fonctionnalite": "f1", "nom": "x.py", "texte": "t"},
                       {"brief": "../x", "texte": "t"}, {"fonctionnalite": "f9", "nom": "x.md", "texte": "t"}):
            code, _ = self.outil("ecrire", entree=entree)
            self.assertEqual(code, 1, entree)


FICHE_NINA = ("Clé : sty-1\nPrénom : Nina\nRôle : style\nService : dev\nModèle : Sonnet\nLieu : local\n\n"
              "Met en forme.\n\n## Leçons\n")
FICHE_PAUL = FICHE_NINA.replace("sty-1", "liv-1").replace("Nina", "Paul").replace("style", "livreur")


def etape(i, role, nom=None):
    return {"id": i, "nom": nom or i, "role": role, "service": "dev"}


class WorkflowParFonctionnalite(Base):
    """Chaque fonctionnalité suit les étapes de son workflow (conception, section 5, point 5)."""

    def deux_workflows(self):
        (self.dossier / "fiches" / "nina.md").write_text(FICHE_NINA, encoding="utf-8")
        (self.dossier / "fiches" / "paul.md").write_text(FICHE_PAUL, encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["workflows"] = [
            {"id": "w-f1", "fonctionnalite": "f1", "genre": "badges",
             "flux": [etape("f1-dev", "dev"), etape("f1-style", "style")]},
            {"id": "w-f2", "fonctionnalite": "f2", "genre": "jeu-android",
             "flux": [etape("f2-dev", "dev"), etape("f2-livraison", "livreur", "Livraison")]}]
        self.factory.write_text(json.dumps(d), encoding="utf-8")

    def deux_fonctionnalites(self):
        self.deux_workflows()
        for texte in ("Des badges", "Un casse-briques"):
            self.ok("actions", entree={"type": "fonctionnalite", "texte": texte})
        for d in self.demande_en_attente():
            self.ok("demande-traitee", entree={"id": d["id"]})
        for fid, w, element in (("f1", "w-f1", "e1"), ("f2", "w-f2", "e2")):
            self.ok("fonctionnalite", entree={"id": fid, "etape": "serie", "workflow": w, "agent_cadrage": "metier-1",
                                              "methode": {"version": 1, "chemin": "pieces/m.md", "validee_le": "2026-11-12T10:00:00+01:00"}})
            self.ok("file", entree={"fonctionnalite": fid, "elements": [{"id": element, "nom": element.upper(),
                                                                          "groupe": "g"}]})

    def etapes(self, fid):
        return [t["etape"] for t in self.taches(fonctionnalite=fid) if str(t["etape"]).startswith("flux:")]

    def test_serie_suit_le_workflow_de_la_fonctionnalite(self):
        self.deux_fonctionnalites()
        actions = regles.avancer(self.projet, self.etat)
        premieres = {t["fonctionnalite"]: (t["role"], t["colonne"]) for t in self.taches()}
        self.assertEqual(premieres, {"f1": ("dev", "f1-dev"), "f2": ("dev", "f2-dev")})
        self.piloter(actions)
        self.assertEqual(self.etapes("f1"), ["flux:f1-dev", "flux:f1-style"])
        self.assertEqual(self.etapes("f2"), ["flux:f2-dev", "flux:f2-livraison"])
        self.assertEqual({t["role"] for t in self.taches(fonctionnalite="f1", etape="flux:f1-style")}, {"style"})
        self.assertEqual({t["role"] for t in self.taches(fonctionnalite="f2", etape="flux:f2-livraison")}, {"livreur"})

    def test_decoupage_et_methodes_lisent_le_workflow_de_la_fonctionnalite(self):
        self.deux_fonctionnalites()
        self.ok("fonctionnalite", entree={"id": "f2", "etape": "cahier", "cahier": {"maquette": [PNG], "etapes": ["x"]}})
        self.ok("decision", entree={"action": "poser", "portee": "f2", "genre": "valider_cahier", "texte": "ok ?"})
        _, actions = self.traiter(type="cahier", fonctionnalite="f2", verdict="valider")
        dossier = actions[0][2]
        self.assertEqual([s["id"] for s in dossier["flux"]], ["f2-dev", "f2-livraison"])
        self.assertEqual([m["flux"] for m in dossier["methodes_validees"]], [["f1-dev", "f1-style"]])

    def test_cadrage_par_le_role_du_workflow(self):
        self.deux_fonctionnalites()
        (self.dossier / "fiches" / "hugo.md").unlink()      # personne ne cadre : le spécialiste de la 1re étape cadre
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["workflows"][0]["flux"][0]["role"] = "style"
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(regles._role_cadrage(self.projet, "f1"), "style")
        self.assertEqual(regles._role_cadrage(self.projet, "f2"), "dev")
        self.assertEqual(regles._role_cadrage(self.projet), "dev")       # sans fonctionnalité : le workflow principal

    def test_projet_sans_workflow_ne_plante_pas(self):
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["flux"] = []
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(regles._production(self.projet, None), [])
        self.assertEqual(regles._colonne_du_role(self.projet, "dev"), "cadrage")
        self.assertEqual(regles._role_cadrage(self.projet, None), "cadrage")


class Serie(Base):
    def test_serie_deux_elements_au_plus(self):
        self.serie(3)
        regles.avancer(self.projet, self.etat)
        f = self.fonc()
        self.assertEqual(len(f["file"]), 1)                         # deux éléments pris sur trois
        flux = [t for t in self.taches() if str(t["etape"]).startswith("flux:")]
        self.assertEqual(sorted(t["element"] for t in flux), ["e1", "e2"])
        regles.avancer(self.projet, self.etat)
        self.assertEqual(len(self.fonc()["file"]), 1)               # pas de troisième tant que deux sont en cours

    def test_deux_elements_forment_un_lot(self):
        self.serie(2)
        actions = regles.avancer(self.projet, self.etat)
        self.assertEqual(len(actions), 1)
        self.assertEqual(len(actions[0][2]), 2)                     # un seul agent pour les deux tâches
        self.assertEqual({t["lot"]["id"] for t in self.taches() if t.get("lot")}, {"L1"})

    def test_prototype_jamais_parallele(self):
        self.fonctionnalite("prototype")
        self.ok("file", entree={"fonctionnalite": "f1", "elements": DECOUPAGE["elements"]})
        regles.avancer(self.projet, self.etat)
        self.assertEqual([t for t in self.taches() if str(t["etape"]).startswith("flux:")], [])
        self.assertEqual(len(self.fonc()["file"]), 3)

    def test_pause_n_avance_pas(self):
        self.serie(2)
        self.ok("actions", entree={"type": "bouton", "id": "pause"})
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(self.taches(), [])

    def test_serie_complete_jusqu_a_terminee(self):
        self.serie(2)
        rapports = [{"statut": "fait", "message": {"texte": "Écran fait."}}] * 2 + [verdict("e1"), verdict("e1"),
                                                                                    verdict("e2"), verdict("e2")]
        self.piloter(regles.avancer(self.projet, self.etat), rapports=rapports)
        self.piloter(regles.avancer(self.projet, self.etat))
        self.assertEqual(self.fonc()["etape"], "terminee")
        self.assertTrue(self.fonc()["catalogue"])

    def vers_la_relecture(self, n=1):
        """n éléments pris en série, leur dev rendu : les relectures sont créées, pas encore rendues."""
        self.serie(n)
        for action in regles.avancer(self.projet, self.etat):
            e = agents.Execution(action[2][0], action[1], rapport=_lu({"statut": "fait", "message": {"texte": "Fait."}}),
                                 usages=[usage()])
            regles.traiter_retour(self.projet, e, self.etat)    # un rapport pour tout le lot

    def test_refus_controle_juge_apres_refus(self):
        self.vers_la_relecture(1)
        rel = [t for t in self.taches(etape="relecture")]
        self.assertEqual(len(rel), 2)                               # deux relecteurs au premier tour
        actions = self.rendre_relectures(rel, [verdict("e1", ["Le titre est trop petit"]), verdict("e1")])
        self.assertEqual([(a[0], a[1]) for a in actions], [("juger", "apres_refus")])
        self.assertEqual(actions[0][2]["refus"]["points"], ["Le titre est trop petit"])
        self.assertIn("Le titre est trop petit", (self.dossier / "controles.md").read_text(encoding="utf-8"))
        suite = self.piloter(actions, juges={"apres_refus": {"suite": "corriger", "consigne": "Agrandir le titre.",
                                                             "raison": "trop petit"}})
        corr = self.taches(etape="correction")
        self.assertEqual(len(corr), 1)
        # la correction rendue, un seul relecteur revérifie (rapport vide = conforme) : l'élément est fait
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")
        self.assertEqual(self.etat["elements"]["f1/e1"]["corrections"], 1)
        self.assertEqual(len(self.taches(etape="relecture")), 3)
        self.assertTrue(self.fonc()["catalogue"])

    def sans_relecteurs(self):
        """Le projet de l'essai de référence : pas d'agent relecteur ; le flux finit par un contrôle."""
        (self.dossier / "fiches" / "remi.md").unlink()
        (self.dossier / "fiches" / "zoe.md").unlink()
        (self.dossier / "fiches" / "ctrl.md").write_text(FICHE_REMI.replace("rel-1", "ctrl-1").replace(
            "relecteur", "controleur"), encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
                     {"id": "controle", "nom": "Contrôle", "role": "controleur", "service": "dev"}]
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def test_sans_relecteur_le_controle_du_flux_conclut(self):
        self.sans_relecteurs()
        self.serie(1)
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Écran fait."}}, verdict("e1")])
        self.assertEqual(self.taches(etape="relecture"), [])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")
        self.assertIn("Rends un `verdicts`", regles._matiere(self.projet, self.etat, self.taches(etape="flux:controle")[0]))
        self.assertNotIn("verdicts", regles._matiere(self.projet, self.etat, self.taches(etape="flux:dev")[0]))

    def test_sans_relecteur_un_refus_du_controle_est_corrige_puis_recontrole(self):
        self.sans_relecteurs()
        self.serie(1)
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Écran fait."}}, verdict("e1", ["Le titre est trop petit"]),
            {"statut": "fait", "message": {"texte": "Corrigé."}}, verdict("e1")],
            juges={"apres_refus": {"suite": "corriger", "consigne": "Agrandir le titre.", "raison": "trop petit"}})
        self.assertEqual(self.taches(etape="relecture"), [])
        self.assertEqual(len(self.taches(etape="correction")), 1)
        self.assertEqual(len(self.taches(etape="flux:controle")), 2)       # le contrôle refait après la correction
        v = self.etat["elements"]["f1/e1"]
        self.assertEqual((v["phase"], v["corrections"]), ("fait", 1))

    def rendre_relectures(self, taches, rapports):
        actions = []
        for t, r in zip(taches, rapports):
            self.ok("tache", entree={"id": t["id"], "agent": "rel-1" if not actions else "rel-2", "active": True})
            self.etat["departs"][t["id"]] = {"agent": "rel-1", "taches": [t["id"]], "matiere": "", "modele": "Sonnet",
                                             "lot": None}
            e = agents.Execution(t["id"], "rel-1", rapport=_lu(r), usages=[usage()])
            actions += regles.traiter_retour(self.projet, e, self.etat)
        return actions

    def test_meme_controle_deux_elements_pose_methode_a_revoir(self):
        self.vers_la_relecture(2)
        rel = self.taches(etape="relecture")
        self.assertEqual(len(rel), 4)
        premier = [t for t in rel if t["element"] == "e1"]
        second = [t for t in rel if t["element"] == "e2"]
        a1 = self.rendre_relectures(premier, [verdict("e1", ["Le titre est trop petit"]), verdict("e1")])
        self.assertEqual([a[1] for a in a1 if a[0] == "juger"], ["apres_refus"])       # le premier refus passe par le jugement
        a2 = self.rendre_relectures(second, [verdict("e2", ["le titre  est TROP petit"]), verdict("e2")])
        self.assertEqual([a for a in a2 if a[0] == "juger"], [])    # le même contrôle sur un autre élément : sans IA
        self.assertEqual([x["genre"] for x in self.fonc()["decisions"]], ["methode_a_revoir"])
        self.assertEqual(self.etat["elements"]["f1/e2"]["phase"], "attente_methode")

    def test_seuil_methode_sans_ia(self):
        self.vers_la_relecture(1)
        v = self.etat["elements"]["f1/e1"]
        v["corrections"] = 3                                         # seuil par défaut : 3 tours déjà faits
        actions = self.rendre_relectures(self.taches(etape="relecture"),
                                         [verdict("e1", ["Encore un défaut"]), verdict("e1")])
        self.assertEqual([a for a in actions if a[0] == "juger"], [])
        self.assertEqual([x["genre"] for x in self.fonc()["decisions"]], ["methode_a_revoir"])
        self.assertIn("(élément e1)", self.fonc()["decisions"][0]["texte"])

    def test_apres_refus_methode_a_revoir_puis_garder_bloque(self):
        self.vers_la_relecture(1)
        actions = self.rendre_relectures(self.taches(etape="relecture"), [verdict("e1", ["Défaut"]), verdict("e1")])
        self.piloter(actions, juges={"apres_refus": {"suite": "methode_a_revoir", "consigne": None, "raison": "flou"}})
        self.assertEqual([x["genre"] for x in self.fonc()["decisions"]], ["methode_a_revoir"])
        d, _ = self.traiter(type="methode", fonctionnalite="f1", verdict="garder")
        self.assertEqual(self.fonc()["decisions"], [])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "bloque")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")


class Arrets(Base):
    def depart_cadrage(self):
        d, actions = self.traiter(type="fonctionnalite", texte="Des écrans pour l'appli")
        return actions

    def test_accord_requis_pose_une_decision(self):
        actions = self.depart_cadrage()
        accord = {"statut": "accord_requis", "message": {"texte": "Il me faut un accord."},
                  "fichiers": [{"chemin": "pieces/f1/x.png", "titre": "Ne doit pas être inscrit"}],
                  "accord": {"quoi": "Générer 5 images", "partenaire": "studio", "cout": "2 $"}}
        suite = self.piloter(actions, rapports=[accord])
        self.assertEqual(suite[-1][0], "agent")
        f = self.fonc()
        derniere = f["discussion"][-1]
        self.assertTrue(derniere["attend"])
        self.assertEqual(derniere["questions"][0]["choix"], [regles.ACCEPTE, regles.REFUSE])
        self.assertEqual(f.get("documents") or [], [])
        t = self.taches(etape="cadrage")[0]
        self.assertFalse(t["active"])
        self.assertIn("f1", self.etat["accords"])
        # Sur « J'accepte », l'agent reprend la même tâche avec l'accord dans son départ.
        d, relance = self.traiter(type="message", fonctionnalite="f1", texte="Générer 5 images ? → " + regles.ACCEPTE)
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("accord pour : Générer 5 images", relance[0][3])
        self.assertEqual(relance[0][2], [t["id"]])

    def test_outil_refuse_pose_une_question(self):
        actions = self.depart_cadrage()
        refus = {"statut": "outil_refuse", "outil": "WebSearch", "message": {"texte": "Je ne peux pas chercher."}}
        self.piloter(actions, rapports=[refus])
        derniere = self.fonc()["discussion"][-1]
        self.assertTrue(derniere["attend"])
        self.assertIn("WebSearch", derniere["texte"])
        self.assertEqual(derniere["questions"][0]["choix"], [regles.FAIT, regles.ECARTE])
        d, relance = self.traiter(type="message", fonctionnalite="f1", texte=regles.ECARTE)
        self.assertEqual(relance, [])
        self.assertTrue(self.taches(etape="cadrage")[0]["bloquee"])

    def test_agent_sans_rapport_relance_une_fois_puis_bloque(self):
        actions = self.depart_cadrage()
        tid = actions[0][2][0]
        e = agents.Execution(tid, "metier-1", usages=[usage()], erreur="rapport illisible")
        again = regles.traiter_retour(self.projet, e, self.etat)
        self.assertEqual([a[0] for a in again], ["agent"])
        self.assertEqual(regles.traiter_retour(self.projet, e, self.etat), [])
        t = self.taches(id=tid)[0]
        self.assertIn("deux essais", t["bloquee"])

    def test_cadrage_rend_cahier_et_nom(self):
        actions = self.depart_cadrage()
        r = {"statut": "fait", "nom": "Écrans de l'appli", "message": {"texte": "Voici le cahier.", "attend": True},
             "cahier": {"maquette": [PNG], "etapes": ["Faire les écrans"]}}
        self.piloter(actions, rapports=[r])
        f = self.fonc()
        self.assertEqual((f["nom"], f["etape"]), ("Écrans de l'appli", "cahier"))
        self.assertEqual([d["genre"] for d in f["decisions"]], ["valider_cahier"])
        self.assertEqual(self.taches(etape="cadrage")[0]["colonne"], "fait")

    def test_agent_libre_manquant_attend(self):
        (self.dossier / "fiches" / "hugo.md").unlink()     # le cadrage revient à dev-1, qui est occupé
        occupe = self.ok("tache", entree={"titre": "Autre chose", "role": "dev", "colonne": "dev", "agent": "dev-1",
                                          "active": True})["id"]
        d, actions = self.traiter(type="fonctionnalite", texte="Des écrans")
        self.assertEqual(actions, [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual([t["id"] for t in self.taches()], [occupe])


if __name__ == "__main__":
    unittest.main()
