// La zone « Services » : état en toutes lettres, adresse, jeton copié sans jamais être affiché, secrets saisis (présent/absent
// seulement, champ vidé après l'envoi), journal en texte, actions par POST. Faux DOM, faux réseau : aucun vrai appel.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.attributs = {}; this.disabled = false; this.value = ""; this.type = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
Object.defineProperty(Noeud.prototype, "innerHTML", {get() { return ""; }, set() { throw new Error("innerHTML interdit"); }});

const {zoneServices, lireServices, LIBELLES_ETATS} = await import("../ui/services.js");

const reponse = (status, corps) => ({ok: status >= 200 && status < 300, status, json: async () => corps});
const JETON = "jeton-de-test-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
const SECRET = "valeur-de-test-api";
function reseau(routes) {
  const appels = [];
  const f = async (url, init = {}) => {
    const methode = init.method || "GET";
    appels.push({methode, url, init, corps: init.body ? JSON.parse(init.body) : null});
    const r = routes[`${methode} ${url}`];
    if (r === undefined) return reponse(404, {erreur: "inconnu"});
    return typeof r === "function" ? r(init) : r;
  };
  f.appels = appels;
  return f;
}
const service = (plus = {}) => ({projet: "fm-stats", nom: "donnees-fm", etat: "actif", sante_ok: true, adresse: "http://serveur.exemple.test:18000",
  jeton_present: true, secrets: {API_FOOTBALL_KEY: false}, journal: ["démarré", "requête ***masqué***"],
  deploiement: {statut: "ok", commit: "a".repeat(40)}, ...plus});
const boutons = (c, t) => c.tous((n) => n.tagName === "button" && n.textContent.includes(t));
const clic = async (n) => { await n.auteurs.click[0](); };

test("la carte dit l etat, l adresse, le journal et la presence des secrets", () => {
  const c = zoneServices([service()], {fetchFn: reseau({})});
  const t = c.textContent;
  assert.match(t, /Services/);
  assert.match(t, /État : actif, santé ok/);
  assert.match(t, /http:\/\/serveur\.exemple\.test:18000/);
  assert.match(t, /API_FOOTBALL_KEY : absent/);
  assert.match(t, /requête \*\*\*masqué\*\*\*/);
  assert.match(t, /Dernier déploiement : réussi \(commit aaaaaaaaaaaa\)/);
  for (const e of Object.keys(LIBELLES_ETATS)) {
    assert.ok(zoneServices([service({etat: e})], {fetchFn: reseau({})}).textContent.includes(LIBELLES_ETATS[e]));
  }
});

test("le jeton est copie sans jamais etre ecrit dans la page", async () => {
  const copies = [];
  const f = reseau({"POST /api/services/fm-stats/jeton": reponse(200, {jeton: JETON})});
  const c = zoneServices([service()], {fetchFn: f, copier: async (t) => copies.push(t)});
  await clic(boutons(c, "Copier le jeton")[0]);
  assert.deepEqual(copies, [JETON]);
  assert.ok(!c.textContent.includes(JETON));
  assert.equal(f.appels[0].init.headers["X-Bureau"], "1");
});

test("un secret saisi part au bureau, le champ est vide et la valeur jamais affichee", async () => {
  const f = reseau({"POST /api/services/fm-stats/secrets": reponse(202, {demarre: true})});
  const c = zoneServices([service()], {fetchFn: f});
  const champ = c.tous((n) => n.tagName === "input")[0];
  assert.equal(champ.type, "password");
  champ.value = `  ${SECRET} `;
  await clic(boutons(c, "Enregistrer")[0]);
  assert.deepEqual(f.appels[0].corps, {secrets: {API_FOOTBALL_KEY: SECRET}});
  assert.equal(champ.value, "");
  assert.ok(!c.textContent.includes(SECRET));
});

