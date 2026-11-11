import test from "node:test";
import assert from "node:assert/strict";
import {entreesAssociation, cheminQR, rendreAssociation} from "../ui/associer.js";

// Un DOM minimal : assez pour vérifier ce que le panneau construit, et que les textes passent par textContent.
class Noeud {
  constructor(tag, ns = null) {
    this.tagName = tag; this.ns = ns; this.enfants = []; this.attributs = {}; this.ecouteurs = {};
    this.className = ""; this._texte = ""; this.hidden = false;
  }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  set innerHTML(v) { throw new Error("innerHTML interdit"); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this.enfants = [...e]; this._texte = ""; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(t, f) { this.ecouteurs[t] = f; }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {
  createElement: (t) => new Noeud(t),
  createElementNS: (ns, t) => new Noeud(t, ns),
};

const ACCES = {
  adresses: [{genre: "tailscale", url: "http://100.64.0.7:8770"},
             {genre: "reseau_local", url: "http://192.168.1.20:8770"}],
  code: "ABCD2345", expire: "2026-11-11T10:10:00",
};

test("entreesAssociation : un lien d'association par adresse, la mention « non chiffré » pour le Wi-Fi", () => {
  const e = entreesAssociation(ACCES);
  assert.deepEqual(e.map((x) => [x.genre, x.lien]),
    [["tailscale", "http://100.64.0.7:8770/associer?code=ABCD2345"],
     ["reseau_local", "http://192.168.1.20:8770/associer?code=ABCD2345"]]);
  assert.equal(e[0].mention, "");
  assert.match(e[1].mention, /non chiffré/i);
  assert.deepEqual(entreesAssociation({adresses: [], code: null}), []);
  assert.deepEqual(entreesAssociation(null), []);
  assert.deepEqual(entreesAssociation({adresses: [{genre: "x", url: "javascript:alert(1)"}], code: "A"}), []);
  assert.deepEqual(entreesAssociation({adresses: [{genre: "tailscale", url: "javascript:alert(1)"}], code: "A"}), []);
  assert.equal(entreesAssociation({...ACCES, code: "A&B"})[0].lien, "http://100.64.0.7:8770/associer?code=A%26B");
});

test("cheminQR : une matrice carrée, un tracé non vide", () => {
  const q = cheminQR("http://100.64.0.7:8770/associer?code=ABCD2345");
  assert.ok(q.taille >= 21);
  assert.match(q.d, /^M\d+ \d+h1v1h-1z/);
});

test("rendreAssociation : un QR par adresse, adresse et mention en textContent, révocation", () => {
  const conteneur = new Noeud("div");
  let revoque = 0;
  const hostile = {...ACCES, adresses: [{genre: "reseau_local", url: "http://192.168.1.20:8770/<img src=x>"}]};
  rendreAssociation(conteneur, hostile, {revoquer: () => { revoque++; }});
  assert.equal(conteneur.tous((n) => n.tagName === "svg").length, 1);
  assert.match(conteneur.textContent, /http:\/\/192\.168\.1\.20:8770\/<img src=x>/);
  assert.match(conteneur.textContent, /non chiffré/i);
  const bouton = conteneur.tous((n) => n.tagName === "button" && /Révoquer les téléphones/.test(n.textContent))[0];
  assert.ok(bouton);
  bouton.ecouteurs.click();
  assert.equal(revoque, 1);

  const deux = new Noeud("div");
  rendreAssociation(deux, ACCES, {revoquer() {}});
  assert.equal(deux.tous((n) => n.tagName === "svg").length, 2);
  assert.match(deux.textContent, /Tailscale/);

  const aucun = new Noeud("div");
  rendreAssociation(aucun, {adresses: [], code: null}, {revoquer() {}});
  assert.equal(aucun.tous((n) => n.tagName === "svg").length, 0);
  assert.match(aucun.textContent, /aucun accès/i);
});
