"""La table de règles du moteur : une ligne de la conception, un test. Appels d'IA et agents simulés."""
import json
import unittest

from moteur import agents, appel, jugement, regles
from orchestrateur import factory as fa
from orchestrateur import workflows as wf
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


ACCES = {"url": "http://127.0.0.1:5173/", "description": "Le jeu qui tourne"}   # de quoi vérifier à la validation


DIT = {"doit_marcher": "L'apk s'installe, s'ouvre en portrait et affiche le menu.",
       "pas_encore": "Le jeu ne répond pas encore : combat, carte et magasin viennent ensuite.",
       "conclusion": "Validez si l'application s'ouvre correctement, même si rien n'est encore jouable."}


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

    def cadrer(self, **champs):
        """Une demande de fonctionnalité dont le genre n'a pas pu être classé : le parcours continue par le cadrage
        (l'issue de secours de la conception, section 8). Rend la demande et les actions du cadrage."""
        d, actions = self.traiter(type="fonctionnalite", **champs)
        (_, type_, _, suite), = actions
        self.assertEqual(type_, "classer_genre")
        return d, regles.appliquer_jugement(self.projet, "classer_genre", jugement.Decision(question="Raté."), suite,
                                            self.etat)

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
        d, actions = self.cadrer(texte="Des écrans pour l'appli")
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
        _, actions = self.cadrer(texte="Des écrans pour l'appli")
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

    def test_la_legende_suit_son_image(self):
        import tempfile
        from pathlib import Path
        from orchestrateur import outil
        png = outil.SIGNATURES[".png"][0] + b"corps"
        with tempfile.TemporaryDirectory() as d:
            jeu = Path(d) / "jeu"
            factory = jeu / ".factory"
            (factory / "pieces" / "f1").mkdir(parents=True)
            (jeu / "assets").mkdir()
            (factory / "factory.json").write_text(json.dumps(
                {"skill": str(Path(__file__).resolve().parent.parent), "genre": None, "mots_interdits": [],
                 "services": [{"id": "dev", "nom": "Dev"}], "reglages": "reglages.json",
                 "flux": [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}]}), encoding="utf-8")
            (factory / "reglages.json").write_text(json.dumps({"images": {"racines": ["pieces"]}}), encoding="utf-8")
            (jeu / "assets" / "a.png").write_bytes(png)
            projet = regles.Projet(factory / "factory.json")
            r = {"statut": "fait",
                 "message": {"texte": "v", "images": [{"chemin": "assets/a.png", "legende": "L'accueil"}, "pieces/f1/z.png"]},
                 "cahier": {"maquette": [{"chemin": ".factory\\pieces\\f1\\b.png", "legende": "Le combat"}, "assets/a.png"],
                            "etapes": ["x"]}}
            n = regles._chemins_du_projet(projet, r, "f1")
            self.assertEqual(n["message"]["images"], [{"chemin": "pieces/f1/a.png", "legende": "L'accueil"},
                                                      "pieces/f1/z.png"])
            self.assertEqual(n["cahier"]["maquette"], [{"chemin": "pieces/f1/b.png", "legende": "Le combat"},
                                                       "pieces/f1/a.png"])
            self.assertEqual(r["message"]["images"][0], {"chemin": "assets/a.png", "legende": "L'accueil"})

    def test_images_hors_des_racines_copiees_sous_les_pieces_de_la_fonctionnalite(self):
        """Vu en vrai : maquettes écrites sous `assets/maquette/` du projet, que le bureau ne sert pas."""
        import tempfile
        from pathlib import Path
        from orchestrateur import outil
        png = outil.SIGNATURES[".png"][0] + b"corps"
        with tempfile.TemporaryDirectory() as d:
            jeu = Path(d) / "jeu"
            factory = jeu / ".factory"
            (factory / "pieces" / "f1").mkdir(parents=True)
            (jeu / "assets").mkdir()
            (factory / "factory.json").write_text(json.dumps(
                {"skill": str(Path(__file__).resolve().parent.parent), "genre": None, "mots_interdits": [],
                 "services": [{"id": "dev", "nom": "Dev"}], "reglages": "reglages.json",
                 "flux": [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}]}), encoding="utf-8")
            (factory / "reglages.json").write_text(json.dumps({"images": {"racines": ["pieces"]}}), encoding="utf-8")
            (jeu / "assets" / "a.png").write_bytes(png)
            (jeu / "assets" / "b.png").write_bytes(png + b"2")
            (jeu / "assets" / "faux.png").write_bytes(b"pas une image")
            (jeu / "assets" / "note.txt").write_bytes(png)
            (factory / "pieces" / "f1" / "a.png").write_bytes(b"deja la")      # un nom déjà pris : jamais écrasé
            (factory / "pieces" / "f1" / "deja.png").write_bytes(png)
            (Path(d) / "dehors.png").write_bytes(png)
            projet = regles.Projet(factory / "factory.json")
            r = {"statut": "fait", "message": {"texte": "v", "images": ["assets/a.png", "pieces/f1/deja.png"]},
                 "cahier": {"maquette": ["assets\\b.png", "assets/faux.png", "assets/absente.png", "assets/note.txt",
                                         str(Path(d) / "dehors.png"), "../dehors.png"], "etapes": ["x"]}}
            n = regles._chemins_du_projet(projet, r, "f1")
            self.assertEqual(n["message"]["images"], ["pieces/f1/a-2.png", "pieces/f1/deja.png"])
            self.assertEqual(n["cahier"]["maquette"], ["pieces/f1/b.png", "assets/faux.png", "assets/absente.png",
                                                       "assets/note.txt", str(Path(d) / "dehors.png"), "../dehors.png"])
            self.assertEqual((factory / "pieces" / "f1" / "b.png").read_bytes(), png + b"2")
            self.assertEqual((factory / "pieces" / "f1" / "a.png").read_bytes(), b"deja la")
            self.assertTrue((jeu / "assets" / "a.png").is_file())              # copiée, pas déplacée
            self.assertEqual(sorted(p.name for p in (factory / "pieces" / "f1").iterdir()),
                             ["a-2.png", "a.png", "b.png", "deja.png"])
            n = regles._chemins_du_projet(projet, {**r, "fichiers": [
                {"chemin": "assets/b.png", "titre": "B", "livrable": True}, {"chemin": "assets/note.txt", "titre": "N"}]}, "f1")
            self.assertEqual([x["chemin"] for x in n["fichiers"]], ["pieces/f1/b.png", "assets/note.txt"])   # les fichiers aussi
            self.assertTrue(n["fichiers"][0]["livrable"])
            again = regles._chemins_du_projet(projet, r, "f1")                 # la même image n'est pas doublée
            self.assertEqual(again["message"]["images"][0], "pieces/f1/a-2.png")
            self.assertEqual(regles._dossier_des_pieces(projet), ".factory/pieces")

    def test_le_cadrage_dit_ou_ecrire_les_maquettes(self):
        _, actions = self.cadrer(texte="Des écrans pour l'appli")
        self.assertIn("pieces/f1/", actions[0][3])

    def test_le_cadrage_demande_une_legende_par_maquette(self):
        _, actions = self.cadrer(texte="Des écrans pour l'appli")
        self.assertIn('"legende"', actions[0][3])
        self.assertIn("légende", actions[0][3])

    def test_le_cadrage_pose_une_seule_serie_de_questions(self):
        """Au passage en vrai, l'agent de cadrage reposait des questions à chaque tour et n'écrivait jamais le cahier."""
        _, actions = self.cadrer(texte="Des écrans pour l'appli")
        matiere = actions[0][3]
        self.assertIn("Une seule série de questions", matiere)
        self.assertIn("rends le cahier corrigé", matiere)

    def test_le_cadrage_donne_la_forme_exacte_d_une_question(self):
        _, actions = self.cadrer(texte="Des écrans pour l'appli")
        self.assertIn('{"texte": "…", "choix": ["…", "…"], "multiple": false}', actions[0][3])

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

    def test_les_taches_se_repartissent_sur_les_places_libres_avant_les_lots(self):
        """Essai réel : cinq tâches regroupées pour un seul agent local pendant que trois agents cloud restaient libres."""
        lots = [{"ids": ["t1", "t2", "t3", "t4", "t5"], "modele": "Sonnet", "lot": "L1"}]
        r = regles._repartir_sur_les_places(lots, 4)
        self.assertEqual(len(r), 4)
        self.assertEqual(sorted(i for x in r for i in x["ids"]), ["t1", "t2", "t3", "t4", "t5"])
        self.assertEqual(regles._repartir_sur_les_places(lots, 1), lots)            # une seule place : le lot reste
        self.assertEqual(len(regles._repartir_sur_les_places(lots, 9)), 5)           # jamais plus de lots que de tâches
        seule = regles._repartir_sur_les_places([{"ids": ["a", "b"], "modele": "Haiku", "lot": "L2"}], 2)
        self.assertTrue(all(x["lot"] is None for x in seule))                       # une tâche seule n'est pas un lot

    def test_un_lot_que_plus_personne_ne_porte_est_defait(self):
        """Essai réel : le moteur relancé avait perdu la suite d'un lot ; ses tâches (rangs 2 à 5) ne partaient jamais
        seules et attendaient avec trois agents libres. Un lot sans tâche active ni en partance est défait."""
        self.cahier_a_valider()
        ids = [self.ok("tache", entree={"titre": f"Équilibrage {k}", "role": "dev", "colonne": "dev", "active": False})["id"]
               for k in range(3)]
        for rang, i in enumerate(ids, 1):
            self.ok("tache", entree={"id": i, "lot": {"id": "L9", "rang": rang}})
        self.ok("tache", entree={"id": ids[0], "colonne": "fait"})
        self.assertEqual(regles._liberer_les_lots_orphelins(self.projet, self.etat, regles._etat(self.projet)),
                         ids[1:])
        for i in ids[1:]:
            t = self.taches(id=i)[0]
            self.assertIsNone(t.get("lot"))
            self.assertIn("Sortie de son lot", t["journal"][-1]["texte"])

    def test_un_lot_en_cours_n_est_jamais_defait(self):
        self.cahier_a_valider()
        ids = [self.ok("tache", entree={"titre": f"Écran {k}", "role": "dev", "colonne": "dev", "active": False})["id"]
               for k in range(2)]
        for rang, i in enumerate(ids, 1):
            self.ok("tache", entree={"id": i, "lot": {"id": "L8", "rang": rang}})
        self.ok("tache", entree={"id": ids[0], "active": True})       # l'agent fait le lot d'une traite
        self.assertEqual(regles._liberer_les_lots_orphelins(self.projet, self.etat, regles._etat(self.projet)), [])
        self.ok("tache", entree={"id": ids[0], "active": False})
        self.etat.setdefault("departs", {})[ids[0]] = {"taches": ids}  # en partance (le moteur le lance)
        self.assertEqual(regles._liberer_les_lots_orphelins(self.projet, self.etat, regles._etat(self.projet)), [])

    def test_une_question_au_chef_recoit_sa_reponse(self):
        """Un retour sur la tâche « Orchestration » est une question au Chef : il répond d'après l'état de tout le
        projet, et la réponse reste sur la demande (le bureau la montre sous la question)."""
        self.cahier_a_valider()
        self.ok("tache", entree={"titre": "Écran", "role": "dev", "colonne": "dev", "active": True})
        d, actions = self.traiter(type="retour", tache="orchestration", texte="Où en est l'atelier ?")
        ((quoi, genre, dossier, _),) = actions
        self.assertEqual((quoi, genre), ("juger", "conseil"))
        self.assertEqual(dossier["evenement"]["type"], "question_chef")
        self.assertIn("Écran", [t["titre"] for t in dossier["etat"]["taches"]])
        self.piloter(actions, juges={"conseil": {"action": "repondre", "parametres": {},
                                                 "reponse": "Un agent fait l'écran, rien n'est bloqué."}})
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.statut(d["id"])["reponse"], "Un agent fait l'écran, rien n'est bloqué.")

    def test_aucune_demande_sans_reponse(self):
        """Pour chaque type de demande, la demande finit traitée (tout de suite, ou à la fin de son jugement)."""
        self.cahier_a_valider()
        self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Une leçon.", "etage_propose": "projet",
                                 "roles": ["dev"]})
        tache = self.ok("tache", entree={"titre": "Écran", "role": "dev", "colonne": "dev", "active": False})["id"]
        cas = [({"type": "fonctionnalite", "texte": "Autre chose"},
                {"classer_genre": {"verdict": "autre", "genre": None, "raison": "Des écrans.",
                                   "nouveau": {"id": "ecrans", "description": "Des écrans d'application."}}}),
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

    def casse_briques(self, flux=None):
        """Sans relecteur : programmation, tests et essai par le service Qualité, livraison de l'apk."""
        (self.dossier / "fiches" / "remi.md").unlink()
        (self.dossier / "fiches" / "zoe.md").unlink()
        for cle, role, service in (("test-1", "testeur", "qualite"), ("liv-1", "livreur", "livraison")):
            (self.dossier / "fiches" / f"{cle}.md").write_text(
                FICHE_REMI.replace("rel-1", cle).replace("relecteur", role).replace("Service : dev", f"Service : {service}"),
                encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["services"] += [{"id": "qualite", "nom": "Qualité"}, {"id": "livraison", "nom": "Livraison"}]
        f["flux"] = flux or [{"id": "dev", "nom": "Programmation", "role": "dev", "service": "dev"},
                             {"id": "essai", "nom": "Tests et essai du jeu", "role": "testeur", "service": "qualite"},
                             {"id": "livraison", "nom": "Livraison de l'apk signé", "role": "livreur", "service": "livraison"}]
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def test_sans_relecteur_la_qualite_juge_et_la_livraison_suit_un_verdict_favorable(self):
        self.casse_briques()
        self.serie(1)
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}}, verdict("e1"),
            {"statut": "fait", "message": {"texte": "Livré."}}])
        v = self.etat["elements"]["f1/e1"]
        self.assertEqual((v["phase"], v["corrections"]), ("fait", 0))
        self.assertEqual([len(self.taches(etape=f"flux:{e}")) for e in ("dev", "essai", "livraison")], [1, 1, 1])
        self.assertIn("Rends un `verdicts`", regles._matiere(self.projet, self.etat, self.taches(etape="flux:essai")[0]))
        self.assertNotIn("verdicts", regles._matiere(self.projet, self.etat, self.taches(etape="flux:livraison")[0]))

    def test_sans_relecteur_un_refus_de_la_qualite_refait_la_qualite_pas_la_livraison(self):
        self.casse_briques()
        self.serie(1)
        vus = self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}}, verdict("e1", ["La balle traverse la raquette"]),
            {"statut": "fait", "message": {"texte": "Corrigé."}}, verdict("e1"),
            {"statut": "fait", "message": {"texte": "Livré."}}],
            juges={"apres_refus": {"suite": "corriger", "consigne": "Corriger la collision.", "raison": "défaut"}})
        self.assertEqual(len(self.taches(etape="flux:essai")), 2)           # les tests refaits après la correction
        self.assertEqual(len(self.taches(etape="correction")), 1)
        self.assertEqual(len(self.taches(etape="flux:livraison")), 1)       # et la livraison une seule fois, après
        ordre = [t["etape"] for t in sorted(self.taches(), key=lambda t: int(t["id"][1:]))
                 if str(t["etape"]).startswith(("flux:", "correction"))]
        self.assertEqual(ordre, ["flux:dev", "flux:essai", "correction", "flux:essai", "flux:livraison"])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")

    def test_sans_relecteur_ni_etape_de_qualite_la_derniere_etape_juge(self):
        self.casse_briques(flux=[{"id": "dev", "nom": "Programmation", "role": "dev", "service": "dev"},
                                 {"id": "livraison", "nom": "Livraison de l'apk signé", "role": "livreur",
                                  "service": "livraison"}])
        self.serie(1)
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}}, verdict("e1")])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")
        self.assertIn("Rends un `verdicts`", regles._matiere(self.projet, self.etat, self.taches(etape="flux:livraison")[0]))

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


