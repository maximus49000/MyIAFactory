import {test} from "node:test";
import assert from "node:assert/strict";
import {tacheAuTravail as auTravail, COULEUR_AU_TRAVAIL} from "../ui/texte.js";

test("une tâche au travail se repère : un agent dessus ou son agent local qui tourne", () => {
  assert.equal(auTravail({active: true, agent: "designer", colonne: "f1-prototype"}), true);
  assert.equal(auTravail({active: false, agent: null, colonne: "f1-contenu", travail: {depuis: "x"}}), true);
  assert.equal(auTravail({active: false, agent: "dev", colonne: "f1-contenu"}), false);   // en attente
  assert.equal(auTravail({active: true, agent: "dev", colonne: "fait"}), false);
  assert.equal(auTravail(undefined), false);
  assert.match(COULEUR_AU_TRAVAIL, /^#/);
});
