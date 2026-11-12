"""La série reprise après un redémarrage du moteur (sa mémoire est perdue) : chaque élément repart de là où le suivi
le montre, sans refaire ce qui est fait ; une série qui ne progresse plus est dite au bureau ; une fonctionnalité finie
est annoncée au Directeur (« Fonctionnalités terminées »). Données inventées, de la forme du suivi réel."""
import json

from moteur import agents, regles
from tests import test_moteur_regles as tmr

ACCES, DIT, _lu, usage, verdict = tmr.ACCES, tmr.DIT, tmr._lu, tmr.usage, tmr.verdict

FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "integ", "nom": "Intégration", "role": "dev", "service": "dev"},
        {"id": "valider", "nom": "Validation du Directeur", "validation": True},
        {"id": "essai", "nom": "Tests et essai du jeu", "role": "testeur", "service": "qualite"},
        {"id": "livraison", "nom": "Livraison de l'apk signé", "role": "livreur", "service": "livraison"}]


class AvecValidation(tmr.Base):
    """Les aides des tests de validation, sans leurs tests."""
    VAL = tmr.Validation.VAL
    projet_avec_validation = tmr.Validation.projet_avec_validation
    fichier = tmr.Validation.fichier
    decisions = tmr.Validation.decisions


ELEMENTS = [{"id": f"e{k}", "nom": f"Élément {k}", "groupe": "jeu"} for k in range(1, 8)]


