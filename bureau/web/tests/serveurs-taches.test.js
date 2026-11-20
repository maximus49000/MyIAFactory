// La section « Tâches du serveur » de l'écran des serveurs : état en toutes lettres, bouton « Arrêter » pour les seules tâches
// actives, suivi périodique arrêté au retrait de la carte, mises à jour en place, texte du serveur jamais interprété.
// Faux DOM, faux réseau : aucun vrai appel.
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

const {ecranServeurs, monterEcranServeurs, lireTaches, arreterTache} = await import("../ui/serveurs.js");

const reponse = (status, corps) => ({ok: status >= 200 && status < 300, status, json: async () => corps});
const VIDE = {serveurs: [], rejets: []};
const tache = (n, plus = {}) => ({id: `t20261119-${String(n).padStart(6, "0")}-abcd`, etat: "terminee", mode: "scenario", projet: "MonJeu",
  serveur_id: "mon-serveur", debut: "2026-11-19T10:00:00Z", duree_s: 125, captures: 4, statut: "ok", ...plus});

const boutons = (c, texte) => c.tous((n) => n.tagName === "button" && (texte === undefined || n.textContent.includes(texte)));
const lignes = (c) => c.tous((n) => n.className.includes("serveurs-tache ") || n.className === "serveurs-tache");
const clic = (n) => n.auteurs.click[0]();

function minuterie() {
  const m = {taches: [], annulees: 0, attendre(f, ms) { m.taches.push({f, ms}); return m.taches.length; }, annuler() { m.annulees++; },
    async tic() { const t = m.taches.shift(); await t.f(); }};
  return m;
}

function reseau(routes) {
  const appels = [];
  const f = async (url, init = {}) => {
    const methode = init.method || "GET";
    const chemin = url.split("?")[0];
    appels.push({methode, url, chemin, init, corps: init.body ? JSON.parse(init.body) : null});
    const r = routes[`${methode} ${chemin}`];
    if (r === undefined) return reponse(404, {erreur: "inconnu"});
    return typeof r === "function" ? r(init) : r;
  };
  f.appels = appels;
  return f;
}
const posts = (f) => f.appels.filter((a) => a.methode === "POST");

function ecran(taches, routes = {}, extra = {}) {
  const f = reseau({"GET /api/serveurs": reponse(200, VIDE), "GET /api/serveurs/lieux": reponse(200, {}), ...routes});
  const m = extra.planifier || minuterie();
  const c = ecranServeurs(VIDE, {fetchFn: f, planifier: m, lieux: {}, taches, ...extra});
  return {c, f, m};
}

test("la liste affiche l etat en toutes lettres", () => {
  const {c} = ecran([tache(5, {etat: "en_cours", statut: null, duree_s: 42, captures: 1}), tache(4, {etat: "en_attente", statut: null, duree_s: null, captures: 0}),
    tache(3, {etat: "terminee", statut: "ok"}), tache(2, {etat: "echouee", statut: "erreur"}), tache(1, {etat: "arretee", statut: "plantage", captures: 0}),
    tache(0, {etat: "terminee", statut: "limite", captures: 50})]);
  const texte = c.textContent;
  assert.match(texte, /Tâches du serveur/);
  for (const mot of ["en attente", "en cours", "terminée", "échouée", "arrêtée"]) assert.ok(texte.includes(mot), mot);
  for (const mot of ["ok", "plantage", "limite", "erreur"]) assert.ok(texte.includes(mot), mot);
  assert.match(texte, /2 min 5 s/);
  assert.match(texte, /42 s/);
  assert.match(texte, /4 captures/);
  assert.match(texte, /1 capture(?!s)/);
  assert.match(texte, /0 capture(?!s)/);
  assert.match(texte, /MonJeu/);
  assert.equal(c.tous((n) => n.className.includes("serveurs-tache-id")).length, 6);
  // la couleur n'est jamais seule : chaque pastille d'état est accompagnée de son libellé dans le même élément
  for (const e of c.tous((n) => n.className.includes("tache-etat"))) assert.ok(e.textContent.length > 0);
});

test("le bouton arreter n existe que pour une tache active", () => {
  const {c} = ecran([tache(1, {etat: "en_cours"}), tache(2, {etat: "en_attente"}), tache(3, {etat: "terminee"}), tache(4, {etat: "echouee"}),
    tache(5, {etat: "arretee"}), tache(6, {etat: "inconnu"})]);
  assert.equal(boutons(c, "Arrêter").length, 2);
  const parTache = (n) => boutons(lignes(c).find((l) => l.textContent.includes(tache(n).id)) || new Noeud("x"), "Arrêter").length;
  assert.deepEqual([1, 2, 3, 4, 5, 6].map(parTache), [1, 1, 0, 0, 0, 0]);
});

