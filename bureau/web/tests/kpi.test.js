import test from "node:test";
import assert from "node:assert/strict";
import {valeurKpi, etiquettePeriode, kpiEnAlerte, idCibleKpi, nombreFr} from "../ui/kpi.js";

test("valeurKpi : la valeur de la période si le projet la donne, sinon la valeur, avec l'unité", () => {
  const k = {valeur: 2, unite: "défauts", periodes: {"7j": 5, "30j": "beaucoup"}};
  assert.equal(valeurKpi(k, "7j"), "5 défauts");
  assert.equal(valeurKpi(k, "30j"), "beaucoup défauts");
  assert.equal(valeurKpi(k, "aujourdhui"), "2 défauts");   // pas de valeur pour cette période : la valeur du projet
  assert.equal(valeurKpi({valeur: 1.5}, "7j"), "1,5");
  assert.equal(valeurKpi({valeur: 0, periodes: {"7j": 0}}, "7j"), "0");   // zéro n'est pas « absent »
  assert.equal(valeurKpi({valeur: "≈ 1,20 €"}, "7j"), "≈ 1,20 €");
  assert.equal(valeurKpi({valeur: null}, "7j"), "—");
  assert.equal(valeurKpi({valeur: NaN}, "7j"), "—");
  assert.equal(valeurKpi({valeur: "<img onerror=x>"}, "7j"), "<img onerror=x>");   // texte tel quel
});

test("etiquettePeriode : « toutes périodes » quand le KPI ne suit pas le sélecteur", () => {
  assert.equal(etiquettePeriode({valeur: 1}), "toutes périodes");
  assert.equal(etiquettePeriode({valeur: 1, periodes: null}), "toutes périodes");
  assert.equal(etiquettePeriode({valeur: 1, periodes: {}}), "toutes périodes");
  assert.equal(etiquettePeriode({valeur: 1, periodes: {"7j": 2}}), null);
  assert.equal(etiquettePeriode({valeur: 1, periodes: {"7j": 2}}, "30j"), "toutes périodes");
  assert.equal(etiquettePeriode({valeur: 1, periodes: {"7j": 2}}, "7j"), null);
});

test("kpiEnAlerte : seulement ceux dont l'alerte est vraie", () => {
  const l = [{id: "a", alerte: true}, {id: "b", alerte: false}, {id: "c"}, {id: "d", alerte: "oui"}];
  assert.deepEqual(kpiEnAlerte(l).map((k) => k.id), ["a"]);
  assert.deepEqual(kpiEnAlerte(undefined), []);
});

test("idCibleKpi : le même identifiant que le serveur, aussi pour un KPI du projet", () => {
  assert.equal(idCibleKpi("dev", "defauts"), "kpi:dev:defauts");
});

test("nombreFr : virgule décimale", () => {
  assert.equal(nombreFr(3), "3");
  assert.equal(nombreFr(2.25), "2,25");
  assert.equal(nombreFr(-0.5), "-0,5");
});
