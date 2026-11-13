import {test} from "node:test";
import assert from "node:assert/strict";
import {tacheEnCours, modeleDeLaTache, lignesModele, modeleAffiche, leconsParMetier} from "../ui/polyvalent.js";
import {contenuLecons} from "../ui/connaissances.js";

const ETAT = {
  agents: [{id: "a1", modele: "?", polyvalent: true, taches: ["t1"]}, {id: "a2", modele: "Opus", taches: ["t1"]},
           {id: "a3", modele: "?", polyvalent: true, taches: []}],
  taches: [{id: "t1", titre: "Écran d'accueil", modele_depart: "Opus", modele_necessaire: {modele: "Sonnet"}}],
  metiers: [{role: "dev", service: "dev", lecons: [{id: "dev:L1", texte: "Toujours tester.", etat: "validée"},
                                                     {id: "dev:L2", texte: "À juger.", etat: "à valider"}]},
            {role: "qa", service: "qa", lecons: []}, {role: "design", service: "dev", lecons: [{id: "design:L1", texte: "Gris.", etat: "validée"}]}],
};

test("carte d'un polyvalent sans plafond : sa tâche et le modèle de cette tâche", () => {
  assert.deepEqual(lignesModele(ETAT, ETAT.agents[0]), [["Tâche", "Écran d'accueil"], ["Modèle de la tâche", "Opus"]]);
  assert.deepEqual(lignesModele(ETAT, ETAT.agents[2]), [["Tâche", "aucune"], ["Modèle de la tâche", "—"]]);
  assert.equal(lignesModele(ETAT, ETAT.agents[0]).flat().includes("Plafond"), false);
});

test("un agent à l'ancienne garde son plafond", () => {
  assert.deepEqual(lignesModele(ETAT, ETAT.agents[1]), [["Plafond", "Opus"]]);
  assert.deepEqual(lignesModele(ETAT, {id: "x"}), [["Plafond", "?"]]);
  assert.equal(modeleAffiche(ETAT, ETAT.agents[1]), "Opus");
});

test("le modèle de la tâche : son départ, sinon son étape", () => {
  assert.equal(modeleDeLaTache({modele_depart: "Opus"}), "Opus");
  assert.equal(modeleDeLaTache({modele_depart: null, modele_necessaire: {modele: "Haiku"}}), "Haiku");
  assert.equal(modeleDeLaTache({}), null);
  assert.equal(modeleAffiche(ETAT, ETAT.agents[0]), "Opus");
  assert.equal(modeleAffiche(ETAT, ETAT.agents[2]), "—");
  assert.equal(tacheEnCours(ETAT, ETAT.agents[2]), null);
});

test("les leçons d'un service s'affichent par métier", () => {
  assert.deepEqual(leconsParMetier(ETAT, "dev").map((m) => [m.role, m.lecons.length]), [["dev", 2], ["design", 1]]);
  assert.deepEqual(leconsParMetier(ETAT, "qa"), []);
  assert.deepEqual(leconsParMetier({agents: []}, "dev"), []);       // projet à l'ancienne : rien de plus
  assert.deepEqual(contenuLecons(ETAT, "dev").map((b) => [b.role, b.lignes.map((l) => l.etat)]),
                   [["dev", ["validée", "à valider"]], ["design", ["validée"]]]);
});
