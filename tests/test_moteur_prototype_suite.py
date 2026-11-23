"""L'élément du prototype finit le flux après la méthode. Cas réel (FM_Stats, 2026-11-23) : un seul élément, le
prototype tenu par le maquettiste (rôle de la première étape) n'a livré que la maquette HTML ; maquette validée, méthode
validée, et le moteur déclarait « La série est terminée. » sans aucune tâche de développement, de tests, de docs ni de
livraison. Le workflow est celui du projet (copie figée du suivi et de la factory) ; agents et IA simulés."""
import json

from moteur import regles
from tests import test_moteur_regles as tmr

# le workflow `w-f1` de FM_Stats, tel quel (sans le préfixe de la fonctionnalité)
FLUX_FM_STATS = [
    {"id": "maquette", "nom": "Maquette HTML du nouvel écran", "role": "maquettiste", "service": "conception",
     "modele": "Sonnet"},
    {"id": "valid-maquette", "nom": "Validation de la maquette par l'utilisateur", "validation": True},
    {"id": "dev", "nom": "Développement Flutter : code", "role": "dev", "service": "developpement", "modele": "Sonnet"},
    {"id": "dev-local", "nom": "Développement Flutter : mise en place et tests", "role": "dev",
     "service": "developpement", "modele": "Sonnet", "lieu": "local"},
    {"id": "docs", "nom": "Mise à jour CHANGELOG, METIER et TECHNIQUE", "role": "redacteur",
     "service": "developpement", "modele": "Haiku"},
    {"id": "livraison", "nom": "Livraison de l'apk signé FM_Stats_N.apk", "role": "release", "service": "livraison",
     "modele": "Haiku", "lieu": "local"}]

E1 = {"id": "e1", "nom": "Probabilités par journée (calcul, sélecteur, comparaison, états, tests et docs)",
      "groupe": "Fonctionnalité", "validations": ["valid-maquette"]}
DECOUPAGE = {"elements": [E1], "prototype": "e1", "depend_de": {}, "reprendre_methode": None,
             "message": "Je propose un seul élément pour toute la fonctionnalité."}
FICHE = ("Clé : {cle}\nPrénom : {cle}\nRôle : {role}\nService : {service}\nModèle : Sonnet\nLieu : local\n\n"
         "Travaille.\n\n## Leçons\n")


class PrototypeSeul(tmr.Base):
    def setUp(self):
        super().setUp()
        for nom in ("remi", "zoe"):          # FM_Stats n'a pas de relecteur
            (self.dossier / "fiches" / f"{nom}.md").unlink()
        for cle, role, service in (("maq-1", "maquettiste", "conception"), ("red-1", "redacteur", "developpement"),
                                   ("rel-1", "release", "livraison")):
            (self.dossier / "fiches" / f"{cle}.md").write_text(FICHE.format(cle=cle, role=role, service=service),
                                                               encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["services"] += [{"id": "conception", "nom": "Conception"}, {"id": "developpement", "nom": "Développement"},
                          {"id": "livraison", "nom": "Livraison"}]
        f["flux"] = FLUX_FM_STATS
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def textes(self):
        return [m["texte"] for m in self.fonc()["discussion"]]

    def test_la_maquette_validee_ne_termine_pas_la_fonctionnalite(self):
        self.cahier_a_valider()
        _, actions = self.traiter(type="cahier", fonctionnalite="f1", verdict="valider")     # parcours complet
        self.piloter(actions, juges={"decouper": DECOUPAGE}, rapports=[
            {"statut": "fait", "message": {"texte": "La maquette HTML est prête. Convient-elle avant que je passe au "
                                                    "développement ?", "attend": True}}])
        (proto,) = self.taches(etape="prototype")
        self.assertEqual((proto["role"], proto["element"]), ("maquettiste", "e1"))
        _, actions = self.traiter(type="message", fonctionnalite="f1", texte="Oui, on continue")
        self.piloter(actions, juges={"traduire_retour": {"validation": True, "consigne": None}})
        _, actions = self.traiter(type="methode", fonctionnalite="f1", verdict="valider")
        self.piloter(actions, juges={"ecrire_methode": tmr.METHODE})
        regles.avancer(self.projet, self.etat)

        self.assertNotIn("La série est terminée.", self.textes())
        self.assertEqual(self.fonc()["etape"], "serie")
        # la maquette et sa validation sont tenues par le prototype : l'élément repart au développement
        (dev,) = self.taches(etape="flux:dev")
        self.assertEqual((dev["element"], dev["role"]), ("e1", "dev"))
        self.assertEqual(self.taches(etape="flux:maquette"), [])
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "flux")
        avant = len(self.taches())
        regles.avancer(self.projet, self.etat)             # le passage suivant ne recrée rien
        self.assertEqual(len(self.taches()), avant)
        self.etat = regles.nouvel_etat()                   # le moteur relancé reprend l'élément à son développement
        regles.avancer(self.projet, self.etat)
        self.assertEqual(len(self.taches()), avant)
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "flux")
        self.assertEqual(self.fonc()["etape"], "serie")

    def test_un_prototype_qui_tient_tout_le_flux_reste_fait(self):
        """Le cas d'avant, inchangé : le développeur tient tout le flux (sans relecteur), la série se termine."""
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"}]
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.fonctionnalite("prototype")
        self.ok("file", entree={"fonctionnalite": "f1", "elements": [E1]})
        self.ok("file-prendre", entree={"fonctionnalite": "f1", "element": "e1"})
        self.ok("tache", entree={"titre": "Prototype", "fonctionnalite": "f1", "role": "dev", "etape": "prototype",
                                 "colonne": "dev", "element": "e1", "active": False})
        self.etat["prototype"]["f1"] = {"id": "e1", "nom": E1["nom"]}
        self.ok("decision", entree={"action": "poser", "portee": "f1", "genre": "valider_methode", "texte": "ok ?"})
        _, actions = self.traiter(type="methode", fonctionnalite="f1", verdict="valider")
        self.piloter(actions, juges={"ecrire_methode": tmr.METHODE})
        self.assertEqual(self.etat["elements"]["f1/e1"]["phase"], "fait")
        self.assertEqual(self.taches(etape="flux:dev"), [])
