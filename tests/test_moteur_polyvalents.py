"""Le moteur et les agents polyvalents : n'importe quel agent libre prend la tâche prête, au bon lieu, et aucune tâche dont
l'amont attend une validation du Directeur ne part, par aucun chemin (conception 2026-11-13-agents-polyvalents-design.md).
Aucun appel réel."""
import json
from unittest import mock

from moteur import regles
from tests.orch_aide import AvecProjet

POLYVALENT = "Clé : {cle}\nPrénom : {prenom}\nLieu : {lieu}\n{session}"
ANCIENNE = ("Clé : {cle}\nPrénom : {prenom}\nRôle : dev\nService : dev\nModèle : {modele}\nLieu : local\n\n"
            "Développe.\n\n## Leçons\n")
FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "val", "nom": "Essai", "validation": True},
        {"id": "qa", "nom": "Recette", "role": "qa", "service": "dev"},
        {"id": "archi", "nom": "Architecture", "role": "dev", "service": "dev", "modele": "Opus",
         "justification": "Conception difficile."},
        {"id": "livraison", "nom": "Livraison", "role": "dev", "service": "dev"}]
SESSION = "https://claude.ai/code/session_01Abc"


class Base(AvecProjet):
    locaux, cloud = 2, 0

    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(flux=FLUX, agents_locaux_max=self.locaux, agents_cloud_max=self.cloud)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for nom in ("lea.md", "hugo.md"):
            (self.dossier / "fiches" / nom).unlink()
        self.briefs = self.dossier / "fiches" / "briefs"
        self.briefs.mkdir()
        self.brief("dev", "Service : dev\n\nBrief des développeurs.\n")
        self.brief("qa", "Brief des testeurs.\n")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=self.cloud, prerequis=lambda: None)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def brief(self, role, texte):
        (self.briefs / f"{role}.md").write_text(texte, encoding="utf-8")

    def agent(self, cle, prenom="Zoé", lieu="local", session=None):
        (self.dossier / "fiches" / f"{cle}.md").write_text(
            POLYVALENT.format(cle=cle, prenom=prenom, lieu=lieu, session=f"Session : {session}\n" if session else ""),
            encoding="utf-8")

    def tache(self, etape, element="e1", titre="Écran", **extra):
        entree = {"titre": titre, "fonctionnalite": "f1", "colonne": etape.split(":")[-1], "etape": etape,
                  "element": element, "active": False}
        entree.update(extra)
        if not etape.startswith("validation:"):
            entree["role"] = "qa" if etape == "flux:qa" else "dev"
        return self.ok("tache", entree=entree)["id"]

    def commencee(self, tid, agent):
        """Une tâche déjà prise un moment (son début est noté), plus active."""
        self.ok("tache", entree={"id": tid, "agent": agent, "active": True})
        self.ok("tache", entree={"id": tid, "active": False})

    def faite(self, tid):
        self.ok("tache", entree={"id": tid, "colonne": "fait", "active": False})

    def demarrer(self, etat=None):
        etat = etat if etat is not None else regles.nouvel_etat()
        regles._demarrer_en_attente(self.projet, etat, None)
        return etat

    @staticmethod
    def parties(etat):
        """{tâche: agent} de tout ce qui est parti (lots compris)."""
        return {i: d["agent"] for d in etat["departs"].values() for i in d["taches"]}


class Choix(Base):
    def test_un_agent_prend_des_taches_de_metiers_differents(self):
        self.agent("agent-1")
        t_dev = self.tache("flux:dev", element="e1")
        t_qa = self.tache("flux:qa", element="e2")
        etat = self.demarrer()
        parties = self.parties(etat)
        if t_qa not in parties:       # pas dans le même lot : le même agent la prend après la première
            self.faite(t_dev)
            etat["en_cours"].clear()
            parties.update(self.parties(self.demarrer(etat)))
        self.assertEqual(parties, {t_dev: "agent-1", t_qa: "agent-1"})

    def test_reprise_revient_au_meme_agent_libre(self):
        self.agent("agent-1")
        self.agent("agent-2", prenom="Max")
        t = self.tache("flux:dev")
        self.commencee(t, "agent-2")
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(t)
        self.assertEqual(self.parties(self.demarrer(etat)), {t: "agent-2"})

    def test_reprise_par_un_autre_agent_si_l_ancien_est_occupe(self):
        self.agent("agent-1")
        self.agent("agent-2", prenom="Max")
        occupee = self.tache("flux:dev", element="e9", titre="Autre")
        self.ok("tache", entree={"id": occupee, "agent": "agent-2", "active": True})
        t = self.tache("flux:dev")
        self.commencee(t, "agent-1")
        self.ok("tache", entree={"id": t, "agent": "agent-2"})
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(t)
        self.assertEqual(self.parties(self.demarrer(etat)), {t: "agent-1"})


