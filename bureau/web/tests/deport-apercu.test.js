// L'aperçu du workflow déporté : le diff s'affiche, « Valider et pousser » envoie l'empreinte affichée.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {};
    this.checked = false; this.disabled = false; this.value = ""; this.name = ""; this.type = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};

const {blocDeport, lireApercu, validerEtPousser} = await import("../ui/deport.js");

const EMP = "a".repeat(64);
const APERCU = {etat: "absent", diff: "--- actuel\n+++ proposé\n+jobs:\n", chemin: ".github/workflows/p.yml", empreinte: EMP};
const reponse = (code, objet) => ({ok: code < 400, status: code, json: async () => objet});
const boutons = (b) => b.tous((n) => n.tagName === "button");
const bouton = (b, re) => boutons(b).find((x) => re.test(x.textContent));
const cliquer = async (n) => { for (const f of n.auteurs.click || []) await f(); };

function rendre(fetchFn, lieux = {apk: "github", tests: "poste", charge: "poste", emulateur: "poste"}) {
  const ctx = {etat: {deport: {lieux, avertissements: []}}, rouvrir() {}};
  return blocDeport(ctx, fetchFn);
}

test("lireApercu demande /api/deport/apercu et rend l'aperçu ; erreur lisible sinon", async () => {
  const vus = [];
  const ok = await lireApercu(async (url) => { vus.push(url); return reponse(200, APERCU); });
  assert.match(vus[0], /\/api\/deport\/apercu/);
  assert.deepEqual(ok, {ok: true, apercu: APERCU});
  const refus = await lireApercu(async () => reponse(400, {erreur: "Aucune commande pour l'action « apk »"}));
  assert.equal(refus.ok, false);
  assert.match(refus.message, /Aucune commande/);
  assert.equal((await lireApercu(async () => { throw new Error("x"); })).ok, false);
});

test("validerEtPousser envoie l'empreinte en POST avec l'en-tête du bureau", async () => {
  const vus = [];
  const r = await validerEtPousser(EMP, async (url, options) => { vus.push([url, options]); return reponse(200, {ok: true, message: "Envoyé."}); });
  assert.match(vus[0][0], /\/api\/deport\/appliquer/);
  assert.equal(vus[0][1].method, "POST");
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.deepEqual(JSON.parse(vus[0][1].body), {empreinte: EMP});
  assert.deepEqual(r, {ok: true, message: "Envoyé."});
  const refus = await validerEtPousser(EMP, async () => reponse(409, {erreur: "plus à jour"}));
  assert.deepEqual(refus, {ok: false, message: "Refusé : plus à jour"});
});

test("le bloc propose l'aperçu ; il affiche le diff et l'état ; rien n'est envoyé sans le second clic", async () => {
  const vus = [];
  const bloc = rendre(async (url, options) => { vus.push([url, options]); return reponse(200, APERCU); });
  assert.equal(bouton(bloc, /Valider et pousser/), undefined);
  await cliquer(bouton(bloc, /Aperçu du workflow/));
  assert.equal(vus.length, 1);
  assert.equal(vus[0][1]?.method, undefined);   // une lecture
  assert.match(bloc.textContent, /\+jobs:/);
  assert.match(bloc.textContent, /n.existe encore/);
  assert.equal(vus.some(([, o]) => o?.method === "POST"), false);
});

test("« Valider et pousser » envoie l'empreinte affichée, puis dit le résultat", async () => {
  const vus = [];
  const bloc = rendre(async (url, options) => {
    vus.push([url, options]);
    return options?.method === "POST" ? reponse(200, {ok: true, message: "Workflow envoyé sur la branche « deport/workflow »."}) : reponse(200, APERCU);
  });
  await cliquer(bouton(bloc, /Aperçu du workflow/));
  await cliquer(bouton(bloc, /Valider et pousser/));
  const post = vus.find(([, o]) => o?.method === "POST");
  assert.deepEqual(JSON.parse(post[1].body), {empreinte: EMP});
  assert.match(bloc.textContent, /deport\/workflow/);
});

test("un fichier modifié à la main ne peut pas être poussé ; sans action GitHub, pas d'aperçu", async () => {
  const bloc = rendre(async () => reponse(200, {...APERCU, etat: "modifie_a_la_main"}));
  await cliquer(bouton(bloc, /Aperçu du workflow/));
  assert.equal(bouton(bloc, /Valider et pousser/).disabled, true);
  assert.match(bloc.textContent, /à la main/);
  const sans = rendre(async () => reponse(200, APERCU), {apk: "poste", tests: "poste", charge: "poste", emulateur: "poste"});
  assert.equal(bouton(sans, /Aperçu du workflow/), undefined);
});

test("un refus du serveur est affiché, le bouton reste utilisable après un nouvel aperçu", async () => {
  const bloc = rendre(async (url, options) => options?.method === "POST" ? reponse(409, {erreur: "n'est plus à jour"}) : reponse(200, APERCU));
  await cliquer(bouton(bloc, /Aperçu du workflow/));
  await cliquer(bouton(bloc, /Valider et pousser/));
  assert.match(bloc.textContent, /Refusé : n'est plus à jour/);
});

test("l'aperçu annonce les commits locaux non poussés qui ne partent pas", async () => {
  const note = "1 commit local non poussé n'est PAS inclus : la branche « deport/workflow » part de origin/main.";
  const bloc = rendre(async () => reponse(200, {...APERCU, non_pousses: 1, note}));
  await cliquer(bouton(bloc, /Aperçu du workflow/));
  assert.match(bloc.textContent, /PAS inclus/);
});
