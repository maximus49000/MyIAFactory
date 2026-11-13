"""Un agent arrêté faute d'outil : la commande refusée est lue, le programme connu du projet est ouvert à l'agent et la
tâche repart ; sinon une décision visible au bureau de direction. Cas réel : deux livraisons arrêtées sur « Bash »
restaient inactives, sans décision au bureau, sans reprise. Aucun appel réel."""
import json
import os
import time
import unittest

from moteur import accord_outil, agents, appel, regles
from orchestrateur import fiches as fi
from tests.test_moteur_appel import sortie_claude
from tests.test_moteur_regles import Base, _lu, usage

REFUS_BASH = {"statut": "outil_refuse", "outil": "Bash", "message": {"texte": "Je ne peux pas lancer la commande."}}


class LireLeRefus(unittest.TestCase):
    def sortie(self, refus):
        d = json.loads(sortie_claude())
        d["permission_denials"] = refus
        return json.dumps(d).encode()

    def test_la_commande_refusee_est_lue_dans_le_resultat(self):
        refus = [{"tool_name": "Bash", "tool_use_id": "x", "tool_input": {"command": "godot --headless --export-release"}},
                 {"tool_name": "WebSearch", "tool_input": {"query": "godot"}}, {"tool_name": 3}, "bizarre"]
        r = appel.appeler("c", "d", "sonnet", executer=lambda *a: (0, self.sortie(refus)), outils=["Read"],
                          dossier_travail=".")
        self.assertEqual(r.refus, [{"outil": "Bash", "commande": "godot --headless --export-release"},
                                   {"outil": "WebSearch"}])

    def test_sans_refus_rien(self):
        r = appel.appeler("c", "d", "haiku", executer=lambda *a: (0, sortie_claude()))
        self.assertEqual(r.refus, [])

    def test_l_execution_porte_les_refus_de_l_agent(self):
        rep = appel.Reponse('```json\n{"statut": "outil_refuse", "outil": "Bash", "message": {"texte": "x"}}\n```',
                            [usage()])
        rep.refus = [{"outil": "Bash", "commande": "godot -v"}]
        e = agents.executer_agent("D", "", agent={"cle": "dev-1", "outils": None}, modele="sonnet",
                                  dossier_projet=".", appeler=lambda *a, **k: rep, tache="t1")
        self.assertEqual(e.refus, [{"outil": "Bash", "commande": "godot -v"}])
        self.assertEqual(e.rapport["statut"], "outil_refuse")


class Programme(unittest.TestCase):
    def test_programmes_de_chaque_commande_du_shell(self):
        self.assertEqual(accord_outil.programmes("godot --headless"), ["godot"])
        self.assertEqual(accord_outil.programmes("cd build && godot --export; adb install a.apk | tee x"),
                         ["godot", "adb", "tee"])
        self.assertEqual(accord_outil.programmes("godot.exe -v"), ["godot.exe"])
        self.assertEqual(accord_outil.programmes("cd x"), [])

    def test_un_premier_mot_qui_n_est_pas_un_nom_simple_est_illisible(self):
        for c in ("C:\\outils\\godot.exe -v", "./godot", "$(godot) x", "FOO=1 godot", '"godot" -v', "-rf /", "`ls`",
                  "C:/a/../b.exe -v", "/a/./b", "C:/a$b/c.exe"):
            self.assertIsNone(accord_outil.programmes(c), c)

    def test_un_chemin_absolu_est_un_programme_que_seul_le_directeur_ouvre(self):
        emu = "C:/Users/x/AppData/Local/Android/Sdk/emulator/emulator.exe"
        self.assertEqual(accord_outil.programmes(f"{emu} -list-avds"), [emu])
        self.assertEqual(accord_outil.programme_refuse([f"{emu} -list-avds"], ["Read"]), (emu, f"{emu} -list-avds"))
        self.assertIsNone(accord_outil.origine(emu, [{"outil": "SDK", "executables": ["emulator.exe"]}]))
        self.assertEqual(fi.regle_bash(emu), f"Bash({emu}:*)")
        self.assertEqual(fi.regle_bash("/usr/bin/adb"), "Bash(/usr/bin/adb:*)")

    def test_le_programme_refuse_est_celui_que_la_fiche_n_ouvre_pas(self):
        outils = ["Read", "Bash(py:*)", "Bash(git:*)"]
        self.assertEqual(accord_outil.programme_refuse(["git status", "cd a && godot -v"], outils),
                         ("godot", "cd a && godot -v"))
        self.assertEqual(accord_outil.programme_refuse(["godot -v && adb devices"], outils),
                         (None, "godot -v && adb devices"))      # deux programmes manquent : à décider
        self.assertEqual(accord_outil.programme_refuse(["./x"], outils), (None, "./x"))
        self.assertEqual(accord_outil.programme_refuse([], outils), (None, None))
        self.assertEqual(accord_outil.programme_refuse(["godot -v"], ["Bash"]), (None, "godot -v"))   # tout le shell

    def test_programme_connu_du_projet(self):
        env = [{"outil": "Godot", "etat": "a_installer", "executables": ["Godot.exe", "godot4"]}, {"outil": "Java"}]
        self.assertEqual(accord_outil.origine("godot", env), "déclaré du projet")
        self.assertEqual(accord_outil.origine("GODOT4", env), "déclaré du projet")
        self.assertEqual(accord_outil.origine("git", []), "de base des agents")
        self.assertIsNone(accord_outil.origine("curl", env))
        self.assertIsNone(accord_outil.origine("rm", None))

    def test_la_commande_montree_est_courte_et_sans_secret(self):
        c = accord_outil.montrer("keytool -genkey -storepass hunter2 -keypass=abc\n -alias x " + "y" * 400)
        self.assertNotIn("hunter2", c)
        self.assertNotIn("abc", c)
        self.assertIn("-storepass ***", c)
        self.assertLessEqual(len(c), accord_outil.COUPE)
        self.assertNotIn("\n", c)