class Lieux(Base):
    locaux, cloud = 1, 1

    def setUp(self):
        super().setUp()
        self.agent("local-1")
        self.agent("cloud-1", prenom="Max", lieu="cloud", session=SESSION)
        occupee = self.tache("flux:dev", element="e9", titre="Autre")
        self.ok("tache", entree={"id": occupee, "agent": "local-1", "active": True})   # la place locale est prise

    def test_metier_local_attend_une_place_locale(self):
        self.brief("qa", "Lieu : local\n\nBrief des testeurs, avec l'émulateur du poste.\n")
        t = self.tache("flux:qa")
        self.assertNotIn(t, self.parties(self.demarrer()))

    def test_cloud_quand_le_local_est_plein(self):
        t = self.tache("flux:qa")
        self.assertEqual(self.parties(self.demarrer()), {t: "cloud-1"})


class AvecServeur(Base):
    """Deux fiches locales, deux fiches serveur, serveur en ligne, ordre [serveur, local]."""
    locaux, cloud = 2, 0

    def setUp(self):
        super().setUp()
        from orchestrateur import outil
        avant = outil.BUREAU_DEPORT      # aucun plafond d'abonnement : jamais le bureau réel
        outil.BUREAU_DEPORT = str(self.dossier / "absent" / "bureau.json")
        self.addCleanup(setattr, outil, "BUREAU_DEPORT", avant)
        self.en_ligne = mock.patch.object(outil, "serveur_hors_ligne", return_value=False)
        self.en_ligne.start()
        self.addCleanup(self.en_ligne.stop)
        self.regler(serveur=2, ordre=["serveur", "local"])
        self.agent("agent-1", prenom="Hugo")
        self.agent("agent-2", prenom="Léa")
        self.agent("agent-3", prenom="Lucas", lieu="serveur")
        self.agent("agent-4", prenom="Emma", lieu="serveur")

    def regler(self, serveur=None, ordre=None, locaux=None):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        if serveur is not None:
            f["agents_serveur_max"] = serveur
        if ordre is not None:
            f["ordre_lieux"] = ordre
        if locaux is not None:
            f["agents_locaux_max"] = locaux
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def lieu(self, etape, lieu):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = [dict(e, lieu=lieu) if e["id"] == etape else e for e in f["flux"]]
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def lieu_de(self, cle):
        return {"agent-1": "local", "agent-2": "local", "agent-3": "serveur", "agent-4": "serveur"}[cle]


