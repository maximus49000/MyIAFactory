"""Création et installation au nouveau format (conception 2026-11-13-agents-polyvalents-design.md) : une organisation porte
des métiers (un brief par rôle) et le nombre d'agents locaux et cloud ; la mise en place écrit les briefs enrichis et les
fiches polyvalentes, et règle les places. L'ancien format reste accepté. Aucun appel réel."""
import copy
import json

from installation import mise_en_place as mep
from installation import proposition
from installation.dossier import Echec
from orchestrateur import factory as fa
from orchestrateur import fiches, metiers
from tests.inst_aide import AvecMaison, proposition_valide
from tests.orch_aide import AvecProjet
from tests.test_inst_definition import Base as BaseDefinition
from tests.test_inst_mise_en_place import MAINTENANT, Base

METIERS = [
    {"role": "dev", "service": "dev", "modele": "Sonnet", "specialite": "écrans du jeu", "outils": "Read, Edit, Bash(gradle:*)",
     "brief": "# Brief du métier : dev\n\nÉcris le code."},
    {"role": "relecteur", "service": "qa", "modele": "Haiku", "lieu": "local",
     "brief": "# Brief du métier : relecteur\n\nRelis."},
]


def poly(**extra):
    """Les champs du nouveau format à poser sur une proposition valide à l'ancienne."""
    corps = {"metiers": copy.deepcopy(METIERS), "agents": {"locaux": 3, "cloud": 0}, "agents_locaux_max": 3}
    corps.update(copy.deepcopy(extra))
    return corps


def sans_briefs(p):
    p = copy.deepcopy(p)
    p.pop("briefs", None)
    return p


class Verification(AvecMaison):
    def proposition(self, **extra):
        p = proposition_valide(self.projet)
        p.pop("briefs")
        p.update(poly(**extra))
        return p

    def test_organisation_polyvalente_verifiee(self):
        self.assertEqual(proposition.verifier(self.proposition()), [])
        p = self.proposition(agents={"locaux": 2, "cloud": 1}, cloud=True, agents_locaux_max=2)
        p["metiers"][0]["lieu"] = "cloud"
        self.assertEqual(proposition.verifier(p), [])
        # le nombre d'agents : locaux de 1 à 16, cloud de 0 à 16, et pas de cloud si la proposition est locale
        for agents in ({"locaux": 0, "cloud": 0}, {"locaux": 17, "cloud": 0}, {"locaux": 1, "cloud": -1},
                       {"locaux": 1}, [], {"locaux": 1, "cloud": 1}):
            e = proposition.verifier(self.proposition(agents=agents, agents_locaux_max=1))
            self.assertTrue(e, agents)
        # un modèle Fable est refusé : l'accord se donne tâche par tâche
        p = self.proposition()
        p["metiers"][0]["modele"] = "Fable"
        self.assertTrue(any("Fable" in x for x in proposition.verifier(p)))
        # un lieu inconnu, un brief vide, un service inconnu, un métier en double
        p = self.proposition()
        p["metiers"][0].update(lieu="ailleurs")
        p["metiers"][1].update(brief="  ", service="nulle-part")
        p["metiers"].append(dict(METIERS[0]))
        e = " ".join(proposition.verifier(p))
        for attendu in ("lieu", "brief", "service inconnu", "en double"):
            self.assertIn(attendu, e)

    def test_role_sans_metier_refuse(self):
        p = self.proposition()
        p["metiers"] = [METIERS[0]]
        e = proposition.verifier(p)
        self.assertEqual([x for x in e if "relecteur" in x], ["Aucun métier pour le rôle « relecteur »."])
        # un brief déjà en place tient lieu de métier (organisation ajoutée à un projet installé)
        self.assertEqual(proposition.verifier_organisation(p["services"], p["flux"], {"locaux": 1, "cloud": 0}, None,
                                                           metiers=p["metiers"], briefs_existants={"relecteur"}), [])

    def test_equipe_deja_en_place_sans_nombre(self):
        p = self.proposition()
        sans = proposition.verifier_organisation(p["services"], p["flux"], None, None, metiers=p["metiers"])
        self.assertTrue(sans)      # un projet neuf doit dire combien d'agents
        ok = proposition.verifier_organisation(p["services"], p["flux"], None, None, metiers=p["metiers"],
                                               equipe_en_place=True)
        self.assertEqual(ok, [])

    def test_ancienne_organisation_acceptee(self):
        self.assertEqual(proposition.verifier(proposition_valide(self.projet)), [])
        self.assertFalse(proposition.est_polyvalente([{"cle": "dev-1"}]))
        self.assertTrue(proposition.est_polyvalente({"locaux": 1, "cloud": 0}))

    def test_nombre_locaux_egal_aux_places(self):
        e = proposition.verifier(self.proposition(agents={"locaux": 3, "cloud": 0}, agents_locaux_max=2))
        self.assertTrue(any("agents_locaux_max" in x for x in e))

    def test_estimation_sans_plafond(self):
        p = self.proposition()
        agents = proposition.agents_pour_estimer(p["metiers"])
        self.assertEqual([(a["role"], a["modele"]) for a in agents], [("dev", "Sonnet"), ("relecteur", "Haiku")])
        self.assertTrue(all(a["sans_plafond"] for a in agents))


