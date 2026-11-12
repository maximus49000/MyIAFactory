// Essai réel : sur un écran d'ordinateur large, des boutons de la barre étaient écrasés à zéro (défilement caché).
// Sur l'ordinateur, la barre passe à la ligne au lieu de cacher des boutons, et la scène suit sa hauteur.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");

function regle(selecteur) {
  const i = css.indexOf(selecteur + " {");
  assert.ok(i >= 0, `règle ${selecteur} absente`);
  return css.slice(i, css.indexOf("}", i));
}

test("sur l'ordinateur, la barre passe à la ligne", () => {
  const r = regle("html:not(.mobile) #barre");
  assert.match(r, /flex-wrap:\s*wrap/);
  assert.match(r, /height:\s*auto/);
});

test("les boutons du projet ne sont jamais écrasés", () => {
  assert.match(regle("html:not(.mobile) .barre-actions"), /flex:\s*none/);
});

test("la barre dit la pause d'une installation et l'attente de charge", async () => {
  const {retenues} = await import("../ui/texte.js");
  assert.deepEqual(retenues({}), []);
  assert.deepEqual(retenues({pause_installation: null, attente_charge: null}), []);
  assert.deepEqual(retenues({
    pause_installation: {texte: "Pause : installation de Godot Engine (CasseBrickReborn)"},
    attente_charge: {texte: "En attente : charge 90 % (plafond 70 %)"}}), [
    {ton: "pause", texte: "Pause : installation de Godot Engine (CasseBrickReborn)"},
    {ton: "attente", texte: "En attente : charge 90 % (plafond 70 %)"}]);
  assert.match(barre, /retenues\(etat\)/);
});

test("la barre dit les places libres qui attendent une validation", async () => {
  const {retenues} = await import("../ui/texte.js");
  const texte = "2 places libres : en attente de votre validation « Validation de la direction artistique »";
  assert.deepEqual(retenues({attente_validation: {texte, places: 2}}), [{ton: "attente", texte}]);
  assert.deepEqual(retenues({attente_validation: {texte: "  "}}), []);
});

test("la carte et le panneau d'une tâche montrent son attente de charge", () => {
  assert.match(readFileSync(new URL("../ui/detail.js", import.meta.url), "utf8"), /t\.attente/);
  assert.match(readFileSync(new URL("../ui/kanban-plein.js", import.meta.url), "utf8"), /t\.attente/);
});

test("la hauteur réelle de la barre est reportée sur la scène", () => {
  assert.match(barre, /ResizeObserver/);
  assert.match(barre, /--hauteur-barre/);
});
