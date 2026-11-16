import test from "node:test";
import assert from "node:assert/strict";
import {etapeCorrection, bandeauCorrection, libelleEtapeCorrection, libelleEtapeTache} from "../ui/parcours-correction.js";
import {libelleEtape} from "../ui/fonctionnalite.js";

const F = {id: "f2", nom: "Score bloqué", nature: "correction", etape: "cadrage"};
const AVEC_QA = {colonnes: [{id: "cadrage"}, {id: "f2-correctif"}, {id: "f2-verification"}, {id: "f2-validation"},
                            {id: "f2-livraison"}, {id: "fait"}]};

test("étape d'une correction : cadrage → diagnostic, colonnes et étapes de flux sans préfixe", () => {
  assert.equal(etapeCorrection("f2", "cadrage"), "diagnostic");
  assert.equal(etapeCorrection("f2", "flux:f2-correctif"), "correctif");
  assert.equal(etapeCorrection("f2", "f2-livraison"), "livraison");
  assert.equal(etapeCorrection("f2", "f3-correctif"), null);
  assert.equal(etapeCorrection("f2", "relecture"), null);
});

test("bandeau d'une correction : diagnostic au cadrage, vérification seulement si le workflow en a une", () => {
  const b = bandeauCorrection(F, {colonnes: []});
  assert.deepEqual(b.map((x) => x.libelle), ["Diagnostic", "Correctif", "Validation", "Livraison"]);
  assert.deepEqual(b.map((x) => x.courante), [true, false, false, false]);
  const enSerie = {...F, etape: "serie"};
  const e = {...AVEC_QA, taches: [{fonctionnalite: "f2", colonne: "f2-verification", etape: "flux:f2-verification"},
                                  {fonctionnalite: "f2", colonne: "fait", etape: "flux:f2-correctif"}]};
  const b2 = bandeauCorrection(enSerie, e);
  assert.deepEqual(b2.map((x) => x.libelle), ["Diagnostic", "Correctif", "Vérification", "Validation", "Livraison"]);
  assert.deepEqual(b2.map((x) => x.faite), [true, true, false, false, false]);
  assert.equal(libelleEtapeCorrection(enSerie, e), "Vérification");
  assert.ok(bandeauCorrection({...F, etape: "terminee"}, e).every((x) => x.faite && !x.courante));
});

test("libellés : la liste et le détail d'une tâche parlent de diagnostic pour une correction, pas de cadrage", () => {
  assert.equal(libelleEtape(F, {}), "Diagnostic");
  assert.equal(libelleEtape({id: "f1", etape: "cadrage"}, {}), "Cadrage");          // une fonctionnalité ne change pas
  const e = {fonctionnalites: [F, {id: "f1", etape: "cadrage"}]};
  assert.equal(libelleEtapeTache(e, {fonctionnalite: "f2", etape: "cadrage", colonne: "cadrage"}), "diagnostic");
  assert.equal(libelleEtapeTache(e, {fonctionnalite: "f2", etape: "flux:f2-verification"}), "vérification");
  assert.equal(libelleEtapeTache(e, {fonctionnalite: "f1", etape: "cadrage"}), "cadrage");
});

test("détail d'une tâche : les questions de l'agent qui attendent une réponse se retrouvent depuis la tâche", async () => {
  const {questionsAAttendre} = await import("../ui/detail.js");
  const q = [{texte: "De quoi s'agit-il ?", choix: ["A", "B"]}];
  const e = {fonctionnalites: [{...F, discussion: [{id: "m1", auteur: "utilisateur", texte: "x"},
                                                   {id: "m2", auteur: "agent-2", texte: "Deux précisions", questions: q}]}]};
  assert.deepEqual(questionsAAttendre(e, {fonctionnalite: "f2", colonne: "cadrage"}), {message: "m2", questions: q});
  assert.equal(questionsAAttendre(e, {fonctionnalite: "f2", colonne: "fait"}), null);
  assert.equal(questionsAAttendre(e, {fonctionnalite: null, colonne: "cadrage"}), null);
  const repondu = {fonctionnalites: [{...F, discussion: [...e.fonctionnalites[0].discussion, {id: "m3", auteur: "utilisateur", texte: "A"}]}]};
  assert.equal(questionsAAttendre(repondu, {fonctionnalite: "f2", colonne: "cadrage"}), null);
});
