// Le rond de consommation : le nombre restant est écrit DANS le cercle, sans « % » ; le pourcentage reste dans
// l'infobulle, le nom accessible et le panneau.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

class Noeud {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.enfants = []; this.parent = null; this.attrs = {}; this.auteurs = {};
    this.hidden = false; this._texte = ""; this.className = ""; this.dataset = {}; this.style = {}; this.title = "";
  }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...es) { for (let e of es) { if (typeof e === "string") { const t = new Noeud("#texte"); t._texte = e; e = t; } e.parent = this; this.enfants.push(e); } }
  replaceChildren(...es) { this.enfants = []; this.append(...es); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener(n, f) { (this.auteurs[n] ||= []).push(f); }
  contains(n) { for (; n; n = n.parent) if (n === this) return true; return false; }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = new Noeud("#document");
document.createElement = (t) => new Noeud(t);
document.createElementNS = (ns, t) => { const n = new Noeud(t); n.ns = ns; return n; };
document.hidden = false;
globalThis.window = {addEventListener() {}};
globalThis.setInterval = () => 0;
let reponse = null;
globalThis.fetch = async () => (reponse ? {ok: true, json: async () => reponse} : {ok: false});

const {creerConso} = await import("../ui/conso.js");
const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");

async function monter(donnees) {
  reponse = donnees;
  const racine = creerConso();
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  const bouton = racine.tous((n) => n.tagName === "BUTTON" && n.classList === undefined && n.className === "conso-rond")[0];
  return {racine, bouton};
}

const dispo = {disponible: true, reste: 43, pire: "five_hour", source: "compte", fenetres: [{cle: "five_hour", libelle: "5 h", reste: 43, utilise: 57}]};

test("le nombre est dans le cercle, sans le signe %", async () => {
  const {bouton} = await monter(dispo);
  const dessin = bouton.enfants.find((n) => n.tagName === "SVG");
  const textes = dessin.tous((n) => n.tagName === "TEXT");
  assert.equal(textes.length, 1, "un seul texte, dans le SVG du rond");
  assert.equal(textes[0].textContent, "43");
  assert.equal(textes[0].getAttribute("text-anchor"), "middle");
  assert.doesNotMatch(bouton.textContent, /%/, "aucun % dans le rond");
  assert.equal(bouton.enfants.length, 1, "rien à côté du rond");
});

test("indisponible : le tiret est dans le rond", async () => {
  const {bouton} = await monter({disponible: false, raison: "Connexion à renouveler"});
  const t = bouton.tous((n) => n.tagName === "TEXT")[0];
  assert.equal(t.textContent, "—");
  assert.equal(bouton.getAttribute("aria-label"), "Consommation Claude Code indisponible");
});

test("le nom accessible garde le pourcentage, le bouton garde ses attributs", async () => {
  const {racine, bouton} = await monter(dispo);
  assert.equal(bouton.getAttribute("aria-label"), "Il reste 43 % (5 h)");
  assert.equal(bouton.title, "Il reste 43 % (5 h)");
  assert.equal(bouton.getAttribute("aria-haspopup"), "true");
  assert.equal(bouton.getAttribute("aria-expanded"), "false");
  assert.equal(racine.dataset.ton, "ok");
  const titre = racine.tous((n) => n.className === "conso-titre")[0];
  assert.equal(titre.textContent, "Il reste 43 %");
});

test("trois chiffres tiennent dans le rond", async () => {
  const {bouton} = await monter({...dispo, reste: 100});
  assert.equal(bouton.tous((n) => n.tagName === "TEXT")[0].textContent, "100");
});

test("la feuille ne connaît plus de texte à côté du rond", () => {
  assert.doesNotMatch(css, /conso-chiffre/);
  assert.doesNotMatch(readFileSync(new URL("../ui/conso.js", import.meta.url), "utf8"), /conso-chiffre|innerHTML/);
});
