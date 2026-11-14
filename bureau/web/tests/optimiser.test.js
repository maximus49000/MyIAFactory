// « Optimiser la charge » : le panneau « Ce qui charge l'ordinateur », la confirmation avant tout arrêt, la demande
// envoyée au serveur. Un DOM minimal ; jamais de vrai serveur.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

class Noeud {
  constructor(tag) {
    this.tagName = tag; this.enfants = []; this.attributs = {}; this.ecouteurs = {};
    this.className = ""; this._texte = ""; this.hidden = false; this.disabled = false;
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
const corps = new Noeud("body");
globalThis.document = {createElement: (t) => new Noeud(t), body: corps};

const {rendreProcessus, confirmationArret, lignesProcessus, demanderArret, brancherOptimiser} =
  await import("../ui/optimiser.js");

const DONNEES = {processus: [
  {pid: 3100, nom: "Godot.exe", cpu: 50, memoire_mo: 900, etiquette: "lancé par un agent", protege: false},
  {pid: 3000, nom: "claude.exe", cpu: 25.5, memoire_mo: 300, etiquette: "agent Léa (tâche t7)", protege: false},
  {pid: 2000, nom: "python.exe", cpu: 2, memoire_mo: 60, etiquette: "moteur", protege: true},
  {pid: 4, nom: "<img src=x>", cpu: 1, memoire_mo: 1, etiquette: null, protege: true},
]};

const boutons = (n, texte) => n.tous((x) => x.tagName === "button" && x.textContent === texte);

test("le panneau : nom, %, mémoire, étiquette, « protégé » sans bouton", () => {
  const c = new Noeud("div");
  rendreProcessus(c, DONNEES, {arreter() {}, actualiser() {}});
  const texte = c.textContent;
  assert.match(texte, /Ce qui charge l'ordinateur/);
  assert.match(texte, /Godot\.exe pid 3100lancé par un agent/);
  assert.match(texte, /agent Léa \(tâche t7\)/);
  assert.match(texte, /moteur/);
  assert.match(texte, /<img src=x>/);                 // en texte, jamais en HTML
  assert.match(texte, /50 %/);
  assert.match(texte, /900 Mo/);
  assert.equal(c.tous((x) => x.tagName === "tr").length, 5);
  assert.equal(boutons(c, "Arrêter").length, 2);       // seulement les deux qui ne sont pas protégés
  assert.equal(c.tous((x) => x.className === "optimiser-protege").length, 2);
  assert.equal(boutons(c, "Actualiser").length, 1);
});

test("une ligne sans `protege` est tenue pour protégée ; une ligne mal formée est écartée", () => {
  const l = lignesProcessus({processus: [{pid: 1, nom: "a"}, {pid: "2", nom: "b"}, null, {pid: 3}]});
  assert.deepEqual(l.map((x) => [x.pid, x.protege]), [[1, true]]);
  assert.deepEqual(lignesProcessus(null), []);
});

test("erreur et mesure en cours", () => {
  const c = new Noeud("div");
  rendreProcessus(c, null, {arreter() {}, actualiser() {}, erreur: "La liste des programmes est indisponible : x"});
  assert.match(c.textContent, /indisponible : x/);
  rendreProcessus(c, null, {arreter() {}, actualiser() {}, enCours: true});
  assert.match(c.textContent, /Mesure en cours/);
  assert.equal(boutons(c, "Actualiser")[0].disabled, true);
});

test("la confirmation nomme le programme et son pid", () => {
  assert.equal(confirmationArret({nom: "Godot.exe", pid: 3100}), "Arrêter Godot.exe (pid 3100) ?");
});

test("la demande d'arrêt : POST avec X-Bureau et le pid en JSON", async () => {
  const appels = [];
  const ok = await demanderArret(3100, async (url, options) => {
    appels.push([url, options]);
    return {ok: true, status: 200, json: async () => ({ok: true, message: "Godot.exe (pid 3100) arrêté."})};
  });
  assert.deepEqual(ok, {ok: true, message: "Godot.exe (pid 3100) arrêté."});
  const [url, options] = appels[0];
  assert.equal(url, "/api/processus/arreter");
  assert.equal(options.method, "POST");
  assert.equal(options.headers["X-Bureau"], "1");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(options.body), {pid: 3100});
  const refus = await demanderArret(4, async () => ({ok: false, status: 403, json: async () => ({erreur: "protégé"})}));
  assert.deepEqual(refus, {ok: false, message: "Arrêt refusé : protégé"});
  const panne = await demanderArret(4, async () => { throw new Error("x"); });
  assert.equal(panne.ok, false);
});

function faux() {
  const appels = [];
  const fetchFn = async (url, options = {}) => {
    appels.push({url, methode: options.method || "GET", corps: options.body});
    if (url === "/api/processus") return {ok: true, status: 200, json: async () => DONNEES};
    return {ok: true, status: 200, json: async () => ({ok: true, message: "arrêté"})};
  };
  return {appels, fetchFn};
}

test("rien n'est arrêté sans confirmation ; confirmé, la demande part puis la liste est relue", async () => {
  const {appels, fetchFn} = faux();
  const questions = [];
  let reponse = false;
  const dits = [];
  const bouton = new Noeud("button");
  const p = brancherOptimiser(bouton, (m, ok) => dits.push([m, ok]), {
    fetchFn, confirmer: (m) => { questions.push(m); return reponse; }});
  await bouton.ecouteurs.click();
  assert.equal(p.fond.hidden, false);
  assert.deepEqual(appels.map((a) => a.url), ["/api/processus"]);

  await boutons(p.contenu, "Arrêter")[0].ecouteurs.click();          // refusé : rien ne part
  assert.deepEqual(questions, ["Arrêter Godot.exe (pid 3100) ?"]);
  assert.equal(appels.filter((a) => a.methode === "POST").length, 0);

  reponse = true;
  await boutons(p.contenu, "Arrêter")[1].ecouteurs.click();
  assert.equal(questions[1], "Arrêter claude.exe (pid 3000) ?");
  const post = appels.filter((a) => a.methode === "POST");
  assert.equal(post.length, 1);
  assert.deepEqual(JSON.parse(post[0].corps), {pid: 3000});
  assert.deepEqual(dits, [["arrêté", true]]);
  assert.equal(appels.at(-1).url, "/api/processus");                   // la liste relue après l'arrêt

  await boutons(p.contenu, "Actualiser")[0].ecouteurs.click();
  assert.equal(appels.filter((a) => a.url === "/api/processus").length, 3);
});

test("le bouton « Optimiser la charge » est dans la jauge de charge", () => {
  const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");
  assert.match(barre, /"Optimiser la charge"/);
  assert.match(barre, /charge\.append\(etiquette, piste, valeur, boutonOptimiser\)/);
  assert.match(barre, /brancherOptimiser\(boutonOptimiser, dire\)/);
});