class Fiche(Base):
    def test_ouvrir_un_programme_cree_la_ligne_avec_les_outils_par_defaut(self):
        r = self.ok("fiche", entree={"action": "ouvrir_outil", "cle": "rel-1", "outil": "Bash(godot:*)"})
        self.assertFalse(r["deja"])
        self.assertEqual(r["outils"], fi.OUTILS_PAR_DEFAUT + ["Bash(godot:*)"])
        ligne = next(l for l in (self.dossier / "fiches" / "remi.md").read_text(encoding="utf-8").splitlines()
                     if l.startswith("Outils :"))
        self.assertTrue(ligne.endswith("Bash(godot:*)"))
        self.assertIn("Bash(py:*)", ligne)
        self.assertTrue(self.ok("fiche", entree={"action": "ouvrir_outil", "cle": "rel-1",
                                                 "outil": "Bash(godot:*)"})["deja"])

    def test_jamais_bash_seul_ni_autre_chose(self):
        for outil in ("Bash", "Bash(*)", "Bash(rm -rf:*)", "Write", "Bash(godot:*) , Bash", "Bash(../x:*)"):
            code, objet = self.outil("lancer", "fiche", entree={"action": "ouvrir_outil", "cle": "rel-1", "outil": outil})
            self.assertEqual(code, 1, outil)
        code, _ = self.outil("lancer", "fiche", entree={"action": "ouvrir_outil", "cle": "inconnu", "outil": "Bash(a:*)"})
        self.assertEqual(code, 1)
        code, _ = self.outil("lancer", "fiche", entree={"action": "autre", "cle": "rel-1", "outil": "Bash(a:*)"})
        self.assertEqual(code, 1)

    def test_le_motif_du_programme_est_celui_du_moteur(self):
        from moteur.environnement import MOTIF_EXECUTABLE
        self.assertEqual(fi.MOTIF_PROGRAMME.pattern, MOTIF_EXECUTABLE.pattern)


class Cadre(Base):
    """Un agent de cadrage (Hugo, `metier-1`) arrêté en cours de tâche, le projet déclarant (ou non) Godot."""

    def setUp(self):
        super().setUp()
        brut = json.loads(self.factory.read_text(encoding="utf-8"))
        brut["environnement"] = [{"outil": "Godot", "etat": "en_place", "executables": ["godot"]}]
        self.factory.write_text(json.dumps(brut), encoding="utf-8")
        self.actions = self.cadrer(texte="Des écrans pour l'appli")[1]
        self.tid = self.actions[0][2][0]

    def arret(self, commande, rapport=REFUS_BASH, refus=None, agent="metier-1"):
        refus = refus if refus is not None else [{"outil": "Bash", "commande": commande}]
        e = agents.Execution(self.tid, agent, rapport=_lu(rapport), usages=[usage()], refus=refus)
        return regles.traiter_retour(self.projet, e, self.etat)

    def tache(self):
        return self.taches(id=self.tid)[0]

    def decisions(self):
        return [d for d in self.suivi()["decisions_projet"] if d["genre"] == "outil_agent"]

    def outils_de_hugo(self):
        return fi.outils(fi.trouver(fi.lire_toutes(self.dossier / "fiches"), "metier-1"))



