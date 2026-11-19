// Résultats et minutes GitHub dans le bloc du déport : « 640 / 2 000 min », le niveau, les actions, les derniers résultats.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {};
    this.checked = false; this.disabled = false; this.value = ""; this.name = ""; this.type = ""; this.attrs = {}; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};

const {blocDeport, blocConso, libelleMinutes} = await import("../ui/deport.js");

const CONSO = {
  niveau: "alerte", texte: "640 / 2 000 min : 80 % du quota", mois: "2026-11", minutes_total: 640, quota: 2000,
  restantes: 1360, public: false,
  par_action: [{action: "apk", libelle: "Générer l'APK", minutes: 25, executions: 5}],
  derniers: [{action: "apk", libelle: "Générer l'APK", conclusion: "success", duree_s: 250, url: "https://github.com/o/d/actions/runs/1"},
             {action: "tests", libelle: "Tests unitaires", conclusion: "failure", duree_s: 45, url: "https://github.com/o/d/actions/runs/2"}],
};

test("libelleMinutes : « 640 / 2 000 min » avec quota, « 640 min » sans, « illimité » en public", () => {
  assert.equal(libelleMinutes(CONSO), "640 / 2 000 min");
  assert.equal(libelleMinutes({...CONSO, quota: null}), "640 min");
  assert.equal(libelleMinutes({...CONSO, public: true, quota: null}), "640 min (illimité)");
});

test("le bloc de consommation affiche les minutes, le niveau, les actions et les résultats avec lien", () => {
  const b = blocConso(CONSO);
  assert.ok(b.textContent.includes("640 / 2 000 min"));
  assert.ok(b.className.includes("deport-conso-alerte"));
  assert.ok(b.textContent.includes("Générer l'APK : 25 min (5 exécutions)"));
  assert.ok(b.textContent.includes("réussi"));
  assert.ok(b.textContent.includes("échoué"));
  assert.ok(b.textContent.includes("4 min 10 s"));
  const liens = b.tous((n) => n.tagName === "a");
  assert.deepEqual(liens.map((a) => a.href), CONSO.derniers.map((d) => d.url));
});

test("niveau dépassé : style dédié ; niveau ok : aucun style d'alerte", () => {
  assert.ok(blocConso({...CONSO, niveau: "depasse"}).className.includes("deport-conso-depasse"));
  assert.ok(!blocConso({...CONSO, niveau: "ok"}).className.includes("deport-conso-alerte"));
});

test("un lien qui n'est pas https n'est pas rendu cliquable", () => {
  const b = blocConso({...CONSO, derniers: [{...CONSO.derniers[0], url: "javascript:alert(1)"}]});
  assert.equal(b.tous((n) => n.tagName === "a").length, 0);
});

test("le bloc du déport montre la consommation quand l'état la porte, rien sinon", () => {
  const ctx = (conso) => ({etat: {deport: {lieux: {apk: "github"}, conso}}});
  assert.ok(blocDeport(ctx(CONSO), async () => ({ok: true})).textContent.includes("640 / 2 000 min"));
  assert.ok(!blocDeport(ctx(undefined), async () => ({ok: true})).textContent.includes("min ("));
});
