// La case « Valider les leçons automatiquement » : une écriture des réglages du projet, jamais un changement direct.
import {test} from "node:test";
import assert from "node:assert/strict";
import {AIDE_LECONS_AUTO, AIDE_CLOUD_DOSSIER, enregistrerLeconsAuto} from "../ui/directeur.js";
import {enregistrerCloudDossierApprouve, demandeRelancerSession} from "../ui/actions.js";

test("la case « Dossier approuvé pour les sessions cloud » : son aide, et elle écrit cloud_dossier_approuve", async () => {
  assert.equal(AIDE_CLOUD_DOSSIER, "Le moteur répond lui-même « Yes, I trust this folder » quand Claude Code le demande " +
    "pour lancer une session cloud dans ce projet.");
  const vus = [];
  const r = await enregistrerCloudDossierApprouve(true, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  assert.equal(r.ok, true);
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.deepEqual(JSON.parse(vus[0][1].body), {cloud_dossier_approuve: true});
  await enregistrerCloudDossierApprouve(false, async (_, options) => { vus.push([_, options]); return {ok: true}; });
  assert.deepEqual(JSON.parse(vus[1][1].body), {cloud_dossier_approuve: false});
  assert.deepEqual(demandeRelancerSession("s1"), {type: "session_cloud", decision: "s1", verdict: "relancer"});
});

test("l'aide dit ce que fait la case", () => {
  assert.equal(AIDE_LECONS_AUTO, "Cochée, chaque leçon proposée est validée d'elle-même au niveau proposé (projet, genre ou skill). " +
    "Les leçons genre et skill vont dans la skill partagée.");
});

test("cocher écrit lecons_auto vrai dans les réglages", async () => {
  const vus = [];
  const r = await enregistrerLeconsAuto(true, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  assert.equal(r.ok, true);
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.equal(vus[0][1].method, "POST");
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.deepEqual(JSON.parse(vus[0][1].body), {lecons_auto: true});
});

test("décocher écrit faux ; une valeur qui n'est pas vraie vaut faux", async () => {
  const corps = [];
  const faux = async (_, options) => { corps.push(JSON.parse(options.body)); return {ok: true}; };
  await enregistrerLeconsAuto(false, faux);
  await enregistrerLeconsAuto("oui", faux);
  assert.deepEqual(corps, [{lecons_auto: false}, {lecons_auto: false}]);
});

test("un refus du serveur dit sa raison, un serveur injoignable aussi, sans lever", async () => {
  const refus = await enregistrerLeconsAuto(true, async () => ({ok: false, status: 400, json: async () => ({erreur: "pas booléen"})}));
  assert.deepEqual(refus, {ok: false, message: "Refusé : pas booléen"});
  const muet = await enregistrerLeconsAuto(true, async () => ({ok: false, status: 500, json: async () => { throw new Error("x"); }}));
  assert.equal(muet.ok, false);
  assert.match(muet.message, /500/);
  const coupe = await enregistrerLeconsAuto(true, async () => { throw new Error("réseau"); });
  assert.deepEqual(coupe, {ok: false, message: "Serveur du bureau injoignable."});
});