class Reprise(AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=FLUX, elements=0)

    def prendre(self, *ids):
        for eid in ids:
            self.ok("file-prendre", entree={"fonctionnalite": "f1", "element": eid})

    def tache(self, eid, etape, fait=True, journal="Fait.", titre=None, role="dev", colonne=None, **plus):
        """Une tâche de l'élément telle que le suivi la garde (faite par défaut, journal compris)."""
        colonne = colonne or (etape.split(":", 1)[1] if ":" in etape else "dev")
        tid = self.ok("tache", entree={"titre": titre or f"{etape} : {eid}", "fonctionnalite": "f1", "role": role,
                                       "etape": etape, "colonne": colonne, "element": eid, "active": False,
                                       **plus})["id"]
        if fait:
            self.ok("tache", entree={"id": tid, "colonne": "fait", "journal": [journal]})
        return tid

    def de(self, eid, etape=None):
        return [t for t in self.taches(element=eid) if etape is None or t["etape"] == etape]

    def serie_arretee(self):
        return [d for d in self.ok("etat")["decisions"] if d["genre"] == "serie_arretee"]

    # --- La cause : la mémoire de la série perdue au redémarrage.

    def test_un_agent_qui_finit_apres_un_redemarrage_fait_avancer_son_element(self):
        """L'agent détaché finit pendant que le moteur a été relancé : son rapport fait passer chaque élément du lot à
        l'étape suivante (avant : `_suite_de_tache` ne trouvait pas l'élément, le rapport était perdu en silence)."""
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        (action,) = [a for a in regles.avancer(self.projet, self.etat) if a[0] == "agent"]
        self.etat = regles.nouvel_etat()                                 # le moteur est relancé
        # il rattache l'agent détaché (comme `Moteur._rattacher_les_agents`) : son départ, pas la série
        self.etat["departs"][action[2][0]] = {"agent": action[1], "taches": list(action[2]), "matiere": "", "lot": None}
        self.etat["en_cours"].add(action[2][0])
        e = agents.Execution(action[2][0], action[1], rapport=_lu({"statut": "fait", "message": {"texte": "Fait."}}),
                             usages=[usage()])
        regles.traiter_retour(self.projet, e, self.etat)
        self.assertEqual(sorted(t["element"] for t in self.taches(etape="flux:integ")), ["e1", "e2"])
        self.assertEqual({t["colonne"] for t in self.taches(etape="flux:dev")}, {"fait"})

    def test_serie_figee_repart_d_elle_meme_au_demarrage(self):
        """L'état réel : toutes les tâches faites, aucune ouverte, ni décision, ni agent ; la série ne bougeait plus."""
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS})
        self.prendre("e1", "e2", "e3", "e4", "e5", "e6", "e7")
        self.fichier("pieces/f1/e5.png")
        # e1 : livré (puis un retour sur sa livraison, fait) -> fini
        for etape in ("flux:dev", "flux:integ"):
            self.tache("e1", etape)
        self.tache("e1", "validation:valider", journal="Validé.", role=None)
        self.tache("e1", "flux:essai", role="testeur")
        liv = self.tache("e1", "flux:livraison", role="livreur", journal="APK livré.")
        self.tache("e1", "retour", titre=f"Retour : Livraison de l'apk signé : Élément 1 ({liv})", role="livreur")
        # e2 et e3 : le développement fait dans un lot, son rapport perdu ; e3 a eu un retour (« où en es-tu ? ») après
        self.tache("e2", "flux:dev", lot={"id": "L6", "rang": 1}, journal="Les deux sont faits.")
        self.tache("e3", "flux:dev", lot={"id": "L6", "rang": 2}, journal="Terminé.")
        self.tache("e3", "retour", titre="Retour : Développement : Élément 3")
        # e4 : l'élément du prototype -> fait par la méthode
        self.tache("e4", "prototype")
        # e5 : l'étape avant la validation faite, son rapport perdu ; une capture rangée dans ses documents
        self.tache("e5", "flux:dev")
        t5 = self.tache("e5", "flux:integ", journal="Intégré, capture jointe.")
        self.ok("document", entree={"fonctionnalite": "f1", "chemin": "pieces/f1/e5.png", "titre": "Écran e5",
                                    "tache": t5, "element": "e5", "etape": "flux:integ"})
        # e6 : validé par le Directeur, l'étape suivante jamais créée
        self.tache("e6", "flux:dev")
        self.tache("e6", "flux:integ")
        self.tache("e6", "validation:valider", journal="Validé. Note du Directeur : bien.", role=None)
        # e7 : un essai non conforme, sa correction faite, la relecture (l'étape de qualité refaite) jamais lancée
        self.tache("e7", "flux:dev")
        self.tache("e7", "flux:integ")
        self.tache("e7", "validation:valider", journal="Validé.", role=None)
        self.tache("e7", "flux:essai", role="testeur", journal="Non conforme : le score déborde.")
        self.tache("e7", "correction", journal="Score corrigé.")
        self.assertEqual([t for t in self.taches() if t["colonne"] != "fait"], [])

        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)

        self.assertEqual(len(self.de("e1")), 6)                                  # rien de refait
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")
        self.assertEqual(len(self.de("e2", "flux:integ")), 1)                     # l'étape suivante, une seule fois
        self.assertEqual(len(self.de("e3", "flux:integ")), 1)                     # le retour ne finit pas l'élément
        self.assertEqual(self.de("e4", "flux:dev"), [])
        self.assertEqual(self.etat["elements"]["f1/e4"]["phase"], "fait")
        (d,) = [d for d in self.decisions() if d["element"]["id"] == "e5"]        # validation posée, rien de refait
        self.assertEqual([f["chemin"] for f in d["fichiers"]], ["pieces/f1/e5.png"])
        self.assertEqual(d["compte_rendu"], "Intégré, capture jointe.")
        self.assertEqual(len(self.de("e5", "flux:integ")), 1)
        self.assertEqual(len(self.de("e6", "flux:essai")), 1)                     # après la validation : les tests
        self.assertEqual(len(self.de("e7", "flux:essai")), 2)                     # les tests refaits après la correction
        self.assertEqual(self.serie_arretee(), [])
        self.assertNotEqual(self.fonc()["etape"], "terminee")
        # Le passage suivant ne recrée rien.
        avant = len(self.taches())
        regles.avancer(self.projet, self.etat)
        self.assertEqual(len(self.taches()), avant)

    def test_reprise_de_l_element_dont_la_tache_est_encore_ouverte(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:1]})
        self.prendre("e1")
        self.tache("e1", "flux:dev")
        tid = self.tache("e1", "flux:integ", fait=False)
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        v = self.etat["elements"]["f1/e1"]
        self.assertEqual((v["phase"], v["pas"], v["taches"][-1]), ("flux", 1, tid))
        self.assertEqual(len(self.de("e1")), 2)

    def test_serie_finie_pendant_l_arret_se_termine_au_demarrage(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        self.prendre("e1", "e2")
        self.tache("e1", "prototype")
        for etape in ("flux:dev", "flux:integ"):
            self.tache("e2", etape)
        self.tache("e2", "validation:valider", journal="Validé.", role=None)
        self.tache("e2", "flux:essai", role="testeur")
        self.tache("e2", "flux:livraison", role="livreur")
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        self.assertEqual(self.fonc()["etape"], "terminee")

    # --- Le garde-fou : jamais une série muette.

    def test_serie_qui_ne_progresse_plus_est_signalee_au_bureau(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        self.prendre("e1", "e2")
        self.tache("e1", "flux:ancienne", journal="Fait.", colonne="dev")            # une étape qui n'est plus dans le workflow
        self.tache("e2", "prototype")
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        (d,) = self.serie_arretee()
        self.assertEqual(d["fonctionnalite"], "f1")
        self.assertTrue(d["texte"].startswith(f"La série de « {self.fonc()['nom']} » ne progresse plus : "), d["texte"])
        self.assertIn("Élément 1", d["texte"])
        self.assertIn("ancienne", d["texte"])
        regles.avancer(self.projet, self.etat)
        self.assertEqual(len(self.serie_arretee()), 1)                 # posée une fois
        # Le Directeur demande de relancer : la décision est levée, la série est relue.
        _, actions = self.traiter(type="serie_arretee", decision=d["id"], verdict="relancer")
        self.assertEqual(self.serie_arretee(), [])

    def test_element_qui_ne_peut_pas_repartir_est_dit_meme_si_d_autres_avancent(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        self.prendre("e1", "e2")
        self.tache("e1", "flux:ancienne", colonne="dev")
        self.tache("e2", "flux:dev", fait=False)                       # e2 travaille encore
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        (d,) = self.serie_arretee()
        self.assertIn("« Élément 1 » : son étape « ancienne »", d["texte"])
        self.assertNotIn("Élément 2", d["texte"])

    def test_serie_qui_avance_n_est_pas_signalee(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        regles.avancer(self.projet, self.etat)
        self.assertEqual(self.serie_arretee(), [])


class FinDeFonctionnalite(AvecValidation):
    """« Quand une fonctionnalité est terminée, avertir la direction, avec un lien vers l'accès à celle-ci. »"""

    def test_fonctionnalite_terminee_annoncee_avec_livrables_et_acces(self):
        self.projet_avec_validation(flux=[FLUX[0], FLUX[3], FLUX[4]], elements=0)
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:1]})
        self.fichier("build/jeu.apk", b"PK" + b"\x00" * 8)
        livraison = {"statut": "fait", "message": {"texte": "Livré."}, "acces": ACCES,
                     "fichiers": [{"chemin": "build/jeu.apk", "titre": "APK signé", "element": "e1", "livrable": True}]}
        self.piloter(regles.avancer(self.projet, self.etat), rapports=[
            {"statut": "fait", "message": {"texte": "Programmé."}},
            {**verdict("e1"), "message": {"texte": "Testé."}, **DIT}, livraison])
        regles.avancer(self.projet, self.etat)
        f = self.fonc()
        self.assertEqual(f["etape"], "terminee")
        fin = f["fin"]
        self.assertFalse(fin["vu"])
        self.assertTrue(fin["date"])
        self.assertEqual(fin["livrables"], [{"chemin": "build/jeu.apk", "titre": "APK signé"}])
        self.assertEqual(fin["acces"], ACCES)
        # « Vu » : l'avis se ferme, la fonctionnalité reste terminée.
        d, _ = self.traiter(type="fin_vue", fonctionnalite="f1")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertTrue(self.fonc()["fin"]["vu"])
        self.assertEqual(self.fonc()["etape"], "terminee")

    def test_fin_refusee_mal_formee(self):
        self.fonctionnalite("serie")
        for fin in ({"livrables": "x"}, {"acces": {"url": "ftp://x"}}, {"livrables": [{"chemin": ""}]}, "oui"):
            code, _ = self.outil("fonctionnalite", entree={"id": "f1", "fin": fin})
            self.assertEqual(code, 1, fin)


if __name__ == "__main__":
    import unittest
    unittest.main()
