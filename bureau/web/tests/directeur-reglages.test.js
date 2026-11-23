// Le panneau Direction ne porte plus « Où tournent les actions » ni « Où s'exécutent les étapes » (page Réglages) ;
// il garde un bouton « Réglages » ; et panneaux.js branche le type « reglages ».
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

test("Direction : plus de déport ni de lieux d'étapes, un bouton « Réglages »", async () => {
  let ouvert = 0;
  const contenu = new Noeud("div");
  contenuDirecteur({etat: ETAT, ouvrirReglages: () => { ouvert += 1; }, barre: {demander: async () => ({ok: true})}}, contenu);
  assert.doesNotMatch(contenu.textContent, /Où tournent les actions/);
  assert.doesNotMatch(contenu.textContent, /Où s'exécutent les étapes/);
  const b = contenu.tous((n) => n.tagName === "button" && n.textContent === "Réglages")[0];
  assert.ok(b);
  for (const f of b.auteurs.click) await f();
  assert.equal(ouvert, 1);
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
