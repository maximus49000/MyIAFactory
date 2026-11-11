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
