import test from "node:test";
import assert from "node:assert/strict";
import {boutons, lienSur, envoyer, challengesDuService, decisionsDirecteur, demandeSerieArretee, demandeFinVue, demandeLecon, demandeGenre, demandeSession, lireSession, libelleMontee, libelleModeleNecessaire, libelleLot} from "../ui/actions.js";

const ACTIONS = [
  {id: "pause", libelle: "Pause", confirmer: "Mettre en pause ?"},
  {id: "doc", libelle: "Documentation", lien: "https://exemple.org/doc"},
  {id: "mauvais", libelle: "Piège", lien: "javascript:alert(1)"},
  {id: "gris", libelle: "Grisé", actif: false},
];

test("boutons sans agir : les liens seuls", () => {
  assert.deepEqual(boutons({agir: false, actions: ACTIONS}),
    [{id: "doc", libelle: "Documentation", lien: "https://exemple.org/doc", confirmer: null, actif: true}]);
  assert.deepEqual(boutons({actions: ACTIONS}).map((b) => b.id), ["doc"]);
  assert.deepEqual(boutons({}), []);
  assert.deepEqual(boutons(null), []);
});

test("boutons avec agir : demandes et liens sûrs, dans l'ordre", () => {
  const b = boutons({agir: true, actions: ACTIONS});
  assert.deepEqual(b.map((x) => x.id), ["pause", "doc", "gris"]);
  assert.deepEqual(b[0], {id: "pause", libelle: "Pause", lien: null, confirmer: "Mettre en pause ?", actif: true});
  assert.equal(b[2].actif, false);
});

test("lienSur", () => {
  assert.equal(lienSur("javascript:x"), false);
  assert.equal(lienSur("claude://claude.ai/code/x"), true);
  assert.equal(lienSur("https://a.b/c"), true);
  assert.equal(lienSur("http://a.b"), true);
  assert.equal(lienSur("HTTPS://a.b"), true);
  assert.equal(lienSur("data:text/html,x"), false);
  assert.equal(lienSur("https://a b"), false);
  assert.equal(lienSur("https://a\n.b"), false);
  assert.equal(lienSur(""), false);
  assert.equal(lienSur(null), false);
  assert.equal(lienSur(3), false);
});

function faux(statut, corps) {
  const appels = [];
  const f = async (url, options) => {
    appels.push({url, options});
    return {ok: statut >= 200 && statut < 300, status: statut, json: async () => corps};
  };
  f.appels = appels;
  return f;
}

test("envoyer : en-têtes, corps et message", async () => {
  const f = faux(200, {ok: true});
  const demande = {type: "bouton", id: "pause"};
  assert.deepEqual(await envoyer(demande, f), {ok: true, message: "Demande envoyée"});
  const {url, options} = f.appels[0];
  assert.equal(url, "/api/demande");
  assert.equal(options.method, "POST");
  assert.equal(options.headers["X-Bureau"], "1");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(options.body), demande);
});

test("envoyer : refus du serveur", async () => {
  assert.deepEqual(await envoyer({type: "bouton", id: "x"}, faux(400, {erreur: "x"})),
                   {ok: false, message: "Demande refusée : x"});
  assert.deepEqual(await envoyer({type: "bouton", id: "x"}, faux(502, {})),
                   {ok: false, message: "Demande refusée : le serveur a répondu 502"});
});

test("envoyer : serveur injoignable", async () => {
  const f = async () => { throw new TypeError("fetch failed"); };
  assert.deepEqual(await envoyer({type: "bouton", id: "x"}, f),
                   {ok: false, message: "Demande refusée : serveur injoignable"});
});

// --- Relecture finale : un challenge reste atteignable quand sa cible n'est plus affichée.

