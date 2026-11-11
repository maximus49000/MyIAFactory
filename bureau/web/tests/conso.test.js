import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {tonReste, partRestante, remiseDans, libelleRond} from "../ui/conso.js";

test("le ton du rond suit ce qu'il reste", () => {
  assert.equal(tonReste(80), "ok");
  assert.equal(tonReste(30), "attention");
  assert.equal(tonReste(10), "alerte");
  assert.equal(tonReste(NaN), "inconnu");
});

test("la part restante est bornée", () => {
  assert.equal(partRestante(150), 1);
  assert.equal(partRestante(-3), 0);
  assert.equal(partRestante(25), 0.25);
  assert.equal(partRestante(undefined), 0);
});

test("la remise à zéro se dit en durée", () => {
  const t0 = Date.parse("2026-11-12T10:00:00Z");
  assert.equal(remiseDans("2026-11-12T10:30:00Z", t0), "dans 30 min");
  assert.equal(remiseDans("2026-11-12T12:05:00Z", t0), "dans 2 h 05");
  assert.equal(remiseDans("2026-11-12T13:00:00Z", t0), "dans 3 h");
  assert.equal(remiseDans("2026-11-15T10:00:00Z", t0), "dans 3 j");
  assert.equal(remiseDans("2026-11-12T09:00:00Z", t0), "maintenant");
  assert.equal(remiseDans(null, t0), "");
});

test("l'infobulle du rond", () => {
  assert.equal(libelleRond({disponible: false, raison: "Connexion à renouveler"}), "Connexion à renouveler");
  assert.equal(libelleRond({disponible: true, reste: 8.5, pire: "seven_day", fenetres: [{cle: "seven_day", libelle: "Semaine"}]}),
    "Il reste 9 % (Semaine)");
});

test("le panneau est fixe : la barre mobile défile et le rognerait", () => {
  const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
  const i = css.indexOf(".conso-panneau {");
  assert.match(css.slice(i, css.indexOf("}", i)), /position:\s*fixed/);
});

test("le rond est dans le bandeau", () => {
  const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");
  assert.match(barre, /creerConso\(\)/);
});