test("un texte du serveur avec du HTML n est pas interprete", () => {
  const hostile = '<img src=x onerror="alert(1)"><b>gras</b>';
  const {c} = ecran([tache(1, {etat: "en_cours", projet: hostile, serveur_id: hostile, erreur: hostile}), {...tache(2), id: hostile}]);
  assert.ok(c.textContent.includes(hostile));
  assert.equal(c.tous((n) => n.tagName === "img" || n.tagName === "b").length, 0);
});

test("la liste vide dit qu il n y a aucune tache", () => {
  const {c} = ecran([]);
  assert.match(c.textContent, /Aucune tâche/);
  assert.equal(lignes(c).length, 0);
  assert.equal(boutons(c, "Arrêter").length, 0);
});

test("la lecture impossible le dit sans exception ni liste", () => {
  const {c} = ecran(null);
  assert.match(c.textContent, /tâches n'ont pas pu être lues/);
  assert.equal(lignes(c).length, 0);
});

test("pas de section quand la liste n est pas demandee", () => {
  const c = ecranServeurs(VIDE, {fetchFn: reseau({}), planifier: minuterie(), lieux: {}});
  assert.doesNotMatch(c.textContent, /Tâches du serveur/);
});

test("un clic envoie un seul POST, le bouton est grise pendant l envoi", async () => {
  let ouvrir;
  const attente = new Promise((r) => { ouvrir = r; });
  const t = tache(1, {etat: "en_cours"});
  const {c, f} = ecran([t], {[`POST /api/serveurs/taches/${t.id}/arreter`]: async () => { await attente; return reponse(202, {demarre: true}); },
    "GET /api/serveurs/taches": reponse(200, {taches: [{...t, arret_en_cours: true}]})});
  const bouton = boutons(c, "Arrêter")[0];
  const p1 = clic(bouton);
  assert.equal(bouton.disabled, true);
  const p2 = bouton.auteurs.click[0]();            // un second clic pendant l'envoi : sans effet
  ouvrir();
  await Promise.all([p1, p2]);
  assert.equal(posts(f).length, 1);
  assert.equal(posts(f)[0].chemin, `/api/serveurs/taches/${t.id}/arreter`);
  assert.equal(posts(f)[0].init.headers["X-Bureau"], "1");
  assert.deepEqual(posts(f)[0].corps, {});
  assert.equal(boutons(c, "Arrêt en cours").length, 1);
  assert.equal(boutons(c, "Arrêt en cours")[0].disabled, true);        // le serveur dit que l'arrêt tourne : grisé
});

test("arret echoue affiche un message sans exception", async () => {
  const t = tache(1, {etat: "en_cours"});
  const cas = [["409", reponse(409, {erreur: "Une opération est déjà en cours : réessayez dans un instant."}), /déjà en cours/],
    ["500", reponse(500, {}), /500/], ["reseau", () => { throw new Error("coupé <b>secret</b>"); }, /injoignable/],
    ["json", {ok: false, status: 502, json: async () => { throw new Error("pas du json"); }}, /502/]];
  for (const [nom, rep, attendu] of cas) {
    const {c} = ecran([t], {[`POST /api/serveurs/taches/${t.id}/arreter`]: rep});
    await clic(boutons(c, "Arrêter")[0]);
    assert.match(c.textContent, attendu, nom);
    assert.doesNotMatch(c.textContent, /secret|Error/, nom);
    assert.equal(boutons(c, "Arrêter")[0].disabled, false, nom);         // un nouvel essai reste possible
  }
});

test("le suivi s arrete quand la carte disparait", async () => {
  const m = minuterie();
  let monte = true;
  const t = tache(1, {etat: "en_cours"});
  const f = reseau({"GET /api/serveurs/taches": reponse(200, {taches: [t]}), "GET /api/serveurs": reponse(200, VIDE), "GET /api/serveurs/lieux": reponse(200, {})});
  const c = ecranServeurs(VIDE, {fetchFn: f, planifier: m, actif: () => monte, lieux: {}, taches: [t]});
  assert.equal(m.taches.length, 1);                    // une lecture prévue, rapprochée tant qu'une tâche est active
  assert.ok(m.taches[0].ms >= 1000 && m.taches[0].ms <= 5000);
  await m.tic();
  assert.equal(f.appels.filter((a) => a.chemin === "/api/serveurs/taches").length, 1);
  assert.equal(m.taches.length, 1);                    // et elle se reprogramme
  monte = false;
  await m.tic();                                       // la carte a disparu : aucune lecture, rien de reprogrammé
  assert.equal(f.appels.filter((a) => a.chemin === "/api/serveurs/taches").length, 1);
  assert.equal(m.taches.length, 0);
  const m2 = minuterie();
  const c2 = ecranServeurs(VIDE, {fetchFn: f, planifier: m2, lieux: {}, taches: [t]});
  c2.arreter();
  assert.equal(m2.annulees, 1);
  assert.ok(c);
});

test("la lecture est plus lente quand aucune tache n est active", () => {
  const actif = ecran([tache(1, {etat: "en_cours"})]).m.taches[0].ms;
  const repos = ecran([tache(2, {etat: "terminee"})]).m.taches[0].ms;
  assert.ok(repos > actif);
});

test("une mise a jour garde le DOM : memes lignes, meme bouton, texte rafraichi", async () => {
  const t = tache(1, {etat: "en_cours", statut: null, duree_s: 10, captures: 0});
  const {c, m, f} = ecran([t], {"GET /api/serveurs/taches": () => reponse(200, {taches: [{...t, duree_s: 70, captures: 3}]})});
  const ligne = lignes(c)[0];
  const bouton = boutons(c, "Arrêter")[0];
  assert.match(c.textContent, /10 s/);
  await m.tic();
  assert.equal(lignes(c)[0], ligne);
  assert.equal(boutons(c, "Arrêter")[0], bouton);
  assert.match(c.textContent, /1 min 10 s/);
  assert.match(c.textContent, /3 captures/);
  assert.equal(f.appels.length >= 1, true);
});

test("la tache qui se termine perd son bouton en place, une nouvelle tache redessine la liste", async () => {
  const t = tache(1, {etat: "en_cours"});
  let reponseSuivante = {taches: [{...t, etat: "arretee", statut: "erreur"}]};
  const {c, m} = ecran([t], {"GET /api/serveurs/taches": () => reponse(200, reponseSuivante)});
  const ligne = lignes(c)[0];
  await m.tic();
  assert.equal(lignes(c)[0], ligne);
  assert.equal(boutons(c, "Arrêter").length, 0);
  assert.match(c.textContent, /arrêtée/);
  reponseSuivante = {taches: [tache(2, {etat: "en_cours"}), {...t, etat: "arretee", statut: "erreur"}]};
  await m.tic();
  assert.equal(lignes(c).length, 2);
  assert.equal(boutons(c, "Arrêter").length, 1);
});

test("une lecture qui echoue garde la derniere liste et le dit", async () => {
  const t = tache(1, {etat: "en_cours"});
  const {c, m} = ecran([t], {"GET /api/serveurs/taches": reponse(500, {})});
  await m.tic();
  assert.equal(lignes(c).length, 1);
  assert.match(c.textContent, /dernière liste/);
  assert.equal(m.taches.length, 1);                    // le suivi continue : la lecture reviendra
});

test("l erreur d un arret du serveur s affiche pour sa tache", () => {
  const {c} = ecran([tache(1, {etat: "en_cours", erreur: "L'arrêt n'est pas confirmé (état : en cours)."})]);
  assert.match(c.textContent, /L'arrêt n'est pas confirmé/);
  assert.equal(boutons(c, "Arrêter")[0].disabled, false);
});

test("lireTaches et arreterTache ne levent jamais", async () => {
  assert.equal(await lireTaches(async () => { throw new Error("x"); }), null);
  assert.equal(await lireTaches(async () => reponse(200, {taches: "pas un tableau"})), null);
  assert.deepEqual(await lireTaches(async () => reponse(200, {taches: [tache(1)]})), {taches: [tache(1)]});
  const r = await arreterTache("t20261119-000001-abcd", async () => { throw new Error("x"); });
  assert.equal(r.ok, false);
  const url = [];
  await arreterTache("a/b ?x", async (u) => { url.push(u); return reponse(404, {}); });
  assert.equal(url[0], "/api/serveurs/taches/a%2Fb%20%3Fx/arreter");
});

test("monterEcranServeurs lit les taches avec les serveurs", async () => {
  const t = tache(1, {etat: "en_cours"});
  const f = reseau({"GET /api/serveurs": reponse(200, VIDE), "GET /api/serveurs/lieux": reponse(200, {}), "GET /api/serveurs/taches": reponse(200, {taches: [t]}),
    "GET /api/serveurs/migration": reponse(200, {proposition: null})});
  const conteneur = new Noeud("div");
  await monterEcranServeurs(conteneur, {fetchFn: f, planifier: minuterie()});
  assert.equal(boutons(conteneur, "Arrêter").length, 1);
});
