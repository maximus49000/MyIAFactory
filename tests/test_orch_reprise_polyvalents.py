"""La reprise d'un projet ouvert aux agents polyvalents (conception 2026-11-13-agents-polyvalents-design.md) : un métier par
rôle, les leçons regroupées par métier sans perte ni doublon, l'équipe ramenée aux places, aucune tâche touchée,
rejouable sans effet. Dossiers temporaires seulement."""
import json

from bureau import releve
from orchestrateur import fiches, metiers, reprise_polyvalents
from orchestrateur import suivi as su
from tests.orch_aide import AvecProjet

FICHE = ("Clé : {cle}\nPrénom : {prenom}\nRôle : {role}\nService : {service}\nModèle : {modele}\nLieu : {lieu}\n"
         "{extra}\n{texte}\n\n## Leçons\n{lecons}")


def fiche(cle, role, lieu, *, prenom=None, service="dev", modele="Sonnet", session=None, specialite=None, outils=None,
          texte=None, lecons=()):
    extra = "".join(f"{nom} : {valeur}\n" for nom, valeur in (("Session", session), ("Spécialité", specialite),
                                                               ("Outils", outils)) if valeur)
    return FICHE.format(cle=cle, prenom=prenom or cle.title(), role=role, service=service, modele=modele, lieu=lieu,
                        extra=extra, texte=texte or f"Tu es {role}.",
                        lecons="".join(f"- [{etat}] {i} : {t}\n" for etat, i, t in lecons))


# Un projet comme ZooRunner : 10 fiches, 5 locales et 5 cloud, des places 2 locaux + 3 cloud.
ZOO = {
    "dev-1": fiche("dev-1", "dev", "local", outils="Read, Edit, Bash(gradle:*)", specialite="écrans",
                   lecons=[("validée", "dev-1:L1", "Toujours lancer les tests."),
                           ("à valider", "dev-1:L2", "Nommer les écrans comme la maquette.")]),
    "dev-2": fiche("dev-2", "dev", "cloud", session="https://claude.ai/code/session_dev2",
                   lecons=[("validée", "dev-2:L1", "Toujours lancer les tests."),     # le même texte que dev-1:L1
                           ("validée", "dev-2:L2", "Garder les ressources petites.")]),
    "designer-1": fiche("designer-1", "designer", "local", service="art", modele="Opus", outils="Read, Write",
                        lecons=[("validée", "designer-1:L1", "Palette de six couleurs au plus.")]),
    "designer-2": fiche("designer-2", "designer", "cloud", service="art", modele="Opus"),
    "designer-3": fiche("designer-3", "designer", "cloud", service="art", modele="Opus",
                        lecons=[("à valider", "designer-3:L1", "Exporter en PNG.")]),
    "graphiste-1": fiche("graphiste-1", "graphiste", "local", service="art", modele="Haiku", outils="Read, Bash(magick:*)"),
    "qa-1": fiche("qa-1", "qa", "cloud", service="qualite", session="https://claude.ai/code/session_qa1",
                  lecons=[("validée", "qa-1:L1", "Essayer sur l'émulateur.")]),
    "release-1": fiche("release-1", "release", "cloud", service="qualite", modele="Haiku"),
    "equilibreur-1": fiche("equilibreur-1", "equilibreur", "local", service="qualite"),
    "metier-1": fiche("metier-1", "cadrage", "local", service="metier", modele="Opus"),
}
TOUTES_LES_LECONS = {
    "Toujours lancer les tests.", "Nommer les écrans comme la maquette.", "Garder les ressources petites.",
    "Palette de six couleurs au plus.", "Exporter en PNG.", "Essayer sur l'émulateur."}


