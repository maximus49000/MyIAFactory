// Les agents retirés de l'équipe : gardés pour l'historique de leurs tâches, jamais dessinés dans la scène.
import {test} from "node:test";
import assert from "node:assert/strict";
import {prenomAgent, nomAgent} from "../ui/detail.js";
import {anciensAgents, ficheAncienAgent, tachesFaites} from "../ui/directeur.js";
import {tachesDuService} from "../ui/dossier.js";

const ETAT = {
  agents: [{id: "a1", prenom: "Léa", service: null, polyvalent: true, taches: []}],
  anciens_agents: [{id: "a2", prenom: "Hugo", couleur: "#336699", lieu: "cloud"},
                   {id: "a3", prenom: "Ana", couleur: "#993366", lieu: "local", service: "art"}],
  services: [{id: "dev", nom: "Dev"}, {id: "art", nom: "Art"}],
  taches: [
    {id: "t1", titre: "Écran", agent: "a2", colonne: "fait", service: "dev", maj: "2026-11-02T10:00:00Z"},
    {id: "t2", titre: "Icône", agent: "a3", colonne: "fait", maj: "2026-11-03T10:00:00Z"},
    {id: "t3", titre: "Menu", agent: "a1", colonne: "dev", active: true, service: "dev", maj: "2026-11-04T10:00:00Z"},
  ],
};

test("les tâches gardent le prénom d'un agent retiré", () => {
  assert.equal(prenomAgent(ETAT, "a2"), "Hugo");
  assert.equal(nomAgent(ETAT, "a2"), "Hugo");
  assert.equal(prenomAgent(ETAT, "a1"), "Léa");
  assert.equal(prenomAgent(ETAT, "inconnu"), "personne");
  assert.equal(prenomAgent({agents: []}, "a2"), "personne");     // relevé sans anciens agents
});

test("la liste des anciens agents", () => {
  assert.deepEqual(anciensAgents(ETAT).map((a) => a.id), ["a2", "a3"]);
  assert.deepEqual(anciensAgents({agents: []}), []);
});

test("la fiche d'un ancien agent : retiré, sans tâche en cours, ses tâches réalisées", () => {
  const a = ficheAncienAgent(ETAT, "a2");
  assert.equal(a.retire, true);
  assert.equal(a.prenom, "Hugo");
  assert.deepEqual(a.taches, []);
  assert.equal(ficheAncienAgent(ETAT, "a1"), null);
  assert.deepEqual(tachesFaites(ETAT, "a2").map((t) => t.id), ["t1"]);
});

test("les vues d'un service gardent les tâches des anciens agents", () => {
  assert.deepEqual(tachesDuService(ETAT, "dev").faites.map((t) => t.id), ["t1"]);      // par le service de la tâche
  assert.deepEqual(tachesDuService(ETAT, "art").faites.map((t) => t.id), ["t2"]);      // par le service de l'ancienne fiche
  assert.deepEqual(tachesDuService(ETAT, "dev").enCours.map((t) => t.id), ["t3"]);
});
