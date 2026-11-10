import {test} from "node:test";
import assert from "node:assert/strict";
import {changements, etatUtilisable} from "../logique/diff.js";
import {E1, copie, modifier, sansAgent} from "./donnees.js";

test("premier état : aucun changement", () => assert.deepEqual(changements(null, E1), []));

test("changement de colonne : c'est l'ancien titulaire qui porte", () => {
  const apres = modifier(E1, "t1", {colonne: "revue", agent: "qa1"});
  assert.deepEqual(changements(E1, apres), [{tache: "t1", de: "encours", vers: "revue", porteur: "dev1"}]);
});

test("ancien titulaire parti : le chef porte", () => {
  const apres = sansAgent(modifier(E1, "t1", {colonne: "revue"}), "dev1");
  assert.deepEqual(changements(E1, apres), [{tache: "t1", de: "encours", vers: "revue", porteur: "chef"}]);
});

test("ancien titulaire nul : le chef porte", () => {
  const apres = modifier(E1, "t2", {colonne: "encours", agent: "dev1"});
  assert.deepEqual(changements(E1, apres), [{tache: "t2", de: "afaire", vers: "encours", porteur: "chef"}]);
});

test("nouvelle tâche : posée par le chef", () => {
  const apres = copie(E1);
  apres.taches.push({id: "t3", titre: "Nouvelle", colonne: "afaire", agent: null, etape: "", maj: "", postit: true});
  assert.deepEqual(changements(E1, apres), [{tache: "t3", de: null, vers: "afaire", porteur: "chef"}]);
});

test("tâche sans post-it ignorée", () => {
  const apres = modifier(E1, "t9", {colonne: "fait"});
  apres.taches.push({id: "t4", titre: "Cachée", colonne: "afaire", agent: null, etape: "", maj: "", postit: false});
  assert.deepEqual(changements(E1, apres), []);
});

test("tâche disparue : rien", () => {
  const apres = copie(E1);
  apres.taches = apres.taches.filter((t) => t.id !== "t2");
  assert.deepEqual(changements(E1, apres), []);
});

test("même colonne, autre agent : rien", () => {
  assert.deepEqual(changements(E1, modifier(E1, "t1", {agent: "qa1"})), []);
});

test("le chef porte aussi ce qu'il tenait lui-même", () => {
  const avant = modifier(E1, "t2", {agent: "chef"});
  const apres = modifier(avant, "t2", {colonne: "encours"});
  assert.equal(changements(avant, apres)[0].porteur, "chef");
});

test("etatUtilisable", () => {
  assert.equal(etatUtilisable(E1), true);
  assert.equal(etatUtilisable({...E1, erreur: "fichier absent"}), false);
  assert.equal(etatUtilisable(null), false);
});