test("un secret vide n est pas envoye", async () => {
  const f = reseau({});
  const c = zoneServices([service()], {fetchFn: f});
  await clic(boutons(c, "Enregistrer")[0]);
  assert.equal(f.appels.length, 0);
  assert.match(c.textContent, /Collez d'abord/);
});

test("arreter demande confirmation, les autres actions partent par POST", async () => {
  const routes = {};
  for (const a of ["etat", "journal", "redemarrer", "arreter", "deployer"]) routes[`POST /api/services/fm-stats/${a}`] = reponse(202, {demarre: true});
  const f = reseau(routes);
  let reponseConfirmation = false;
  let relu = 0;
  const c = zoneServices([service()], {fetchFn: f, confirmer: () => reponseConfirmation, relire: () => { relu++; }});
  await clic(boutons(c, "Arrêter")[0]);
  assert.equal(f.appels.length, 0);
  reponseConfirmation = true;
  for (const t of ["Arrêter", "Actualiser", "Lire le journal", "Redémarrer", "Déployer"]) await clic(boutons(c, t)[0]);
  assert.deepEqual(f.appels.map((a) => a.url), ["arreter", "etat", "journal", "redemarrer", "deployer"].map((a) => `/api/services/fm-stats/${a}`));
  assert.equal(relu, 5);
});

test("un refus du bureau est dit", async () => {
  const f = reseau({"POST /api/services/fm-stats/redemarrer": reponse(409, {erreur: "Une action sur ce service est déjà en cours."})});
  const c = zoneServices([service()], {fetchFn: f});
  await clic(boutons(c, "Redémarrer")[0]);
  assert.match(c.textContent, /déjà en cours/);
});

test("un texte hostile n est jamais interprete", () => {
  const hostile = '<img src=x onerror="alert(1)">';
  const c = zoneServices([service({nom: hostile, adresse: hostile, journal: [hostile], secrets: {[hostile]: true}})], {fetchFn: reseau({})});
  assert.ok(c.textContent.includes(hostile));
  assert.equal(c.tous((n) => n.tagName === "img").length, 0);
});

test("lecture impossible et liste vide", async () => {
  assert.match(zoneServices(null).textContent, /n'ont pas pu être lus/);
  assert.match(zoneServices([]).textContent, /Aucun projet/);
  assert.equal(await lireServices(reseau({"GET /api/services": reponse(500, {})})), null);
  assert.equal((await lireServices(reseau({"GET /api/services": reponse(200, {services: [service()]})}))).length, 1);
});

test("copie refusee (bureau en http) : le jeton s'affiche dans un champ a selectionner, jamais avant le clic", async () => {
  const f = reseau({"POST /api/services/fm-stats/jeton": reponse(200, {jeton: JETON})});
  const c = zoneServices([service()], {fetchFn: f, copier: async () => { throw new Error("refusé"); }});
  assert.ok(!c.textContent.includes(JETON));
  await clic(boutons(c, "Copier le jeton")[0]);
  const champs = c.tous((n) => n.tagName === "input" && n.value === JETON);
  assert.equal(champs.length, 1);
  assert.equal(champs[0].readOnly, true);
});

test("la case « Déployer automatiquement » : cochée au départ si activée, envoie actif, et revient si le bureau refuse", async () => {
  const f = reseau({"POST /api/services/fm-stats/auto": reponse(200, {auto: true})});
  const c = zoneServices([service({auto: false})], {fetchFn: f});
  const [case_] = c.tous((n) => n.tagName === "input" && n.type === "checkbox");
  assert.equal(case_.checked, false);
  case_.checked = true;
  await case_.auteurs.change[0]();
  assert.deepEqual(f.appels[0].corps, {actif: true});
  assert.match(c.textContent, /Déploiement automatique activé/);
  assert.equal(service({auto: true}).auto, true);
  const refuse = reseau({"POST /api/services/fm-stats/auto": reponse(400, {erreur: "non"})});
  const c2 = zoneServices([service({auto: true})], {fetchFn: refuse});
  const [case2] = c2.tous((n) => n.tagName === "input" && n.type === "checkbox");
  assert.equal(case2.checked, true);
  case2.checked = false;
  await case2.auteurs.change[0]();
  assert.equal(case2.checked, true);
});

test("un déploiement en cours est dit en toutes lettres (l'ancienne version répond encore)", () => {
  const c = zoneServices([service({deploiement: {statut: "en_cours", commit: "b".repeat(40), debut: "2026-11-26T08:56:18Z"}})], {fetchFn: reseau({})});
  assert.match(c.textContent, /Déploiement en cours depuis .* \(commit bbbbbbbbbbbb\) : l'ancienne version répond encore/);
  const fini = zoneServices([service()], {fetchFn: reseau({})});
  assert.ok(!fini.textContent.includes("Déploiement en cours"));
});
