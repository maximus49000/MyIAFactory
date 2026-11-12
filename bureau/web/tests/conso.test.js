import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {tonReste, partRestante, remiseDans, libelleRond} from "../ui/conso.js";
import {lignePart, surConso, definirConsoCourante, consoCourante} from "../ui/mesure.js";

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

test("l'infobulle dit d'où vient la mesure quand elle vient du dernier appel", () => {
  const c = {disponible: true, source: "moteur", mesure: 1000, reste: 40, pire: "five_hour",
             fenetres: [{cle: "five_hour", libelle: "5 heures"}]};
  assert.equal(libelleRond(c, 1000 + 720), "Il reste 40 % (5 heures) — d'après le dernier appel, il y a 12 min");
  assert.equal(libelleRond({...c, source: "compte"}, 1000 + 720), "Il reste 40 % (5 heures)");
});

test("la ligne de part estimée du panneau", () => {
  assert.equal(lignePart({pourcent_par_euro: 2.04, mesures: 5, minimum: 3}),
    "Part estimée de vos coûts : ≈ 2,0 % de la semaine par euro");
  assert.equal(lignePart({pourcent_par_euro: null, mesures: 1, minimum: 3}),
    "Part estimée de vos coûts : étalonnage en cours (1/3 mesures)");
  assert.equal(lignePart(null), "");   // couche API : pas de part
});

test("la lecture du rond est partagée avec les jauges", () => {
  const vus = [];
  surConso((c) => vus.push(c));
  definirConsoCourante({disponible: true});
  assert.deepEqual(consoCourante(), {disponible: true});
  assert.equal(vus.length, 1);
});

test("les fenêtres 5 h / semaine ne passent dans le panneau que sans la place des jauges", () => {
  const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
  assert.match(css, /\.conso-principales \{ display: none; \}/);
  assert.match(css, /@media \(max-width: 700px\) \{\s*\.bloc-abonnement \.jauges \{ display: none; \}\s*\.conso-principales \{ display: block; \}/);
  const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");
  assert.match(barre, /blocAbonnement\.append\(creerConso\(\), jauges\)/);
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
