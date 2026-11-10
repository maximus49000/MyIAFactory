import test from "node:test";
import assert from "node:assert/strict";
import {demandeChallenge, demandeSolution, demandesVerdicts, challengeDe, resumeEnvoi} from "../ui/actions.js";
import {agentsSansApport, dansLaPeriode, provenances} from "../ui/connaissances.js";

const CIBLE = {type: "connaissance", id: "k1"};

test("demandeChallenge : forme exacte, champs vides omis", () => {
  assert.deepEqual(demandeChallenge(CIBLE), {type: "challenge", cible: {type: "connaissance", id: "k1"}});
  assert.deepEqual(demandeChallenge(CIBLE, "  ", "\n"), {type: "challenge", cible: {type: "connaissance", id: "k1"}});
  assert.deepEqual(demandeChallenge({type: "source", id: "s", autre: 1}, "pourquoi", "Relire"),
    {type: "challenge", cible: {type: "source", id: "s"}, texte: "pourquoi", solution: "Relire"});
});

test("demandeSolution : forme exacte", () => {
  assert.deepEqual(demandeSolution("ch1", "Ma solution"), {type: "solution", challenge: "ch1", texte: "Ma solution"});
});

test("demandesVerdicts : un « valider » par solution cochée, rien pour les autres, dans l'ordre", () => {
  const toutes = [{id: "s1"}, {id: "s2"}, {id: "s3"}];
  assert.deepEqual(demandesVerdicts("ch1", ["s3", "s1"], toutes), [
    {type: "verdict_solution", challenge: "ch1", solution: "s1", verdict: "valider"},
    {type: "verdict_solution", challenge: "ch1", solution: "s3", verdict: "valider"},
  ]);
  assert.deepEqual(demandesVerdicts("ch1", [], toutes), []);
  assert.deepEqual(demandesVerdicts("ch1", ["s9"], toutes), []);  // une solution qui n'est plus là
  assert.deepEqual(demandesVerdicts("ch1", new Set(["s2"]), toutes).map((d) => d.solution), ["s2"]);
});

test("challengeDe : trouve, ne trouve pas", () => {
  const etat = {challenges: [{id: "ch1", cible: {type: "connaissance", id: "k1"}},
                             {id: "ch2", cible: {type: "kpi", id: "k1"}}]};
  assert.equal(challengeDe(etat, CIBLE).id, "ch1");
  assert.equal(challengeDe(etat, {type: "kpi", id: "k1"}).id, "ch2");
  assert.equal(challengeDe(etat, {type: "source", id: "k1"}), null);
  assert.equal(challengeDe({}, CIBLE), null);
  assert.equal(challengeDe(null, CIBLE), null);
});

test("resumeEnvoi : dit lesquelles sont parties et lesquelles non", () => {
  assert.equal(resumeEnvoi([{nom: "A", ok: true}, {nom: "B", ok: true}]), "Demandes envoyées : A, B.");
  assert.equal(resumeEnvoi([{nom: "A", ok: true}, {nom: "B", ok: false, message: "Demande refusée : Solution inconnue."}]),
    "Envoyées : A. Non envoyées : B (Demande refusée : Solution inconnue.).");
  assert.equal(resumeEnvoi([{nom: "A", ok: false, message: "x"}]), "Non envoyées : A (x).");
  assert.equal(resumeEnvoi([]), "");
});

const M = new Date("2026-11-10T12:00:00Z");

test("dansLaPeriode", () => {
  assert.equal(dansLaPeriode("2026-11-05T12:00:00Z", "7j", M), true);
  assert.equal(dansLaPeriode("2026-11-01T12:00:00Z", "7j", M), false);
  assert.equal(dansLaPeriode("2026-11-01T12:00:00Z", "30j", M), true);
  assert.equal(dansLaPeriode("hier", "7j", M), false);
  assert.equal(dansLaPeriode(null, "7j", M), false);
  assert.equal(dansLaPeriode(M.toISOString(), "aujourdhui", M), true);
  assert.equal(dansLaPeriode("2026-11-08T12:00:00Z", "aujourdhui", M), false);
});

const SAVOIR = [
  {agent: "d1", prenom: "Léa", service: "dev", present: true, connaissances: [
    {id: "k1", texte: "a", date: "2026-11-09", partagee: true,
     appris_de: [{agent: "q1", prenom: "Hugo", service: "qa", tache: "t1", titre: "Export CSV", retour: "2026-11-08"}]}]},
  {agent: "d2", prenom: "Paul", service: "dev", present: true, connaissances: [
    {id: "k2", texte: "b", date: "2026-10-01", partagee: true, appris_de: [{agent: "d1", prenom: "Léa", service: "dev"}]},
    {id: "k3", texte: "c", date: "2026-11-09", partagee: false, appris_de: []}]},
  {agent: "d3", prenom: "Zoé", service: "dev", present: false, connaissances: []},
  {agent: "q1", prenom: "Hugo", service: "qa", present: true, connaissances: []},
];

test("agentsSansApport : agents présents du service sans connaissance reçue sur la période", () => {
  assert.deepEqual(agentsSansApport(SAVOIR, "dev", "7j", M).map((a) => a.agent), ["d2"]);
  assert.deepEqual(agentsSansApport(SAVOIR, "dev", "30j", M).map((a) => a.agent), ["d2"]);
  assert.deepEqual(agentsSansApport(SAVOIR, "qa", "7j", M).map((a) => a.agent), ["q1"]);
  assert.deepEqual(agentsSansApport([], "dev", "7j", M), []);
});

test("provenances : « appris du retour de … sur … », autre service signalé", () => {
  const [k1] = SAVOIR[0].connaissances;
  assert.deepEqual(provenances(k1, "dev"), ["appris du retour de Hugo (service qa) sur « Export CSV »"]);
  assert.deepEqual(provenances(SAVOIR[1].connaissances[0], "dev"), ["appris du retour de Léa"]);
  assert.deepEqual(provenances({appris_de: [{agent: "x", tache: "t9"}]}, "dev"), ["appris du retour de x sur « t9 »"]);
  assert.deepEqual(provenances({appris_de: [{agent: "x", prenom: "<img onerror=x>", titre: "<b>"}]}, "dev"),
    ["appris du retour de <img onerror=x> sur « <b> »"]);
});
