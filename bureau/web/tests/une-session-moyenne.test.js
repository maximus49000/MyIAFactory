// Le réglage « Évolution moyenne : une seule session » : la case du Directeur écrit `une_session_moyenne`, décochée par défaut.
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

const {enregistrerUneSessionMoyenne, AIDE_UNE_SESSION_MOYENNE} = await import("../ui/directeur.js");

test("la case « une seule session » écrit une_session_moyenne", async () => {
  const vus = [];
  const r = await enregistrerUneSessionMoyenne(true, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  assert.equal(r.ok, true);
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.deepEqual(JSON.parse(vus[0][1].body), {une_session_moyenne: true});
  const coupe = await enregistrerUneSessionMoyenne(false, async () => { throw new Error("réseau"); });
  assert.equal(coupe.ok, false);
});

test("l'aide dit ce qui change et ce que l'on perd", () => {
  assert.match(AIDE_UNE_SESSION_MOYENNE, /moyenne/);
  assert.match(AIDE_UNE_SESSION_MOYENNE, /regard/);
});