class Arret(Cadre):
    def test_programme_declare_ouvert_sans_decision_et_la_tache_repart(self):
        suite = self.arret("godot --headless --export-release Android build/x.apk")
        self.assertIn("Bash(godot:*)", self.outils_de_hugo())
        self.assertEqual(self.decisions(), [])
        self.assertEqual([(a[0], a[1], a[2]) for a in suite], [("agent", "metier-1", [self.tid])])
        self.assertIn("Bash(godot:*) est maintenant ouvert", suite[0][3])
        t = self.tache()
        self.assertTrue(t["active"])
        textes = [j["texte"] for j in t["journal"]]
        self.assertTrue(any("a besoin de l'outil Bash(godot:*)" in x and "Commande refusée" in x for x in textes), textes)
        self.assertIn("Outil ouvert à Hugo : Bash(godot:*) (programme déclaré du projet)", textes)
        self.assertNotIn("godot", " ".join(str(x) for x in self.etat["accords"]))

    def test_un_outil_de_base_deja_ouvert_a_tous_mais_retire_de_la_fiche_est_rouvert(self):
        (self.dossier / "fiches" / "hugo.md").write_text(
            (self.dossier / "fiches" / "hugo.md").read_text(encoding="utf-8").replace(
                "Lieu : local", "Lieu : local\nOutils : Read, Write, Edit"), encoding="utf-8")
        suite = self.arret("git status")
        self.assertIn("Bash(git:*)", self.outils_de_hugo())
        self.assertEqual([a[0] for a in suite], ["agent"])
        self.assertIn("(programme de base des agents)", " ".join(j["texte"] for j in self.tache()["journal"]))

    def test_second_refus_du_meme_programme_pose_la_decision(self):
        self.arret("godot -v")
        suite = self.arret("godot -v", refus=[{"outil": "Bash", "commande": "godot --headless -v"}])
        # La fiche ouvre déjà godot : la commande refusée n'a plus de programme à ouvrir, la décision le dit.
        self.assertEqual(suite, [])
        d, = self.decisions()
        self.assertEqual((d["agent"], d["tache"]), ("metier-1", self.tid))
        self.assertFalse(self.tache()["active"])

    def test_programme_inconnu_pose_une_decision_visible_au_bureau(self):
        suite = self.arret("curl -O https://exemple.test/x.zip")
        self.assertEqual(suite, [])
        self.assertNotIn("Bash(curl:*)", self.outils_de_hugo())
        d, = self.decisions()
        self.assertEqual((d["agent"], d["tache"], d["outil"], d["programme"]), ("metier-1", self.tid, "Bash(curl:*)", "curl"))
        self.assertEqual(d["commande"], "curl -O https://exemple.test/x.zip")
        self.assertIn("Hugo", d["texte"])
        self.assertIn("pas déclaré dans l'environnement", d["texte"])
        self.assertFalse(self.tache()["active"])
        self.assertTrue(any("a besoin de l'outil Bash(curl:*)" in j["texte"] for j in self.tache()["journal"]))
        # Visible au bureau de direction : dans le relevé, et la discussion le dit.
        releve = self.ok("releve")
        self.assertEqual([x["id"] for x in releve["decisions_projet"] if x["genre"] == "outil_agent"], [d["id"]])
        self.assertIn("arrêté faute d'un outil", self.fonc()["discussion"][-1]["texte"])

    def test_le_message_de_l_agent_est_dans_la_discussion(self):
        self.arret("curl x")
        self.assertIn("Je ne peux pas lancer la commande.", [m["texte"] for m in self.fonc()["discussion"]])

    def test_autoriser_ouvre_le_programme_et_relance_la_meme_tache(self):
        self.arret("curl -O https://exemple.test/x.zip")
        d, = self.decisions()
        demande, suite = self.traiter(type="outil_agent", decision=d["id"], verdict="autoriser")
        self.assertIn("Bash(curl:*)", self.outils_de_hugo())
        self.assertEqual(self.decisions(), [])
        self.assertEqual([(a[0], a[1], a[2]) for a in suite], [("agent", "metier-1", [self.tid])])
        self.assertIn("Outil ouvert à Hugo : Bash(curl:*) (autorisé par le Directeur)",
                      [j["texte"] for j in self.tache()["journal"]])
        self.assertEqual(self.statut(demande["id"])["statut"], "traitée")
        self.assertIn("Bash(curl:*)", self.statut(demande["id"])["reponse"])

    def test_refuser_bloque_la_tache_avec_la_raison(self):
        self.arret("curl x")
        d, = self.decisions()
        demande, suite = self.traiter(type="outil_agent", decision=d["id"], verdict="refuser")
        self.assertEqual(suite, [])
        self.assertNotIn("Bash(curl:*)", self.outils_de_hugo())
        self.assertIn("refusé", self.tache()["bloquee"])
        self.assertEqual(self.decisions(), [])

    def test_autre_outil_que_le_shell_demande_la_main_du_directeur(self):
        self.arret(None, rapport={"statut": "outil_refuse", "outil": "WebSearch", "message": {"texte": "Pas de recherche."}},
                   refus=[{"outil": "WebSearch"}])
        d, = self.decisions()
        self.assertNotIn("programme", d)
        self.assertEqual(d["outil"], "WebSearch")
        self.assertIn("Outils : » de sa fiche", d["texte"])
        # Il ouvre l'outil à la main, puis « relancer ».
        demande, suite = self.traiter(type="outil_agent", decision=d["id"], verdict="relancer")
        self.assertEqual([a[0] for a in suite], ["agent"])
        self.assertIn("WebSearch", suite[0][3])

    def test_commande_nommee_par_l_agent_et_chemin_absolu_autorisables_au_bureau(self):
        """Cas réel : l'agent rend `"outil": "Bash : C:/…/emulator.exe -list-avds"` sans refus lu ; la décision
        nomme le programme (bouton « Autoriser ») et l'accord l'ouvre à l'agent."""
        emu = "C:/Sdk/emulator/emulator.exe"
        suite = self.arret(None, rapport=dict(REFUS_BASH, outil=f"Bash : {emu} -list-avds"), refus=[])
        self.assertEqual(suite, [])
        d, = self.decisions()
        self.assertEqual((d["programme"], d["outil"], d["commande"]), (emu, f"Bash({emu}:*)", f"{emu} -list-avds"))
        self.traiter(type="outil_agent", decision=d["id"], verdict="autoriser")
        self.assertIn(f"Bash({emu}:*)", self.outils_de_hugo())

    def test_commande_illisible_pose_la_decision_sans_programme(self):
        self.arret("C:\\outils\\godot.exe --headless")
        d, = self.decisions()
        self.assertNotIn("programme", d)
        self.assertEqual(d["commande"], "C:\\outils\\godot.exe --headless")
        self.assertNotIn("Bash(godot", " ".join(self.outils_de_hugo()))

    def test_jamais_bash_sans_motif_si_aucune_commande_n_est_connue(self):
        self.arret(None, refus=[])
        d, = self.decisions()
        self.assertNotIn("programme", d)
        self.assertNotIn("Bash", self.outils_de_hugo())

    def test_un_agent_cloud_passe_toujours_par_la_decision(self):
        (self.dossier / "fiches" / "nuage.md").write_text(
            "Clé : nuage-1\nPrénom : Noa\nRôle : cadrage\nService : metier\nModèle : Sonnet\nLieu : cloud\n"
            "Session : s1\n\nTravaille.\n\n## Leçons\n", encoding="utf-8")
        self.ok("tache", entree={"id": self.tid, "agent": "nuage-1"})
        suite = self.arret("godot -v", agent="nuage-1")
        self.assertEqual(suite, [])
        d, = self.decisions()
        self.assertEqual(d["programme"], "godot")
        self.assertIn("agent cloud", d["texte"])
        self.assertNotIn("Bash(godot:*)", fi.outils(fi.trouver(fi.lire_toutes(self.dossier / "fiches"), "nuage-1")))


