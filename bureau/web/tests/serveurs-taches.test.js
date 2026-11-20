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

const {ecranServeurs, monterEcranServeurs, lireTaches, arreterTache, LIEN_CONNEXION_ABONNEMENT, messageArretAgent} = await import("../ui/serveurs.js");
const {partieParallelisme, ordreDeLieux, demandeParallelisme, enregistrerPlafondAbonnement} = await import("../ui/facturation.js");
// Aucun texte venu du serveur ni du projet ne passe jamais par innerHTML : le faux DOM le refuse.
Object.defineProperty(Noeud.prototype, "innerHTML", {get() { return ""; }, set() { throw new Error("innerHTML interdit"); }});

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

// ---- les agents du serveur (tranche B)
const agent = (n, plus = {}) => ({id: `t20261119-${String(n).padStart(6, "0")}-abcd`, type: "agent", etat: "en_cours", mode: "pilote", projet: "MonJeu",
  tache: "t-12", serveur_id: "mon-serveur", debut: "2026-11-19T10:00:00Z", duree_s: 90, statut: null, branche: "agent/t-12", ...plus});

test("une tache d agent montre sa tache et sa branche", () => {
  const hostile = '<img src=x onerror="alert(1)"><b>gras</b>';
  const {c} = ecran([agent(1), agent(2, {etat: "terminee", mode: "seul", statut: "ok", tache: hostile, branche: `agent/${hostile}`, duree_s: 720}), tache(3)]);
  const lignesAgent = lignes(c).filter((l) => l.textContent.includes("agent serveur"));
  assert.equal(lignesAgent.length, 2);                                   // l'agent est dit en toutes lettres, la tâche d'émulation ne l'est pas
  const premiere = lignes(c).find((l) => l.textContent.includes(agent(1).id));
  for (const mot of ["tâche t-12", "branche agent/t-12", "pilote", "MonJeu", "serveur mon-serveur", "en cours", "1 min 30 s"]) {
    assert.ok(premiere.textContent.includes(mot), mot);
  }
  const seule = lignes(c).find((l) => l.textContent.includes(agent(2).id));
  assert.ok(seule.textContent.includes("seul") && seule.textContent.includes("rapport : ok") && seule.textContent.includes("12 min 0 s"));
  assert.ok(c.textContent.includes(hostile));                            // du texte, jamais du HTML
  assert.equal(c.tous((n) => n.tagName === "img" || n.tagName === "b").length, 0);
  const emulation = lignes(c).find((l) => l.textContent.includes(tache(3).id));
  assert.doesNotMatch(emulation.textContent, /branche|agent serveur/);
  assert.match(emulation.textContent, /4 captures/);
  assert.doesNotMatch(premiere.textContent, /captures?/);                // un agent n'a pas de captures
});