class RetourSurTache(Base):
    """Un retour de l'utilisateur sur une tâche bloquée la reprend ; sur une tâche faite, il crée une tâche de retour."""

    def tache(self, **plus):
        self.fonctionnalite()
        t = self.ok("tache", entree={"titre": "Livraison", "fonctionnalite": "f1", "role": "dev", "colonne": "dev",
                                     "agent": "dev-1", "active": True, "etape": "demande"})["id"]
        self.ok("tache", entree={"id": t, "active": False, **plus})
        return t

    def retour(self, t, texte="Crée la variable et reprends"):
        d, actions = self.traiter(type="retour", tache=t, texte=texte)
        return d, actions

    def test_retour_sur_bloquee_la_reprend_sans_nouvelle_tache(self):
        t = self.tache(bloquee="L'agent n'a pas pu finir : mot de passe du keystore absent")
        avant = len(self.taches())
        d, actions = self.retour(t)
        self.assertEqual(len(self.taches()), avant)
        self.assertFalse(self.taches(titre="Retour : Livraison"))
        fiche = self.taches(id=t)[0]
        self.assertIsNone(fiche["bloquee"])
        self.assertTrue(any("Reprise sur votre retour : Crée la variable et reprends" in j["texte"]
                            for j in fiche["journal"]))
        self.assertEqual(self.statut(d["id"])["reponse"], "Je reprends la tâche bloquée avec votre consigne.")
        (action,) = actions
        self.assertEqual((action[0], action[1], action[2]), ("agent", "dev-1", [t]))
        self.assertIn("Crée la variable et reprends", action[3])      # la consigne est dans la matière de la reprise
        self.assertTrue(self.taches(id=t)[0]["active"])

    def test_retour_sur_arretee_la_reprend(self):
        t = self.tache()              # commencée puis arrêtée, pas bloquée
        _, actions = self.retour(t)
        self.assertFalse(self.taches(titre="Retour : Livraison"))
        self.assertEqual([a[0] for a in actions], ["agent"])
        self.assertIn("Crée la variable", actions[0][3])

    def test_retour_sur_faite_cree_une_tache_de_retour(self):
        t = self.tache()
        self.ok("tache", entree={"id": t, "colonne": "fait"})
        d, _ = self.retour(t)
        (retour,) = self.taches(titre="Retour : Livraison")
        self.assertTrue(any("Retour de l'utilisateur" in j["texte"] for j in retour["journal"]))
        self.assertEqual(self.statut(d["id"])["reponse"], "J'ai confié votre retour à un agent.")

    def test_retour_sur_active_en_plein_travail_est_transmis(self):
        t = self.tache()
        self.ok("tache", entree={"id": t, "active": True})
        self.etat["en_cours"].add(t)
        d, actions = self.retour(t, "Où en es-tu ?")
        self.assertEqual(actions, [])
        self.assertFalse(self.taches(titre="Retour : Livraison"))
        self.assertTrue(self.statut(d["id"])["reponse"].startswith("Question transmise à"))
        self.assertTrue(self.taches(id=t)[0]["active"])