class OrdreDesLieux(AvecServeur):
    """Le choix de l'agent suit l'ordre des lieux du projet (`ordre_lieux`) et ses places serveur (`agents_serveur_max`),
    comptées à part des places locales ; un lieu imposé (étape, métier) l'emporte. Essai réel FM_Stats : ordre [serveur,
    local], deux fiches serveur libres, serveur en ligne, et le prototype partait quand même sur une fiche locale."""

    def test_tache_libre_part_au_serveur(self):
        t = self.tache("flux:dev")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "serveur")

    def test_prototype_part_au_serveur(self):
        t = self.tache("prototype", colonne="dev")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "serveur")

    def test_places_serveur_a_part_des_places_locales(self):
        """Une place serveur prise ne retire aucune place locale : 1 serveur + 1 local, deux tâches, deux départs."""
        self.regler(serveur=1, locaux=1)
        a = self.tache("flux:dev", element="e1")
        b = self.tache("flux:dev", element="e2", titre="Autre")
        parties = self.parties(self.demarrer())
        self.assertEqual(sorted(self.lieu_de(parties[x]) for x in (a, b)), ["local", "serveur"])

    def test_places_serveur_pleines_repli_sur_le_local(self):
        self.regler(serveur=1)
        occupee = self.tache("flux:dev", element="e9", titre="Occupée")
        self.ok("tache", entree={"id": occupee, "agent": "agent-3", "active": True})
        t = self.tache("flux:dev")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_serveur_hors_ligne_repli_sur_le_local(self):
        from orchestrateur import outil
        t = self.tache("flux:dev")
        with mock.patch.object(outil, "serveur_hors_ligne", return_value=True):
            self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_etape_au_lieu_local_reste_locale(self):
        self.lieu("livraison", "local")
        t = self.tache("flux:livraison")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_metier_local_reste_local(self):
        self.brief("qa", "Lieu : local\n\nBrief des testeurs, avec l'émulateur du poste.\n")
        t = self.tache("flux:qa")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_reprise_d_un_agent_serveur_jamais_sur_une_etape_locale(self):
        """Une tâche reprise revient de préférence à son agent : pas s'il est au serveur et que l'étape exige le poste."""
        self.lieu("livraison", "local")
        t = self.tache("flux:livraison")
        self.commencee(t, "agent-3")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_ordre_local_d_abord(self):
        self.regler(ordre=["local", "serveur"])
        t = self.tache("flux:dev")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_lieu_retire_jamais_utilise(self):
        """`ordre_lieux` sans `local` : la place locale libre n'est jamais prise ; serveur plein, la tâche attend."""
        self.regler(serveur=1, ordre=["serveur"])
        occupee = self.tache("flux:dev", element="e9", titre="Occupée")
        self.ok("tache", entree={"id": occupee, "agent": "agent-3", "active": True})
        t = self.tache("flux:dev")
        self.assertNotIn(t, self.parties(self.demarrer()))


PUBSPEC_FLUTTER = "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n"


class CorrectionAuServeur(AvecServeur):
    """Essai réel FM_Stats (2026-11-24) : l'étape de correction d'un projet Flutter partait chez un agent local, qui
    tentait `flutter build apk` au poste (refusé) : aucun APK, validation bloquée. Une étape du flux d'une correction
    d'un projet Flutter part au serveur, jamais en local, même quand l'ordre du projet met le poste d'abord."""

    def setUp(self):
        super().setUp()
        self.regler(ordre=["local", "serveur"])
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Le score est faux", "nature": "correction"})
        self.ok("demande-traitee", entree={"id": "r2"})
        self.ok("fonctionnalite", entree={"id": "f2", "etape": "serie"})

    def flutter(self):
        (self.dossier / "pubspec.yaml").write_text(PUBSPEC_FLUTTER, encoding="utf-8")

    def test_correction_flutter_part_au_serveur(self):
        self.flutter()
        t = self.tache("flux:dev", fonctionnalite="f2")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "serveur")

    def test_correction_flutter_attend_le_serveur_plutot_que_le_poste(self):
        self.flutter()
        self.regler(serveur=1)
        occupee = self.tache("flux:dev", element="e9", titre="Occupée")
        self.ok("tache", entree={"id": occupee, "agent": "agent-3", "active": True})
        t = self.tache("flux:dev", fonctionnalite="f2")
        self.assertNotIn(t, self.parties(self.demarrer()))

    def test_reprise_d_une_correction_flutter_ne_revient_pas_a_l_agent_local(self):
        self.flutter()
        t = self.tache("flux:dev", fonctionnalite="f2")
        self.commencee(t, "agent-1")
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(t)
        self.assertEqual(self.lieu_de(self.parties(self.demarrer(etat))[t]), "serveur")

    def test_fonctionnalite_flutter_part_aussi_au_serveur(self):
        # Essai réel FM_Stats (f8) : les étapes d'une fonctionnalité Flutter partaient chez l'agent du poste.
        self.flutter()
        t = self.tache("flux:dev")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "serveur")

    def test_correction_hors_flutter_suit_l_ordre_du_projet(self):
        t = self.tache("flux:dev", fonctionnalite="f2")
        self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")

    def test_serveur_hors_ligne_la_correction_n_attend_pas_indefiniment(self):
        from orchestrateur import outil
        self.flutter()
        t = self.tache("flux:dev", fonctionnalite="f2")
        with mock.patch.object(outil, "serveur_hors_ligne", return_value=True):
            self.assertEqual(self.lieu_de(self.parties(self.demarrer())[t]), "local")


