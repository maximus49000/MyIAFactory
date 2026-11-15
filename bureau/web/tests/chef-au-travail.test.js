import {test} from "node:test";
import assert from "node:assert/strict";
import {texteChef, retenues} from "../ui/texte.js";
import {ecritDetail} from "../ui/fonctionnalite.js";

// Essai réel : pendant que le moteur écrivait une méthode, rien ne bougeait au bureau et le processus semblait bloqué.
const etat = {
  fonctionnalites: [{id: "f5", nom: "Quantités multiples", attend_reponse: false, discussion: []}],
  chef_au_travail: {texte: "Le Chef est en train d'écrire la méthode", fonctionnalite: "f5", depuis: 1000},
};

test("la barre dit ce que fait le Chef, avec la fonctionnalité et la durée", () => {
  assert.equal(texteChef(etat, null, 1000_000 + 125_000),
    "Le Chef est en train d'écrire la méthode de « Quantités multiples » · depuis 2 min…");
  assert.equal(texteChef(etat, null, 1000_000 + 10_000),
    "Le Chef est en train d'écrire la méthode de « Quantités multiples » · à l'instant…");
  assert.equal(retenues(etat)[0].texte.startsWith("Le Chef est en train d'écrire la méthode"), true);
  assert.equal(texteChef({}, null), null);
});

test("la discussion de la fonctionnalité concernée le dit, pas les autres", () => {
  const d = ecritDetail(etat.fonctionnalites[0], etat, false, new Date(1000_000 + 70_000));
  assert.deepEqual(d, {texte: "Le Chef est en train d'écrire la méthode · depuis 1 min…", actif: true});
  assert.equal(texteChef(etat, "f1"), null);
});
