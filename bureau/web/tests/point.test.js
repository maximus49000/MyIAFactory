import {test} from "node:test";
import assert from "node:assert/strict";
import {pointAtelier} from "../ui/point.js";

const maintenant = new Date("2026-11-13T09:50:00+01:00");

test("le point dit qui fait quoi, depuis quand, et ce qui attend", () => {
  const etat = {
    agents: [{id: "chef", chef: true, taches: []},
             {id: "dev", prenom: "Hugo", lieu: "local", statut: "travail", taches: ["t81"]},
             {id: "art", prenom: "Léa", lieu: "cloud", statut: "travail", taches: ["t90"]}],
    taches: [{id: "t81", titre: "Prototype jouable", colonne: "f1-prototype",
              travail: {depuis: "2026-11-13T09:45:00+01:00", action: "lance les tests", action_t: "2026-11-13T09:49:30+01:00"}},
             {id: "t90", titre: "Planches", colonne: "art"},
             {id: "t64", titre: "Validation", colonne: "v", bloquee: "Rien à valider"}],
    decisions_projet: [{id: "d1"}], fonctionnalites: [{decisions: [{id: "d2"}]}],
    attente_charge: {texte: "Le poste est chargé."},
  };
  const p = pointAtelier(etat, maintenant);
  assert.equal(p.agents.length, 2);
  assert.equal(p.agents[0].prenom, "Hugo");
  assert.match(p.agents[0].etat, /au travail depuis 5 min · dernière action à l'instant : lance les tests/);
  assert.equal(p.agents[1].etat, "en cours dans sa session cloud");
  assert.equal(p.decisions, 2);
  assert.deepEqual(p.bloquees.map((b) => b.tache), ["t64"]);
  assert.equal(p.retenue, "Le poste est chargé.");
});

test("un état vide ne casse rien", () => {
  assert.deepEqual(pointAtelier({}, maintenant), {agents: [], decisions: 0, bloquees: [], retenue: null});
});

import {echangesChef} from "../ui/point.js";

test("les échanges avec le Chef : ses questions et ses réponses, les plus récentes d'abord", () => {
  const etat = {taches: [{id: "orchestration", retours: [
    {t: "2026-11-13T10:00:00+01:00", texte: "Où en est Hugo ?", reponse: "Il lance les tests."},
    {t: "2026-11-13T10:05:00+01:00", texte: "Et la boutique ?"}]},
    {id: "t1", retours: [{texte: "autre"}]}]};
  assert.deepEqual(echangesChef(etat), [
    {t: "2026-11-13T10:05:00+01:00", question: "Et la boutique ?", reponse: null},
    {t: "2026-11-13T10:00:00+01:00", question: "Où en est Hugo ?", reponse: "Il lance les tests."}]);
  assert.deepEqual(echangesChef({}), []);
});
