import test from "node:test";
import assert from "node:assert/strict";
import {lignesTaches, lignesModeles, serviceFacture} from "../ui/facturation.js";

const f = {
  services: {
    prod: {total: 3, taches: {t1: {total: 1, etapes: {code: 0.6, "": 0.4}}, "": {total: 2, etapes: {"": 2}}},
            modeles: {a: 1, b: 2}, usages: []},
  },
  direction: {total: 5, taches: {}, modeles: {}, usages: []},
};

test("serviceFacture : service, direction, absent", () => {
  assert.equal(serviceFacture(f, "prod").total, 3);
  assert.equal(serviceFacture(f, "autre"), null);
  assert.equal(serviceFacture(null, "prod"), null);
});

test("lignesTaches : tri décroissant, « hors tâche » et « sans étape »", () => {
  const l = lignesTaches(f.services.prod, [{id: "t1", titre: "<img onerror=x>"}]);
  assert.deepEqual(l.map((x) => x.titre), ["Hors tâche", "<img onerror=x>"]);
  assert.deepEqual(l[1].etapes, [{nom: "code", total: 0.6}, {nom: "Sans étape", total: 0.4}]);
});

test("lignesModeles : tri décroissant", () => {
  assert.deepEqual(lignesModeles(f.services.prod), [{nom: "b", total: 2}, {nom: "a", total: 1}]);
});