test("challengesDuService : par cible (KPI, source, connaissance d'un agent du service)", () => {
  const etat = {
    services: [{id: "dev"}, {id: "dev:web"}, {id: "qa"}],
    savoir: [{agent: "d1", service: "dev", connaissances: [{id: "k1"}]},
             {agent: "q1", service: "qa", connaissances: [{id: "k2"}]}],
    challenges: [
      {id: "c1", cible: {type: "kpi", id: "kpi:dev:defauts"}, texte: "A",
       solutions: [{id: "s1", etat: "proposée"}, {id: "s2", etat: "Validée"}, {id: "s3"}]},
      {id: "c2", cible: {type: "source", id: "source:dev:tache_chere:t1"}, texte: "B", solutions: []},
      {id: "c3", cible: {type: "connaissance", id: "k1"}, texte: "C", solutions: [{id: "s4", etat: "écartée"}]},
      {id: "c4", cible: {type: "connaissance", id: "k2"}, texte: "D"},
      {id: "c5", cible: {type: "kpi", id: "kpi:dev:web:lenteur"}, texte: "E"},
      {id: "c6", cible: {type: "kpi", id: "kpi:devops:x"}, texte: "F"},
      null, {id: "c7"},
    ],
  };
  assert.deepEqual(challengesDuService(etat, "dev").map((x) => [x.challenge.id, x.aDecider]),
                   [["c1", 2], ["c2", 0], ["c3", 0]]);
  assert.deepEqual(challengesDuService(etat, "dev:web").map((x) => x.challenge.id), ["c5"]);
  assert.deepEqual(challengesDuService(etat, "qa").map((x) => x.challenge.id), ["c4"]);
  assert.deepEqual(challengesDuService({}, "dev"), []);
});

// --- Le Directeur enrichi (version 4).

test("decisionsDirecteur : chaque entrée garde sa fonctionnalité", () => {
  const etat = {
    fonctionnalites: [
      {id: "f1", nom: "Accueil", decisions: [{id: "d1", genre: "valider_cahier", texte: "Cahier"},
                                              {id: "d2", genre: "valider_methode", texte: "Méthode"}]},
      {id: "f2", nom: "Recherche", decisions: [{id: "d3", genre: "methode_a_revoir", texte: "Revoir ?"},
                                               {id: "d4", genre: "valider_cahier", texte: "Cahier 2"}]},
    ],
    decisions_projet: [{id: "p1", genre: "confirmer_genre", texte: "Genre", propose: "vitrine", genres_connus: ["vitrine"]},
                       {id: "p2", genre: "session_cloud", texte: "Session", agent: "dev:1"}],
  };
  const d = decisionsDirecteur(etat);
  assert.deepEqual(d.cahiers.map((x) => [x.id, x.fonctionnalite, x.nom]), [["d1", "f1", "Accueil"], ["d4", "f2", "Recherche"]]);
  assert.deepEqual(d.methodes.map((x) => [x.id, x.fonctionnalite]), [["d2", "f1"]]);
  assert.deepEqual(d.revoir.map((x) => [x.id, x.fonctionnalite]), [["d3", "f2"]]);
  assert.deepEqual(d.genres.map((x) => x.id), ["p1"]);
  assert.equal(d.genres[0].propose, "vitrine");
  assert.deepEqual(d.sessions.map((x) => [x.id, x.agent]), [["p2", "dev:1"]]);
  assert.deepEqual(decisionsDirecteur({}), {cahiers: [], methodes: [], revoir: [], genres: [], sessions: [], organisations: [], reponses: [],
    genresDemandes: [], environnements: [], elargissements: [], validations: [], outils: [], accords: [], series: [], terminees: [], chezPartenaires: [], fables: [], blocages: []});
});

test("decisionsDirecteur : fonctionnalités terminées pas encore vues et séries arrêtées", () => {
  const fin = {date: "2026-11-12T20:00:00+01:00", vu: false, livrables: [{chemin: "build/jeu.apk", titre: "APK"}]};
  const d = decisionsDirecteur({
    fonctionnalites: [{id: "f1", nom: "Jeu", etape: "terminee", catalogue: true, decisions: [], fin},
                      {id: "f2", nom: "Vu", etape: "terminee", decisions: [], fin: {...fin, vu: true}},
                      {id: "f3", nom: "Sans avis", etape: "terminee", decisions: []},
                      {id: "f4", nom: "En série", etape: "serie", decisions: []}],
    decisions_projet: [{id: "s1", genre: "serie_arretee", texte: "La série ne progresse plus", fonctionnalite: "f4"}]});
  assert.deepEqual(d.terminees.map((x) => [x.fonctionnalite, x.nom, x.catalogue, x.livrables.length]), [["f1", "Jeu", true, 1]]);
  assert.deepEqual(d.series.map((x) => [x.id, x.fonctionnalite, x.nom]), [["s1", "f4", "En série"]]);
  assert.deepEqual(demandeSerieArretee({id: "s1"}), {type: "serie_arretee", decision: "s1", verdict: "relancer"});
  assert.deepEqual(demandeFinVue("f1"), {type: "fin_vue", fonctionnalite: "f1"});
});

