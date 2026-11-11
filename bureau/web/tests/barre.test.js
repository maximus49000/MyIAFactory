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

test("la hauteur réelle de la barre est reportée sur la scène", () => {
  assert.match(barre, /ResizeObserver/);
  assert.match(barre, /--hauteur-barre/);
});
