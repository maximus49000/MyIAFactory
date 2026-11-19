// La migration du serveur OVH existant dans l'écran des serveurs : proposition détectée, aperçu en lecture seule, confirmation
// à usage unique avec la case d'accord décochée par défaut. Faux DOM, faux réseau : aucun vrai appel.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.attributs = {}; this.disabled = false; this.checked = false; this.value = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const {ecranServeurs, monterEcranServeurs, lireMigration, MESSAGE_MIGRATION_DETECTEE} = await import("../ui/serveurs.js");

const reponse = (status, corps) => ({ok: status >= 200 && status < 300, status, json: async () => corps});
const PROPOSITION = {serveur: {nom: "Serveur OVH", hote: "203.0.113.9", utilisateur: "ubuntu", fournisseur: "ovh"},
  source: ["ovh.json", "plateforme.json", "id_ed25519_myiafactory"]};
const CAPACITES = {base: "presente", "android-build": "presente", "android-emulateur": "absente", "unity-cli": "inconnue"};
const APERCU = {...PROPOSITION, capacites: CAPACITES, joignable: true};
const VIDE = {serveurs: [], rejets: []};

const boutons = (c, texte) => c.tous((n) => n.tagName === "button" && (texte === undefined || n.textContent.includes(texte)));
const caseAccord = (c) => c.tous((n) => n.tagName === "input" && n.type === "checkbox")[0];
const clic = (n) => n.auteurs.click[0]();
const vide = () => ({taches: [], attendre(f, ms) { this.taches.push({f, ms}); return this.taches.length; }, annuler() {}});

function reseau(routes) {
  const appels = [];
  const f = async (url, init = {}) => {
    const methode = init.method || "GET";
    const chemin = url.split("?")[0];
    appels.push({methode, chemin, corps: init.body ? JSON.parse(init.body) : null, entetes: init.headers});
    const r = routes[`${methode} ${chemin}`];
    if (r === undefined) return reponse(404, {erreur: "inconnu"});
    return typeof r === "function" ? r(init) : r;
  };
  f.appels = appels;
  return f;
}
const posts = (f) => f.appels.filter((a) => a.methode === "POST");

function ecran(proposition, routes = {}) {
  const f = reseau({"GET /api/serveurs": reponse(200, VIDE), "GET /api/serveurs/lieux": reponse(200, {}),
    "POST /api/serveurs/migration/apercu": reponse(200, APERCU), "POST /api/serveurs/migration/confirmer": reponse(200, {serveur: {id: "serveur-ovh"}}), ...routes});
  const c = ecranServeurs(VIDE, {fetchFn: f, planifier: vide(), lieux: {}, migration: proposition});
  return {c, f};
}

test("sans proposition, aucune carte de migration", () => {
  const {c} = ecran(null);
  assert.ok(!c.textContent.includes(MESSAGE_MIGRATION_DETECTEE));
  assert.equal(boutons(c, "Confirmer").length, 0);
});

test("une proposition affiche le serveur détecté, sans rien écrire ni appeler", () => {
  const {c, f} = ecran(PROPOSITION);
  assert.equal(MESSAGE_MIGRATION_DETECTEE, "Votre serveur OVH a été détecté");
  assert.ok(c.textContent.includes("Votre serveur OVH a été détecté"));
  assert.ok(c.textContent.includes("203.0.113.9"));
  assert.ok(c.textContent.includes("ubuntu"));
  assert.equal(boutons(c, "aperçu").length, 1);
  assert.equal(boutons(c, "Confirmer").length, 1);
  assert.equal(posts(f).length, 0);
});

test("la case d'accord est décochée par défaut", () => {
  const {c} = ecran(PROPOSITION);
  assert.equal(caseAccord(c).checked, false);
});

test("l'aperçu appelle la route de lecture seule et montre les capacités constatées", async () => {
  const {c, f} = ecran(PROPOSITION);
  await clic(boutons(c, "aperçu")[0]);
  assert.deepEqual(posts(f).map((a) => a.chemin), ["/api/serveurs/migration/apercu"]);
  assert.equal(posts(f)[0].entetes["X-Bureau"], "1");
  const t = c.textContent;
  assert.ok(t.includes("Base du serveur") && t.includes("présente"));
  assert.ok(t.includes("Émulateur Android") && t.includes("absente"));
  assert.ok(t.includes("inconnue"));
});

test("un serveur injoignable montre « inconnue », jamais « absente »", async () => {
  const inconnues = Object.fromEntries(Object.keys(CAPACITES).map((k) => [k, "inconnue"]));
  const {c} = ecran(PROPOSITION, {"POST /api/serveurs/migration/apercu": reponse(200, {...APERCU, capacites: inconnues, joignable: false})});
  await clic(boutons(c, "aperçu")[0]);
  assert.ok(!c.textContent.includes("absente"));
  assert.ok(c.textContent.includes("inconnue"));
});

test("confirmer sans case cochée n'envoie rien", async () => {
  const {c, f} = ecran(PROPOSITION);
  await clic(boutons(c, "Confirmer")[0]);
  assert.equal(posts(f).length, 0);
  assert.ok(c.textContent.includes("Cochez"));
});