class Amont(Base):
    """L'élément e1 attend la validation du Directeur (étape « val ») : sa recette (« qa », après la validation) ne part
    par aucun chemin, même avec des places libres ; la barre le dit."""
    locaux, cloud = 2, 1

    def setUp(self):
        super().setUp()
        self.agent("agent-1")
        self.agent("agent-2", prenom="Max")
        self.validation = self.tache("validation:val")
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "valider_etape", "fonctionnalite": "f1",
                                    "texte": "L'élément « e1 » attend votre validation.", "element": {"id": "e1", "nom": "e1"},
                                    "etape": "val", "tache": self.validation})
        self.qa = self.tache("flux:qa")

    def bloquee(self, etat):
        self.assertNotIn(self.qa, self.parties(etat))
        regles._noter_les_places_libres(self.projet, etat)
        self.assertIn("attente_validation", etat)
        self.assertIn("Essai", etat["attente_validation"]["texte"])

    def test_amont_en_validation_bloque_lot(self):
        autre = self.tache("flux:dev", element="e2")
        etat = self.demarrer()
        self.assertIn(autre, self.parties(etat))       # l'autre élément part, lui
        self.assertNotIn(self.qa, self.parties(etat))
        # la place qu'il reste ne sert à rien : la barre le dit
        self.faite(autre)
        etat["en_cours"].clear()
        etat["departs"].clear()
        self.bloquee(self.demarrer(etat))

    def test_amont_en_validation_bloque_a_lancer(self):
        self.commencee(self.qa, "agent-1")
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(self.qa)
        self.bloquee(self.demarrer(etat))

    def test_amont_en_validation_bloque_retour(self):
        self.commencee(self.qa, "agent-1")
        self.ok("tache", entree={"id": self.qa, "bloquee": "Une erreur."})
        etat = regles.nouvel_etat()
        regles._reprendre_la_tache(self.projet, etat, self.qa, "f1", "Reprends avec ma consigne.", "Reprise sur retour.")
        self.bloquee(etat)

    def test_amont_en_validation_bloque_reprise_apres_redemarrage(self):
        self.commencee(self.qa, "agent-1")
        etat = regles.nouvel_etat()      # un moteur neuf : il ne sait rien de la tâche
        self.assertEqual(regles.orphelines(self.projet, etat), [])
        self.bloquee(self.demarrer(etat))

    def test_amont_en_validation_bloque_session_cloud(self):
        self.agent("cloud-1", prenom="Léo", lieu="cloud")
        self.commencee(self.qa, "cloud-1")
        self.ok("tache", entree={"id": self.qa, "bloquee": "session cloud : pas de terminal"})
        d = self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "session_cloud", "agent": "cloud-1",
                                        "tache": self.qa, "texte": "Créez la session."})["id"]
        etat = regles.nouvel_etat()
        regles.traiter_demande(self.projet, {"id": "r9", "type": "session_cloud", "decision": d,
                                             "session": "https://claude.ai/code/session_01Manuel"}, etat)
        t = next(x for x in regles._etat(self.projet)["taches"] if x["id"] == self.qa)
        self.assertFalse(t["active"])
        self.assertNotIn(self.qa, etat["en_cours"])
        self.bloquee(self.demarrer(etat))


