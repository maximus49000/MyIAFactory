// Le panneau « Questions » : les demandes, les fils, les gestes d'une réponse, l'accusé de réception.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {demandeQuestion, demandeApprofondir, filsAffiches, gestesDuFil} from "../ui/questions.js";
import {accuseDe} from "../ui/accuse.js";

const lire = (f) => readFileSync(new URL("../ui/" + f, import.meta.url), "utf8");

test("la barre et la page ouvrent le panneau Questions", () => {
  assert.match(lire("panneaux.js"), /boutonQuestion\.addEventListener\("click", \(\) => ouvrirPanneau\("questions", null\)\)/);
});

test("une question : la demande, le suivi, « Chercher dans le code »", () => {
  assert.deepEqual(demandeQuestion("Pourquoi ?"), {type: "question", texte: "Pourquoi ?"});
  assert.deepEqual(demandeQuestion("Pourquoi ?", {fonctionnalite: "f1"}), {type: "question", texte: "Pourquoi ?", fonctionnalite: "f1"});
  assert.deepEqual(demandeQuestion("Et ?", {fil: "q1", fonctionnalite: "f1"}), {type: "question", texte: "Et ?", fil: "q1"});
  assert.deepEqual(demandeApprofondir("q1"), {type: "question_approfondir", fil: "q1"});
});

test("les fils vont du plus récent au plus ancien", () => {
  assert.deepEqual(filsAffiches({questions: [{id: "q1"}, {id: "q2"}]}).map((q) => q.id), ["q2", "q1"]);
  assert.deepEqual(filsAffiches({}), []);
});

test("les gestes d'un fil suivent son état et sa dernière réponse", () => {
  const rep = (niveau, suggestion) => ({auteur: "factory", texte: "R", niveau, suggestion});
  const fil = (etat, ...messages) => ({id: "q1", etat, messages: [{auteur: "utilisateur", texte: "Q"}, ...messages]});
  assert.equal(gestesDuFil(fil("en_cours")).attente, "Reçu, en cours de traitement…");
  assert.equal(gestesDuFil(fil("en_lecture", rep("documents"))).attente, "Lecture du code en cours…");
  assert.equal(gestesDuFil(fil("en_lecture", rep("documents"))).approfondir, false);
  const docs = gestesDuFil(fil("repondue", rep("documents")));
  assert.deepEqual([docs.attente, docs.approfondir, docs.suivi, docs.suggestion], [null, true, true, null]);
  assert.equal(gestesDuFil(fil("repondue", rep("code"))).approfondir, false);
  const s = {nature: "correction", texte: "Le score ne repart pas à zéro.", concerne: "f1"};
  assert.deepEqual(gestesDuFil(fil("repondue", rep("code", s))).suggestion, s);
  assert.equal(gestesDuFil(fil("repondue", rep("code", {nature: "autre", texte: "x"}))).suggestion, null);
});

test("le panneau Questions est branché : suggestion = formulaire prérempli, rien n'est envoyé", () => {
  const q = lire("questions.js");
  assert.match(q, /ctx\.ouvrirNouvelle\(s\.nature, s\.texte\.slice\(0, MAX_TEXTE\), s\.concerne \|\| null\)/);
  assert.match(q, /"Chercher dans le code"/);
  assert.match(q, /"Poser une question de suivi"/);
  assert.match(lire("panneaux.js"), /contenuQuestions\(contexte\(\), contenu\)/);
});

test("l'accusé d'une question : traitée quand la réponse est arrivée", () => {
  const avant = {questions: [{id: "q1", etat: "repondue", messages: [{}, {}]}]};
  const neuve = accuseDe({type: "question", texte: "Q"}, avant);
  assert.equal(neuve.cle, "question:nouvelle");
  assert.equal(neuve.traite(avant), false);
  assert.equal(neuve.traite({questions: [...avant.questions, {id: "q2", etat: "en_cours", messages: [{}]}]}), false);
  assert.equal(neuve.traite({questions: [...avant.questions, {id: "q2", etat: "repondue", messages: [{}, {}]}]}), true);
  const suivi = accuseDe({type: "question", texte: "Et ?", fil: "q1"}, avant);
  assert.equal(suivi.cle, "question:q1");
  assert.equal(suivi.traite(avant), false);
  assert.equal(suivi.traite({questions: [{id: "q1", etat: "repondue", messages: [{}, {}, {}, {}]}]}), true);
});
