import test from "node:test";
import assert from "node:assert/strict";
import {tronquer, voyant, libelleCharge, dureeEnClair, ilYA} from "../ui/texte.js";

const MAINTENANT = new Date("2026-11-10T12:00:00Z");
const ilYa = (minutes) => new Date(MAINTENANT.getTime() - minutes * 60000).toISOString();

test("tronquer", () => {
  assert.equal(tronquer("x".repeat(300), 40), "x".repeat(40) + "…");
  assert.equal(tronquer(null, 5), "");
  assert.equal(tronquer(undefined, 5), "");
  assert.equal(tronquer("abc", 5), "abc");
  assert.equal(tronquer("abcde", 5), "abcde");
});

test("tronquer garde le texte hostile tel quel", () => {
  const t = tronquer("<img src=x onerror=alert(1)>" + "y".repeat(300), 60);
  assert.ok(t.startsWith("<img src=x onerror=alert(1)>"));
  assert.ok(t.endsWith("…"));
  assert.equal(t.length, 61);
});

test("dureeEnClair", () => {
  assert.deepEqual([45, 60, 125, 47 * 60, 48 * 60, 5000].map(dureeEnClair),
                   ["45 min", "1 h", "2 h", "47 h", "2 j", "3 j"]);
});

test("voyant", () => {
  assert.deepEqual(voyant({etat: "en marche", inactive: false}, null), {libelle: "En marche", ton: "ok"});
  assert.deepEqual(voyant({etat: "en pause"}, null), {libelle: "En pause", ton: "pause"});
  assert.equal(voyant({etat: "en marche", inactive: true, derniere_activite: ilYa(125)}, null, MAINTENANT).libelle,
               "En marche, sans activité depuis 2 h");
  assert.equal(voyant({etat: "en marche", inactive: true, derniere_activite: null}, null, MAINTENANT).libelle,
               "En marche, sans activité");
  assert.equal(voyant({etat: "inconnu"}, "fichier absent").ton, "alerte");
  assert.equal(voyant({etat: "inconnu"}, "fichier absent").libelle, "Relevé indisponible");
  assert.equal(voyant(null, null).ton, "alerte");
});

test("libelleCharge", () => {
  assert.equal(libelleCharge({disponible: true, charge: 62, cpu: 12.4, memoire: 61.6}), "Charge 62 % · processeur 12 %, mémoire 62 %");
  assert.equal(libelleCharge({disponible: false}), "Mesure indisponible");
  assert.equal(libelleCharge(null), "Mesure indisponible");
});

test("ilYA", () => {
  assert.equal(ilYA(ilYa(5), MAINTENANT), "il y a 5 min");
  assert.equal(ilYA(ilYa(125), MAINTENANT), "il y a 2 h");
  assert.equal(ilYA(ilYa(0), MAINTENANT), "à l'instant");
  assert.equal(ilYA("", MAINTENANT), "inconnue");
  assert.equal(ilYA("hier", MAINTENANT), "inconnue");
  assert.equal(ilYA(null, MAINTENANT), "inconnue");
});