class NonRepris(AvecProjet):
    """Un projet aux fiches à l'ancienne : mêmes agents, mêmes modèles qu'avant, même avec des briefs à en-tête."""

    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = FLUX
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        (self.dossier / "fiches" / "lea.md").unlink()
        for cle, prenom, modele in (("dev-o", "Max", "Opus"), ("dev-s", "Léa", "Sonnet")):
            (self.dossier / "fiches" / f"{cle}.md").write_text(ANCIENNE.format(cle=cle, prenom=prenom, modele=modele),
                                                               encoding="utf-8")
        (self.dossier / "fiches" / "briefs").mkdir()
        (self.dossier / "fiches" / "briefs" / "dev.md").write_text("Modèle : Haiku\nLieu : cloud\n\nBrief.\n",
                                                                   encoding="utf-8")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=0, prerequis=lambda: None)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def tache(self, etape, element):
        return self.ok("tache", entree={"titre": "Écran", "fonctionnalite": "f1", "role": "dev", "colonne": "dev",
                                        "etape": etape, "element": element, "active": False})["id"]

    def test_projet_non_repris_choisit_comme_avant(self):
        archi, dev = self.tache("flux:archi", "e1"), self.tache("flux:dev", "e2")
        etat = regles.nouvel_etat()
        regles._demarrer_en_attente(self.projet, etat, "f1")
        vu = {d["taches"][0]: (d["agent"], d["modele"]) for d in etat["departs"].values()}
        self.assertEqual(vu, {archi: ("dev-o", "Opus"), dev: ("dev-s", "Sonnet")})
        # la reprise d'une tâche commencée attend son agent, comme avant
        court = regles._etat(self.projet)
        self.assertEqual(regles._modele_de_depart(self.projet, court, "dev-s",
                                                  next(t for t in court["taches"] if t["id"] == dev)), "Sonnet")


class Regroupement(Base):
    """Le regroupement d'une étape (conception du Directeur) : `parallele` (le défaut) répartit ses tâches sur les places
    libres, une par agent ; `regroupe` les garde en un seul lot pour un seul agent, sans les mêler à une autre étape."""
    locaux = 3

    def setUp(self):
        super().setUp()
        for k in range(1, 4):
            self.agent(f"agent-{k}", prenom=f"P{k}")

    def regrouper(self, etape):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        for e in f["flux"]:
            if e["id"] == etape:
                e["regroupement"] = "regroupe"
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def departs(self, etat):
        return sorted(sorted(d["taches"]) for d in etat["departs"].values())

    def test_en_parallele_par_defaut_les_taches_se_repartissent(self):
        ids = [self.tache("flux:dev", element=f"e{k}", titre=f"Équilibrage {k}") for k in range(1, 4)]
        etat = self.demarrer()
        self.assertEqual(self.departs(etat), sorted([i] for i in ids))
        self.assertEqual(len(set(self.parties(etat).values())), 3)

    def test_regroupees_un_seul_agent_enchaine_toutes_les_taches(self):
        self.regrouper("dev")
        ids = [self.tache("flux:dev", element=f"e{k}", titre=f"Équilibrage {k}") for k in range(1, 4)]
        etat = self.demarrer()
        self.assertEqual(self.departs(etat), [sorted(ids)])       # un seul départ malgré trois places libres
        self.assertEqual(len(set(self.parties(etat).values())), 1)

    def test_regroupees_ne_se_melent_pas_a_une_autre_etape(self):
        self.regrouper("dev")
        dev = [self.tache("flux:dev", element=f"e{k}", titre=f"Équilibrage {k}") for k in range(1, 3)]
        livraison = self.tache("flux:livraison", element="e3", titre="Livrer")
        etat = self.demarrer()
        self.assertEqual(self.departs(etat), sorted([sorted(dev), [livraison]]))

    def test_une_etape_regroupee_ne_regroupe_pas_les_autres(self):
        self.regrouper("livraison")
        dev = [self.tache("flux:dev", element=f"e{k}", titre=f"Écran {k}") for k in range(1, 3)]
        etat = self.demarrer()
        self.assertEqual(self.departs(etat), sorted([i] for i in dev))      # l'étape « dev » reste en parallèle


class RetraitPrevu(Base):
    def test_moteur_retire_l_agent_marque_a_la_fin_de_sa_tache(self):
        self.agent("agent-1")
        (self.dossier / "fiches" / "agent-2.md").write_text(
            "Clé : agent-2\nPrénom : Léa\nLieu : local\nRetrait : prévu\n", encoding="utf-8")
        t = self.tache("flux:dev")
        self.ok("tache", entree={"id": t, "agent": "agent-2", "active": True})
        self.demarrer()
        # au travail : l'agent marqué reste, il n'est ni retiré ni choisi
        self.assertTrue((self.dossier / "fiches" / "agent-2.md").is_file())
        self.ok("tache", entree={"id": t, "colonne": "fait", "active": False})
        self.demarrer()
        # retiré, mais gardé (il a une tâche au suivi) : Retrait : fait
        self.assertIn("Retrait : fait", (self.dossier / "fiches" / "agent-2.md").read_text(encoding="utf-8"))
        self.assertTrue((self.dossier / "fiches" / "agent-1.md").is_file())

    def test_agent_marque_ne_prend_pas_la_tache(self):
        (self.dossier / "fiches" / "agent-2.md").write_text(
            "Clé : agent-2\nPrénom : Léa\nLieu : local\nRetrait : prévu\n", encoding="utf-8")
        self.agent("agent-1")
        t = self.tache("flux:dev")
        self.ok("tache", entree={"id": t, "agent": "agent-2", "active": True})
        t2 = self.tache("flux:dev", element="e2", titre="Autre")
        etat = self.demarrer()
        self.assertEqual(self.parties(etat).get(t2), "agent-1")


