"""Le relevé d'un projet polyvalent : le service d'un agent est celui de sa tâche en cours (de son étape, sinon de son
métier) ; chaque tâche dit son service ; les leçons se lisent par métier (conception 2026-11-13-agents-polyvalents-design.md,
« Bureau vivant »). Un projet à l'ancienne garde son relevé d'avant."""
import json

from bureau import etat as modetat
from bureau import releve
from tests.orch_aide import AvecProjet

FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "qa", "nom": "Recette", "role": "qa", "service": "metier"}]
BRIEF_DEV = "Service : dev\nSpécialité : écrans\n\nBrief dev.\n\n## Leçons\n- [validée] dev:L1 : Toujours tester.\n" \
            "- [à valider] dev:L2 : À juger.\n"
BRIEF_QA = "Service : metier\n\nBrief qa.\n\n## Leçons\n- [validée] qa:L1 : Cas limites.\n"
BRIEF_INCONNU = "Service : nulle-part\n\nBrief.\n"


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(flux=FLUX, agents_locaux_max=2, agents_cloud_max=0)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for nom in ("lea.md", "hugo.md"):
            (self.dossier / "fiches" / nom).unlink()
        briefs = self.dossier / "fiches" / "briefs"
        briefs.mkdir()
        (briefs / "dev.md").write_text(BRIEF_DEV, encoding="utf-8")
        (briefs / "qa.md").write_text(BRIEF_QA, encoding="utf-8")
        for cle, prenom in (("agent-1", "Zoé"), ("agent-2", "Max")):
            (self.dossier / "fiches" / f"{cle}.md").write_text(f"Clé : {cle}\nPrénom : {prenom}\nLieu : local\n",
                                                               encoding="utf-8")
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def tache(self, role, agent=None, etape=None, active=True):
        e = {"titre": f"Travail {role}", "role": role, "active": active, "agent": agent,
             "colonne": role if role in ("dev", "qa") else "dev"}
        if etape is not None:
            e.update(fonctionnalite="f1", etape=etape, element="e" + role)
        return self.ok("tache", entree=e)["id"]

    def titulaires(self):
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        return r, {t["cle"]: t for t in r["titulaires"]}


class TestReleveServiceDeLaTache(Base):
    def test_titulaire_suit_le_service_de_sa_tache(self):
        t = self.tache("qa", "agent-1", "flux:qa")        # le service de l'étape : « metier »
        r, ti = self.titulaires()
        self.assertEqual(ti["agent-1"]["service"], "metier")
        self.assertIs(ti["agent-1"]["polyvalent"], True)
        self.assertIsNone(ti["agent-2"]["service"])        # libre : aucun service
        self.assertEqual(next(x for x in r["taches"] if x["id"] == t)["service"], "metier")
        # la même fiche, une autre tâche : elle change de service
        self.ok("tache", entree={"id": t, "active": False, "colonne": "fait"})
        self.tache("dev", "agent-1", "flux:dev")
        self.assertEqual(self.titulaires()[1]["agent-1"]["service"], "dev")

    def test_tache_sans_etape_prend_le_service_du_metier(self):
        t = self.tache("dev", "agent-1")                    # pas d'étape de flux : le brief du métier dit « dev »
        r, ti = self.titulaires()
        self.assertEqual(ti["agent-1"]["service"], "dev")
        self.assertEqual(next(x for x in r["taches"] if x["id"] == t)["service"], "dev")

    def test_service_inconnu_ou_sans_metier_est_nul(self):
        (self.dossier / "fiches" / "briefs" / "fantome.md").write_text(BRIEF_INCONNU, encoding="utf-8")
        t = self.tache("fantome", "agent-1")
        r, ti = self.titulaires()
        self.assertIsNone(ti["agent-1"]["service"])
        self.assertIsNone(next(x for x in r["taches"] if x["id"] == t)["service"])
        t2 = self.tache("sans-brief", "agent-2")
        self.assertIsNone(next(x for x in self.ok("releve")["taches"] if x["id"] == t2)["service"])

    def test_etat_publie_le_service_de_l_agent(self):
        from datetime import datetime
        from bureau.equipe import Equipe
        self.tache("qa", "agent-1", "flux:qa")
        n = releve.normaliser(self.ok("releve"))
        e = modetat.construire(n, Equipe(self.dossier / "equipe.json"), datetime.now().astimezone(), 600)
        a = next(x for x in e["agents"] if x["id"] == "agent-1")
        self.assertEqual((a["service"], a["polyvalent"]), ("metier", True))
        t = next(x for x in e["taches"] if x["titre"] == "Travail qa")
        self.assertEqual(t["service"], "metier")
        self.assertEqual({m["role"] for m in e["metiers"]}, {"dev", "qa"})
        ancien = next(x for x in e["agents"] if x["id"] == "agent-2")
        self.assertEqual((ancien["service"], ancien["polyvalent"]), (None, True))


class TestReleveLeconsParMetier(Base):
    def test_metiers_publies_avec_leurs_lecons(self):
        r, _ = self.titulaires()
        m = {x["role"]: x for x in r["metiers"]}
        self.assertEqual(m["dev"]["service"], "dev")
        self.assertEqual([(le["id"], le["etat"]) for le in m["dev"]["lecons"]], [("dev:L1", "validée"), ("dev:L2", "à valider")])
        self.assertEqual(m["qa"]["lecons"][0]["texte"], "Cas limites.")

    def test_projet_a_l_ancienne_sans_metiers_ni_service_de_tache(self):
        from tests.orch_aide import factory_minimale
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            f = factory_minimale(Path(d))
            code, r = self.outil("releve", factory=f)
            self.assertEqual(code, 0, r)
            self.assertNotIn("metiers", r)
            self.assertTrue(all("service" not in t for t in r["taches"]))
            self.assertTrue(all("polyvalent" not in t for t in r["titulaires"]))
