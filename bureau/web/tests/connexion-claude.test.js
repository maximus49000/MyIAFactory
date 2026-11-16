import test from "node:test";
import assert from "node:assert/strict";
import {texteSansMesure, connexionAProposer, lancerConnexion} from "../ui/abonnement.js";

const SANS = {disponible: false, raison: "Connexion Claude Code introuvable."};

test("sans mesure : la raison remplace « pas de mesure »", () => {
  assert.equal(texteSansMesure(SANS), "abonnement : connexion Claude Code introuvable");
  assert.equal(texteSansMesure({disponible: false}), "abonnement : pas de mesure");
  assert.equal(texteSansMesure(null), "abonnement : pas de mesure");
});

test("le bouton n'est proposé que quand c'est la connexion qui manque", () => {
  assert.ok(connexionAProposer(SANS));
  assert.ok(connexionAProposer({disponible: false, raison: "Connexion à renouveler : utilisez Claude Code un instant."}));
  assert.ok(!connexionAProposer({disponible: false, raison: "Consommation indisponible (réseau)."}));
  assert.ok(!connexionAProposer({disponible: true, raison: "Connexion Claude Code introuvable."}));   // repli moteur
  assert.ok(!connexionAProposer(null));
});

test("lancerConnexion : POST avec l'en-tête du bureau, et la commande à taper en cas d'échec", async () => {
  let vu;
  const ok = await lancerConnexion(async (url, o) => { vu = {url, o}; return {ok: true, json: async () => ({ok: true, message: "Connexion lancée."})}; });
  assert.deepEqual(ok, {ok: true, message: "Connexion lancée."});
  assert.equal(vu.url, "/api/conso/connexion");
  assert.equal(vu.o.method, "POST");
  assert.equal(vu.o.headers["X-Bureau"], "1");
  const ko = await lancerConnexion(async () => ({ok: true, json: async () => ({ok: false, message: "Introuvable.", a_copier: "claude auth login"})}));
  assert.equal(ko.ok, false);
  assert.match(ko.message, /claude auth login/);
  const panne = await lancerConnexion(async () => { throw new Error("x"); });
  assert.equal(panne.ok, false);
});
