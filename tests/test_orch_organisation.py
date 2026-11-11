"""La décision et la commande `organisation` : l'organisation qui évolue (tâche 10)."""
import json

from bureau import releve
from tests.orch_aide import AvecProjet

FICHE_AUTRE = ("Clé : bruit-1\nPrénom : Zoé\nRôle : bruit\nService : dev\nModèle : Haiku\nLieu : local\n\n"
               "Fait du bruit.\n\n## Leçons\n")
COUT = {"tokens": [20000, 60000], "euros": None}


def organisation(**extra):
    o = {"services": [{"id": "metier", "nom": "Métier"}, {"id": "dev", "nom": "Dev"}, {"id": "son", "nom": "Son"}],
         "flux": [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
                  {"id": "son", "nom": "Sonorisation", "role": "son", "service": "son"}],
         "agents": [{"cle": "son-1", "prenom": "Mia", "role": "son", "service": "son", "modele": "Sonnet",
                     "lieu": "local", "texte": "Compose les sons."}],
         "briefs": {"son": "# Brief du rôle : son\n\nCompose.", "dev": "# Brief du rôle : dev\n\nCode."},
         "cout": dict(COUT)}
    o.update(extra)
    return o


def poser(organisation_, **extra):
    return {"action": "poser", "portee": "projet", "genre": "organisation", "texte": "Un service son",
            "organisation": organisation_, **extra}


class TestOrganisation(AvecProjet):
    def lire_factory(self):
        return json.loads(self.factory.read_text(encoding="utf-8"))

    def poser(self, o=None):
        return self.ok("decision", entree=poser(o or organisation()))["id"]

    def test_decision_organisation_valide(self):
        i = self.poser()
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        d = next(x for x in r["decisions_projet"] if x["id"] == i)
        self.assertEqual(d["genre"], "organisation")
        self.assertEqual(d["organisation"]["cout"], COUT)
        self.assertEqual(self.poser(), i)   # la même décision posée deux fois n'en crée qu'une

    def test_decision_organisation_fable_refuse(self):
        o = organisation()
        o["agents"][0]["modele"] = "Fable"
        code, sortie = self.outil("decision", entree=poser(o))
        self.assertEqual(code, 1, sortie)
        self.assertIn("Fable", json.dumps(sortie))

    def test_decision_organisation_refus_du_contenu(self):
        for nom, o in (("service inconnu", organisation(flux=[{"id": "x", "nom": "X", "role": "dev", "service": "zz"}])),
                       ("clé prise", organisation(agents=[{"cle": "dev-1", "role": "son", "service": "son",
                                                           "modele": "Sonnet", "lieu": "local", "texte": "t"}])),
                       ("brief manquant", organisation(briefs={"dev": "# B"})),
                       ("coût absent", {k: v for k, v in organisation().items() if k != "cout"}),
                       ("coût renversé", organisation(cout={"tokens": [9, 1], "euros": None}))):
            code, sortie = self.outil("decision", entree=poser(o))
            self.assertEqual(code, 1, (nom, sortie))
        self.assertEqual(self.ok("etat")["decisions"], [])

    def test_appliquer_organisation(self):
        i = self.poser()
        r = self.ok("lancer", "organisation", entree={"action": "appliquer", "decision": i})
        self.assertTrue(r["ok"])
        self.assertEqual([s["id"] for s in r["services"]], ["metier", "dev", "son"])
        self.assertEqual([e["id"] for e in r["flux"]], ["dev", "son"])
        f = self.lire_factory()
        self.assertEqual([s["id"] for s in f["services"]], ["metier", "dev", "son"])
        self.assertIn("son", [e["id"] for e in f["flux"]])
        self.assertTrue((self.dossier / "fiches" / "son-1.md").is_file())
        self.assertTrue((self.dossier / "fiches" / "briefs" / "son.md").is_file())
        self.assertEqual(self.ok("etat")["decisions"], [])   # décision levée

    def test_appliquer_garde_les_autres_cles(self):
        d = self.lire_factory()
        d["mots_interdits"] = ["Secret"]
        d["commandes"] = {"etat": ["x"]}
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        i = self.poser()
        self.ok("lancer", "organisation", entree={"action": "appliquer", "decision": i})
        f = self.lire_factory()
        self.assertEqual(f["mots_interdits"], ["Secret"])
        self.assertEqual(f["commandes"], {"etat": ["x"]})
        self.assertEqual(f["reglages"], "reglages.json")

    def test_service_qui_a_encore_des_agents_jamais_retire(self):
        # retirer « dev » laisserait la fiche dev-1 dans un service qui n'existe plus
        o = organisation(services=[{"id": "metier", "nom": "Métier"}, {"id": "son", "nom": "Son"}],
                         flux=[{"id": "son", "nom": "Sonorisation", "role": "son", "service": "son"}])
        code, sortie = self.outil("lancer", "decision", entree=poser(o))
        self.assertEqual(code, 1, sortie)
        self.assertIn("dev", sortie["erreur"])

    def test_refus_etape_service_inconnu(self):
        i = self.poser()
        d = self.lire_factory()
        # le projet a changé depuis la décision : le service « son » existe déjà avec une fiche prise
        (self.dossier / "fiches" / "son-1.md").write_text(FICHE_AUTRE, encoding="utf-8")
        avant = self.factory.read_text(encoding="utf-8")
        code, sortie = self.outil("lancer", "organisation", entree={"action": "appliquer", "decision": i})
        self.assertEqual(code, 1, sortie)
        self.assertEqual(self.factory.read_text(encoding="utf-8"), avant)
        self.assertEqual(len(self.ok("etat")["decisions"]), 1)   # la décision reste
        self.assertEqual(d["services"], self.lire_factory()["services"])

    def test_appliquer_decision_inconnue_ou_autre_genre(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "session_cloud",
                                    "texte": "S", "agent": "dev-1"})
        autre = self.ok("etat")["decisions"][0]["id"]
        for entree in ({"action": "appliquer", "decision": "zz"}, {"action": "appliquer", "decision": autre},
                       {"action": "appliquer"}, {"action": "defaire", "decision": autre}):
            self.assertEqual(self.outil("lancer", "organisation", entree=entree)[0], 1, entree)

    def test_actions_organisation_est_une_demande(self):
        i = self.poser()
        r = self.ok("actions", entree={"type": "organisation", "decision": i, "verdict": "accepter"})
        self.assertTrue(r["ok"])


