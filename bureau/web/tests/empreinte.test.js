// L'empreinte carbone estimée : mise en forme, jamais de chiffre sans valeur ; affichée aux endroits des coûts.
import {test, beforeEach} from "node:test";
import assert from "node:assert/strict";
import {etiquetteCO2, energie, infobulleCO2, INFOBULLE_CO2, URL_METHODE, texteEquivalences, infobulleEquivalences, nombreFr} from "../ui/empreinte.js";
import {definirAbonnement} from "../ui/abonnement.js";
import {texteCout, lignesBrouillons, lignesProposition, texteAbandonnes} from "../ui/echange.js";
import {libelleCout} from "../ui/organisation.js";
import {lignesTaches, lignesModeles, lignesDiscussions, coutDeTache, totalProjet} from "../ui/facturation.js";

beforeEach(() => definirAbonnement(undefined));

test("la fourchette en grammes, en kg au-delà de 1000 g", () => {
  assert.equal(etiquetteCO2({min: 0.456, max: 0.724}), "≈ 0,46 à 0,72 g CO₂e");
  assert.equal(etiquetteCO2({min: 3.04, max: 12.6}), "≈ 3,0 à 13 g CO₂e");
  assert.equal(etiquetteCO2({min: 840, max: 1200}), "≈ 0,8 à 1,2 kg CO₂e");
  assert.equal(etiquetteCO2({min: 1200, max: 3400}), "≈ 1,2 à 3,4 kg CO₂e");
  assert.equal(etiquetteCO2({min: 0.001, max: 0.004}), "< 0,01 g CO₂e");
  assert.equal(etiquetteCO2({min: 5, max: 5.01}), "≈ 5,0 g CO₂e");
});

test("jamais de chiffre sans valeur", () => {
  for (const v of [undefined, null, {}, {min: 1}, {min: NaN, max: NaN}, {min: 0, max: 0}, {min: "1", max: "2"}]) {
    assert.equal(etiquetteCO2(v), "");
  }
});

test("un cumul partiel le dit", () => {
  assert.equal(etiquetteCO2({min: 1, max: 2, incomplet: true}), "≈ 1,0 à 2,0 g CO₂e (partiel)");
});

test("l'énergie et l'infobulle", () => {
  assert.equal(energie({wh_min: 1.13, wh_max: 1.8}), "1,13 à 1,80 Wh");
  assert.equal(energie({}), "");
  assert.match(infobulleCO2({wh_min: 1.13, wh_max: 1.8}), /énergie ≈ 1,13 à 1,80 Wh/);
  assert.equal(infobulleCO2({}), INFOBULLE_CO2);
  assert.match(INFOBULLE_CO2, /EcoLogits.*tokens de sortie seulement.*États-Unis/);
  assert.match(URL_METHODE, /^https:\/\/ecologits\.ai\//);
});

const CO2 = {min: 0.46, max: 0.72};

test("le coût de l'échange de création et ses brouillons", () => {
  assert.equal(texteCout({euros: 0.12, tokens: 100, co2: CO2}), "Coût de l'échange : 0,12 € · ≈ 0,46 à 0,72 g CO₂e");
  assert.equal(texteCout({euros: 0.12, tokens: 100}), "Coût de l'échange : 0,12 €");
  assert.match(texteCout({euros: null, tokens: 1000, co2: CO2}), /prix inconnu.*CO₂e/);
  const l = lignesBrouillons([{id: "b", nom: "Jeu", euros: 0.5, co2: CO2, tours: 1}]);
  assert.match(l[0].detail, /0,50 € · ≈ 0,46 à 0,72 g CO₂e/);
  assert.match(texteAbandonnes({euros: 0.3, co2: CO2}), /Échanges abandonnés : 0,30 € · ≈ 0,46/);
});

test("la proposition du chef et l'organisation proposée", () => {
  const p = {cout: {tokens: [1000, 2000], euros: [0.1, 0.2], co2: {min: 12, max: 30}}, workflow: {flux: []}, services: []};
  assert.match(lignesProposition(p).join("\n"), /soit 0,10 à 0,20 €.*≈ 12 à 30 g CO₂e/);
  const sans = {...p, cout: {tokens: [1000, 2000], euros: null, co2: {min: 12, max: 30}}};
  assert.match(lignesProposition(sans).join("\n"), /prix inconnu.*≈ 12 à 30 g CO₂e/);
  assert.match(libelleCout({tokens: [1000, 2000], euros: [0.1, 0.2], co2: {min: 12, max: 30}}), /≈ 0,10 € à ≈ 0,20 € · ≈ 12 à 30 g CO₂e$/);
  assert.doesNotMatch(libelleCout({tokens: [1000, 2000], euros: [0.1, 0.2]}), /CO₂e/);
});

test("la facturation : par tâche, par étape, par modèle, par discussion et en total", () => {
  const s = {taches: {t1: {total: 1, sans_prix: 0, etapes: {dev: 1}, co2: CO2, etapes_co2: {dev: {min: 0.2, max: 0.3}}}},
             modeles: {sonnet: 1}, modeles_co2: {sonnet: CO2},
             usages: [{id: "u", t: "2026-11-10T10:00:00", modele: "sonnet", tokens: {}, cout: 1, co2: CO2}]};
  const taches = lignesTaches(s, [{id: "t1", titre: "Tâche"}]);
  assert.deepEqual(taches[0].co2, CO2);
  assert.deepEqual(taches[0].etapes[0].co2, {min: 0.2, max: 0.3});
  assert.match(coutDeTache(taches[0]), /1,00.*· ≈ 0,46 à 0,72 g CO₂e/);
  assert.deepEqual(lignesModeles(s)[0].co2, CO2);
  assert.deepEqual(lignesDiscussions(s, {})[0].co2, CO2);
  assert.deepEqual(totalProjet({total: 2, co2: CO2, direction: {total: 0, co2: {min: 1, max: 2}}}).co2, CO2);
  assert.equal(lignesTaches({taches: {t1: {total: 1, etapes: {}}}}, [])[0].co2, undefined);   // pas de zéro inventé
});

const EQ = [{cle: "voiture", valeur: 1.4, unite: "km", libelle: "km en voiture thermique", min: 1.1, max: 1.7},
            {cle: "smartphone", valeur: 12500, unite: "recharge", libelle: "recharges complètes de smartphone", min: 10000, max: 15000},
            {cle: "led", valeur: 230, unite: "h", libelle: "heures d'ampoule LED 10 W", min: 200, max: 260}];

test("les équivalences : écrites telles que le serveur les sert, avec la fourchette en infobulle", () => {
  const co2 = {min: 300, max: 400, equivalences: EQ};
  assert.equal(texteEquivalences(co2),
    "Équivaut à ≈ 1,4 km en voiture thermique · ≈ 12 500 recharges complètes de smartphone · ≈ 230 heures d'ampoule LED 10 W");
  const t = infobulleEquivalences(co2);
  assert.match(t, /Ordre de grandeur/);
  assert.match(t, /ADEME/);
  assert.match(t, /km en voiture thermique : 1,1 à 1,7/);
  assert.equal(nombreFr(0.5), "0,5");
});

test("pas d'équivalence : rien, jamais de chiffre inventé", () => {
  for (const co2 of [null, {}, {min: 1, max: 2}, {equivalences: []}, {equivalences: [{libelle: "x"}]}]) {
    assert.equal(texteEquivalences(co2), "");
  }
  assert.equal(totalProjet({total: 1, co2: {min: 1, max: 2, equivalences: EQ}}).co2.equivalences.length, 3);
});