class MiseEnPlace(Base):
    def appliquer_poly(self, **extra):
        self.lier_skill()
        p = proposition_valide(self.projet)
        p.pop("briefs")
        p.update(poly(**extra))
        return mep.appliquer(p, MAINTENANT, git=self.git_simule, adresses=self.adresses)

    def test_mise_en_place_ecrit_metiers_et_agents(self):
        self.appliquer_poly()
        f = fa.lire(self.projet / ".factory" / "factory.json")
        self.assertEqual((f["agents_locaux_max"], f["agents_cloud_max"]), (3, 0))
        lues = fiches.lire_toutes(f["fiches"])
        self.assertEqual(len(lues), 3)
        self.assertTrue(all(fiches.est_polyvalente(x) and x["lieu"] == "local" for x in lues))
        self.assertEqual(len({x["cle"] for x in lues}), 3)
        self.assertEqual(len({x["prenom"] for x in lues}), 3)
        briefs = f["fiches"] / "briefs"
        dev = metiers.lire_metier(briefs, "dev")
        self.assertEqual((dev["service"], dev["modele"], dev["specialite"]), ("dev", "Sonnet", "écrans du jeu"))
        self.assertEqual(dev["outils"], "Read, Edit, Bash(gradle:*)")
        self.assertIn("Écris le code.", dev["texte"])
        self.assertEqual(dev["lieu"], "indifférent")
        self.assertEqual(metiers.lire_metier(briefs, "relecteur")["lieu"], "local")

    def test_mise_en_place_cloud_regle_les_places(self):
        self.appliquer_poly(agents={"locaux": 2, "cloud": 2}, cloud=True, agents_locaux_max=2)
        f = fa.lire(self.projet / ".factory" / "factory.json")
        self.assertEqual((f["agents_locaux_max"], f["agents_cloud_max"]), (2, 2))
        lues = fiches.lire_toutes(f["fiches"])
        self.assertEqual(sorted(x["lieu"] for x in lues), ["cloud", "cloud", "local", "local"])
        self.assertTrue(all(x["session"] is None for x in lues))

    def test_ecrire_organisation_ajoute_des_metiers_sans_toucher_l_equipe(self):
        self.appliquer_poly()
        chemin = self.projet / ".factory" / "factory.json"
        f = fa.lire(chemin)
        services = [dict(s) for s in f["services"]]
        flux = [{"id": "mixage", "nom": "Mixage", "role": "mixeur", "service": "dev"}]
        # un projet qui a déjà son équipe : pas de nombre d'agents, aucune fiche ajoutée
        mep.ecrire_organisation(chemin, services, flux, None, {}, workflow={"id": "w-son", "genre": None,
                                                                            "fonctionnalite": None},
                                metiers=[{"role": "mixeur", "service": "dev", "brief": "Mixe."}])
        self.assertEqual(len(fiches.lire_toutes(f["fiches"])), 3)
        self.assertEqual(metiers.lire_metier(f["fiches"] / "briefs", "mixeur")["texte"], "Mixe.")

    def test_ecrire_organisation_refuse_sans_rien_ecrire(self):
        self.appliquer_poly()
        chemin = self.projet / ".factory" / "factory.json"
        f = fa.lire(chemin)
        avant = sorted(c.name for c in f["fiches"].rglob("*"))
        with self.assertRaises(Echec):    # le rôle du flux n'a pas de métier
            mep.ecrire_organisation(chemin, [dict(s) for s in f["services"]],
                                    [{"id": "mixage", "nom": "Mixage", "role": "mixeur", "service": "dev"}], None, {},
                                    workflow={"id": "w-son", "genre": None, "fonctionnalite": None}, metiers=[])
        self.assertEqual(sorted(c.name for c in f["fiches"].rglob("*")), avant)

    def test_ancien_format_inchange(self):
        self.appliquer()
        f = fa.lire(self.projet / ".factory" / "factory.json")
        self.assertIsNone(f.get("agents_cloud_max"))
        self.assertEqual(sorted(x["cle"] for x in fiches.lire_toutes(f["fiches"])), ["dev-1", "relecteur-1"])
        self.assertTrue(all(not fiches.est_polyvalente(x) for x in fiches.lire_toutes(f["fiches"])))