class Arrets(Base):
    def depart_cadrage(self):
        d, actions = self.cadrer(texte="Des écrans pour l'appli")
        return actions

    ACCORD = {"statut": "accord_requis", "message": {"texte": "Il me faut un accord."},
              "fichiers": [{"chemin": "pieces/f1/x.png", "titre": "Ne doit pas être inscrit"}],
              "accord": {"quoi": "Générer 5 images", "partenaire": "studio", "cout": "2 $"}}

    def decisions_accord(self):
        return [d for d in self.suivi()["decisions_projet"] if d["genre"] == "accord_agent"]

    def test_accord_requis_pose_une_decision_au_bureau_de_direction(self):
        actions = self.depart_cadrage()
        suite = self.piloter(actions, rapports=[self.ACCORD])
        self.assertEqual(suite[-1][0], "agent")
        d, = self.decisions_accord()
        self.assertEqual((d["agent"], d["quoi"], d["partenaire"], d["cout"]), ("metier-1", "Générer 5 images", "studio", "2 $"))
        self.assertEqual(d["pourquoi"], "Il me faut un accord.")
        self.assertNotIn("appareil", d)
        t = self.taches(etape="cadrage")[0]
        self.assertEqual(d["tache"], t["id"])
        self.assertFalse(t["active"])
        self.assertEqual(self.fonc().get("documents") or [], [])
        self.assertIn("bureau de direction", self.fonc()["discussion"][-1]["texte"])
        # Sur « accepter », l'agent reprend la même tâche avec l'accord dans son départ.
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="accepter")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("accord pour : Générer 5 images", relance[0][3])
        self.assertEqual(relance[0][2], [t["id"]])
        self.assertEqual(self.decisions_accord(), [])

    def test_accord_refuse_avec_consigne_l_agent_reprend_sans_l_action(self):
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        d, = self.decisions_accord()
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="refuser",
                                        texte="Prends des images libres de droits.")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("refuse : Générer 5 images", relance[0][3])
        self.assertIn("Prends des images libres de droits.", relance[0][3])
        t = self.taches(etape="cadrage")[0]
        self.assertFalse(t.get("bloquee"))
        self.assertEqual(self.decisions_accord(), [])

    def test_accord_sur_appareil_physique_remonte_au_directeur_avec_la_regle(self):
        accord = {**self.ACCORD, "message": {"texte": "Je lance adb devices puis adb install sur le téléphone branché."},
                  "accord": {"quoi": "adb install de l'apk sur le téléphone", "partenaire": "aucun", "cout": "0"}}
        self.piloter(self.depart_cadrage(), rapports=[accord])
        d, = self.decisions_accord()      # jamais refusé tout seul : le Directeur statue
        self.assertTrue(d["appareil"])
        self.assertIn("émulateur", d["regle"])
        self.assertIn("fenêtre de validation", d["regle"])
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="refuser")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("Pas de test sur appareil", relance[0][3])
        self.assertIn("émulateur", relance[0][3])
        self.assertFalse(self.taches(etape="cadrage")[0].get("bloquee"))

    APPAREIL = {**ACCORD, "message": {"texte": "Je lance adb devices puis adb install sur le téléphone branché."},
                "accord": {"quoi": "adb install de l'apk sur le téléphone", "partenaire": "aucun", "cout": "0"}}
    REGLE_APPAREIL = ("Pas d'installation ni de test sur un appareil physique : tests automatiques sur émulateur, "
                      "validation de version par la fenêtre de validation.")

    def test_accord_sur_appareil_propose_la_case_regle_du_projet_sauf_si_elle_existe(self):
        self.piloter(self.depart_cadrage(), rapports=[self.APPAREIL])
        d, = self.decisions_accord()
        self.assertEqual(d["regle_proposee"], self.REGLE_APPAREIL)      # la case cochée, texte pré-rempli
        self.assertNotIn("regles_touchees", d)                          # aucune règle n'existe encore
        self.assertEqual(self.ok("regles", entree={"action": "lister"})["regles"], [])     # rien n'est créé d'office

    def test_une_demande_qui_touche_une_regle_la_rappelle_sans_rien_refuser(self):
        self.ok("regles", entree={"action": "ajouter", "texte": self.REGLE_APPAREIL})
        self.ok("regles", entree={"action": "ajouter", "texte": "Les images viennent toujours du partenaire Tripo."})
        self.piloter(self.depart_cadrage(), rapports=[self.APPAREIL])
        d, = self.decisions_accord()            # toujours posée : le Directeur statue
        self.assertEqual([x["id"] for x in d["regles_touchees"]], ["r1"])
        self.assertEqual(d["regles_touchees"][0]["texte"], self.REGLE_APPAREIL)
        self.assertNotIn("regle_proposee", d)                            # la règle existe déjà : pas reproposée

    def test_accord_sans_rapport_avec_les_regles(self):
        self.ok("regles", entree={"action": "ajouter", "texte": self.REGLE_APPAREIL})
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        d, = self.decisions_accord()
        self.assertNotIn("regles_touchees", d)
        self.assertNotIn("regle_proposee", d)

    def test_retenir_comme_regle_en_repondant(self):
        self.piloter(self.depart_cadrage(), rapports=[self.APPAREIL])
        d, = self.decisions_accord()
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="refuser",
                                        texte="Utilise l'émulateur.", regle=self.REGLE_APPAREIL)
        self.assertEqual([a[0] for a in relance], ["agent"])             # l'agent reprend comme avant
        r, = self.ok("regles", entree={"action": "lister"})["regles"]
        self.assertEqual((r["texte"], r["origine"]), (self.REGLE_APPAREIL, {"decision": d["id"], "agent": "metier-1"}))

    def test_sans_la_case_aucune_regle_n_est_creee(self):
        self.piloter(self.depart_cadrage(), rapports=[self.APPAREIL])
        d, = self.decisions_accord()
        self.traiter(type="accord_agent", decision=d["id"], verdict="refuser", texte="Utilise l'émulateur.")
        self.assertEqual(self.ok("regles", entree={"action": "lister"})["regles"], [])

    def test_regle_refusee_par_l_outil_ne_bloque_pas_la_reponse(self):
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        d, = self.decisions_accord()
        for i in range(40):
            self.ok("regles", entree={"action": "ajouter", "texte": f"Règle {i}."})
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="accepter", regle="De trop.")
        self.assertEqual([a[0] for a in relance], ["agent"])
        t = self.taches(etape="cadrage")[0]
        self.assertTrue(any("règle du projet n'a pas été notée" in j["texte"] for j in t["journal"]))

    AVEC_CHOIX = {**ACCORD, "message": {"texte": "Je peux tester sur votre téléphone branché (adb install).", "attend": True,
                  "questions": [{"texte": "Que faire ?", "choix": ["Oui, je branche le téléphone", "Non, livrer sans ce test",
                                                                    "Oui, je branche le téléphone", " "], "multiple": False}]},
                  "accord": {"quoi": "adb install de l'apk", "partenaire": "aucun", "cout": "0"}}

    def test_choix_de_l_agent_deviennent_les_boutons_de_la_decision(self):
        self.piloter(self.depart_cadrage(), rapports=[self.AVEC_CHOIX])
        d, = self.decisions_accord()
        self.assertEqual(d["choix"], ["Oui, je branche le téléphone", "Non, livrer sans ce test"])
        self.assertTrue(d["appareil"])                                    # le rappel de règle reste
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="choisir",
                                        choix="Non, livrer sans ce test", texte="Merci.", regle="Livrer sans test sur téléphone.")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("a choisi : « Non, livrer sans ce test »", relance[0][3])
        self.assertIn("Sa consigne : Merci.", relance[0][3])
        self.assertEqual(self.decisions_accord(), [])
        self.assertEqual(self.ok("regles", entree={"action": "lister"})["regles"][0]["texte"], "Livrer sans test sur téléphone.")

    def test_choix_inconnu_refuse_et_sans_choix_comme_avant(self):
        self.piloter(self.depart_cadrage(), rapports=[self.AVEC_CHOIX])
        d, = self.decisions_accord()
        demande, relance = self.traiter(type="accord_agent", decision=d["id"], verdict="choisir", choix="Autre chose")
        self.assertEqual(relance, [])
        self.assertIn("pas l'un de ceux", self.statut(demande["id"])["reponse"])
        self.assertEqual(len(self.decisions_accord()), 1)                  # rien n'est écarté
        self.assertNotIn("choix", self.ACCORD["message"])

    def test_demande_de_regle_du_bureau(self):
        d, relance = self.traiter(type="regle_projet", operation="ajouter", texte="Pas de Docker.")
        self.assertEqual(relance, [])
        self.assertEqual(self.statut(d["id"])["reponse"], "La règle est notée.")
        r, = self.ok("regles", entree={"action": "lister"})["regles"]
        d, _ = self.traiter(type="regle_projet", operation="modifier", id=r["id"], texte="Pas de Docker ni de WSL.")
        self.assertEqual(self.ok("regles", entree={"action": "lister"})["regles"][0]["texte"], "Pas de Docker ni de WSL.")
        d, _ = self.traiter(type="regle_projet", operation="supprimer", id=r["id"])
        self.assertEqual(self.ok("regles", entree={"action": "lister"})["regles"], [])
        d, _ = self.traiter(type="regle_projet", operation="supprimer", id="r9")     # déjà partie : dit, pas une erreur
        self.assertIn("La règle n'a pas été notée", self.statut(d["id"])["reponse"])

    def test_refus_dans_la_discussion_avec_consigne_ne_met_pas_la_tache_de_cote(self):
        actions = self.depart_cadrage()
        tid = actions[0][2][0]
        self.etat["accords"]["f1"] = {"tache": tid, "quoi": "Générer 5 images", "supplement": "ok"}
        self.etat["en_cours"].discard(tid)
        regles.lancer(self.projet, "tache", {"id": tid, "active": False})
        d, relance = self.traiter(type="message", fonctionnalite="f1",
                                  texte="Générer 5 images ? → " + regles.REFUSE + " : fais-le avec des formes simples")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("fais-le avec des formes simples", relance[0][3])
        self.assertFalse(self.taches(id=tid)[0].get("bloquee"))

    def test_outil_refuse_pose_une_decision_au_bureau_de_direction(self):
        # Le cas réel : la question n'était posée que dans la discussion de la fonctionnalité (invisible au bureau de
        # direction une fois en série) et rien ne relançait la tâche. C'est maintenant une décision de projet.
        actions = self.depart_cadrage()
        refus = {"statut": "outil_refuse", "outil": "WebSearch", "message": {"texte": "Je ne peux pas chercher."}}
        self.piloter(actions, rapports=[refus])
        decisions = [d for d in self.suivi()["decisions_projet"] if d["genre"] == "outil_agent"]
        self.assertEqual(len(decisions), 1)
        self.assertEqual((decisions[0]["agent"], decisions[0]["outil"]), ("metier-1", "WebSearch"))
        self.assertIn("WebSearch", decisions[0]["texte"])
        t = self.taches(etape="cadrage")[0]
        self.assertFalse(t["active"])
        self.assertEqual(decisions[0]["tache"], t["id"])
        d, relance = self.traiter(type="outil_agent", decision=decisions[0]["id"], verdict="refuser")
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

    def test_panne_du_service_ne_bloque_pas_et_attend_avant_de_reessayer(self):
        """Essai réel : une panne d'authentification (403 Cloudflare) a bloqué douze tâches d'un coup. La tâche reste
        prête, rien ne part avant le prochain essai (dit au bureau), puis elle repart seule."""
        actions = self.depart_cadrage()
        tid = actions[0][2][0]
        e = agents.Execution(tid, "metier-1", usages=[usage()],
                             erreur="l'appel a échoué : Failed to authenticate. API Error: 403 | Cloudflare")
        e.panne = True
        self.assertEqual(regles.traiter_retour(self.projet, e, self.etat), [])
        t = self.taches(id=tid)[0]
        self.assertFalse(t["bloquee"])
        self.assertIn("Service Claude indisponible", t["journal"][-1]["texte"])
        self.assertIn(tid, self.etat["a_lancer"])
        self.assertEqual(regles._demarrer_en_attente(self.projet, self.etat, None), [])      # pendant la panne
        self.assertIn("nouvel essai à", self.etat["attente_charge"]["texte"])
        self.etat["panne"]["jusqu_a"] = 0                                                   # l'heure est passée
        repart = regles._demarrer_en_attente(self.projet, self.etat, None)
        self.assertEqual([(a[0], a[2]) for a in repart], [("agent", [tid])])
        # une deuxième panne attend plus longtemps
        e2 = agents.Execution(tid, "metier-1", usages=[usage()], erreur="l'appel a échoué : API Error: 529 Overloaded")
        e2.panne = True
        regles.traiter_retour(self.projet, e2, self.etat)
        import time as _t
        self.assertGreater(self.etat["panne"]["jusqu_a"] - _t.time(), 200)
        self.assertNotIn(tid, self.etat.get("relancees", set()))                          # aucun essai compté

    # Le cas réel : l'agent de cadrage rend des questions mal formées, l'outil refuse son message.
    MAL_FORME = {"statut": "fait", "message": {"texte": "Quatre questions.", "attend": True,
                                                 "questions": [{"enonce": "Quel style ?", "choix": ["a", "b"]}]}}

    def execution(self, tid, r):
        return agents.Execution(tid, "metier-1", rapport=_lu(r), usages=[usage()])

    def test_un_message_refuse_relance_l_agent_avec_la_raison(self):
        tid = self.depart_cadrage()[0][2][0]
        again = regles.traiter_retour(self.projet, self.execution(tid, self.MAL_FORME), self.etat)
        self.assertEqual([(a[0], a[1], a[2]) for a in again], [("agent", "metier-1", [tid])])
        matiere = again[0][3]
        self.assertIn("Ta réponse a été refusée", matiere)
        self.assertIn("la question 1 doit avoir un « texte »", matiere)
        self.assertIn("sans refaire le travail", matiere)
        self.assertIn("Quel style ?", matiere)                       # son message n'est pas perdu
        self.assertIn("Matière de la tâche", matiere)
        t = self.taches(id=tid)[0]
        self.assertTrue(t["active"])
        self.assertIsNone(t["bloquee"])
        self.assertIn(tid, self.etat["en_cours"])
        self.assertNotIn("metier-1", [m["auteur"] for m in self.fonc()["discussion"]])      # rien n'est passé
        # L'agent rend le bon format : le message passe, la tâche attend la réponse de l'utilisateur.
        bon = {"statut": "fait", "message": {"texte": "Quatre questions.", "attend": True,
                                              "questions": [{"texte": "Quel style ?", "choix": ["a", "b"]}]}}
        self.assertEqual(regles.traiter_retour(self.projet, self.execution(tid, bon), self.etat), [])
        self.assertEqual(self.fonc()["discussion"][-1]["questions"][0]["texte"], "Quel style ?")
        self.assertFalse(self.taches(id=tid)[0]["active"])

    def test_un_message_refuse_deux_fois_bloque_la_tache(self):
        tid = self.depart_cadrage()[0][2][0]
        regles.traiter_retour(self.projet, self.execution(tid, self.MAL_FORME), self.etat)
        self.assertEqual(regles.traiter_retour(self.projet, self.execution(tid, self.MAL_FORME), self.etat), [])
        t = self.taches(id=tid)[0]
        self.assertFalse(t["active"])
        self.assertIn("refusée", t["bloquee"])
        self.assertIn("la question 1 doit avoir un « texte »", t["bloquee"])
        self.assertNotIn(tid, self.etat["en_cours"])
        self.assertIn("est bloquée", self.fonc()["discussion"][-1]["texte"])

    def test_le_refus_d_un_tour_n_use_pas_l_essai_du_tour_suivant(self):
        tid = self.depart_cadrage()[0][2][0]
        bon = {"statut": "fait", "message": {"texte": "Ok.", "attend": True}}
        regles.traiter_retour(self.projet, self.execution(tid, self.MAL_FORME), self.etat)
        regles.traiter_retour(self.projet, self.execution(tid, bon), self.etat)
        again = regles.traiter_retour(self.projet, self.execution(tid, self.MAL_FORME), self.etat)
        self.assertEqual([a[0] for a in again], ["agent"])      # un nouveau tour : un nouvel essai

    def etat_t2(self, avec_reponse_apres=False):
        """L'état réel du projet bloqué : agent attribué, tâche inactive, « Refusé par l'outil » au journal."""
        tid = self.depart_cadrage()[0][2][0]
        self.ok("tache", entree={"id": tid, "active": False, "journal": [
            "Refusé par l'outil (message) : message : « questions » : la question 1 doit avoir un « texte ».",
            "Quatre questions courtes avant d'écrire le cahier."]})
        if avec_reponse_apres:
            self.ok("message", entree={"fonctionnalite": "f1", "auteur": "metier-1", "texte": "Quatre questions."})
        return tid

    def test_au_demarrage_une_tache_au_message_refuse_est_relancee_une_fois(self):
        tid = self.etat_t2()
        etat = regles.nouvel_etat()
        actions = regles.orphelines(self.projet, etat)
        self.assertEqual([(a[0], a[1], a[2]) for a in actions], [("agent", "metier-1", [tid])])
        self.assertIn("Ta réponse a été refusée", actions[0][3])
        self.assertIn("la question 1 doit avoir un « texte »", actions[0][3])
        self.assertTrue(self.taches(id=tid)[0]["active"])
        self.assertEqual(regles.orphelines(self.projet, etat), [])         # une seule fois
        # L'agent se trompe encore : la tâche est bloquée, avec la raison.
        self.assertEqual(regles.traiter_retour(self.projet, self.execution(tid, self.MAL_FORME), etat), [])
        t = self.taches(id=tid)[0]
        self.assertFalse(t["active"])
        self.assertIn("la question 1 doit avoir un « texte »", t["bloquee"])
        self.assertEqual(regles.orphelines(self.projet, regles.nouvel_etat()), [])    # bloquée : plus reprise

    def test_au_demarrage_une_tache_dont_l_agent_a_repondu_depuis_n_est_pas_relancee(self):
        self.etat_t2(avec_reponse_apres=True)
        self.assertEqual(regles.orphelines(self.projet, regles.nouvel_etat()), [])

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
        d, actions = self.cadrer(texte="Des écrans")
        self.assertEqual(actions, [])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual([t["id"] for t in self.taches()], [occupe])