class TestFableSurAccord(AvecProjet):
    def test_tache_sur_fable_seulement_pour_un_agent_accorde(self):
        t = self.ok("tache", entree={"titre": "A", "role": "dev", "colonne": "dev", "active": False})["id"]
        for entree in ({"id": t, "modele_depart": "Fable"}, {"id": t, "modele_depart": "fable", "agent": "dev-1"},
                       {"id": t, "montee": {"de": "Opus", "a": "Fable", "raison": "x"}}):
            self.assertEqual(self.outil("tache", entree=entree)[0], 1, entree)
        (self.dossier / "fiches" / "archi.md").write_text(
            "Clé : archi-1\nRôle : archi\nModèle : Fable\nLieu : local\nFable : accordé par le Directeur le 2026-11-12\n\n"
            "Conçoit.\n\n## Leçons\n", encoding="utf-8")
        self.ok("tache", entree={"id": t, "role": "archi", "agent": "archi-1", "modele_depart": "Fable"})
        # l'accord de l'un ne vaut pas pour un autre agent, ni pour une montée
        self.assertEqual(self.outil("tache", entree={"id": t, "agent": "dev-1", "modele_depart": "Fable"})[0], 1)
        self.assertEqual(self.outil("tache", entree={"id": t, "montee": {"de": "Opus", "a": "Fable",
                                                                         "raison": "x"}})[0], 1)


