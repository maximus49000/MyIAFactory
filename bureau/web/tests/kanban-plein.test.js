import test from "node:test";
import assert from "node:assert/strict";
import {colonnesKanban} from "../ui/kanban-plein.js";

test("colonnesKanban : une colonne par colonne du relevé, les tâches les plus récentes en tête, la file à part", () => {
  const etat = {
    colonnes: [{id: "a", nom: "À faire"}, {id: "b", nom: "En cours"}, {id: "f", nom: "Fait", terminee: true}],
    agents: [{id: "dev-1", prenom: "Noé"}],
    taches: [{id: "t1", titre: "Un", colonne: "b", agent: "dev-1", maj: "2026-11-10T10:00:00", active: true},
             {id: "t2", titre: "Deux", colonne: "b", agent: null, maj: "2026-11-10T12:00:00", active: true, bloquee: "attend"},
             {id: "t3", titre: "Trois", colonne: "f", maj: "2026-11-10T09:00:00", active: false},
             {id: "t4", titre: "Perdue", colonne: "inconnue", maj: "2026-11-10T09:00:00"}],
    file: {visibles: [{id: "q1", titre: "Prochain"}], suite: [], reste: 3}};
  const c = colonnesKanban(etat);
  assert.deepEqual(c.map((x) => [x.id, x.nom, x.taches.map((t) => t.id)]),
    [["a", "À faire", []], ["b", "En cours", ["t2", "t1"]], ["f", "Fait", ["t3"]]]);
  assert.equal(c[1].taches[1].prenom, "Noé");
  assert.equal(c[1].taches[0].bloquee, "attend");
  assert.deepEqual(c.file, {elements: [{id: "q1", titre: "Prochain"}], reste: 3});
  assert.deepEqual(colonnesKanban({}).length, 0);
});

test("colonnesKanban : une tâche sans post-it (le chef qui orchestre) n'est pas sur le Kanban, comme dans la scène", () => {
  const etat = {colonnes: [{id: "cadrage", nom: "Cadrage"}],
                taches: [{id: "orchestration", titre: "Orchestration", colonne: "cadrage", postit: false},
                         {id: "t1", titre: "Cadrage : Pictos", colonne: "cadrage"}]};
  assert.deepEqual(colonnesKanban(etat)[0].taches.map((t) => t.id), ["t1"]);
});
