// Le réglage « Livrer seulement sur demande » : la case du Directeur écrit `livraison_sur_demande`, décochée par défaut.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };

const {contenuDecisionsV4} = await import("../ui/decisions.js");
const {enregistrerLivraisonSurDemande, AIDE_LIVRAISON_SUR_DEMANDE} = await import("../ui/directeur.js");

test("la case « Livrer seulement sur demande » écrit livraison_sur_demande", async () => {
  const vus = [];
  const r = await enregistrerLivraisonSurDemande(true, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  assert.equal(r.ok, true);
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.deepEqual(JSON.parse(vus[0][1].body), {livraison_sur_demande: true});
  const coupe = await enregistrerLivraisonSurDemande(false, async () => { throw new Error("réseau"); });
  assert.equal(coupe.ok, false);
});

test("l'aide de la case dit ce qui change et comment livrer", () => {
  assert.match(AIDE_LIVRAISON_SUR_DEMANDE, /Livrer maintenant/);
  assert.match(AIDE_LIVRAISON_SUR_DEMANDE, /apk/i);
});
