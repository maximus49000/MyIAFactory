// Les jauges d'abonnement et la part estimée : fonctions pures (les jauges elles-mêmes sont vérifiées dans le navigateur).
import {test, beforeEach} from "node:test";
import assert from "node:assert/strict";
import {
  tonJauge, ageMesure, heureRemise, vueJauge, formaterPart, etiquettePart, etiquettePlage, avecPart, definirAbonnement,
  INFOBULLE_PART, TEXTE_ETALONNAGE,
} from "../ui/abonnement.js";
import {texteCout, lignesBrouillons, lignesProposition} from "../ui/echange.js";
import {libelleCout} from "../ui/organisation.js";

const MAINTENANT = 1794480000;
const AB = {instantane: {five_hour: {pourcent: 25, remise: MAINTENANT + 3600}, seven_day: {pourcent: 96.4, remise: MAINTENANT + 86400}, t: MAINTENANT - 180},
            pourcent_par_euro: {five_hour: null, seven_day: 4}, mesures: {five_hour: 0, seven_day: 5}, minimum: 3};

beforeEach(() => definirAbonnement(undefined));

test("le ton : orange à partir de 80 %, rouge à partir de 95 %", () => {
  assert.equal(tonJauge(79.9), "ok");
  assert.equal(tonJauge(80), "attention");
  assert.equal(tonJauge(94.9), "attention");
  assert.equal(tonJauge(95), "alerte");
  assert.equal(tonJauge(null), "inconnu");
});

test("l'âge de la mesure", () => {
  assert.equal(ageMesure(MAINTENANT - 10, MAINTENANT), "à l'instant");
  assert.equal(ageMesure(MAINTENANT - 180, MAINTENANT), "il y a 3 min");
  assert.equal(ageMesure(MAINTENANT - 7200, MAINTENANT), "il y a 2 h");
  assert.equal(ageMesure(MAINTENANT - 3 * 86400, MAINTENANT), "il y a 3 j");
  assert.equal(ageMesure(undefined, MAINTENANT), "");
});

test("l'heure de remise à zéro est en heure locale (fuseau explicite pour le test)", () => {
  assert.equal(heureRemise(1794485400, false, {timeZone: "UTC"}), "12:10");
  assert.match(heureRemise(1794485400, true, {timeZone: "UTC"}), /^\w+\.? 12:10$/);
  assert.equal(heureRemise(undefined), "");
});

test("la jauge dit le nombre, le ton, la remise et l'âge ; rien d'inventé sans mesure", () => {
  const v = vueJauge("seven_day", AB, MAINTENANT, {timeZone: "UTC"});
  assert.equal(v.texte, "96 %");
  assert.equal(v.ton, "alerte");
  assert.equal(v.age, "il y a 3 min");
  assert.match(v.remise, /^RAZ /);
  assert.equal(vueJauge("five_hour", {instantane: {t: 1}}, MAINTENANT), null);
  assert.equal(vueJauge("five_hour", {instantane: null}, MAINTENANT), null);
  // la remise à zéro est passée depuis la mesure : on ne montre plus le vieux pourcentage
  const passee = vueJauge("five_hour", {instantane: {five_hour: {pourcent: 90, remise: MAINTENANT - 5}, t: MAINTENANT - 9000}}, MAINTENANT);
  assert.equal(passee.texte, "—");
  assert.equal(passee.ton, "inconnu");
});

test("le format d'une part", () => {
  assert.equal(formaterPart(0.04), "< 0,1");
  assert.equal(formaterPart(1.26), "1,3");
  assert.equal(formaterPart(12.4), "12");
  assert.equal(formaterPart(NaN), "");
});

test("la part estimée d'un coût : approximative, jamais sans mesure", () => {
  definirAbonnement(AB);
  assert.equal(etiquettePart(0.5), "≈ 2,0 % semaine");
  assert.equal(etiquettePart(0.01), "< 0,1 % semaine");
  assert.equal(etiquettePart(0), "");
  assert.equal(etiquettePart(null), "");
  assert.equal(etiquettePlage(0.4, 1.2), "≈ 1,6 à 4,8 % semaine");
  assert.match(INFOBULLE_PART, /autres sessions Claude/);
});

test("en cours d'étalonnage tant que le ratio manque (muet dans les listes)", () => {
  definirAbonnement({...AB, pourcent_par_euro: {five_hour: null, seven_day: null}});
  assert.equal(etiquettePart(0.5), TEXTE_ETALONNAGE);
  assert.equal(etiquettePart(0.5, {court: true}), "");
  assert.equal(etiquettePlage(0.4, 1.2), TEXTE_ETALONNAGE);
});

test("couche API ou état absent : aucune part", () => {
  definirAbonnement(null);
  assert.equal(etiquettePart(0.5), "");
  assert.equal(etiquettePlage(0.4, 1.2), "");
  assert.equal(avecPart("Coût", ""), "Coût");
  assert.equal(avecPart("Coût", "≈ 2 % semaine"), "Coût · ≈ 2 % semaine");
});

test("la part s'ajoute à chaque coût montré", () => {
  definirAbonnement(AB);
  assert.equal(texteCout({euros: 0.5}), "Coût de l'échange : 0,50 € · ≈ 2,0 % semaine");
  assert.match(lignesBrouillons([{id: "a", nom: "X", etat: "questions", euros: 0.5}])[0].detail, /0,50 € · ≈ 2,0 % semaine$/);
  assert.match(libelleCout({tokens: [1000, 2000], euros: [0.4, 1.2]}), /≈ 0,40 € à ≈ 1,20 € · ≈ 1,6 à 4,8 % semaine$/);
  const p = {nom: "N", agents: [], services: [], flux: [], cout: {tokens: [1000, 2000], euros: [0.4, 1.2]}};
  assert.match(lignesProposition(p).join("\n"), /\(≈ 1,6 à 4,8 % semaine\)\.$/m);
});

test("sans abonnement, les textes de coût sont ceux d'avant", () => {
  assert.equal(texteCout({euros: 0.5}), "Coût de l'échange : 0,50 €");
  assert.equal(libelleCout({tokens: [1000, 2000], euros: [0.4, 1.2]}), "1,0 k à 2,0 k tokens, ≈ 0,40 € à ≈ 1,20 €");
});