# --- Le chef propose des métiers et un nombre d'agents ; la création les écrit ; la proposition d'une fonctionnalité aussi.

def proposition_chef(**extra):
    """Ce que le chef rend (`definir_workflow`) au nouveau format."""
    from tests.test_inst_definition import proposition
    o = proposition()
    for cle in ("agents", "briefs"):
        del o[cle]
    o["metiers"] = [{"role": "dev", "service": "dev", "modele": "Sonnet", "specialite": "le jeu",
                     "brief": "Écris le code du jeu."},
                    {"role": "livreur", "service": "dev", "modele": "Haiku", "lieu": "local", "brief": "Remets l'apk."}]
    o["agents"] = {"locaux": 2, "cloud": 0}
    o.update(copy.deepcopy(extra))
    return o


class Chef(AvecMaison):
    """Le jugement valide les deux formats ; la proposition calculée et la création écrivent le nouveau."""

    def valider(self, o, d=None):
        from moteur import jugement
        return jugement._valider_proposer_organisation(o, d or {"services": [], "agents": [], "fonctionnalite": "f1"})

    def test_chef_nouveau_format_valide_et_ancien_aussi(self):
        from tests.test_inst_definition import proposition
        o = proposition_chef()
        flux = [dict(x, etape=x["etape"]) for x in o["flux"]]
        self.assertIsNone(self.valider(dict(o, flux=flux)))
        self.assertIsNone(self.valider(proposition()))

    def test_chef_refus_du_nouveau_format(self):
        for nom, o in (("sans le nombre d'agents", {k: v for k, v in proposition_chef().items() if k != "agents"}),
                       ("nombre faux", proposition_chef(agents={"locaux": 0, "cloud": 0})),
                       ("rôle sans métier", proposition_chef(metiers=proposition_chef()["metiers"][:1])),
                       ("Fable par défaut", proposition_chef(metiers=[dict(proposition_chef()["metiers"][0], modele="Fable"),
                                                                       proposition_chef()["metiers"][1]])),
                       ("briefs mêlés", dict(proposition_chef(), briefs={"dev": "x"})),
                       ("lieu inconnu", proposition_chef(metiers=[dict(proposition_chef()["metiers"][0], lieu="mars"),
                                                                   proposition_chef()["metiers"][1]]))):
            self.assertIsNotNone(self.valider(o), nom)

    def test_chef_projet_a_l_ancienne_garde_l_ancien_format(self):
        d = {"services": [], "agents": [{"cle": "dev-1", "role": "dev"}], "fonctionnalite": "f1"}
        e = self.valider(proposition_chef(), d)
        self.assertIn("agents par rôle", e)

    def test_chef_projet_polyvalent_equipe_en_place(self):
        d = {"services": [], "agents": [{"cle": "agent-1", "role": None}], "fonctionnalite": "f1",
             "metiers": [{"role": "dev", "service": "dev"}]}
        o = proposition_chef(metiers=[proposition_chef()["metiers"][1]])
        del o["agents"]          # l'équipe est celle des places : pas de nombre à donner
        self.assertIsNone(self.valider(o, d))
        o["metiers"] = [dict(o["metiers"][0], role="dev")]      # un métier du projet reproposé
        self.assertIn("déjà au projet", self.valider(o, d))

    def test_proposition_calculee_porte_metiers_et_agents(self):
        from installation import definition
        from tests.test_inst_definition import INFOS, a_installer, prix
        p = definition.proposition_calculee(proposition_chef(), dict(INFOS, facturation=False),
                                            verifier_environnement=a_installer, prix_de=prix)
        self.assertNotIn("briefs", p)
        self.assertEqual(p["agents"], {"locaux": 2, "cloud": 0})
        roles = [m["role"] for m in p["metiers"]]
        self.assertEqual(roles, ["dev", "livreur", "environnement"])     # l'installation est un métier, pas un agent
        self.assertEqual(p["installateur"], "environnement")
        self.assertIn("2 agents locaux, 0 agent cloud", p["texte"])
        self.assertIn("dev, service", p["texte"])
        self.assertEqual(len(p["cout"]["tokens"]), 2)
        self.assertEqual(p["workflow"]["flux"][0]["role"], "dev")
        self.assertNotIn("plafond", p["texte"])


