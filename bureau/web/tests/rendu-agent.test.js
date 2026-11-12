// Les textes d'agent (compte rendu de la validation, message de la discussion, journal d'une tâche) sont rendus en Markdown
// sûr : tableaux, retours à la ligne gardés, aucun HTML interprété. Faux DOM.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.attributs = {}; this.value = ""; this.dataset = {};
    const n = this; this.classList = {add: (c) => { n.className = (n.className + " " + c).trim(); }}; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
globalThis.localStorage = {getItem: () => null, setItem() {}};

const V = await import("../ui/validation.js");
const F = await import("../ui/fonctionnalite.js");
const T = await import("../ui/detail.js");

const COMPTE = "Ajustements appliqués (scripts/jeu/equilibrage.gd)\n\n| Valeur | Avant | Après | Pourquoi |\n|---|---|---|---|\n"
  + "| EVENEMENT_ANOMALIE_COUT | 20 | 40 | La vie reste haute |\n| Texte de l'anomalie | <script>x</script> | y | z |";
const tables = (n) => n.tous((x) => x.tagName === "table");

test("fenêtre de validation : le compte rendu est un tableau, pas une ligne", () => {
  const d = {id: "v7", genre: "valider_etape", texte: "t", fonctionnalite: "f1", element: {id: "e1", nom: "Jeu"}, objectif: "o",
    a_valider: "a", compte_rendu: COMPTE, fichiers: [], points: ["p"]};
  const {boite} = V.contenuValidation({etat: {agir: true}, barre: {}}, d, {fermer() {}, hotePage: "127.0.0.1", origine: null});
  const t = tables(boite);
  assert.equal(t.length, 1);
  assert.equal(t[0].tous((n) => n.tagName === "tr").length, 3);
  assert.equal(boite.tous((n) => n.tagName === "script").length, 0);
  assert.match(boite.textContent, /<script>x<\/script>/);
  // et un compte rendu en texte simple garde ses retours à la ligne
  const simple = V.contenuValidation({etat: {agir: true}, barre: {}}, {...d, compte_rendu: "Un\nDeux"}, {fermer() {}, hotePage: "127.0.0.1", origine: null}).boite;
  assert.match(simple.tous((n) => /val-compte-rendu/.test(n.className))[0].textContent, /^Un\nDeux$/);
});

test("discussion : un message d'agent est rendu en Markdown, celui de l'utilisateur reste du texte", () => {
  const agent = F.messageDe({id: "m1", auteur: "dev-1", prenom: "Orion", texte: COMPTE}, {}, [{mot: "Valeur", definition: "ce qu'on règle"}]);
  assert.equal(tables(agent).length, 1);
  assert.equal(agent.tous((n) => n.className === "terme").length, 1);      // le glossaire fonctionne encore dans le tableau
  const moi = F.messageDe({id: "m2", auteur: "utilisateur", texte: "| a |\n|---|\n| 1 |"}, {}, []);
  assert.equal(tables(moi).length, 0);
});

test("panneau d'une tâche : le journal est rendu en Markdown", () => {
  const contenu = new Noeud("div");
  const ctx = {etat: {colonnes: [], agents: [], taches: [], types: []}, brouillons: new Map(), barre: {}};
  T.contenuTache(ctx, contenu, {id: "t1", titre: "T", colonne: "c", agent: "a", etape: "", maj: "2026-11-12T10:00:00+01:00", journal:
    [{t: "2026-11-12T10:00:00+01:00", texte: COMPTE}], liens: [], images: [], retours: [], notes: []});
  assert.equal(tables(contenu).length, 1);
});