class Reprise(Cadre):
    """Au démarrage du moteur : la tâche arrêtée faute d'outil, dont la fiche ouvre maintenant l'outil, repart une fois."""

    def arreter_a_l_ancienne(self):
        """L'état réel de t44 : arrêtée par l'ancienne règle (« Bash », sans commande), tâche inactive, agent attribué."""
        self.ok("tache", entree={"id": self.tid, "active": False, "lot": {"id": "L8", "rang": 1},
                                 "journal": ["L'agent metier-1 a besoin de l'outil Bash, que sa fiche ne lui ouvre pas. "
                                             "Pour le lui donner, ajoutez-le à la ligne « Outils : » de sa fiche."]})
        self.etat["en_cours"].discard(self.tid)
        self.etat["a_lancer"].clear()

    def modifier_la_fiche(self, apres_s=5):
        chemin = self.dossier / "fiches" / "hugo.md"
        chemin.write_text(chemin.read_text(encoding="utf-8").replace(
            "Lieu : local", "Lieu : local\nOutils : Read, Write, Edit, Bash(py:*), Bash(godot:*)"), encoding="utf-8")
        futur = time.time() + apres_s
        os.utime(chemin, (futur, futur))

    def test_la_tache_repart_quand_la_fiche_a_ete_completee_apres_l_arret(self):
        self.arreter_a_l_ancienne()
        self.modifier_la_fiche()
        actions = regles.reprendre_les_taches_sans_outil(self.projet, self.etat)
        self.assertEqual([(a[0], a[1], a[2]) for a in actions], [("agent", "metier-1", [self.tid])])
        t = self.tache()
        self.assertTrue(t["active"])
        self.assertIsNone(t["lot"])
        self.assertIn("Le moteur a repris : l'outil Bash est ouvert dans la fiche", t["journal"][-1]["texte"])
        # Une seule fois.
        self.assertEqual(regles.reprendre_les_taches_sans_outil(self.projet, self.etat), [])

    def test_une_fiche_inchangee_depuis_l_arret_ne_relance_rien(self):
        self.arreter_a_l_ancienne()
        self.modifier_la_fiche(apres_s=-3600)
        self.assertEqual(regles.reprendre_les_taches_sans_outil(self.projet, self.etat), [])
        self.assertFalse(self.tache()["active"])

    def test_pas_de_reprise_tant_qu_une_decision_attend(self):
        self.arret("curl x")
        self.assertEqual(self.etat["en_cours"] - {self.tid}, set())
        self.etat["en_cours"].discard(self.tid)
        self.modifier_la_fiche()
        self.assertEqual(regles.reprendre_les_taches_sans_outil(self.projet, self.etat), [])

    def test_la_regle_nommee_par_l_arret_est_cherchee_dans_la_fiche(self):
        self.arret("curl x")
        d, = self.decisions()
        self.ok("decision", entree={"action": "lever", "id": d["id"]})
        self.etat["en_cours"].discard(self.tid)
        self.assertEqual(regles.reprendre_les_taches_sans_outil(self.projet, self.etat), [])     # curl pas dans la fiche
        self.ok("fiche", entree={"action": "ouvrir_outil", "cle": "metier-1", "outil": "Bash(curl:*)"})
        actions = regles.reprendre_les_taches_sans_outil(self.projet, self.etat)
        self.assertEqual([a[0] for a in actions], ["agent"])
        self.assertIn("Bash(curl:*) est ouvert dans la fiche", self.tache()["journal"][-1]["texte"])

    def test_une_tache_bloquee_ou_faite_ou_cloud_n_est_pas_reprise(self):
        self.arreter_a_l_ancienne()
        self.modifier_la_fiche()
        self.ok("tache", entree={"id": self.tid, "bloquee": "mise de côté"})
        self.assertEqual(regles.reprendre_les_taches_sans_outil(self.projet, self.etat), [])

    def test_le_moteur_relance_apres_le_demarrage_complet(self):
        """Le démarrage de la boucle appelle la reprise (la fonction du moteur, pas seulement la règle)."""
        from moteur import boucle
        self.arreter_a_l_ancienne()
        self.modifier_la_fiche()
        vus = []
        m = boucle.Moteur.__new__(boucle.Moteur)
        m._executer = lambda projet, actions: vus.extend(actions)
        m._noter = lambda *a: None
        m._rattacher_les_agents = lambda *a: None
        m._retrouver_les_sessions = lambda *a: None
        m._outils_manquants = lambda *a: None
        import unittest.mock as mock
        with mock.patch.object(regles, "genre_a_proposer", return_value=[]), \
                mock.patch.object(regles, "lancer", wraps=regles.lancer):
            m._demarrage(self.projet, self.etat)
        self.assertIn(("agent", "metier-1", [self.tid]), [(a[0], a[1], a[2]) for a in vus])


if __name__ == "__main__":
    unittest.main()
