import test from "node:test";
import assert from "node:assert/strict";
import {boutons, lienSur, envoyer} from "../ui/actions.js";

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