def organisation_de_fonctionnalite(fid="f1", **extra):
    flux = [{"id": f"{fid}-dev", "nom": "Développement", "role": "dev", "service": "dev"},
            {"id": f"{fid}-son", "nom": "Livraison des sons", "role": "son", "service": "son"}]
    o = organisation(flux=flux, fonctionnalite=fid, livrable="Les sons",
                     workflow={"id": f"w-{fid}", "genre": "jeu-mobile", "flux": [dict(x) for x in flux]},
                     environnement=[{"outil": "Java", "pour": "dev", "executables": ["java"], "installation": "x",
                                     "etat": "a_installer"}], outils_installation=["Bash(winget:*)"])
    o["agents"][0].update(modele="Opus", justification="Conception.", fable_suggere=True)
    o.update(extra)
    return o


class TestWorkflowDeFonctionnalite(AvecProjet):
    def nouvelle(self):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Un jeu"})
        (self.dossier / "fiches" / "briefs").mkdir(exist_ok=True)
        (self.dossier / "fiches" / "briefs" / "dev.md").write_text("Brief dev.", encoding="utf-8")
        return "f1"

    def lire_factory(self):
        return json.loads(self.factory.read_text(encoding="utf-8"))

    def poser(self, o=None):
        return self.ok("decision", entree=poser(o or organisation_de_fonctionnalite()))["id"]

    def test_decision_d_un_workflow_valide_et_lisible_au_releve(self):
        self.nouvelle()
        i = self.poser()
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        d = next(x for x in r["decisions_projet"] if x["id"] == i)
        self.assertEqual(d["organisation"]["workflow"]["id"], "w-f1")
        self.assertEqual(d["organisation"]["agents"][0]["fable_suggere"], True)
        self.assertEqual(self.poser(), i)

    def test_decision_d_un_workflow_refusee(self):
        self.nouvelle()
        base = organisation_de_fonctionnalite()
        etape_prise = dict(base["flux"][0], id="dev")
        cas = {"fonctionnalité inconnue": {**base, "fonctionnalite": "f9"},
               "workflow sans id": {**base, "workflow": {"genre": "x", "flux": base["flux"]}},
               "workflow réservé": {**base, "workflow": {**base["workflow"], "id": "principal"}},
               "flux différent": {**base, "workflow": {**base["workflow"], "flux": base["flux"][:1]}},
               "genre invalide": {**base, "workflow": {**base["workflow"], "genre": "Pas Valide"}},
               "étape déjà prise": {**base, "flux": [etape_prise, base["flux"][1]],
                                    "workflow": {**base["workflow"], "flux": [etape_prise, base["flux"][1]]}},
               "fable_suggere": {**base, "agents": [dict(base["agents"][0], fable_suggere="oui")]},
               "environnement": {**base, "environnement": ["java"]}}
        for nom, o in cas.items():
            code, sortie = self.outil("decision", entree=poser(o))
            self.assertEqual(code, 1, (nom, sortie))
        self.assertEqual(self.ok("etat")["decisions"], [])

    def appliquer(self, **plus):
        self.nouvelle()
        i = self.poser()
        return self.outil("lancer", "organisation", entree={"action": "appliquer", "decision": i, **plus})

    def test_appliquer_ajoute_le_workflow_sans_toucher_au_flux(self):
        code, r = self.appliquer()
        self.assertEqual(code, 0, r)
        self.assertEqual((r["workflow"], r["fonctionnalite"], r["genre"]), ("w-f1", "f1", "jeu-mobile"))
        f = self.lire_factory()
        self.assertEqual([e["id"] for e in f["flux"]], ["dev", "relecture"])
        self.assertEqual([(w["id"], w["fonctionnalite"], w["genre"]) for w in f["workflows"]],
                         [("w-f1", "f1", "jeu-mobile")])
        self.assertEqual([e["id"] for e in f["workflows"][0]["flux"]], ["f1-dev", "f1-son"])
        self.assertEqual([s["id"] for s in f["services"]], ["metier", "dev", "son"])
        self.assertEqual(f["environnement"][0]["outil"], "Java")
        fonc = self.ok("etat")["fonctionnalites"][0]
        self.assertEqual((fonc["genre"], fonc["workflow"]), ("jeu-mobile", "w-f1"))
        self.assertEqual(self.ok("etat")["decisions"], [])
        self.assertEqual(releve.valider(self.ok("releve")), [])

    def test_appliquer_sans_fable_coche_garde_opus(self):
        self.appliquer()
        fiche = (self.dossier / "fiches" / "son-1.md").read_text(encoding="utf-8")
        self.assertIn("Modèle : Opus", fiche)
        self.assertNotIn("Fable", fiche)

    def test_appliquer_avec_fable_coche(self):
        code, r = self.appliquer(fable=["son-1"])
        self.assertEqual(code, 0, r)
        fiche = (self.dossier / "fiches" / "son-1.md").read_text(encoding="utf-8")
        self.assertIn("Modèle : Fable", fiche)
        self.assertRegex(fiche, r"Fable : accordé par le Directeur le \d{4}-\d{2}-\d{2}")
        self.assertEqual(next(a for a in self.ok("etat")["agents"] if a["cle"] == "son-1")["modele"], "Fable")

    def test_fable_refuse_pour_un_agent_non_suggere_ou_mal_forme(self):
        self.nouvelle()
        i = self.poser()
        for fable in (["dev-1"], ["inconnu"], "son-1", [3]):
            code, r = self.outil("lancer", "organisation", entree={"action": "appliquer", "decision": i, "fable": fable})
            self.assertEqual(code, 1, (fable, r))
        self.assertEqual(len(self.ok("etat")["decisions"]), 1)          # la décision reste
        self.assertFalse((self.dossier / "fiches" / "son-1.md").exists())

    def test_appliquer_refuse_une_etape_devenue_prise(self):
        self.nouvelle()
        i = self.poser()
        d = self.lire_factory()
        d["workflows"] = [{"id": "ailleurs", "fonctionnalite": None, "genre": None,
                           "flux": [{"id": "f1-dev", "nom": "X", "role": "dev", "service": "dev"}]}]
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        code, r = self.outil("lancer", "organisation", entree={"action": "appliquer", "decision": i})
        self.assertEqual(code, 1, r)
        self.assertEqual(len(self.ok("etat")["decisions"]), 1)

    def test_decision_genre_fonctionnalite(self):
        self.nouvelle()
        entree = {"action": "poser", "portee": "f1", "genre": "genre_fonctionnalite", "texte": "Où ?",
                  "propose": "jeu-mobile", "genres_connus": ["badges"], "incertain": False,
                  "nouveau": {"id": "jeu-mobile", "description": "Jeux pour téléphone"}}
        i = self.ok("decision", entree=entree)["id"]
        self.assertEqual(self.ok("decision", entree=entree)["id"], i)
        d = self.ok("detail", entree={"fonctionnalite": "f1"})["decisions"][0]
        self.assertEqual((d["propose"], d["incertain"], d["nouveau"]["id"]), ("jeu-mobile", False, "jeu-mobile"))
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        for refus in ({"propose": "Pas Valide"}, {"propose": None}, {"genres_connus": ["Pas Valide"]},
                      {"incertain": "oui"}, {"nouveau": {"id": "jeu-mobile"}}, {"nouveau": "jeu"},
                      {"portee": "f9"}):
            code, sortie = self.outil("decision", entree={**entree, "texte": "Autre ?", **refus})
            self.assertEqual(code, 1, (refus, sortie))

    def test_confirmer_genre_porte_la_fonctionnalite_qui_attend(self):
        self.nouvelle()
        entree = {"action": "poser", "portee": "projet", "genre": "confirmer_genre", "texte": "Genre ?",
                  "propose": "badges", "genres_connus": ["badges"], "fonctionnalite": "f1"}
        i = self.ok("decision", entree=entree)["id"]
        d = next(x for x in self.ok("etat")["decisions"] if x["id"] == i)
        self.assertEqual(d["fonctionnalite"], "f1")
        self.assertEqual(self.outil("decision", entree={**entree, "texte": "Autre ?", "fonctionnalite": "f9"})[0], 1)

    def test_actions_genre_fonctionnalite_est_une_demande(self):
        self.nouvelle()
        r = self.ok("actions", entree={"type": "genre_fonctionnalite", "decision": "d1", "fonctionnalite": "f1",
                                       "choix": "ici"})
        self.assertTrue(r["ok"])
