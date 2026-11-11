// Essai réel : sans orchestrateur en cours, un bandeau bloque les gestes et propose de le lancer.
import {test} from "node:test";
import assert from "node:assert/strict";
import {lancerOrchestrateur, bandeauVisible} from "../ui/orchestrateur.js";

const reponse = (status, corps) => async (url, init) => {
  reponse.appels.push([url, init]);
  return {ok: status === 200, status, json: async () => corps};
};
reponse.appels = [];

test("le bandeau ne paraît que si le relevé dit l'orchestrateur absent", () => {
  assert.equal(bandeauVisible({orchestrateur_absent: true}), true);
  assert.equal(bandeauVisible({orchestrateur_absent: false}), false);
  assert.equal(bandeauVisible({}), false);
  assert.equal(bandeauVisible(null), false);
});

test("lancer : un POST avec l'en-tête du bureau, le message de la réponse", async () => {
  const r = await lancerOrchestrateur(reponse(200, {ok: true, message: "L'orchestrateur démarre."}));
  assert.deepEqual(r, {ok: true, message: "L'orchestrateur démarre.", aCopier: null});
  const [url, init] = reponse.appels.at(-1);
  assert.match(url, /\/api\/orchestrateur\/lancer/);
  assert.equal(init.method, "POST");
  assert.equal(init.headers["X-Bureau"], "1");
});

test("lancer sans claude : le message à copier est rendu", async () => {
  const r = await lancerOrchestrateur(reponse(200, {ok: false, message: "claude n'est pas installé", a_copier: "Tu es l'orchestrateur"}));
  assert.equal(r.ok, false);
  assert.equal(r.aCopier, "Tu es l'orchestrateur");
});

test("lancer refusé ou serveur injoignable : un message clair", async () => {
  assert.match((await lancerOrchestrateur(reponse(409, {erreur: "L'orchestrateur est déjà en cours."}))).message, /déjà en cours/);
  const r = await lancerOrchestrateur(async () => { throw new Error("réseau"); });
  assert.equal(r.ok, false);
  assert.match(r.message, /injoignable/);
});