test("demandeLecon : étage changé, inchangé", () => {
  const l = {id: "L1", etage_propose: "genre"};
  assert.deepEqual(demandeLecon(l, "valider", "genre"), {type: "lecon", id: "L1", verdict: "valider"});
  assert.deepEqual(demandeLecon(l, "valider", "skill"), {type: "lecon", id: "L1", verdict: "valider", etage: "skill"});
  assert.deepEqual(demandeLecon(l, "invalider"), {type: "lecon", id: "L1", verdict: "invalider"});
  assert.deepEqual(demandeLecon({id: "L2"}, "valider", "projet"), {type: "lecon", id: "L2", verdict: "valider"});
  assert.deepEqual(demandeLecon({id: "L2"}, "valider", "genre"), {type: "lecon", id: "L2", verdict: "valider", etage: "genre"});
});

test("demandeGenre : existant, et nouveau avec description", () => {
  assert.deepEqual(demandeGenre("p1", "vitrine"), {type: "genre", decision: "p1", genre: "vitrine"});
  assert.deepEqual(demandeGenre("p1", "jeu-web", "  "), {type: "genre", decision: "p1", genre: "jeu-web"});
  assert.deepEqual(demandeGenre("p1", "jeu-web", "Un jeu dans le navigateur"),
    {type: "genre", decision: "p1", genre: "jeu-web", description: "Un jeu dans le navigateur"});
});

test("demandeSession", () => {
  assert.deepEqual(demandeSession("p2", "Session dev 1"), {type: "session_cloud", decision: "p2", session: "Session dev 1"});
  // la session collée : l'adresse claude.ai/code ou l'identifiant (comme moteur/cloud.py, lire_session)
  assert.deepEqual(lireSession(" https://claude.ai/code/session_01AbC?x=1 "),
    {session: "session_01AbC", adresse: "https://claude.ai/code/session_01AbC"});
  assert.equal(lireSession("session_01AbC").adresse, "https://claude.ai/code/session_01AbC");
  assert.equal(lireSession("0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b").session, "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b");
  for (const x of ["Ma session", "", "https://example.com/code/session_1", "https://claude.ai/code/", "session_", null]) {
    assert.equal(lireSession(x), null, String(x));
  }
});

test("libelleMontee", () => {
  assert.equal(libelleMontee({montee: {de: "Haiku", a: "Sonnet", raison: "trois échecs"}}), "Sonnet, monté depuis Haiku : trois échecs");
  assert.equal(libelleMontee({montee: null}), null);
  assert.equal(libelleMontee({}), null);
  assert.equal(libelleMontee(null), null);
  assert.equal(libelleMontee({montee: {de: "Haiku", a: "Sonnet"}}), "Sonnet, monté depuis Haiku");
});

test("libelleModeleNecessaire : le modèle de la tâche et sa raison", () => {
  assert.equal(libelleModeleNecessaire({modele_necessaire: {modele: "Haiku", raison: "déduit de l'étape : tests", ramene: false}}),
               "Haiku — déduit de l'étape : tests");
  assert.equal(libelleModeleNecessaire({modele_necessaire: {modele: "Sonnet", raison: "", ramene: false}}), "Sonnet");
  for (const t of [{}, null, {modele_necessaire: null}, {modele_necessaire: {modele: ""}}, {modele_necessaire: "Haiku"}]) {
    assert.equal(libelleModeleNecessaire(t), null);
  }
});

test("nomAgent : le prénom, sinon la clé (un agent pas encore au bureau)", async () => {
  const {nomAgent} = await import("../ui/detail.js");
  const e = {agents: [{id: "dev:1", prenom: "Léa"}]};
  assert.equal(nomAgent(e, "dev:1"), "Léa");
  assert.equal(nomAgent(e, "dev:2"), "dev:2");
  assert.equal(nomAgent({}, null), "personne");
});

test("decisionsDirecteur : les discussions qui attendent la réponse de l'utilisateur", () => {
  const m = (auteur, texte = "?") => ({id: "m" + auteur, t: "2026-11-10T10:00:00+01:00", auteur, texte});
  const e = {fonctionnalites: [
    {id: "f1", nom: "A", etape: "cadrage", discussion: [m("utilisateur"), m("cadrage-1", "Quelle taille ?")]},
    {id: "f2", nom: "B", etape: "prototype", discussion: [m("dev-1")]},
    {id: "f3", nom: "C", etape: "cadrage", discussion: [m("cadrage-1"), m("utilisateur")]},
    {id: "f4", nom: "D", etape: "cahier", discussion: [m("cadrage-1")], decisions: [{id: "x", genre: "valider_cahier", texte: "T"}]},
    {id: "f5", nom: "E", etape: "serie", discussion: [m("dev-1")]},
    {id: "f6", nom: "F", etape: "cadrage"}]};
  const r = decisionsDirecteur(e).reponses;
  assert.deepEqual(r.map((x) => x.fonctionnalite), ["f1", "f2"]);
  assert.equal(r[0].nom, "A");
  assert.equal(r[0].dernier.texte, "Quelle taille ?");
  assert.deepEqual(decisionsDirecteur({}).reponses, []);
});

