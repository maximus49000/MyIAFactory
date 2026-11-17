// Le panneau d'une tâche : la ligne « Story » mène à la carte de sa fonctionnalité.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; this.disabled = false; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  get lastChild() { return this.enfants[this.enfants.length - 1] || null; }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};

const {contenuTache} = await import("../ui/detail.js");

const tache = (fonctionnalite) => ({id: "t26", titre: "Cadrage : Simplification du menu", fonctionnalite, colonne: "a", agent: null,
  etape: "", journal: [], liens: [], retours: [], images: [], notes: [], maj: ""});
const etat = (t) => ({agir: false, colonnes: [{id: "a", nom: "A"}], agents: [], taches: [t], types: [],
  fonctionnalites: [{id: "f5", nom: "Simplification globale"}]});

function rendre(t, ctxEnPlus = {}) {
  const contenu = new Noeud("div");
  contenuTache({etat: etat(t), ...ctxEnPlus}, contenu, t);
  return contenu;
}

test("la ligne Story nomme la fonctionnalité et ouvre sa carte", () => {
  const ouvertes = [];
  const contenu = rendre(tache("f5"), {ouvrirFonctionnalite: (id) => ouvertes.push(id)});
  assert.match(contenu.textContent, /Story.*Simplification globale/);
  const b = contenu.tous((n) => n.tagName === "button" && /Simplification globale/.test(n.textContent))[0];
  assert.ok(b, "un bouton mène à la story");
  b.auteurs.click[0]();
  assert.deepEqual(ouvertes, ["f5"]);
});

test("sans fonctionnalité connue, pas de ligne Story", () => {
  assert.doesNotMatch(rendre(tache(null), {ouvrirFonctionnalite() {}}).textContent, /Story/);
  assert.doesNotMatch(rendre(tache("f99"), {ouvrirFonctionnalite() {}}).textContent, /Story/);
});

test("sans moyen d'ouvrir, le nom seul, sans bouton", () => {
  const contenu = rendre(tache("f5"));
  assert.match(contenu.textContent, /Story.*Simplification globale/);
  assert.equal(contenu.tous((n) => n.tagName === "button").length, 0);
});
