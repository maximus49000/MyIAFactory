// « Partager les connaissances » : le surcoût affiché, le résumé de la file, et les demandes au serveur.
import {test} from "node:test";
import assert from "node:assert/strict";
import {libelleSurcout, resumeFile, demandeConnaissances} from "../ui/partage.js";

const vue = (s, niveau = "renforce") => ({niveau, surcout: s});

test("le surcoût : estimé avant la première relecture, mesuré ensuite, rien au niveau standard", () => {
  assert.equal(libelleSurcout(vue({relectures: 0, cout_usd: 0, par_lecon_usd: 0.003, estime: true, a_venir: 0})),
    "Surcoût de la relecture par Claude (Haiku) : ≈ 0,0030 $ par leçon (estimation).");
  assert.equal(libelleSurcout(vue({relectures: 4, cout_usd: 0.012, par_lecon_usd: 0.003, estime: false, a_venir: 2})),
    "Surcoût de la relecture par Claude (Haiku) : 0,0030 $ par leçon (moyenne mesurée) · 4 relectures : 0,01 $ au " +
    "total · 2 leçons à relire ≈ 0,0060 $.");
  assert.equal(libelleSurcout(vue({relectures: 4, cout_usd: 0.012, par_lecon_usd: 0.003}, "standard")),
    "Aucun surcoût : pas d'appel à Claude.");
  // le menu change avant la réponse du serveur : le libellé suit le niveau choisi
  assert.match(libelleSurcout(vue({relectures: 0, par_lecon_usd: 0.003, estime: true}, "standard"), "strict"), /≈ 0,0030/);
});

test("le résumé de la file ne dit que ce qui existe", () => {
  assert.equal(resumeFile({compte: {locale: 2, a_relire: 1, envoyee: 0}}), "2 gardée(s) sur ce poste · 1 à relire");
  assert.equal(resumeFile({}), "");
});

test("une demande porte l'en-tête du bureau ; un refus redit le message du serveur", async () => {
  const vus = [];
  const ok = await demandeConnaissances({action: "regler", actif: true}, async (url, o) => {
    vus.push([url, o]);
    return {ok: true, json: async () => ({actif: true, message: "Partage activé."})};
  });
  assert.deepEqual([ok.ok, ok.message], [true, "Partage activé."]);
  assert.equal(vus[0][0], "/api/connaissances");
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.deepEqual(JSON.parse(vus[0][1].body), {action: "regler", actif: true});
  const refus = await demandeConnaissances({action: "regler", actif: true}, async () =>
    ({ok: false, status: 409, json: async () => ({actif: null, ok: false, message: "Demandez une invitation."})}));
  assert.deepEqual([refus.ok, refus.message, refus.vue.actif], [false, "Demandez une invitation.", null]);
  const panne = await demandeConnaissances({}, async () => { throw new Error("x"); });
  assert.equal(panne.message, "Serveur du bureau injoignable.");
});
