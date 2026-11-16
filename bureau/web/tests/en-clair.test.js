import test from "node:test";
import assert from "node:assert/strict";
import {objectifEnClair} from "../ui/fonctionnalite.js";

const demande = (texte) => ({auteur: "utilisateur", texte});

test("objectif en clair d'une correction : la lecture « En clair » de sa fiche d'abord", () => {
  const f = {nature: "correction", discussion: [demande("Trouve moi un bug")],
             cahier: {etapes: ["En clair : Le surlignage est faux.", "Symptôme : x", "Attendu : y"]}};
  assert.deepEqual(objectifEnClair(f), {titre: "En clair", texte: "Le surlignage est faux."});
});

test("objectif en clair d'une correction sans « En clair » : ce qui est attendu", () => {
  const f = {nature: "correction", cahier: {etapes: ["Symptôme : x", "Attendu : Le champ suit la résolution."]}};
  assert.deepEqual(objectifEnClair(f), {titre: "Objectif", texte: "Le champ suit la résolution."});
});

test("objectif en clair avant tout cahier : la demande d'origine, abrégée", () => {
  const f = {discussion: [{auteur: "Chef", texte: "Bonjour"}, demande("  Un export   PDF des roadmaps  ")]};
  assert.deepEqual(objectifEnClair(f), {titre: "Demande", texte: "Un export PDF des roadmaps"});
  const long = objectifEnClair({discussion: [demande("a".repeat(800))]});
  assert.ok(long.texte.length <= 400 && long.texte.endsWith("…"));
});

test("objectif en clair : rien à dire, rien d'affiché", () => {
  assert.equal(objectifEnClair(null), null);
  assert.equal(objectifEnClair({discussion: [], cahier: {etapes: []}}), null);
});