class CorrectionSurLePoste(Base):
    """Essai réel : quatre allers-retours ; chaque correction se faisait dans le cloud, sans SDK ni émulateur, rendue
    « non compilée », et le contrôle suivant, sur le poste, trouvait le défaut d'après. Une correction refusée par un
    contrôle du poste se fait sur le poste."""

    def lieu(self, etape, lieu):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = [dict(e, lieu=lieu) if e["id"] == etape else e for e in f["flux"]]
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def corriger_apres(self, etape):
        t = self.tache(etape)
        self.ok("tache", entree={"id": t, "colonne": "fait"})
        etat = regles.nouvel_etat()
        etat["elements"]["f1/e1"] = {"fid": "f1", "element": {"id": "e1", "nom": "Écran"}, "phase": "relecture",
                                     "pas": 2, "tour": 0, "corrections": 0, "taches": [t], "attendus": 1, "rapports": []}
        with mock.patch.object(regles, "reprendre_la_serie"):
            regles._apres_apres_refus(self.projet, {"suite": "corriger", "consigne": "Corriger le test."},
                                      {"fonctionnalite": "f1", "element": "e1"}, etat)
        return next(x for x in regles._etat(self.projet)["taches"] if x.get("etape") == "correction")

    def test_refus_d_un_controle_du_poste_correction_sur_le_poste(self):
        self.lieu("qa", "local")
        c = self.corriger_apres("flux:qa")
        self.assertIs(c.get("sur_le_poste"), True)
        journal = regles._tache(self.projet, c["id"])["journal"]
        self.assertIn("ni « non compilé » ni avec un test rouge", " ".join(j["texte"] for j in journal))

    def test_refus_d_un_controle_ailleurs_correction_comme_avant(self):
        c = self.corriger_apres("flux:qa")
        self.assertFalse(c.get("sur_le_poste"))

    def test_methode_a_revoir_corriger_encore_sur_le_poste(self):
        """« Méthode à revoir ? » → « Non, corriger encore » : une correction de plus, sur le poste, avec le constat du
        dernier contrôle ; la décision est levée."""
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        self.ok("tache", entree={"id": t, "colonne": "fait", "journal": ["Non conforme : 7 tests instrumentés rouges."]})
        self.ok("decision", entree={"action": "poser", "portee": "f1", "genre": "methode_a_revoir",
                                    "texte": "La méthode est peut-être à revoir ? (élément e1)"})
        etat = regles.nouvel_etat()
        etat["elements"]["f1/e1"] = {"fid": "f1", "element": {"id": "e1", "nom": "Écran"}, "phase": "attente_methode",
                                     "pas": 2, "tour": 1, "corrections": 3, "taches": [t], "attendus": 1,
                                     "rapports": []}
        self.ok("actions", entree={"type": "methode", "fonctionnalite": "f1", "verdict": "corriger"})
        suivi = lambda: json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        demande = next(x for x in suivi()["demandes"] if x.get("verdict") == "corriger")
        with mock.patch.object(regles, "reprendre_la_serie"):
            regles.traiter_demande(self.projet, demande, etat)
        c = next(x for x in regles._etat(self.projet)["taches"] if x.get("etape") == "correction")
        self.assertIs(c.get("sur_le_poste"), True)
        journal = " ".join(j["texte"] for j in regles._tache(self.projet, c["id"])["journal"])
        self.assertIn("7 tests instrumentés rouges", journal)
        self.assertEqual(etat["elements"]["f1/e1"]["corrections"], 0)
        self.assertEqual(suivi()["fonctionnalites"][0]["decisions"], [])