test("confirmer avec la case envoie exactement {accord: true}, une seule fois, puis décoche", async () => {
  let ouvre;
  const attente = new Promise((r) => { ouvre = r; });
  const {c, f} = ecran(PROPOSITION, {"POST /api/serveurs/migration/confirmer": async () => { await attente; return reponse(200, {serveur: {id: "serveur-ovh"}}); }});
  caseAccord(c).checked = true;
  const bouton = boutons(c, "Confirmer")[0];
  const p1 = clic(bouton);
  assert.equal(caseAccord(c).checked, false);       // décochée tout de suite
  const p2 = clic(bouton);                          // double clic : ignoré
  ouvre();
  await Promise.all([p1, p2]);
  assert.equal(posts(f).length, 1);
  assert.deepEqual(posts(f)[0].corps, {accord: true});
  assert.equal(posts(f)[0].chemin, "/api/serveurs/migration/confirmer");
});

test("après confirmation, la carte disparaît et la liste est relue", async () => {
  const {c, f} = ecran(PROPOSITION);
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.ok(!c.textContent.includes("Votre serveur OVH a été détecté"));
  assert.ok(f.appels.some((a) => a.methode === "GET" && a.chemin === "/api/serveurs"));
});

test("un refus (déjà déclaré) est montré en français et ne se rejoue pas sans nouvelle case", async () => {
  const {c, f} = ecran(PROPOSITION, {"POST /api/serveurs/migration/confirmer": reponse(409, {erreur: "Un serveur est déjà déclaré : la migration n'a rien changé."})});
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.ok(c.textContent.includes("déjà déclaré"));
  assert.equal(caseAccord(c).checked, false);
  await clic(boutons(c, "Confirmer")[0]);
  assert.equal(posts(f).length, 1);
});

test("bureau injoignable : message, case décochée, aucune exception", async () => {
  const f = async (url, init = {}) => { if ((init.method || "GET") === "POST") throw new Error("coupé"); return reponse(200, url.includes("lieux") ? {} : VIDE); };
  const c = ecranServeurs(VIDE, {fetchFn: f, planifier: vide(), lieux: {}, migration: PROPOSITION});
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.ok(c.textContent.includes("injoignable"));
  assert.equal(caseAccord(c).checked, false);
});

test("tout texte venu du serveur passe par textContent", async () => {
  const hostile = {serveur: {nom: "<img onerror=x>", hote: "<b>203</b>", utilisateur: "u", fournisseur: "ovh"}, source: ["<i>f</i>"]};
  const {c} = ecran(hostile);
  assert.ok(c.textContent.includes("<b>203</b>"));
  assert.equal(c.tous((n) => n.tagName === "b" || n.tagName === "img" || n.tagName === "i").length, 0);
});

test("lireMigration : proposition, null, ou null si le bureau ne répond pas", async () => {
  assert.deepEqual(await lireMigration(reseau({"GET /api/serveurs/migration": reponse(200, {proposition: PROPOSITION})})), PROPOSITION);
  assert.equal(await lireMigration(reseau({"GET /api/serveurs/migration": reponse(200, {proposition: null})})), null);
  assert.equal(await lireMigration(reseau({})), null);
  assert.equal(await lireMigration(async () => { throw new Error("x"); }), null);
});

test("monterEcranServeurs lit la proposition au démarrage sans rien écrire", async () => {
  const f = reseau({"GET /api/serveurs": reponse(200, VIDE), "GET /api/serveurs/lieux": reponse(200, {}),
    "GET /api/serveurs/migration": reponse(200, {proposition: PROPOSITION})});
  const conteneur = new Noeud("div");
  await monterEcranServeurs(conteneur, {fetchFn: f, planifier: vide()});
  assert.ok(conteneur.textContent.includes("Votre serveur OVH a été détecté"));
  assert.equal(posts(f).length, 0);
});

const CONNU = {serveurs: [{id: "serveur-ovh", nom: "Serveur OVH", hote: "203.0.113.9", utilisateur: "ubuntu", fournisseur: "ovh", capacites: {}, installation_en_cours: false}], rejets: []};

test("409 « déjà déclaré » : la liste est relue et la carte disparaît", async () => {
  const {c, f} = ecran(PROPOSITION, {"POST /api/serveurs/migration/confirmer": reponse(409, {erreur: "Un serveur est déjà déclaré : la migration n'a rien changé."}),
    "GET /api/serveurs": reponse(200, CONNU)});
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.ok(f.appels.some((a) => a.methode === "GET" && a.chemin === "/api/serveurs"));
  assert.ok(!c.textContent.includes("Votre serveur OVH a été détecté"));
});

test("504 : la carte disparaît si la liste relue montre le serveur inscrit", async () => {
  const {c} = ecran(PROPOSITION, {"POST /api/serveurs/migration/confirmer": reponse(504, {erreur: "La migration prend trop de temps."}),
    "GET /api/serveurs": reponse(200, CONNU)});
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.ok(!c.textContent.includes("Votre serveur OVH a été détecté"));
});

test("504 : nouvel envoi bloqué tant que la liste n'a pas été relue", async () => {
  let lisible = false;
  const {c, f} = ecran(PROPOSITION, {"POST /api/serveurs/migration/confirmer": reponse(504, {erreur: "La migration prend trop de temps."}),
    "GET /api/serveurs": () => (lisible ? reponse(200, VIDE) : reponse(500, {erreur: "x"}))});
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.equal(posts(f).length, 1);
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);              // liste toujours illisible : pas de second envoi
  assert.equal(posts(f).length, 1);
  assert.ok(c.textContent.includes("Relisez"));
  lisible = true;
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);              // la liste est relue (vide) : on débloque, mais sans envoyer
  assert.equal(posts(f).length, 1);
  caseAccord(c).checked = true;
  await clic(boutons(c, "Confirmer")[0]);
  assert.equal(posts(f).length, 2);
});