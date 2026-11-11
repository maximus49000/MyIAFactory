import test from "node:test";
import assert from "node:assert/strict";
import {doitProposer, DUREES, phase, departs, tomber, signeDeCode, texteTape, SIGNES} from "../logique/lancement.js";

test("doitProposer : seulement une réponse qui dit « pas vu »", () => {
  assert.equal(doitProposer({vu: false}), true);
  for (const r of [{vu: true}, null, undefined, {erreur: "x"}, {vu: "false"}, {}, "vu", []])
    assert.equal(doitProposer(r), false, JSON.stringify(r));
});

test("phase : réflexion, frappe, pause, lettres, attente du bureau, chute de la fenêtre, fin", () => {
  assert.deepEqual(DUREES, {reflexion: 2.2, frappe: 2.0, pause: 0.9, lettres: 2.6, fenetre: 1.2, plafond: 10});
  const nom = (t, pret) => phase(t, pret).nom;
  assert.equal(nom(0, null), "reflexion");
  assert.equal(nom(2.3, null), "frappe");
  assert.equal(nom(4.5, null), "pause");
  assert.equal(nom(6, null), "lettres");
  assert.equal(nom(8, null), "attente");     // lettres finies, bureau pas prêt
  assert.equal(nom(8, 1), "fenetre");         // prêt depuis longtemps : la fenêtre tombe dès la fin des lettres
  assert.equal(nom(9.5, 9), "fenetre");       // prêt à 9 s : la fenêtre tombe depuis 9 s
  assert.equal(nom(8.9, 9), "attente");
  assert.equal(nom(10.1, null), "fenetre");   // plafond : on tombe quand même
  assert.equal(nom(20, null), "fin");
  assert.equal(nom(20, 1), "fin");
});

test("phase : l'avancement va de 0 à 1 dans chaque phase", () => {
  assert.equal(phase(0, null).avance, 0);
  assert.equal(phase(1.1, null).avance, 0.5);
  assert.equal(phase(3.2, null).avance, 0.5);   // frappe : 2,2 → 4,2
  assert.equal(phase(20, null).avance, 1);
  const f = phase(10.6, null);                   // fenêtre : 10 → 11,2
  assert.equal(f.nom, "fenetre");
  assert.ok(Math.abs(f.avance - 0.5) < 1e-9);
  assert.equal(phase(-1, null).nom, "reflexion");
  assert.equal(phase(-1, null).avance, 0);
});

test("departs : de gauche à droite, du haut vers le bas, un peu au hasard, bornés", () => {
  assert.deepEqual(departs([{x: 0, y: 0}], 100, 100, () => 0), [0.3]);
  assert.deepEqual(departs([{x: 0, y: 100}], 100, 100, () => 0), [0]);
  const d = departs([{x: 100, y: 0}, {x: 500, y: -50}], 100, 100, () => 1);
  assert.ok(Math.abs(d[0] - 2.1) < 1e-9);
  assert.equal(d[1], 2.1);
  assert.deepEqual(departs([{x: NaN, y: undefined}], 0, 0, () => 0), [0.3]);   // illisible : en haut à gauche
});

test("tomber : la pesanteur, sans modifier la lettre d'origine", () => {
  const l = {c: "a", y: 0, v: 0};
  const n = tomber(l, 0.1);
  assert.ok(Math.abs(n.v - 140) < 1e-9);
  assert.ok(Math.abs(n.y - 14) < 1e-9);
  assert.equal(n.c, "a");
  assert.deepEqual(l, {c: "a", y: 0, v: 0});
});

test("signeDeCode et texteTape", () => {
  assert.equal(signeDeCode(() => 0), "a");
  assert.equal(signeDeCode(() => 0.9999999), SIGNES.at(-1));
  assert.equal(texteTape("abcd", 0.5), "ab");
  assert.equal(texteTape("abcd", 0), "");
  assert.equal(texteTape("abcd", 1), "abcd");
  assert.equal(texteTape("abcd", 7), "abcd");
});
