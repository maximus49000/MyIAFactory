import test from "node:test";
import assert from "node:assert/strict";
import {vignetteUrl, vignettesVoulues, planVignettes} from "../logique/vignettes.js";

const T1 = {id: "t1", maj: "2026-11-10T09:00:00", images: [{chemin: "img/a b.png"}, {chemin: "img/b.png"}]};
const T2 = {id: "t2", maj: "m", images: []};
const T3 = {id: "t3", maj: "m", images: [{chemin: "c.png"}]};

test("vignetteUrl : la première image, seulement si les images sont servies", () => {
  assert.equal(vignetteUrl(true, T1), "/api/image?chemin=img%2Fa%20b.png&t=2026-11-10T09%3A00%3A00");
  assert.equal(vignetteUrl(false, T1), null);
  assert.equal(vignetteUrl(undefined, T1), null);
  assert.equal(vignetteUrl(true, T2), null);
  assert.equal(vignetteUrl(true, {id: "x"}), null);
  assert.equal(vignetteUrl(true, null), null);
});

test("vignettesVoulues : une adresse par post-it visible qui a une image", () => {
  const taches = [T1, T2, T3];
  const v = vignettesVoulues(true, taches, ["t1", "t2", "t9"]);
  assert.deepEqual([...v.keys()], ["t1"]);   // t2 sans image, t9 inconnue
  assert.equal(v.get("t1"), vignetteUrl(true, T1));
  assert.equal(vignettesVoulues(false, taches, ["t1", "t3"]).size, 0);   // aucune requête sans images_ok
  assert.equal(vignettesVoulues(true, taches, []).size, 0);              // t3 n'a pas de post-it visible
  assert.deepEqual([...vignettesVoulues(true, taches, ["t3", "t1", "t3"]).keys()], ["t3", "t1"]);
  assert.equal(vignettesVoulues(true, null, ["t1"]).size, 0);
});

test("planVignettes : charge les nouvelles, libère celles qui disparaissent ou changent", () => {
  const vide = new Map();
  assert.deepEqual(planVignettes(vide, new Map([["a", "u1"], ["b", "u2"]])),
                   {charger: [{cle: "a", url: "u1"}, {cle: "b", url: "u2"}], liberer: []});
  // rien ne change : aucune requête, aucune libération
  assert.deepEqual(planVignettes(new Map([["a", "u1"]]), new Map([["a", "u1"]])), {charger: [], liberer: []});
  // le post-it disparaît
  assert.deepEqual(planVignettes(new Map([["a", "u1"], ["b", "u2"]]), new Map([["b", "u2"]])),
                   {charger: [], liberer: ["a"]});
  // l'image change : on libère l'ancienne texture et on charge la nouvelle
  assert.deepEqual(planVignettes(new Map([["a", "u1"]]), new Map([["a", "u1bis"]])),
                   {charger: [{cle: "a", url: "u1bis"}], liberer: ["a"]});
  // l'image disparaît de la tâche
  assert.deepEqual(planVignettes(new Map([["a", "u1"]]), vide), {charger: [], liberer: ["a"]});
  // images_ok devient faux : tout est libéré, rien n'est chargé
  assert.deepEqual(planVignettes(new Map([["a", "u1"], ["b", "u2"]]), vide), {charger: [], liberer: ["a", "b"]});
});
