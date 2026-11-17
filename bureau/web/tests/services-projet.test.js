import test from "node:test";
import assert from "node:assert/strict";
import {lignesServicesProjet} from "../ui/facturation.js";

const services = [{id: "dev", nom: "Développement"}, {id: "qa", nom: "Qualité"}, {id: "facturation", nom: "Facturation"}];

test("« Tout le projet » détaille chaque service du bureau, même sans dépense", () => {
  const f = {services: {dev: {total: 6.91, sans_prix: [], co2: {bas: 1, haut: 2}}}};
  assert.deepEqual(lignesServicesProjet(f, services), [
    {id: "dev", nom: "Développement", total: 6.91, sans_prix: 0, co2: {bas: 1, haut: 2}},
    {id: "qa", nom: "Qualité", total: 0, sans_prix: 0},
    {id: "facturation", nom: "Facturation", total: 0, sans_prix: 0},
  ]);
});

test("un service disparu qui a dépensé dans la période reste listé, sous son id", () => {
  const l = lignesServicesProjet({services: {jeu: {total: 1.5, sans_prix: ["x"]}}}, services);
  assert.deepEqual(l.at(-1), {id: "jeu", nom: "jeu", total: 1.5, sans_prix: 1});
  assert.deepEqual(lignesServicesProjet(null, null), []);
});