class Creation(BaseDefinition):
    def setUp(self):
        super().setUp()
        from installation import dossier
        from tests.test_inst_creation import Executeur
        self.parent = self.base / "mes projets"
        self.git, self.gh = Executeur(), Executeur()
        self.bureau = dossier.bureau()

    def test_creer_projet_polyvalent(self):
        from installation import brouillons, definition
        from tests.test_inst_definition import GENRES, INFOS, T0, Faux, Pont, a_installer
        infos = dict(INFOS, parent=str(self.parent), nom="Casse-briques")
        b = brouillons.creer(infos, dossier=self.d, maintenant=T0)
        b = definition.tour(b, genres_connus=GENRES, couche="claude", appeler=Faux(proposition_chef()),
                            verifier_environnement=a_installer, maintenant=T0)
        brouillons.ecrire(b, dossier=self.d, maintenant=T0)
        definition.valider(b, installer=True, bureau_json=self.bureau, git=self.git, gh=self.gh, maintenant=T0,
                           dossier=self.d, commun=self.base / "usage.jsonl",
                           executer=Pont({"genre": (0, {"genre": "jeu-android", "cree": True})}))
        f = fa.lire(self.parent / "Casse-briques" / ".factory" / "factory.json")
        lues = fiches.lire_toutes(f["fiches"])
        self.assertEqual(len(lues), 2)
        self.assertTrue(all(fiches.est_polyvalente(x) for x in lues))
        self.assertEqual((f["agents_locaux_max"], f["agents_cloud_max"]), (2, 0))
        briefs = f["fiches"] / "briefs"
        self.assertEqual(sorted(c.stem for c in briefs.glob("*.md")), ["dev", "environnement", "livreur"])
        self.assertEqual(metiers.lire_metier(briefs, "dev")["modele"], "Sonnet")
        self.assertEqual(metiers.lire_metier(briefs, "livreur")["lieu"], "local")
        self.assertIn("Bash(winget:*)", metiers.lire_metier(briefs, "environnement")["outils"])
        w = next(x for x in f["workflows"] if x["id"] == "w-jeu-android")
        self.assertEqual(w["flux"][0]["role"], "dev")


