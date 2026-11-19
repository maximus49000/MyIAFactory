// Essai réel (téléphone) : le panneau ouvert remontait en haut à chaque rafraîchissement du relevé.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const source = readFileSync(new URL("../ui/panneaux.js", import.meta.url), "utf8");

test("le même panneau redessiné garde son défilement", () => {
  const i = source.indexOf("panneau.replaceChildren(fermer, contenu);");
  assert.ok(i > 0);
  // la position est tenue jusqu'à l'arrivée du contenu chargé après coup (la facturation) : ui/defilement.js
  assert.match(source.slice(i, i + 200), /garde = memeVue \? garderDefilementDOM\(panneau, contenu, defilement\) : null;/);
  assert.match(source, /const defilement = memeVue \? \(garde\?\.actif\(\) \? garde\.y : panneau\.scrollTop\) : 0;/);
});

test("la carte d'un agent passe par lignesModele : un polyvalent n'a pas de « Plafond » à lui", () => {
  assert.match(source, /lignesModele\(e, a\)/);
  assert.doesNotMatch(source, /ligne\("Plafond"/);
});

// Essai réel : « Vu » sur une fonctionnalité terminée ne fermait pas l'avis (le panneau ne voyait pas `fin.vu`).
test("le panneau Direction se redessine quand un avis de fin ou une anomalie est vu", async () => {
  const {signatureDirecteur} = await import("../ui/directeur.js");
  const etat = (vu, anomalie) => ({version: 4, fonctionnalites: [{id: "f3", nom: "Corriger", etape: "terminee", decisions: [],
    fin: {date: "2026-11-16", vu}}], anomalies_logiciel: [{id: "a1", etat: anomalie}]});
  assert.notEqual(signatureDirecteur(etat(false, "nouvelle")), signatureDirecteur(etat(true, "nouvelle")));
  assert.notEqual(signatureDirecteur(etat(true, "nouvelle")), signatureDirecteur(etat(true, "vue")));
  assert.equal(signatureDirecteur(etat(true, "vue")), signatureDirecteur(etat(true, "vue")));
});

// La plateforme est globale : la carte « Serveur » est montée dans le panneau Direction (toujours atteignable),
// pas derrière le garde « e.partenaires » du panneau Partenaires.
test("la carte Serveur est montée dans le panneau Direction, pas dans la branche partenaires", () => {
  assert.match(source, /import \{monterCarteServeur\} from "\.\/plateforme\.js";/);
  assert.equal(source.split("monterCarteServeur(contenu)").length - 1, 1);
  const iPart = source.indexOf('type === "partenaires") {');
  const iAgent = source.indexOf('type === "agent") {', iPart);
  assert.doesNotMatch(source.slice(iPart, iAgent), /monterCarteServeur/);
  const iDir = source.indexOf("contenuDirecteur(contexte(), contenu);");
  assert.match(source.slice(iDir, iDir + 500), /e\.agir === true && typeof fetch === "function"\) monterCarteServeur\(contenu\)/);
});