class Validation(Base):
    """Une étape de validation du Directeur dans le flux : l'élément s'arrête, le Directeur valide ou renvoie."""

    VAL = {"id": "valider", "nom": "Validation du Directeur", "validation": True}

    def projet_avec_validation(self, flux=None, elements=1):
        """Sans relecteur : programmation, tests, validation du Directeur, livraison de l'apk."""
        (self.dossier / "fiches" / "remi.md").unlink()
        (self.dossier / "fiches" / "zoe.md").unlink()
        for cle, role, service in (("test-1", "testeur", "qualite"), ("liv-1", "livreur", "livraison")):
            (self.dossier / "fiches" / f"{cle}.md").write_text(
                FICHE_REMI.replace("rel-1", cle).replace("relecteur", role).replace("Service : dev", f"Service : {service}"),
                encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["services"] += [{"id": "qualite", "nom": "Qualité"}, {"id": "livraison", "nom": "Livraison"}]
        f["flux"] = flux or [{"id": "dev", "nom": "Programmation", "role": "dev", "service": "dev"},
                             {"id": "essai", "nom": "Tests et essai du jeu", "role": "testeur", "service": "qualite"},
                             self.VAL,
                             {"id": "livraison", "nom": "Livraison de l'apk signé", "role": "livreur",
                              "service": "livraison"}]
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.serie(elements)

    def fichier(self, chemin, octets=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16):
        """Un fichier rendu par un agent, qui existe vraiment (jamais rien à valider : le moteur le vérifie)."""
        f = self.dossier / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(octets)
        return f

    def jusqu_a_la_validation(self, **plus):
        self.projet_avec_validation(**plus)
        self.fichier("pieces/f1/essai.png")
        rapports = [{"statut": "fait", "message": {"texte": "Programmé."}},
                    {**verdict("e1"), **DIT, "message": {"texte": "Tout est vert, apk d'essai prêt."},
                     "fichiers": [{"chemin": "pieces/f1/essai.png", "titre": "Capture de l'essai", "element": "e1"},
                                  {"chemin": "pieces/f1/autre.png", "titre": "D'un autre élément", "element": "e9"}]}]
        return self.piloter(regles.avancer(self.projet, self.etat), rapports=rapports)

    def decisions(self):
        return [d for d in self.ok("etat")["decisions"] if d["genre"] == "valider_etape"]

    def repondre(self, **champs):
        d = self.decisions()[0]
        return self.traiter(type="valider_etape", decision=d["id"], **champs)

    def test_element_s_arrete_a_la_validation(self):
        vus = self.jusqu_a_la_validation()
        self.assertEqual([a[0] for a in vus].count("agent"), 2)        # la programmation et les tests, rien de plus
        (d,) = self.decisions()
        self.assertEqual((d["portee"], d["fonctionnalite"], d["etape"]), ("projet", "f1", "valider"))
        self.assertEqual(d["element"], {"id": "e1", "nom": "Accueil"})
        self.assertEqual(d["compte_rendu"], "Tout est vert, apk d'essai prêt.")
        self.assertEqual(d["fichiers"], [{"chemin": "pieces/f1/essai.png", "titre": "Capture de l'essai"}])
        (t,) = self.taches(etape="validation:valider")
        self.assertEqual((t["colonne"], t["role"], t["agent"], t["active"], d["tache"]), ("valider", None, None, False, t["id"]))
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "validation")
        self.assertEqual(self.taches(etape="flux:livraison"), [])
        self.assertEqual(regles.avancer(self.projet, self.etat), [])    # rien ne part tant que le Directeur n'a pas répondu

    def test_valider_passe_a_l_etape_suivante(self):
        self.jusqu_a_la_validation()
        d, actions = self.repondre(verdict="valider")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.taches(etape="validation:valider")[0]["colonne"], "fait")
        self.piloter(actions, rapports=[{"statut": "fait", "message": {"texte": "Livré."}}])
        self.assertEqual(len(self.taches(etape="flux:livraison")), 1)
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")

    def test_renvoyer_refait_l_etape_precedente_avec_la_remarque(self):
        self.jusqu_a_la_validation()
        d, actions = self.repondre(verdict="renvoyer", texte="Le menu est trop chargé.")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertIn("Remarque du Directeur : Le menu est trop chargé.", [j["texte"] for j in essais[-1]["journal"]])
        self.assertIn("Remarque du Directeur : Le menu est trop chargé.",
                      regles._matiere(self.projet, self.etat, essais[-1]))
        self.assertEqual(self.etat["elements"]["f1/e1"]["pas"], 1)
        # l'étape refaite, l'élément revient à la validation : une nouvelle décision, avec le nouveau compte rendu
        self.piloter(actions, rapports=[{**verdict("e1"), "message": {"texte": "Menu allégé."}, "acces": ACCES, **DIT}])
        (nouvelle,) = self.decisions()
        self.assertEqual(nouvelle["compte_rendu"], "Menu allégé.")
        self.assertEqual(len(self.taches(etape="validation:valider")), 2)
        self.assertEqual(self.taches(etape="flux:livraison"), [])

    def test_apres_un_renvoi_ce_qui_doit_marcher_vient_des_points_renvoyes(self):
        """Essai réel : l'agent, jugeant la correction déjà faite, ne disait pas ce qui doit marcher (deux fois) ; la
        validation restait bloquée. Après un renvoi, ce sont les points que le Directeur a demandé de revoir."""
        self.jusqu_a_la_validation()
        _, actions = self.repondre(verdict="renvoyer", texte="Le menu est trop chargé.")
        self.piloter(actions, rapports=[{**verdict("e1"), "message": {"texte": "Rien à changer."}, "acces": ACCES}])
        (nouvelle,) = self.decisions()
        self.assertEqual(nouvelle["doit_marcher"], "Les points renvoyés sont corrigés : Le menu est trop chargé.")

    def test_renvoyer_sans_remarque_refuse(self):
        self.jusqu_a_la_validation()
        for texte in (None, "   "):
            champs = {} if texte is None else {"texte": texte}
            d = self.decisions()[0]
            i = self.ok("actions", entree={"type": "valider_etape", "decision": d["id"], "verdict": "renvoyer", **champs})["id"]
            demande = next(x for x in self.demande_en_attente() if x["id"] == i)
            self.assertEqual(regles.traiter_demande(self.projet, demande, self.etat), [])
            self.assertIn("remarque", self.statut(i)["reponse"])
        self.assertEqual(len(self.decisions()), 1)                      # l'élément reste en attente
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "validation")
        self.assertEqual(len(self.taches(etape="flux:essai")), 1)

    # --- La fenêtre de validation (conception 2026-11-12-fenetre-de-validation-design.md).

    def test_points_a_verifier_de_l_agent_et_livrable_mesure(self):
        self.projet_avec_validation()
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 98)
        points = ["Le jeu se lance sur le téléphone", "Le bouton Jouer ouvre la partie", "Le score s'affiche"]
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}},
            {**verdict("e1"), **DIT, "message": {"texte": "Apk prêt."}, "points_a_verifier": points,
             "fichiers": [{"chemin": "build/jeu.apk", "titre": "L'apk d'essai", "element": "e1"}]}])
        (d,) = self.decisions()
        self.assertEqual(d["points"], points)
        (f,) = d["fichiers"]
        self.assertEqual((f["chemin"], f["titre"], f["taille"]), ("build/jeu.apk", "L'apk d'essai", 100))
        self.assertRegex(f["date"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertNotIn("acces", d)

    def test_points_derives_de_l_objectif(self):
        self.jusqu_a_la_validation()
        (d,) = self.decisions()
        self.assertEqual(d["points"], ["Le résultat correspond à l'objectif : Produire « Accueil » (écrans), jusqu'à "
                                       "l'étape « Tests et essai du jeu ».",
                                       "Les images montrent ce qui est attendu, sans défaut visible"])
        self.assertTrue(all(len(p) <= 160 for p in d["points"]))

    def test_consigne_des_points_avant_la_validation_seulement(self):
        self.projet_avec_validation()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[{"statut": "fait", "message": {"texte": "Ok."}}],
                     limite=1)
        (dev,) = self.taches(etape="flux:dev")
        self.assertNotIn("points_a_verifier", regles._matiere(self.projet, self.etat, dev))
        (essai,) = self.taches(etape="flux:essai")
        m = regles._matiere(self.projet, self.etat, essai)
        self.assertIn("points_a_verifier", m)
        self.assertIn("3 à 8 phrases de 160 caractères au plus", m)
        self.assertIn('"acces"', m.replace("`acces`", '"acces"'))

    def test_tous_ok_valide_et_transmet_la_note(self):
        self.jusqu_a_la_validation()
        d = self.decisions()[0]
        reponses = [{"point": p, "ok": True} for p in d["points"]]
        demande, actions = self.repondre(verdict="valider", reponses=reponses, texte="Pensez au mode sombre plus tard.")
        self.assertEqual(self.statut(demande["id"])["statut"], "traitée")
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("Validé. Note du Directeur : Pensez au mode sombre plus tard.", [j["texte"] for j in val["journal"]])
        (livraison,) = self.taches(etape="flux:livraison")
        self.assertIn("Note du Directeur à la validation « Accueil » : Pensez au mode sombre plus tard.",
                      [j["texte"] for j in livraison["journal"]])

    def test_un_point_a_revoir_renvoie_avec_la_remarque_structuree(self):
        self.jusqu_a_la_validation()
        d = self.decisions()[0]
        reponses = [{"point": d["points"][0], "ok": True}, {"point": d["points"][1], "ok": False}]
        self.repondre(verdict="renvoyer", reponses=reponses)       # le texte libre est facultatif
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertIn("Remarque du Directeur : points à revoir : Les images montrent ce qui est attendu, sans défaut "
                      "visible.", [j["texte"] for j in essais[-1]["journal"]])
        self.assertEqual(self.decisions(), [])

    def test_reponses_qui_ne_collent_pas_refusees(self):
        self.jusqu_a_la_validation()
        d = self.decisions()[0]
        tous = [{"point": p, "ok": True} for p in d["points"]]
        for champs in ({"verdict": "renvoyer", "reponses": tous},                     # le verdict ne découle pas
                       {"verdict": "valider", "reponses": tous[:1]},                  # un point sans réponse
                       {"verdict": "valider", "reponses": tous + [{"point": "Autre", "ok": True}]},
                       {"verdict": "valider", "reponses": [{"point": p["point"], "ok": "oui"} for p in tous]}):
            try:
                i = self.ok("actions", entree={"type": "valider_etape", "decision": d["id"], **champs})["id"]
            except AssertionError:
                continue                                                         # refusé dès l'outil
            demande = next(x for x in self.demande_en_attente() if x["id"] == i)
            self.assertEqual(regles.traiter_demande(self.projet, demande, self.etat), [])
        self.assertEqual(len(self.decisions()), 1)
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "validation")

    def test_decision_d_avant_sans_points(self):
        self.jusqu_a_la_validation()
        suivi = self.suivi()
        for d in suivi["decisions_projet"]:
            d.pop("points", None)
        (self.dossier / "suivi.json").write_text(json.dumps(suivi), encoding="utf-8")
        self.repondre(verdict="valider", reponses=[{"point": "L'élément correspond à l'objectif", "ok": True}])
        self.assertEqual(self.decisions(), [])
        self.assertEqual(len(self.taches(etape="flux:livraison")), 1)

    def test_jamais_rien_a_valider(self):
        """Ni image, ni livrable, ni lien : l'étape précédente est refaite une fois ; au second échec, la tâche de
        validation est bloquée avec la raison, sans décision."""
        self.projet_avec_validation()
        rien = {**verdict("e1"), **DIT, "message": {"texte": "Testé."},
                "fichiers": [{"chemin": "pieces/f1/absent.png", "titre": "Introuvable", "element": "e1"},
                             {"chemin": "src/main.gd", "titre": "Le code", "element": "e1"}]}
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, rien, rien])
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertTrue(any(j["texte"].startswith("Rien à valider") for j in essais[-1]["journal"]))
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("Rien à valider", val["bloquee"])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "bloque")

    def test_ce_que_dit_la_validation_est_stocke_sur_la_decision(self):
        self.jusqu_a_la_validation()
        (d,) = self.decisions()
        self.assertEqual({c: d[c] for c in DIT}, DIT)

    def test_validation_sans_doit_marcher_relance_une_fois_puis_pose_avec_l_objectif(self):
        """Essai réel : trois validations bloquées, l'agent jugeant qu'il n'y avait rien à modifier. Au second essai
        muet, s'il y a de quoi vérifier, la validation est posée avec l'objectif de l'étape comme consigne."""
        self.projet_avec_validation()
        self.fichier("pieces/f1/essai.png")
        sans = {**verdict("e1"), "message": {"texte": "Testé."},
                "fichiers": [{"chemin": "pieces/f1/essai.png", "titre": "Capture", "element": "e1"}],
                "doit_marcher": "x" * 481}                      # trop long : écarté comme absent
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, sans, sans])
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertTrue(any(j["texte"].startswith("Validation sans consigne") for j in essais[-1]["journal"]))
        (d,) = self.decisions()
        self.assertTrue(d["doit_marcher"].startswith("L'agent ne l'a pas précisé"))
        self.assertLessEqual(len(d["doit_marcher"]), 480)
        (val,) = self.taches(etape="validation:valider")
        self.assertFalse(val.get("bloquee"))
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "validation")

    def test_retour_sur_une_validation_bloquee_refait_l_etape_d_avant(self):
        """Tout se règle depuis le bureau : un retour sur la validation bloquée refait l'étape précédente avec le texte
        du Directeur, puis la validation est reposée."""
        self.projet_avec_validation()
        rien = {**verdict("e1"), **DIT, "message": {"texte": "Testé."}}
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, rien, rien])
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("Écrivez un retour sur cette tâche", val["bloquee"])
        d, actions = self.traiter(type="retour", tache=val["id"], texte="Joins une capture de l'écran.")
        self.assertIn("refaite", self.statut(d["id"])["reponse"])
        (val,) = self.taches(etape="validation:valider")
        self.assertEqual((val["colonne"], val.get("bloquee")), ("fait", None))
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 3)
        self.assertTrue(any("Joins une capture" in j["texte"] for j in essais[-1]["journal"]))
        self.assertEqual([t for t in self.taches() if t["titre"].startswith("Retour :")], [])
        self.fichier("pieces/f1/essai.png")
        self.piloter(actions, rapports=[{**rien, "fichiers": [
            {"chemin": "pieces/f1/essai.png", "titre": "Capture", "element": "e1"}]}])
        (nouvelle,) = self.decisions()
        self.assertEqual(nouvelle["doit_marcher"], DIT["doit_marcher"])

    def test_doit_marcher_rendu_a_la_relance_pose_la_decision(self):
        self.projet_avec_validation()
        self.fichier("pieces/f1/essai.png")
        sans = {**verdict("e1"), "message": {"texte": "Testé."},
                "fichiers": [{"chemin": "pieces/f1/essai.png", "titre": "Capture", "element": "e1"}]}
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}}, sans, {**sans, **DIT, "pas_encore": ""}])
        (d,) = self.decisions()
        self.assertEqual((d["doit_marcher"], d["pas_encore"]), (DIT["doit_marcher"], ""))

    def test_consigne_des_trois_champs_avant_la_validation(self):
        self.projet_avec_validation()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[{"statut": "fait", "message": {"texte": "Ok."}}],
                     limite=1)
        (essai,) = self.taches(etape="flux:essai")
        m = regles._matiere(self.projet, self.etat, essai)
        for c in ("doit_marcher", "pas_encore", "conclusion"):
            self.assertIn(f"`{c}`", m)
        self.assertIn("480 caractères au plus", m)

    def test_rien_a_valider_puis_de_quoi_verifier(self):
        self.projet_avec_validation()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}}, {**verdict("e1"), "message": {"texte": "Testé."}},
            {**verdict("e1"), "message": {"texte": "Le site tourne."}, "acces": ACCES, **DIT}])
        (d,) = self.decisions()
        self.assertEqual(d["acces"], ACCES)
        self.assertIn("Le site s'ouvre depuis le lien d'accès et répond sans erreur", d["points"])
        self.assertEqual(self.taches(etape="validation:valider")[0].get("bloquee"), None)

    # --- La nature de ce qu'on fait valider : les preuves qui conviennent (règle de l'utilisateur).

    MODE = ["Installez l'apk sur le téléphone.", "Ouvrez le jeu.", "Touchez Jouer et observez le menu."]

    def valider_nature(self, *rapports):
        """Programmation, puis les rapports des tests donnés (le dernier pose la décision ou bloque)."""
        self.projet_avec_validation()
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, *rapports])

    def rendu(self, nature=None, fichiers=(), **plus):
        r = {**verdict("e1"), **DIT, "message": {"texte": "Testé."},
             "fichiers": [{"chemin": c, "titre": c.rsplit("/", 1)[-1], "element": "e1"} for c in fichiers], **plus}
        if nature:
            r["nature"] = nature
        return r

    def test_en_jeu_avec_apk_et_mode_operatoire_pose_la_decision(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        self.valider_nature(self.rendu("en_jeu", ["build/jeu.apk"], mode_operatoire=self.MODE))
        (d,) = self.decisions()
        self.assertEqual((d["nature"], d["mode_operatoire"]), ("en_jeu", self.MODE))
        self.assertEqual([f["chemin"] for f in d["fichiers"]], ["build/jeu.apk"])

    def test_en_jeu_avec_lien_d_acces_suffit_sans_livrable(self):
        self.valider_nature(self.rendu("en_jeu", acces=ACCES, mode_operatoire=self.MODE))
        (d,) = self.decisions()
        self.assertEqual((d["nature"], d["acces"]), ("en_jeu", ACCES))

    def test_en_jeu_sans_mode_operatoire_relance_puis_pose(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        sans = self.rendu("en_jeu", ["build/jeu.apk"])
        self.valider_nature(sans, {**sans, "mode_operatoire": self.MODE})
        (d,) = self.decisions()
        self.assertEqual(d["mode_operatoire"], self.MODE)
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertTrue(any("mode opératoire" in j["texte"] for j in essais[-1]["journal"]))

    def test_en_jeu_mode_operatoire_mal_forme_compte_comme_absent(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        mauvais = self.rendu("en_jeu", ["build/jeu.apk"], mode_operatoire=["une seule étape"])
        self.valider_nature(mauvais, mauvais)
        self.assertEqual(self.decisions(), [])
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("mode opératoire", val["bloquee"])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "bloque")

    def test_en_jeu_sans_livrable_relance_une_fois_puis_bloque(self):
        self.fichier("pieces/f1/essai.png")
        sans = self.rendu("en_jeu", ["pieces/f1/essai.png"], mode_operatoire=self.MODE)    # une image n'est pas un livrable
        self.valider_nature(sans, sans)
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertTrue(any("sans livrable" in j["texte"] for j in essais[-1]["journal"]))
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("sans livrable", val["bloquee"])

    def test_visuel_sans_image_relance_et_l_apk_n_est_pas_une_preuve(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        sans = self.rendu("visuel", ["build/jeu.apk"])
        self.valider_nature(sans, sans)
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertTrue(any("Validation visuelle sans image" in j["texte"] for j in essais[-1]["journal"]))
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("sans image", val["bloquee"])

    def test_visuel_retire_l_apk_des_fichiers_montres(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        self.fichier("pieces/f1/essai.png")
        self.valider_nature(self.rendu("visuel", ["build/jeu.apk", "pieces/f1/essai.png"],
                                       mode_operatoire=self.MODE, acces=ACCES))
        (d,) = self.decisions()
        self.assertEqual([f["chemin"] for f in d["fichiers"]], ["pieces/f1/essai.png"])
        self.assertEqual(d["nature"], "visuel")
        self.assertNotIn("mode_operatoire", d)                  # le mode opératoire ne sert qu'à une validation en jeu
        self.assertNotIn("Le livrable se télécharge", " ".join(d["points"]))

    def test_visuel_exige_une_image_un_son_seul_ne_suffit_plus(self):
        self.fichier("sons/coup.mp3", b"ID3")
        sans = self.rendu("visuel", ["sons/coup.mp3"])
        self.valider_nature(sans, sans)
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertTrue(any("Validation visuelle sans image" in j["texte"] for j in essais[-1]["journal"]))

    def test_visuel_avec_image_et_son_pose_les_deux(self):
        self.fichier("sons/coup.mp3", b"ID3")
        self.fichier("pieces/f1/essai.png")
        self.valider_nature(self.rendu("visuel", ["pieces/f1/essai.png", "sons/coup.mp3"]))
        (d,) = self.decisions()
        self.assertEqual(sorted(f["chemin"] for f in d["fichiers"]), ["pieces/f1/essai.png", "sons/coup.mp3"])

    def test_son_demande_un_fichier_audio_une_image_ne_suffit_pas(self):
        self.fichier("pieces/f1/essai.png")
        sans = self.rendu("son", ["pieces/f1/essai.png"])
        self.valider_nature(sans, sans)
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertEqual(len(essais), 2)
        self.assertTrue(any("sans fichier audio" in j["texte"] for j in essais[-1]["journal"]))
        (val,) = self.taches(etape="validation:valider")
        self.assertIn("sans son", val["bloquee"])

    def test_son_avec_audio_pose_sans_apk_ni_mode_operatoire(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        for audio in ("sons/coup.flac", "sons/musique.ogg"):
            self.fichier(audio, b"fLaC")
        self.valider_nature(self.rendu("son", ["build/jeu.apk", "sons/coup.flac", "sons/musique.ogg"],
                                       mode_operatoire=self.MODE))
        (d,) = self.decisions()
        self.assertEqual(d["nature"], "son")
        self.assertEqual(sorted(f["chemin"] for f in d["fichiers"]), ["sons/coup.flac", "sons/musique.ogg"])
        self.assertNotIn("mode_operatoire", d)

    def test_son_dans_un_compte_rendu_de_lot(self):
        self.fichier("sons/coup.wav", b"RIFF")
        r = self.rendu(None, ["sons/coup.wav"], comptes_rendus=[{"element": "e1", "texte": "Sons.", "nature": "son"}])
        self.valider_nature(r)
        (d,) = self.decisions()
        self.assertEqual(d["nature"], "son")

    def test_mecanique_demande_un_document_et_retire_l_apk(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        self.fichier("pieces/f1/schema.png")
        sans = self.rendu("mecanique", ["build/jeu.apk", "pieces/f1/schema.png"])
        self.valider_nature(sans, sans)
        self.assertEqual(self.decisions(), [])
        essais = self.taches(etape="flux:essai")
        self.assertTrue(any("document explicatif" in j["texte"] for j in essais[-1]["journal"]))

    def test_mecanique_avec_document_pose_sans_apk(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        self.fichier("docs/equilibrage.md", b"# Equilibrage\n")
        self.fichier("pieces/f1/schema.png")
        self.valider_nature(self.rendu("mecanique", ["build/jeu.apk", "docs/equilibrage.md", "pieces/f1/schema.png"]))
        (d,) = self.decisions()
        self.assertEqual(sorted(f["chemin"] for f in d["fichiers"]), ["docs/equilibrage.md", "pieces/f1/schema.png"])
        self.assertEqual(d["nature"], "mecanique")

    def test_nature_autre_et_absente_gardent_le_comportement_actuel(self):
        self.fichier("pieces/f1/essai.png")
        self.valider_nature(self.rendu("autre", ["pieces/f1/essai.png"]))
        (d,) = self.decisions()
        self.assertEqual(d["nature"], "autre")
        self.assertNotIn("mode_operatoire", d)

    def test_nature_absente_ou_inconnue_n_ajoute_rien(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        self.valider_nature(self.rendu("sprites", ["build/jeu.apk"]))          # nature inconnue : écartée par le rapport
        (d,) = self.decisions()
        self.assertNotIn("nature", d)
        self.assertEqual([f["chemin"] for f in d["fichiers"]], ["build/jeu.apk"])

    def test_nature_du_compte_rendu_d_un_lot(self):
        self.fichier("pieces/f1/essai.png")
        r = self.rendu(None, [], comptes_rendus=[{"element": "e1", "texte": "Sprites.", "nature": "visuel",
                                                  "images": [{"chemin": "pieces/f1/essai.png", "legende": "Sprite"}]}])
        self.valider_nature(r)
        (d,) = self.decisions()
        self.assertEqual(d["nature"], "visuel")

    def test_nature_retrouvee_apres_redemarrage(self):
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        self.valider_nature(self.rendu("en_jeu", ["build/jeu.apk"], mode_operatoire=self.MODE))
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        v = self.etat["elements"]["f1/e1"]["dernier_rapport"]
        self.assertEqual((v["nature"], v["mode_operatoire"]), ("en_jeu", self.MODE))

    def test_consigne_de_nature_courte_et_avant_la_validation_seulement(self):
        self.projet_avec_validation()
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[{"statut": "fait", "message": {"texte": "Ok."}}],
                     limite=1)
        (dev,) = self.taches(etape="flux:dev")
        self.assertNotIn("mode_operatoire", regles._matiere(self.projet, self.etat, dev))
        (essai,) = self.taches(etape="flux:essai")
        m = regles._matiere(self.projet, self.etat, essai)
        for mot in ("`nature`", "`en_jeu`", "`visuel`", "`son`", "`mecanique`", "`autre`", "`mode_operatoire`", "2 à 10 étapes",
                    "200 caractères au plus"):
            self.assertIn(mot, m)
        self.assertLess(len(regles.CONSIGNE_AVANT_VALIDATION), 3200)

    def test_validation_apres_redemarrage(self):
        self.jusqu_a_la_validation()
        self.etat = regles.nouvel_etat()                                # le moteur est relancé : sa mémoire est perdue
        regles.avancer(self.projet, self.etat)
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "validation")   # il retrouve l'élément qui attend
        self.assertEqual(self.taches(etape="flux:livraison"), [])
        self.etat = regles.nouvel_etat()
        d, actions = self.repondre(verdict="valider")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.piloter(actions, rapports=[{"statut": "fait", "message": {"texte": "Livré."}}])
        self.assertEqual(len(self.taches(etape="flux:livraison")), 1)
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")

    def test_un_element_en_attente_du_directeur_ne_retient_pas_le_suivant(self):
        """Parallélisme (2026-11-12) : les places vont aux tâches qui mènent à la validation. Deux éléments attendent le
        Directeur : ils ne comptent plus parmi les éléments au travail, e3 part vers la validation (avant : il
        attendait)."""
        self.projet_avec_validation(elements=3)
        deux = {"statut": "fait", "message": {"texte": "Testé."}, "acces": ACCES, **DIT, "verdicts": [
            {"element": e, "conforme": True, "points": []} for e in ("e1", "e2")]}
        rapports = [{"statut": "fait", "message": {"texte": "Programmé."}}, deux]    # un agent pour chaque lot de deux
        self.piloter(regles.avancer(self.projet, self.etat), rapports=rapports)
        self.assertEqual({d["element"]["id"] for d in self.decisions()}, {"e1", "e2"})
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}},
            {**verdict("e3"), "message": {"texte": "Testé."}, "acces": ACCES, **DIT}])
        self.assertEqual(self.fonc()["file"], [])
        self.assertEqual({d["element"]["id"] for d in self.decisions()}, {"e1", "e2", "e3"})
        self.assertEqual(self.taches(etape="flux:livraison"), [])
        self.assertNotEqual(self.fonc()["etape"], "terminee")

    # --- Parallélisme et barrières (conception 2026-11-12-parallelisme-design.md).

    def file_avec(self, **validations):
        """Deux éléments e1, e2 ; `validations` : l'élément -> les étapes de validation qui le concernent."""
        elements = [dict(x, **({"validations": validations[x["id"]]} if x["id"] in validations else {}))
                    for x in DECOUPAGE["elements"][:2]]
        self.ok("file", entree={"fonctionnalite": "f1", "elements": elements})

    def jusqu_aux_validations(self):
        """e1 et e2 programmés et testés ensemble (un lot à chaque étape)."""
        deux = {"statut": "fait", "message": {"texte": "Testé."}, "acces": ACCES, **DIT, "verdicts": [
            {"element": e, "conforme": True, "points": []} for e in ("e1", "e2")]}
        return self.piloter(regles.avancer(self.projet, self.etat),
                            rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, deux])

    def test_barriere_retient_la_suite_tant_qu_un_element_concerne_attend(self):
        self.projet_avec_validation(elements=2)
        self.jusqu_aux_validations()
        d1 = next(d for d in self.decisions() if d["element"]["id"] == "e1")
        _, actions = self.traiter(type="valider_etape", decision=d1["id"], verdict="valider")
        self.assertEqual([a for a in actions if a[0] == "agent"], [])          # e2 attend encore : rien après la barrière
        (livraison,) = self.taches(etape="flux:livraison")
        self.assertFalse(livraison["active"])
        self.assertEqual([a for a in regles.avancer(self.projet, self.etat) if a[0] == "agent"], [])
        self.assertEqual(self.etat["attente_validation"]["texte"],
                         "2 places libres : en attente de votre validation « Validation du Directeur »")
        d2 = self.decisions()[0]
        _, actions = self.traiter(type="valider_etape", decision=d2["id"], verdict="valider")
        agents_partis = [a for a in actions if a[0] == "agent"]
        self.assertEqual(sorted(i for a in agents_partis for i in a[2]),
                         sorted(t["id"] for t in self.taches(etape="flux:livraison")))
        self.assertEqual(len(self.taches(etape="flux:livraison")), 2)
        regles.avancer(self.projet, self.etat)
        self.assertNotIn("attente_validation", self.etat)

    def test_element_non_concerne_passe_sans_arret_mais_attend_la_barriere(self):
        self.projet_avec_validation(elements=0)
        self.file_avec(e2=[])                                   # e1 : toutes (défaut), e2 : aucune
        self.jusqu_aux_validations()
        self.assertEqual([d["element"]["id"] for d in self.decisions()], ["e1"])
        self.assertEqual(self.taches(etape="validation:valider", element="e2"), [])
        (l2,) = self.taches(etape="flux:livraison", element="e2")
        self.assertFalse(l2["active"])                          # retenue : e1 n'est pas encore validé
        _, actions = self.traiter(type="valider_etape", decision=self.decisions()[0]["id"], verdict="valider")
        self.assertEqual(sorted(i for a in actions if a[0] == "agent" for i in a[2]),
                         sorted(t["id"] for t in self.taches(etape="flux:livraison")))

    def test_validations_du_decoupage_filtrees_et_gardees_dans_la_file(self):
        self.projet_avec_validation(elements=0)
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "decoupage"})
        o = dict(DECOUPAGE, elements=[dict(DECOUPAGE["elements"][0], validations=["valider", "inconnue"],
                                           objectif="L'écran d'accueil du jeu.")])
        try:
            regles._apres_decouper(self.projet, o, {"fonctionnalite": "f1"}, self.etat)
        except regles.Refus:
            pass
        e1 = self.ok("detail", entree={"fonctionnalite": "f1"})["elements"]["e1"]
        self.assertEqual((e1["validations"], e1["objectif"]), (["valider"], "L'écran d'accueil du jeu."))

    def test_objectif_et_a_valider_en_tete_de_la_decision(self):
        self.projet_avec_validation(elements=0)
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"][2]["raison"] = "voir l'apk d'essai avant de le livrer"
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.ok("file", entree={"fonctionnalite": "f1", "elements": [dict(DECOUPAGE["elements"][0])]})
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}},
            {**verdict("e1"), "message": {"texte": "Testé."}, "acces": ACCES, **DIT}])
        (d,) = self.decisions()
        self.assertEqual(d["objectif"], "Produire « Accueil » (écrans), jusqu'à l'étape « Tests et essai du jeu ».")
        self.assertEqual(d["a_valider"], "Validation du Directeur — voir l'apk d'essai avant de le livrer")

    def test_objectif_du_decoupage_rappele(self):
        self.projet_avec_validation(elements=0)
        self.ok("file", entree={"fonctionnalite": "f1", "elements": [
            dict(DECOUPAGE["elements"][0], objectif="L'écran d'accueil, avec le logo et le bouton Jouer.")]})
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}},
            {**verdict("e1"), "message": {"texte": "Testé."}, "acces": ACCES, **DIT}])
        self.assertEqual(self.decisions()[0]["objectif"], "L'écran d'accueil, avec le logo et le bouton Jouer.")

    def test_compte_rendu_garde_ses_sauts_de_ligne_et_son_tableau(self):
        """Vu en vrai : un tableau Markdown du compte rendu s'affichait sur une seule ligne. Les sauts de ligne vont du
        rapport à la décision, pour le compte rendu de l'élément comme pour le texte d'un lot réparti par élément."""
        tableau = "Ajustements (equilibrage.gd)\n\n| Valeur | Avant | Après |\n|---|---|---|\n| COUT | 20 | 40 |"
        self.projet_avec_validation(elements=2)
        self.fichier("pieces/f1/e1.apk")
        self.fichier("pieces/f1/e2.apk")
        lot = {"statut": "fait", **DIT, "verdicts": [{"element": e, "conforme": True, "points": []} for e in ("e1", "e2")],
               "fichiers": [{"chemin": f"pieces/f1/{e}.apk", "titre": f"Apk {e}", "element": e} for e in ("e1", "e2")],
               "message": {"texte": "Accueil (e1) : vert\n| e1 | 1 |\nProfil (e2) : rien."},
               "comptes_rendus": [{"element": "e2", "texte": tableau}]}
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, lot])
        par = {d["element"]["id"]: d for d in self.decisions()}
        self.assertEqual(par["e2"]["compte_rendu"], tableau)
        self.assertEqual(par["e1"]["compte_rendu"], "Accueil (e1) : vert\n| e1 | 1 |")      # les lignes restent des lignes

    def test_sous_chaque_element_seulement_son_compte_rendu(self):
        """Vu en vrai : les rapports de deux éléments d'un même lot apparaissaient sous chacun."""
        self.projet_avec_validation(elements=2)
        for c in ("pieces/f1/e1-ecran.png", "pieces/f1/e2-ecran.png", "pieces/f1/e2.apk"):
            self.fichier(c)
        lot = {"statut": "fait", **DIT, "verdicts": [{"element": e, "conforme": True, "points": []} for e in ("e1", "e2")],
               "message": {"texte": "Accueil (e1) : tout est vert.\n\nProfil (e2) : un menu à revoir.",
                           "images": [{"chemin": "pieces/f1/e1-ecran.png", "legende": "Accueil"},
                                      {"chemin": "pieces/f1/e2-ecran.png", "legende": "Profil"}]},
               "fichiers": [{"chemin": "pieces/f1/commun.md", "titre": "Commun"},
                            {"chemin": "pieces/f1/e2.apk", "titre": "Apk du profil", "element": "e2"}]}
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, lot])
        par = {d["element"]["id"]: d for d in self.decisions()}
        self.assertEqual(par["e1"]["compte_rendu"], "Accueil (e1) : tout est vert.")
        self.assertEqual(par["e2"]["compte_rendu"], "Profil (e2) : un menu à revoir.")
        self.assertEqual([f["chemin"] for f in par["e1"]["fichiers"]], ["pieces/f1/e1-ecran.png"])
        self.assertEqual([f["chemin"] for f in par["e2"]["fichiers"]], ["pieces/f1/e2.apk", "pieces/f1/e2-ecran.png"])

    def test_comptes_rendus_par_element_l_emportent(self):
        self.projet_avec_validation(elements=2)
        self.fichier("pieces/f1/p.png")
        lot = {"statut": "fait", "verdicts": [{"element": e, "conforme": True, "points": []} for e in ("e1", "e2")],
               "message": {"texte": "Les deux écrans sont testés."},
               "comptes_rendus": [{"element": "e1", "texte": "Accueil : vert.", "acces": ACCES, **DIT},
                                  {"element": "e2", "texte": "Profil : vert.",
                                   "images": [{"chemin": "pieces/f1/p.png", "legende": "Le profil"}],
                                   "doit_marcher": "Le profil s'affiche.", "pas_encore": "", "conclusion": "Validez."}]}
        self.piloter(regles.avancer(self.projet, self.etat),
                     rapports=[{"statut": "fait", "message": {"texte": "Programmé."}}, lot])
        par = {d["element"]["id"]: d for d in self.decisions()}
        self.assertEqual((par["e1"]["compte_rendu"], par["e1"]["fichiers"]), ("Accueil : vert.", []))
        self.assertEqual(par["e2"]["fichiers"], [{"chemin": "pieces/f1/p.png", "titre": "Le profil"}])

    def test_les_taches_avant_une_validation_passent_d_abord(self):
        self.projet_avec_validation(elements=2)
        court = self.ok("etat")
        barrieres, _ = regles._barrieres(self.projet, court)
        self.assertEqual(barrieres["f1"]["premiere"], 2)
        self.assertTrue(regles._avant_une_validation({"etape": "flux:essai", "fonctionnalite": "f1"}, barrieres))
        self.assertFalse(regles._avant_une_validation({"etape": "flux:livraison", "fonctionnalite": "f1"}, barrieres))
        self.assertTrue(regles._avant_une_validation({"etape": "cadrage", "fonctionnalite": "f2"}, barrieres))

    def test_places_locales(self):
        self.projet_avec_validation(elements=0)
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["agents_locaux_max"] = 1
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for titre, role, etape in (("A", "dev", "flux:dev"), ("B", "testeur", "flux:essai")):
            self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": role, "colonne": "dev",
                                     "etape": etape, "active": False})
        partis = [a for a in regles._demarrer_en_attente(self.projet, self.etat, None) if a[0] == "agent"]
        self.assertEqual(len(partis), 1)
        self.assertEqual(regles._places(self.projet, self.ok("etat"))["locaux"], 0)
        self.assertEqual([a for a in regles._demarrer_en_attente(self.projet, self.etat, None) if a[0] == "agent"], [])

    def test_pause_globale_au_dessus_de_tout(self):
        self.projet_avec_validation(elements=1)
        self.projet.pause_globale = "Pause : installation de Godot"
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertNotIn("attente_validation", self.etat)

    def test_reglage_du_parallelisme(self):
        d, _ = self.traiter(type="parallelisme", agents_locaux_max=3, agents_cloud_max=2)
        self.assertIn("au plus 3 agents locaux et 2 agents cloud", self.statut(d["id"])["reponse"])
        f = fa.lire(self.factory)
        self.assertEqual((f["agents_locaux_max"], f["agents_cloud_max"]), (3, 2))
        d, _ = self.traiter(type="parallelisme", agents_locaux_max=0, agents_cloud_max=2)
        self.assertIn("agents_locaux_max", self.statut(d["id"])["reponse"])
        self.assertEqual(fa.lire(self.factory)["agents_locaux_max"], 3)

    def test_relecture_sans_relecteur_ignore_la_validation(self):
        self.projet_avec_validation(flux=[
            {"id": "dev", "nom": "Programmation", "role": "dev", "service": "dev"}, self.VAL,
            {"id": "livraison", "nom": "Livraison", "role": "livreur", "service": "livraison"}])
        production = regles._production(self.projet, "f1")
        self.assertEqual(len(production), 3)
        self.assertEqual(regles._etape_de_relecture(self.projet, "f1"), 2)    # la livraison, jamais la validation
        self.assertEqual([s["id"] for s in wf.etapes_d_agent(production)], ["dev", "livraison"])
        self.assertEqual(regles._role_production(self.projet, "f1"), "dev")
        self.assertEqual(regles._colonne_du_role(self.projet, "livreur", "f1"), "livraison")

    def test_proposition_avec_validation_prefixee(self):
        """La décision `organisation` d'une fonctionnalité dont le workflow a une validation : acceptée, puis suivie."""
        flux = [{"id": "f1-dev", "nom": "Programmation", "role": "dev", "service": "dev"},
                {"id": "f1-valider", "nom": "Validation du Directeur", "validation": True},
                {"id": "f1-livraison", "nom": "Livraison", "role": "dev", "service": "dev"}]
        self.fonctionnalite("cadrage")
        o = {"services": [{"id": "metier", "nom": "Métier"}, {"id": "dev", "nom": "Dev"}], "flux": flux, "agents": [],
             "briefs": {}, "cout": {"tokens": [1, 2], "euros": None}, "fonctionnalite": "f1",
             "workflow": {"id": "w-f1", "genre": None, "flux": flux}, "livrable": "L'apk.", "environnement": [],
             "outils_installation": []}
        o["briefs"] = {"dev": "# Brief du rôle : dev"}
        d = self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "organisation", "texte": "ok ?",
                                        "organisation": o})
        self.ok("organisation", entree={"action": "appliquer", "decision": d["id"]})
        f = fa.lire(self.factory)
        w = next(x for x in f["workflows"] if x["id"] == "w-f1")
        self.assertEqual(w["flux"][1], {"id": "f1-valider", "nom": "Validation du Directeur", "validation": True})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie", "workflow": "w-f1",
                                          "methode": {"version": 1, "chemin": "pieces/f1/m.md"}})
        self.ok("file", entree={"fonctionnalite": "f1", "elements": DECOUPAGE["elements"][:1]})
        self.piloter(regles.avancer(self.projet, self.etat))
        self.assertEqual([t["etape"] for t in self.taches(fonctionnalite="f1") if t["etape"] != "cadrage"][:1],
                         ["flux:f1-dev"])
        cols = [c["id"] for c in self.ok("releve")["colonnes"]]
        self.assertIn("f1-valider", cols)


if __name__ == "__main__":
    unittest.main()