class Decision(AvecProjet):
    """La décision `organisation` du nouveau format : posée, validée par le relevé, appliquée (métiers, pas d'agent de plus)."""

    def organisation(self, **extra):
        o = {"services": [{"id": "metier", "nom": "Métier"}, {"id": "dev", "nom": "Dev"}, {"id": "son", "nom": "Son"}],
             "flux": [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
                      {"id": "son", "nom": "Sonorisation", "role": "son", "service": "son"}],
             "metiers": [{"role": "son", "service": "son", "modele": "Haiku", "brief": "Compose les sons."},
                         {"role": "dev", "service": "dev", "brief": "Code."}],
             "cout": {"tokens": [20000, 60000], "euros": None}}
        o.update(extra)
        return o

    def poser(self, o):
        return self.outil("decision", entree={"action": "poser", "portee": "projet", "genre": "organisation",
                                              "texte": "Un service son", "organisation": o})

    def equipe_polyvalente(self):
        for nom in ("lea.md", "hugo.md"):
            (self.dossier / "fiches" / nom).unlink()
        (self.dossier / "fiches" / "agent-1.md").write_text("Clé : agent-1\nPrénom : Zoé\nLieu : local\n", encoding="utf-8")

    def test_projet_a_l_ancienne_refuse_les_metiers(self):
        code, sortie = self.poser(self.organisation(agents={"locaux": 1, "cloud": 0}))
        self.assertEqual(code, 1, sortie)
        self.assertIn("agents par rôle", json.dumps(sortie, ensure_ascii=False))

    def test_decision_polyvalente_posee_validee_et_appliquee(self):
        from bureau import releve
        self.equipe_polyvalente()
        code, sortie = self.poser(self.organisation())          # l'équipe est en place : pas de nombre d'agents
        self.assertEqual(code, 0, sortie)
        i = sortie["id"]
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        d = next(x for x in r["decisions_projet"] if x["id"] == i)
        self.assertEqual([m["role"] for m in d["organisation"]["metiers"]], ["son", "dev"])
        self.assertNotIn("agents", d["organisation"])
        self.assertNotIn("briefs", d["organisation"])
        self.ok("lancer", "organisation", entree={"action": "appliquer", "decision": i})
        self.assertEqual([x.name for x in (self.dossier / "fiches").glob("*.md")], ["agent-1.md"])
        briefs = self.dossier / "fiches" / "briefs"
        self.assertEqual(metiers.lire_metier(briefs, "son")["modele"], "Haiku")
        self.assertEqual(self.ok("etat")["decisions"], [])

    def test_polyvalent_refuse_les_agents_par_role(self):
        self.equipe_polyvalente()
        o = {"services": [{"id": "metier", "nom": "Métier"}, {"id": "dev", "nom": "Dev"}, {"id": "son", "nom": "Son"}],
             "flux": [{"id": "son", "nom": "Sonorisation", "role": "son", "service": "son"}],
             "agents": [{"cle": "son-1", "role": "son", "service": "son", "modele": "Sonnet", "lieu": "local",
                         "texte": "Compose."}], "briefs": {"son": "Compose."}, "cout": {"tokens": [1, 2], "euros": None}}
        code, sortie = self.poser(o)
        self.assertEqual(code, 1, sortie)
        self.assertIn("agents polyvalents", json.dumps(sortie, ensure_ascii=False))

    def test_fable_refuse_par_agent_dans_une_decision_polyvalente(self):
        self.equipe_polyvalente()
        code, sortie = self.poser(self.organisation(metiers=[{"role": "dev", "service": "dev", "modele": "Fable", "brief": "B"},
                                                             {"role": "son", "service": "son", "brief": "S"}]))
        self.assertEqual(code, 1, sortie)
