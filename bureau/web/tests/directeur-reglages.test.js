// Le panneau Direction ne porte plus « Où tournent les actions » ni « Où s'exécutent les étapes » (page Réglages) ;
// son bouton « Réglages » est parti (la roue de la barre y mène) ; et panneaux.js branche le type « reglages ».
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; this.disabled = false; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  after(...e) { this.apres = e; }
  replaceChildren(...e) { this.enfants = e; }
  querySelector() { return new Noeud("x"); }
  querySelectorAll() { return []; }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };
globalThis.window = globalThis.window || {confirm: () => true};

const {contenuDirecteur} = await import("../ui/directeur.js");
const source = readFileSync(new URL("../ui/panneaux.js", import.meta.url), "utf8");

const ETAT = {version: 4, agir: true, lecons: [], decisions: 0,
  etapes_lieux: [{id: "build", nom: "Build", role: "dev", validation: false, lieu: "local"}],
  deport: {lieux: {apk: "poste", tests: "poste", charge: "poste", emulateur: "poste"}, avertissements: []}};

test("Direction : plus de déport ni de lieux d'étapes", () => {
  const contenu = new Noeud("div");
  contenuDirecteur({etat: ETAT, ouvrirReglages: () => {}, barre: {demander: async () => ({ok: true})}}, contenu);
  assert.doesNotMatch(contenu.textContent, /Où tournent les actions/);
  assert.doesNotMatch(contenu.textContent, /Où s'exécutent les étapes/);
});

test("le_bouton_Reglages_de_Direction_a_disparu", () => {
  // L'accès à la page Réglages passe par la roue crantée de la barre du haut.
  const contenu = new Noeud("div");
  contenuDirecteur({etat: ETAT, ouvrirReglages: () => {}, barre: {demander: async () => ({ok: true})}}, contenu);
  assert.equal(contenu.tous((n) => n.tagName === "button" && n.textContent === "Réglages").length, 0);
  assert.doesNotMatch(readFileSync(new URL("../ui/directeur.js", import.meta.url), "utf8"), /ctx\.ouvrirReglages/);
});

test("panneaux.js : le type « reglages » est branché, avec retour vers Direction", () => {
  assert.match(source, /import \{contenuReglages\} from "\.\/reglages\.js";/);
  assert.match(source, /ouvrirReglages: \(\) => ouvrirPanneau\("reglages", null\)/);
  assert.match(source, /if \(type === "reglages"\) return JSON\.stringify\(\[e\.reglages_page, e\.reglages_page_erreur, e\.deport, e\.etapes_lieux, e\.agir\]\);/);
  const i = source.indexOf('type === "reglages") {');
  assert.ok(i > 0);
  const j = source.indexOf('type === "agent") {', i);
  const branche = source.slice(i, j);
  assert.match(branche, /contenuReglages\(contexte\(\), contenu\)/);
  assert.match(branche, /← Direction/);
  assert.match(branche, /ouvrirPanneau\("direction", null\)/);
  assert.doesNotMatch(branche, /monterCarteServeur/);
});
