// « + Nouvelle correction » et « ? Une question » : les boutons et le mode correction du formulaire.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {demandeNouvelle, estCorrection, cleNouvelle, fonctionnalitesConcernables} from "../ui/fonctionnalite.js";

const lire = (f) => readFileSync(new URL("../ui/" + f, import.meta.url), "utf8");

test("la barre porte les trois boutons, montrés ensemble", () => {
  const barre = lire("barre.js");
  assert.match(barre, /"\+ Nouvelle correction"/);
  assert.match(barre, /"\? Une question"/);
  assert.match(barre, /for \(const b of \[boutonNouvelle, boutonCorrection, boutonQuestion, boutonFonctions\]\)/);
  assert.match(barre, /boutonNouvelle\.hidden = boutonCorrection\.hidden = boutonQuestion\.hidden = boutonFonctions\.hidden = !v4/);
  assert.match(barre, /boutonCorrection,\s+boutonQuestion,/);
});

test("les boutons ouvrent le formulaire en mode correction", () => {
  const p = lire("panneaux.js");
  assert.match(p, /boutonCorrection\.addEventListener\("click", \(\) => ouvrirNouvelle\("correction"\)\)/);
  assert.match(p, /function ouvrirNouvelle\(nature = "fonctionnalite", texte = null, concerne = null\)/);
});

test("la demande d'une correction porte nature et concerne ; celle d'une fonctionnalité reste inchangée", () => {
  assert.deepEqual(demandeNouvelle("Idée", []), {type: "fonctionnalite", texte: "Idée"});
  assert.deepEqual(demandeNouvelle("Idée", [], {nature: "fonctionnalite", concerne: "f1"}), {type: "fonctionnalite", texte: "Idée"});
  assert.deepEqual(demandeNouvelle("Bug", [], {nature: "correction"}), {type: "fonctionnalite", texte: "Bug", nature: "correction"});
  assert.deepEqual(demandeNouvelle("Bug", [], {nature: "correction", concerne: "f1"}),
                   {type: "fonctionnalite", texte: "Bug", nature: "correction", concerne: "f1"});
  assert.deepEqual(demandeNouvelle("Bug", [], {nature: "correction", concerne: ""}), {type: "fonctionnalite", texte: "Bug", nature: "correction"});
});

test("une correction se reconnaît, a son brouillon, et la liste des visées écarte les corrections terminées", () => {
  assert.equal(estCorrection({nature: "correction"}), true);
  assert.equal(estCorrection({}), false);
  assert.notEqual(cleNouvelle("correction"), cleNouvelle("fonctionnalite"));
  const etat = {fonctionnalites: [{id: "f1", nom: "A", etape: "production"}, {id: "f2", nom: "B", nature: "correction", etape: "terminee"},
                                  {id: "f3", nom: "C", nature: "correction", etape: "cadrage"}]};
  assert.deepEqual(fonctionnalitesConcernables(etat).map((f) => f.id), ["f1", "f3"]);
  assert.deepEqual(fonctionnalitesConcernables({}), []);
});

test("le formulaire en mode correction : titre, aide, liste, badge", () => {
  const f = lire("fonctionnalite.js");
  assert.match(f, /"Nouvelle correction"/);
  assert.match(f, /Décrivez l'anomalie/);
  assert.match(f, /Fonctionnalité concernée \(facultatif\)/);
  assert.match(f, /el\("span", "badge-correction", "Correction"\)/);
  assert.match(lire("../style.css"), /\.badge-correction/);
});