test("le message d arret ne parle d emulation que s il y en avait une", () => {
  assert.equal(messageArretAgent({etat: "arretee"}), "Arrêt confirmé : l'agent est arrêté.");               // agent seul
  assert.equal(messageArretAgent({etat: "arretee", emulation: "arretee"}), "Arrêt confirmé : l'agent et son émulation sont arrêtés.");
  assert.match(messageArretAgent({etat: "terminee", emulation: "non_confirmee"}), /émulation n'est pas confirmé/);
  assert.match(messageArretAgent({etat: "en_cours", emulation: "arretee"}), /n'est pas confirmé \(état : en cours\)/);
});

test("le bouton arreter d un agent", async () => {
  const a = agent(1);
  const suivante = {taches: [{...a, etat: "arretee"}]};
  const {c, f} = ecran([a, agent(2, {etat: "terminee"})], {
    [`POST /api/serveurs/taches/${a.id}/arreter`]: () => reponse(200, {demarre: true, etat: "arretee", emulation: "arretee"}),
    "GET /api/serveurs/taches": () => reponse(200, suivante)});
  assert.equal(boutons(c, "Arrêter").length, 1);                         // seule la tâche active a son bouton
  await clic(boutons(c, "Arrêter")[0]);
  assert.equal(posts(f).length, 1);
  assert.equal(posts(f)[0].chemin, `/api/serveurs/taches/${a.id}/arreter`);
  assert.equal(posts(f)[0].init.headers["X-Bureau"], "1");
  assert.deepEqual(posts(f)[0].corps, {});
  const ligne = lignes(c).find((l) => l.textContent.includes(a.id));
  assert.match(ligne.textContent, /arrêtée/);
  assert.match(ligne.textContent, /Arrêt confirmé : l'agent et son émulation sont arrêtés/);   // la réponse dit l'état final
  assert.equal(boutons(c, "Arrêter").length, 0);
  // l'arrêt n'est pas confirmé : le message le dit, un nouvel essai reste possible
  const b = agent(3);
  const autre = ecran([b], {[`POST /api/serveurs/taches/${b.id}/arreter`]: reponse(200, {demarre: true, etat: "inconnu", erreur: "<b>x</b>"})});
  await clic(boutons(autre.c, "Arrêter")[0]);
  assert.match(autre.c.textContent, /n'est pas confirmé \(état : état inconnu\)/);
  assert.equal(boutons(autre.c, "Arrêter")[0].disabled, false);
  assert.equal(autre.c.tous((n) => n.tagName === "b").length, 0);
  // la réponse 202 (arrêt long) : on laisse le suivi lire l'état
  const d = agent(4);
  const long = ecran([d], {[`POST /api/serveurs/taches/${d.id}/arreter`]: reponse(202, {demarre: true}),
    "GET /api/serveurs/taches": reponse(200, {taches: [{...d, arret_en_cours: true}]})});
  await clic(boutons(long.c, "Arrêter")[0]);
  assert.equal(boutons(long.c, "Arrêt en cours").length, 1);
  assert.doesNotMatch(long.c.textContent, /Arrêt confirmé/);
});

const serveurAbonnement = (statut, extra = {}) => ({id: "mon-serveur", nom: "Mon serveur", hote: "h.exemple.fr", utilisateur: "bob", fournisseur: null,
  capacites: {agent: {statut: "presente", detail: "", geste: ""}, "agent-abonnement": {statut, detail: "voir docs/serveur-agents.md#connexion-a-l-abonnement : x", geste: "", ...extra}}});
const ecranServeur = (s) => ecranServeurs({serveurs: [s], rejets: []}, {fetchFn: reseau({}), planifier: minuterie(), lieux: {}});

test("abonnement a faire affiche le lien de la procedure", () => {
  assert.equal(LIEN_CONNEXION_ABONNEMENT.endsWith("docs/serveur-agents.md#connexion-a-l-abonnement"), true);
  for (const statut of ["absente", "a_faire", "bloque"]) {
    const c = ecranServeur(serveurAbonnement(statut));
    assert.match(c.textContent, /Connexion à l'abonnement à faire/, statut);
    const liens = c.tous((n) => n.tagName === "a");
    assert.equal(liens.length, 1, statut);
    assert.equal(liens[0].href, LIEN_CONNEXION_ABONNEMENT);
    assert.ok(liens[0].textContent.length > 0);
    assert.match(liens[0].rel, /noopener/);
  }
  for (const statut of ["presente", "fait", "inconnue", "en_cours"]) {                // rien à dire : présente, ou pas encore sondée
    const c = ecranServeur(serveurAbonnement(statut));
    assert.doesNotMatch(c.textContent, /Connexion à l'abonnement à faire/, statut);
    assert.equal(c.tous((n) => n.tagName === "a").length, 0, statut);
  }
  // un texte hostile venu du serveur n'est jamais interprété (le faux DOM refuse tout innerHTML)
  const c = ecranServeur(serveurAbonnement("absente", {detail: '<a href="https://evil.example">x</a>'}));
  assert.equal(c.tous((n) => n.tagName === "a").length, 1);
  // sans la capacité d'agent dans le relevé : pas de carte inventée
  const sans = ecranServeur({id: "s", nom: "S", hote: "h", utilisateur: "u", capacites: {base: {statut: "presente"}}});
  assert.doesNotMatch(sans.textContent, /Connexion à l'abonnement à faire/);
});

const ctxPlaces = (etat, demandes = []) => ({etat: {agir: true, agents_locaux_max: 2, agents_cloud_max: 1, agents_serveur_max: 1, agents: [],
  ordre_lieux: ["local", "serveur", "cloud"], ordre_lieux_par_metier: {qa: ["cloud", "local"]}, metiers: [{role: "qa"}, {role: "dev"}], ...etat},
  barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }}});
const parAttribut = (c, cle, valeur) => c.tous((n) => n.attributs[cle] === valeur);

test("l ordre des lieux se regle et refuse un doublon", async () => {
  assert.deepEqual(ordreDeLieux(["serveur", "", "local"]), {ordre: ["serveur", "local"]});
  assert.deepEqual(ordreDeLieux(["", "", ""], true), {ordre: null});                  // facultatif (par métier) : comme le projet
  for (const mauvais of [["local", "local", ""], ["serveur", "local", "serveur"], ["", "", ""], ["x", "", ""], [], "local"]) {
    assert.ok(ordreDeLieux(mauvais).erreur, JSON.stringify(mauvais));
  }
  assert.deepEqual(demandeParallelisme(2, 1), {type: "parallelisme", agents_locaux_max: 2, agents_cloud_max: 1});      // sans ces réglages : comme avant
  assert.deepEqual(demandeParallelisme(2, 1, {serveur: "3", ordre: ["serveur", "local"], parMetier: {qa: ["cloud"]}}),
    {type: "parallelisme", agents_locaux_max: 2, agents_cloud_max: 1, agents_serveur_max: 3, ordre_lieux: ["serveur", "local"], ordre_lieux_par_metier: {qa: ["cloud"]}});
  for (const serveur of [5, -1, "x", 1.5, true, ""]) assert.equal(demandeParallelisme(2, 1, {serveur}), null, String(serveur));

  const demandes = [];
  const c = partieParallelisme(ctxPlaces({}, demandes));
  const serveur = parAttribut(c, "data-champ", "agents_serveur_max")[0];
  assert.equal(serveur.value, "1");
  const rang = (ordre, n) => parAttribut(c, "data-ordre", ordre).find((s) => s.attributs["data-rang"] === String(n));
  assert.deepEqual([1, 2, 3].map((n) => rang("projet", n).value), ["local", "serveur", "cloud"]);     // l'ordre actuel
  assert.deepEqual([1, 2, 3].map((n) => rang("metier:qa", n).value), ["cloud", "local", ""]);
  assert.deepEqual([1, 2, 3].map((n) => rang("metier:dev", n).value), ["", "", ""]);                 // « comme le projet »
  assert.equal(parAttribut(c, "data-ordre", "metier:qa").length, 3);
  const erreur = c.tous((n) => n.className.includes("saisie-erreur"))[0];
  const enregistrer = boutons(c, "Enregistrer")[0];
  // un ordre valide part, tel que réglé
  serveur.value = "2";
  rang("projet", 1).value = "serveur"; rang("projet", 2).value = "local"; rang("projet", 3).value = "";
  rang("metier:dev", 1).value = "local";
  await clic(enregistrer);
  assert.deepEqual(demandes, [{type: "parallelisme", agents_locaux_max: 2, agents_cloud_max: 1, agents_serveur_max: 2, ordre_lieux: ["serveur", "local"],
    ordre_lieux_par_metier: {qa: ["cloud", "local"], dev: ["local"]}}]);
  // un doublon est refusé avant tout envoi (projet, puis un métier)
  rang("projet", 3).value = "serveur";
  await clic(enregistrer);
  assert.equal(demandes.length, 1);
  assert.match(erreur.textContent, /qu'une fois/);
  rang("projet", 3).value = "cloud";
  rang("metier:qa", 2).value = "cloud";
  await clic(enregistrer);
  assert.equal(demandes.length, 1);
  assert.match(erreur.textContent, /qu'une fois/);
  assert.match(erreur.textContent, /qa/);
  rang("metier:qa", 2).value = "local";
  rang("projet", 1).value = ""; rang("projet", 2).value = ""; rang("projet", 3).value = "";
  await clic(enregistrer);
  assert.equal(demandes.length, 1);
  assert.match(erreur.textContent, /au moins un lieu/);
  // les noms de rôle ne passent jamais par innerHTML : un métier hostile s'écrit en texte
  const hostile = '<img src=x onerror="alert(1)">';
  const h = partieParallelisme(ctxPlaces({metiers: [{role: hostile}], ordre_lieux_par_metier: {}}));
  assert.ok(h.textContent.includes(hostile));
  assert.equal(h.tous((n) => n.tagName === "img").length, 0);
});

test("le plafond de l abonnement se regle avec les places", async () => {
  const c = partieParallelisme(ctxPlaces({agents_abonnement_max: 6}));
  const champ = parAttribut(c, "data-champ", "agents_abonnement_max")[0];
  assert.equal(champ.value, "6");
  assert.equal(parAttribut(partieParallelisme(ctxPlaces({agents_abonnement_max: null})), "data-champ", "agents_abonnement_max")[0].value, "");
  assert.equal(parAttribut(partieParallelisme(ctxPlaces({})), "data-champ", "agents_abonnement_max").length, 0);   // un seul projet : pas de fichier du bureau
  const envois = [];
  const f = async (url, init) => { envois.push({url, corps: JSON.parse(init.body), entetes: init.headers}); return reponse(200, {agents_abonnement_max: 4}); };
  assert.equal((await enregistrerPlafondAbonnement("4", f)).ok, true);
  assert.deepEqual(envois[0].corps, {agents_abonnement_max: 4});
  assert.equal(envois[0].entetes["X-Bureau"], "1");
  assert.equal((await enregistrerPlafondAbonnement("", f)).ok, true);
  assert.deepEqual(envois[1].corps, {agents_abonnement_max: null});                       // vide : plus de plafond
  for (const mauvais of ["0", "33", "x", "2.5", "-1"]) assert.equal((await enregistrerPlafondAbonnement(mauvais, f)).ok, false, mauvais);
  assert.equal(envois.length, 2);                                                         // rien n'est envoyé pour une valeur refusée
  assert.equal((await enregistrerPlafondAbonnement("3", async () => reponse(400, {erreur: "Refus"}))).ok, false);
  assert.equal((await enregistrerPlafondAbonnement("3", async () => { throw new Error("x"); })).ok, false);
});