test("demandeToutes : chaque leçon en attente, avec son étage choisi s'il change", async () => {
  const {demandeToutes} = await import("../ui/actions.js");
  const lecons = [{id: "a", etage_propose: "projet"}, {id: "b", etage_propose: "genre", texte_general: "G"},
                  {id: "c", etage_propose: "projet", verdict_demande: "valider"},            // déjà envoyée
                  {id: "d", etage_propose: "skill", texte_general: "S"}];
  const etages = new Map([["a", "projet"], ["b", "projet"], ["d", "skill"]]);           // b : changé par l'utilisateur
  assert.deepEqual(demandeToutes(lecons, "valider", etages),
                   {type: "lecons", verdict: "valider", lecons: [{id: "a"}, {id: "b", etage: "projet"}, {id: "d"}]});
  assert.deepEqual(demandeToutes(lecons, "invalider", new Map()).lecons.map((d) => d.id), ["a", "b", "d"]);
});

test("demandeChallengeLecon : la leçon visée et le texte", async () => {
  const {demandeChallengeLecon} = await import("../ui/actions.js");
  assert.deepEqual(demandeChallengeLecon({id: "dev-1:L4"}, "  Pourquoi trois passes ?  "),
    {type: "challenge", cible: {type: "lecon", id: "dev-1:L4"}, texte: "Pourquoi trois passes ?"});
});

test("decisionsDirecteur : un compte rendu n'attend pas de réponse", () => {
  const m = (texte, x = {}) => ({id: "m", t: "2026-11-10T10:00:00", auteur: "dev-1", texte, ...x});
  const e = {fonctionnalites: [
    {id: "f1", nom: "A", etape: "prototype", discussion: [m("Les joints sont supprimés.")]},
    {id: "f2", nom: "B", etape: "prototype", discussion: [m("Ça vous va ?")]},
    {id: "f3", nom: "C", etape: "cadrage", discussion: [m("Voici", {attend: true})]},
    {id: "f4", nom: "D", etape: "cadrage", discussion: [m("Fait ? oui.", {attend: false})]},
    {id: "f5", nom: "E", etape: "cadrage", discussion: [m("Choisissez", {questions: [{texte: "T", choix: ["a", "b"]}]})]}]};
  assert.deepEqual(decisionsDirecteur(e).reponses.map((x) => x.fonctionnalite), ["f2", "f3", "f5"]);
});

test("libelleLot : « Lot L2, tâche 3 sur 4 »", () => {
  const taches = [1, 2, 3, 4].map((rang) => ({lot: {id: "L2", rang}})).concat([{lot: {id: "L3", rang: 1}}, {lot: null}]);
  assert.equal(libelleLot(taches[2], taches), "Lot L2, tâche 3 sur 4");
  assert.equal(libelleLot(taches[4], taches), "Lot L3, tâche 1 sur 1");
  assert.equal(libelleLot({lot: null}, taches), null);
  assert.equal(libelleLot({}, taches), null);
  assert.equal(libelleLot({lot: {id: "L2", rang: 0}}, taches), null);
  assert.equal(libelleLot({lot: {id: "L9", rang: 2}}, undefined), "Lot L9, tâche 2 sur 2");
});

test("Tout valider : une seule demande groupée, avec l'étage choisi de chaque leçon", async () => {
  const {demandeToutes} = await import("../ui/actions.js");
  const lecons = [{id: "a", etage_propose: "genre"}, {id: "b", verdict_demande: "valider"}, {id: "c"}];
  assert.deepEqual(demandeToutes(lecons, "valider", new Map([["a", "projet"]])),
                   {type: "lecons", verdict: "valider", lecons: [{id: "a", etage: "projet"}, {id: "c"}]});
  assert.equal(demandeToutes([{id: "b", verdict_demande: "valider"}], "valider"), null);
});