class Base(AvecProjet):
    locaux, cloud = 2, 3

    def setUp(self):
        super().setUp()
        self.fiches = self.dossier / "fiches"
        self.briefs = self.fiches / "briefs"
        for c in self.fiches.glob("*.md"):
            c.unlink()
        for cle, texte in self.contenu().items():
            (self.fiches / f"{cle}.md").write_text(texte, encoding="utf-8")
        self.briefs.mkdir(exist_ok=True)
        (self.briefs / "dev.md").write_text("# Brief des développeurs\n\nÉcris le code des écrans.\n", encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(agents_locaux_max=self.locaux, agents_cloud_max=self.cloud)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.preparer_suivi()

    def contenu(self):
        return ZOO

    def preparer_suivi(self):
        """Les leçons « à valider » sont aussi au suivi, comme le moteur les y inscrit."""
        with su.Suivi(self.suivi_chemin()).transaction() as s:
            for i, agent, texte in (("dev-1:L2", "dev-1", "Nommer les écrans comme la maquette."),
                                    ("designer-3:L1", "designer-3", "Exporter en PNG.")):
                s["lecons"].append({"id": i, "agent": agent, "tache": None, "date": "2026-11-01", "texte": texte,
                                    "etat": "à valider", "etage_propose": "projet", "texte_general": None,
                                    "roles": ["tous"]})

    def suivi_chemin(self):
        from orchestrateur import factory as fa
        return fa.lire(self.factory)["suivi"]

    def tache_active(self, agent, titre="Travail"):
        return self.ok("tache", entree={"titre": titre, "role": "dev", "agent": agent, "active": True})["id"]

    def reprendre(self):
        return self.ok("polyvalents", entree={"confirme": True})

    def equipe(self):
        return fiches.lire_toutes(self.fiches)

    def metier(self, role):
        return metiers.lire_metier(self.briefs, role)

    def textes_des_lecons(self):
        return [le["texte"] for m in metiers.lire_tous(self.briefs).values() for le in m["lecons"]]

    def instantane(self):
        """Tout ce que la reprise a le droit de toucher, en octets, pour comparer deux états."""
        racine = self.dossier
        return {str(c.relative_to(racine)): c.read_bytes() for c in sorted(racine.rglob("*"))
                if c.is_file() and c.suffix in (".md", ".json") and ".verrou" not in c.name
                and c.name != "presence.json"}


class TestReprise(Base):
    def test_reprise_zoo_like(self):
        r = self.reprendre()
        roles = {"dev", "designer", "graphiste", "qa", "release", "equilibreur", "cadrage"}
        self.assertEqual({m["role"] for m in r["metiers"]}, roles)
        self.assertEqual({c.stem for c in self.briefs.glob("*.md")}, roles)
        # les métiers : service, modèle et outils d'une fiche du rôle ; texte du brief gardé ou pris de la fiche
        dev = self.metier("dev")
        self.assertEqual((dev["service"], dev["modele"], dev["specialite"]), ("dev", "Sonnet", "écrans"))
        self.assertEqual(dev["outils"], "Read, Edit, Bash(gradle:*)")
        self.assertIn("Écris le code des écrans.", dev["texte"])
        self.assertEqual(dev["lieu"], "indifférent")               # une fiche locale et une cloud
        designer = self.metier("designer")
        self.assertEqual((designer["service"], designer["modele"], designer["texte"]), ("art", "Opus", "Tu es designer."))
        self.assertEqual(self.metier("graphiste")["lieu"], "local")     # toutes locales, des outils déclarés
        self.assertEqual(self.metier("graphiste")["modele"], "Haiku")
        self.assertEqual(self.metier("equilibreur")["lieu"], "indifférent")   # locale mais sans outils déclarés
        self.assertEqual(self.metier("qa")["lieu"], "indifférent")            # cloud
        # les leçons : toutes présentes une fois, le doublon exact fusionné, les ids gardés
        textes = self.textes_des_lecons()
        self.assertEqual(sorted(textes), sorted(TOUTES_LES_LECONS))
        self.assertEqual(r["lecons_regroupees"], len(TOUTES_LES_LECONS))
        self.assertEqual(r["doublons"], 1)
        ids = {le["id"]: le["etat"] for le in dev["lecons"]}
        self.assertEqual(ids["dev-1:L1"], "validée")
        self.assertEqual(ids["dev-1:L2"], "à valider")
        self.assertEqual(ids["dev-2:L2"], "validée")
        self.assertNotIn("dev-2:L1", ids)
        # l'équipe : 2 locaux + 3 cloud, ceux qui ont une session gardés d'abord, tous polyvalents et sans leçon
        equipe = self.equipe()
        self.assertEqual(len(equipe), 5)
        self.assertTrue(all(fiches.est_polyvalente(x) and not x["lecons"] for x in equipe))
        self.assertEqual(sorted(x["cle"] for x in equipe if x["lieu"] == "local"), ["designer-1", "dev-1"])
        cloud = {x["cle"]: x for x in equipe if x["lieu"] == "cloud"}
        self.assertEqual(sorted(cloud), ["designer-2", "dev-2", "qa-1"])
        self.assertEqual(cloud["dev-2"]["session"], "https://claude.ai/code/session_dev2")
        self.assertEqual(cloud["qa-1"]["session"], "https://claude.ai/code/session_qa1")
        self.assertEqual(sorted(r["agents_gardes"]), ["designer-1", "designer-2", "dev-1", "dev-2", "qa-1"])
        self.assertEqual(sorted(r["agents_retires"]), ["designer-3", "equilibreur-1", "graphiste-1", "metier-1",
                                                       "release-1"])
        self.assertIn("5 agents", r["compte_rendu"])
        # les leçons « à valider » du suivi vont à leur métier, même si l'agent a disparu
        suivi = su.Suivi(self.suivi_chemin()).lire()
        self.assertEqual({x["id"]: x.get("metier") for x in suivi["lecons"]},
                         {"dev-1:L2": "dev", "designer-3:L1": "designer"})
        # l'original de chaque fiche est mis de côté
        self.assertEqual(len(list((self.fiches / "avant-polyvalents").glob("*.md"))), 10)
        self.assertIn("Toujours lancer les tests.",
                      (self.fiches / "avant-polyvalents" / "dev-2.md").read_text(encoding="utf-8"))
        # le relevé reste valide
        releve_ = self.ok("releve")
        self.assertEqual(releve.valider(releve_), [], releve.valider(releve_))
        # le compte rendu est dans le journal du projet
        journal = self.suivi_chemin().with_name("reprise-polyvalents.md").read_text(encoding="utf-8")
        self.assertIn("5 agents", journal)

    def test_validation_apres_reprise_va_au_metier(self):
        self.reprendre()
        self.ok("lecon", entree={"action": "appliquer", "id": "dev-1:L2", "verdict": "valider"})
        self.ok("lecon", entree={"action": "appliquer", "id": "designer-3:L1", "verdict": "valider"})
        etats = {le["id"]: le["etat"] for le in self.metier("dev")["lecons"]}
        self.assertEqual(etats["dev-1:L2"], "validée")
        self.assertEqual({le["id"]: le["etat"] for le in self.metier("designer")["lecons"]},
                         {"designer-1:L1": "validée", "designer-3:L1": "validée"})
        self.assertEqual(self.textes_des_lecons().count("Nommer les écrans comme la maquette."), 1)

    def test_reprise_rejouee_sans_effet(self):
        premiere = self.reprendre()
        avant = self.instantane()
        seconde = self.reprendre()
        self.assertEqual(self.instantane(), avant)
        self.assertEqual(seconde["lecons_regroupees"], 0)
        self.assertEqual(seconde["doublons"], 0)
        self.assertEqual(seconde["agents_retires"], [])
        self.assertEqual(sorted(seconde["agents_gardes"]), sorted(premiere["agents_gardes"]))
        self.assertIn("déjà", seconde["compte_rendu"])
        self.assertEqual(sorted(self.textes_des_lecons()), sorted(TOUTES_LES_LECONS))

    def test_reprise_interrompue_puis_rejouee(self):
        # 1. interrompue après les métiers, 2. après les leçons, 3. à mi-chemin des fiches
        ctx = self.contexte()
        reprise_polyvalents.mettre_de_cote(ctx)
        reprise_polyvalents.fixer_les_metiers(ctx)
        self.assertEqual(len(self.equipe()), 10)
        reprise_polyvalents.regrouper_les_lecons(ctx)
        self.assertEqual(len(self.equipe()), 10)                     # les fiches gardent encore leurs leçons
        self.assertEqual(sorted(self.textes_des_lecons()), sorted(TOUTES_LES_LECONS))
        # une fiche déjà réécrite en polyvalente, les autres non
        a_reecrire = fiches.trouver(self.equipe(), "dev-1")
        fiches.ecrire_fiche({**fiches.nouvelle_fiche("dev-1", "Dev-1", "local"), "chemin": a_reecrire["chemin"]})
        r = self.reprendre()
        self.assertEqual(sorted(self.textes_des_lecons()), sorted(TOUTES_LES_LECONS))       # ni perdue ni dupliquée
        self.assertEqual(len(self.textes_des_lecons()), len(TOUTES_LES_LECONS))
        equipe = self.equipe()
        self.assertEqual((len([x for x in equipe if x["lieu"] == "local"]), len([x for x in equipe if x["lieu"] == "cloud"])),
                         (2, 3))
        self.assertEqual(len(list((self.fiches / "avant-polyvalents").glob("*.md"))), 10)
        self.assertIn("dev-1", r["agents_gardes"])
        # la sauvegarde de dev-1 est son fichier d'origine, pas la fiche réécrite
        self.assertIn("Toujours lancer les tests.",
                      (self.fiches / "avant-polyvalents" / "dev-1.md").read_text(encoding="utf-8"))

    def contexte(self):
        from orchestrateur import outil
        return outil.Contexte(self.factory)

    def test_aucune_tache_touchee(self):
        t = self.tache_active("equilibreur-1", "Équilibrer le niveau 3")
        self.ok("tache", entree={"titre": "Autre", "role": "qa", "agent": "qa-1", "active": False})
        avant = json.dumps(su.Suivi(self.suivi_chemin()).lire()["taches"], sort_keys=True)
        self.reprendre()
        apres = json.dumps(su.Suivi(self.suivi_chemin()).lire()["taches"], sort_keys=True)
        self.assertEqual(apres, avant)
        self.assertTrue(su.tache(su.Suivi(self.suivi_chemin()).lire(), t)["active"])

    def test_agent_au_travail_garde(self):
        # un local et un cloud sans session au travail : gardés avant les autres
        self.tache_active("equilibreur-1")
        self.tache_active("designer-3")
        r = self.reprendre()
        equipe = {x["cle"]: x for x in self.equipe()}
        self.assertIn("equilibreur-1", equipe)
        self.assertIn("designer-3", equipe)
        self.assertEqual(sorted(x["cle"] for x in equipe.values() if x["lieu"] == "local"), ["designer-1", "equilibreur-1"])
        self.assertEqual(sorted(x["cle"] for x in equipe.values() if x["lieu"] == "cloud"),
                         ["designer-3", "dev-2", "qa-1"])
        self.assertFalse(any(x["retrait_prevu"] for x in equipe.values()))
        self.assertNotIn("equilibreur-1", r["agents_retires"])

    def test_plus_d_agents_au_travail_que_de_places(self):
        for cle in ("dev-1", "designer-1", "graphiste-1"):       # trois locaux au travail, deux places
            self.tache_active(cle)
        r = self.reprendre()
        equipe = {x["cle"]: x for x in self.equipe()}
        locaux = sorted(x["cle"] for x in equipe.values() if x["lieu"] == "local")
        self.assertEqual(locaux, ["designer-1", "dev-1", "graphiste-1"])      # aucun agent au travail n'est retiré
        self.assertEqual([k for k, x in equipe.items() if x["retrait_prevu"]], ["graphiste-1"])
        self.assertEqual(r["retraits_prevus"], ["graphiste-1"])
        # il part à la fin de sa tâche
        tache = next(t for t in su.Suivi(self.suivi_chemin()).lire()["taches"] if t["agent"] == "graphiste-1")
        self.ok("tache", entree={"id": tache["id"], "colonne": "fait", "active": False})
        self.ok("equipe")
        self.assertEqual(sorted(x["cle"] for x in self.equipe() if x["lieu"] == "local" and not x["retire"]),
                         ["designer-1", "dev-1"])
        self.assertTrue(fiches.trouver(self.equipe(), "graphiste-1")["retire"])     # gardé pour l'historique

    def test_aucun_agent_cloud_au_dela_des_places(self):
        self.reprendre()
        self.assertEqual(len([x for x in self.equipe() if x["lieu"] == "cloud"]), 3)

    def test_aucun_agent_cloud_cree(self):
        for cle in ("dev-2", "designer-2", "designer-3", "release-1"):
            (self.fiches / f"{cle}.md").unlink()       # une seule fiche cloud (qa-1) pour 3 places
        r = self.reprendre()
        cloud = [x for x in self.equipe() if x["lieu"] == "cloud"]
        self.assertEqual([x["cle"] for x in cloud], ["qa-1"])
        self.assertEqual(r["agents_crees"], [])

    def test_locaux_manquants_crees_jusqu_aux_places(self):
        for cle in ("designer-1", "graphiste-1", "equilibreur-1", "metier-1"):
            (self.fiches / f"{cle}.md").unlink()       # une seule fiche locale (dev-1) pour 2 places
        r = self.reprendre()
        locaux = [x for x in self.equipe() if x["lieu"] == "local"]
        self.assertEqual(len(locaux), 2)
        self.assertEqual(len(r["agents_crees"]), 1)
        self.assertTrue(all(fiches.est_polyvalente(x) for x in self.equipe()))

    def test_places_sans_reglage_ancienne_limite(self):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        del f["agents_cloud_max"]
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.reprendre()
        self.assertEqual(len([x for x in self.equipe() if x["lieu"] == "cloud"]), 3)      # l'ancienne limite, 3

    def test_confirmation_exigee(self):
        code, objet = self.outil("polyvalents", entree={})
        self.assertEqual(code, 1)
        self.assertEqual(len(self.equipe()), 10)

    def test_projet_deja_polyvalent_rien_a_faire(self):
        for c in self.fiches.glob("*.md"):
            c.unlink()
        (self.fiches / "agent-1.md").write_text("Clé : agent-1\nPrénom : Zoé\nLieu : local\n", encoding="utf-8")
        avant = self.instantane()
        r = self.reprendre()
        self.assertEqual(self.instantane(), avant)
        self.assertIn("déjà", r["compte_rendu"])

    def test_chef_et_brief_illisible_gardes(self):
        (self.fiches / "chef.md").write_text(fiche("chef", "chef", "local", service="metier", modele="Opus"),
                                             encoding="utf-8")
        self.reprendre()
        self.assertIn("chef", [x["cle"] for x in self.equipe()])           # le chef n'est pas un agent polyvalent
        self.assertNotIn("chef", {c.stem for c in self.briefs.glob("*.md")})

    def test_releve_dit_la_reprise_possible(self):
        self.assertIs(self.ok("releve")["recrutement"]["reprise_possible"], True)
        self.reprendre()
        r = self.ok("releve")
        self.assertIs(r["recrutement"]["reprise_possible"], False)
        self.assertIs(r["recrutement"]["polyvalent"], True)


class Demande(Base):
    """Le clic du Directeur : le bureau le vérifie, l'outil l'accepte, le moteur le traite."""

    def test_le_bureau_verifie_le_clic(self):
        from bureau import demandes
        r = self.ok("releve")
        verifier = lambda d, rel=r: demandes.verifier(demandes.nettoyer(d), rel)      # noqa: E731
        self.assertIsNone(verifier({"type": "passer_polyvalent", "confirme": True}))
        self.assertIn("clic", verifier({"type": "passer_polyvalent", "confirme": "oui"}))
        self.assertIn("clic", verifier({"type": "passer_polyvalent"}))
        self.assertIn("version 4", verifier({"type": "passer_polyvalent", "confirme": True}, {"version": 3}))
        self.assertIn("mettez à jour", verifier({"type": "passer_polyvalent", "confirme": True}, {"version": 4}))
        self.reprendre()
        self.assertIn("déjà", verifier({"type": "passer_polyvalent", "confirme": True}, self.ok("releve")))
        self.assertEqual(demandes.nettoyer({"type": "passer_polyvalent", "confirme": True, "x": 1}),
                         {"type": "passer_polyvalent", "confirme": True})

    def test_le_moteur_traite_la_demande(self):
        from moteur import regles
        projet = regles.Projet(self.factory, feu_vert=lambda: True, prerequis=lambda: None)
        etat = regles.nouvel_etat()
        i = self.ok("actions", entree={"type": "passer_polyvalent", "confirme": True})["id"]
        d = next(x for x in self.ok("demandes")["demandes"] if x["id"] == i)
        regles.traiter_demande(projet, d, etat)
        statut = next(x for x in su.Suivi(self.suivi_chemin()).lire()["demandes"] if x["id"] == i)
        self.assertEqual(statut["statut"], "traitée")
        self.assertIn("Passage aux agents polyvalents", statut["reponse"])
        self.assertEqual(len(self.equipe()), 5)
        self.assertTrue(all(fiches.est_polyvalente(x) for x in self.equipe()))
