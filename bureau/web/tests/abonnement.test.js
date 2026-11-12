// Les jauges d'abonnement et la part estimée : fonctions pures (les jauges elles-mêmes sont vérifiées dans le navigateur).
import {test, beforeEach} from "node:test";
import assert from "node:assert/strict";
import {
  tonJauge, ageMesure, heureRemise, vueJauge, formaterPart, etiquettePart, etiquettePlage, avecPart, definirAbonnement,
  INFOBULLE_PART, TEXTE_ETALONNAGE,
} from "../ui/abonnement.js";
import {texteCout, lignesBrouillons, lignesProposition} from "../ui/echange.js";
import {libelleCout} from "../ui/organisation.js";
import {tonReste} from "../ui/mesure.js";

const MAINTENANT = 1794480000;
const AB = {instantane: {five_hour: {pourcent: 25, remise: MAINTENANT + 3600}, seven_day: {pourcent: 96.4, remise: MAINTENANT + 86400}, t: MAINTENANT - 180},
            pourcent_par_euro: {five_hour: null, seven_day: 4}, mesures: {five_hour: 0, seven_day: 5}, minimum: 3};

// La lecture du rond (/api/conso) : la source unique des jauges.
const iso = (t) => new Date(t * 1000).toISOString();
const CONSO = {disponible: true, source: "compte", mesure: MAINTENANT - 180, reste: 3.6, pire: "seven_day",
               fenetres: [{cle: "five_hour", libelle: "5 heures", utilise: 25, reste: 75, remise: iso(MAINTENANT + 3600)},
                          {cle: "seven_day", libelle: "Semaine", utilise: 96.4, reste: 3.6, remise: iso(MAINTENANT + 86400)}]};

beforeEach(() => definirAbonnement(undefined));

test("le ton des jauges est celui du rond : même seuils sur ce qui reste", () => {
  assert.equal(tonJauge(69.9), "ok");
  assert.equal(tonJauge(70), "attention");
  assert.equal(tonJauge(89.9), "attention");
  assert.equal(tonJauge(90), "alerte");
  assert.equal(tonJauge(null), "inconnu");
  for (const utilise of [0, 40, 70, 85, 90, 99.5]) {
    assert.equal(tonJauge(utilise), tonReste(100 - utilise));   // une jauge rouge quand le rond est en alerte
  }
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
  const v = vueJauge("seven_day", CONSO, MAINTENANT, {timeZone: "UTC"});
  assert.equal(v.texte, "96 %");
  assert.equal(v.ton, "alerte");
  assert.equal(v.age, "il y a 3 min");
  assert.match(v.remise, /^RAZ /);
  assert.equal(vueJauge("five_hour", {disponible: true, fenetres: [], mesure: 1}, MAINTENANT), null);
  assert.equal(vueJauge("five_hour", {disponible: false, raison: "x"}, MAINTENANT), null);
  assert.equal(vueJauge("five_hour", null, MAINTENANT), null);
  // la remise à zéro est passée depuis la mesure : on ne montre plus le vieux pourcentage
  const vieux = {...CONSO, fenetres: [{cle: "five_hour", utilise: 90, reste: 10, remise: iso(MAINTENANT - 5)}]};
  const passee = vueJauge("five_hour", vieux, MAINTENANT);
  assert.equal(passee.texte, "—");
  assert.equal(passee.ton, "inconnu");
});

test("le rond et les jauges disent la même chose : mêmes nombres, mêmes tons, même provenance", () => {
  const rond = CONSO.fenetres.map((f) => [f.cle, Math.round(f.reste), tonReste(f.reste)]);
  const jauges = CONSO.fenetres.map((f) => {
    const v = vueJauge(f.cle, CONSO, MAINTENANT);
    return [f.cle, 100 - Math.round(v.pourcent), v.ton];
  });
  assert.deepEqual(jauges.map((j) => j[2]), rond.map((r) => r[2]));
  assert.deepEqual(jauges.map((j) => j[1]), rond.map((r) => r[1]));
  assert.equal(tonReste(CONSO.reste), vueJauge("seven_day", CONSO, MAINTENANT).ton);
});

test("repli sur le dernier appel du moteur : les jauges le disent", () => {
  const moteur = {...CONSO, source: "moteur", mesure: MAINTENANT - 720};
  assert.equal(vueJauge("seven_day", moteur, MAINTENANT).age, "d'après le dernier appel, il y a 12 min");
  assert.equal(vueJauge("seven_day", moteur, MAINTENANT).source, "moteur");
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
