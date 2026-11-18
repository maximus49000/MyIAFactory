import {test} from "node:test";
import assert from "node:assert/strict";
import {suiviDuRetour, retourSansReponse, retoursRepondusNonVus} from "../ui/texte.js";

const transmis = {texte: "Le téléchargement échoue", reponse: "Question transmise à Hugo : il répondra à la fin de sa tâche en cours.",
                  suivi: {etat: "transmis", texte: "En attente : Hugo travaille encore sur la tâche t55", tache: "t55"}};

test("un retour transmis dit où en est l'agent (essai réel du 2026-11-18)", () => {
  const s = suiviDuRetour(transmis, {etat: "avance", etat_texte: "avance", reste_texte: "2 à 6 min",
    points: [{texte: "a", fait: true}, {texte: "b", fait: false}], en_cours: "lance les tests"});
  assert.equal(s.libelle, "Transmis, en attente");
  assert.equal(s.ouAgent, "1/2 points faits · en cours : lance les tests · avance · reste 2 à 6 min");
  assert.equal(retourSansReponse(transmis), true);      // « Question transmise » n'est pas une réponse
});

test("répondu : plus sans réponse, et compte au bureau du Directeur jusqu'à « Pris en compte »", () => {
  const r = {id: "r43", texte: "x", reponse: "transmise", suivi: {etat: "repondu", texte: "Réponse de Hugo : corrigé."}};
  assert.equal(retourSansReponse(r), false);
  assert.equal(suiviDuRetour(r, null).ton, "ok");
  const etat = {taches: [{id: "t55", retours: [r, transmis]}], echanges_vus: []};
  assert.deepEqual(retoursRepondusNonVus(etat).map((x) => x.retour.id), ["r43"]);
  assert.deepEqual(retoursRepondusNonVus({...etat, echanges_vus: ["retour:r43"]}), []);
});

test("un ancien retour sans suivi garde sa règle", () => {
  assert.equal(suiviDuRetour({texte: "x"}, null), null);
  assert.equal(retourSansReponse({texte: "x"}), true);
  assert.equal(retourSansReponse({texte: "x", reponse: "ok"}), false);
});
