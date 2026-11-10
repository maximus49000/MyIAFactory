import test from "node:test";
import assert from "node:assert/strict";
import {ETAPES_PARCOURS, bandeau, demandeNouvelle, demandeMessage, demandeCahier, demandeMethode,
        verifierPieces, lireImage, ecrit, nouvelleApparue} from "../ui/fonctionnalite.js";

const Mo = 1024 * 1024;
const png = (nom = "a.png", size = 100) => ({name: nom, type: "image/png", size});

test("bandeau : prototype et terminee", () => {
  assert.equal(ETAPES_PARCOURS.length, 6);
  const b = bandeau("prototype");
  assert.deepEqual(b.map((x) => x.libelle), ["Cadrage", "Cahier des charges", "Découpage", "Prototype", "Méthode", "Série"]);
  assert.deepEqual(b.map((x) => x.faite), [true, true, true, false, false, false]);
  assert.deepEqual(b.map((x) => x.courante), [false, false, false, true, false, false]);
  assert.ok(bandeau("terminee").every((x) => x.faite && !x.courante));
  assert.ok(bandeau("inconnue").every((x) => !x.faite && !x.courante));
});

test("formes exactes des quatre demandes", () => {
  const img = [{nom: "a.png", type: "image/png", donnees: "AAAA"}];
  assert.deepEqual(demandeNouvelle("Une idée", []), {type: "fonctionnalite", texte: "Une idée"});
  assert.deepEqual(demandeNouvelle("Une idée", img), {type: "fonctionnalite", texte: "Une idée", images: img});
  assert.deepEqual(demandeMessage("f1", "Salut", undefined), {type: "message", fonctionnalite: "f1", texte: "Salut"});
  assert.deepEqual(demandeMessage("f1", "Salut", img), {type: "message", fonctionnalite: "f1", texte: "Salut", images: img});
  assert.deepEqual(demandeCahier("f1", "valider"), {type: "cahier", fonctionnalite: "f1", verdict: "valider"});
  assert.deepEqual(demandeCahier("f1", "corriger", "Plus court"), {type: "cahier", fonctionnalite: "f1", verdict: "corriger", texte: "Plus court"});
  assert.deepEqual(demandeCahier("f1", "valider", "  "), {type: "cahier", fonctionnalite: "f1", verdict: "valider"});
  assert.deepEqual(demandeMethode("f1", "revoir", "Autre angle"), {type: "methode", fonctionnalite: "f1", verdict: "revoir", texte: "Autre angle"});
  assert.deepEqual(demandeMethode("f1", "garder"), {type: "methode", fonctionnalite: "f1", verdict: "garder"});
});

test("verifierPieces : 5 fichiers, 6 Mo, .gif", () => {
  assert.equal(verifierPieces([png()]), null);
  assert.equal(verifierPieces([]), null);
  assert.match(verifierPieces([png("1.png"), png("2.png"), png("3.png"), png("4.png"), png("5.png")]), /4 images/);
  assert.match(verifierPieces([png("gros.png", 6 * Mo)]), /5 Mo/);
  assert.equal(verifierPieces([png("ok.png", 5 * Mo)]), null);
  assert.match(verifierPieces([{name: "a.gif", type: "image/gif", size: 10}]), /PNG ou JPEG/);
  assert.match(verifierPieces([{name: "a.png", type: "image/gif", size: 10}]), /PNG ou JPEG/);
  assert.match(verifierPieces([{name: "a.jpg", type: "image/png", size: 10}]), /ne correspond pas/);
  assert.equal(verifierPieces([{name: "A.JPEG", type: "image/jpeg", size: 10}]), null);
  assert.match(verifierPieces([png("x:y.png")]), /nom/);
});

test("lireImage rend nom, type et base64", async () => {
  const fichier = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], {type: "image/png"});
  fichier.name = "a.png";
  assert.deepEqual(await lireImage(fichier), {nom: "a.png", type: "image/png", donnees: "iVBORw=="});
});

test("ecrit : trois cas", () => {
  const etat = {agents: [{id: "marie", prenom: "Marie"}], orchestrateur_actif: true};
  const f = {id: "f1", agent_cadrage: "marie", attend_reponse: true};
  assert.equal(ecrit(f, etat), "Marie est en train d'écrire…");
  assert.equal(ecrit(f, {...etat, orchestrateur_actif: false}), "En attente de l'orchestrateur");
  assert.equal(ecrit({...f, attend_reponse: false}, etat), null);
  assert.equal(ecrit({...f, agent_cadrage: null}, etat), "L'agent de cadrage est en train d'écrire…");
  assert.equal(ecrit(null, etat), null);
});

test("nouvelleApparue", () => {
  const avant = {fonctionnalites: [{id: "f1", discussion: [{texte: "Ancien"}]}]};
  const apres = {fonctionnalites: [{id: "f1", discussion: [{texte: "Ancien"}]},
                                   {id: "f2", discussion: [{auteur: "utilisateur", texte: "Mon idée"}]}]};
  assert.equal(nouvelleApparue(avant, apres, "Mon idée"), "f2");
  assert.equal(nouvelleApparue(avant, apres, "Autre"), null);
  assert.equal(nouvelleApparue(apres, apres, "Mon idée"), null);
  assert.equal(nouvelleApparue({}, apres, "Mon idée"), "f2");
  assert.equal(nouvelleApparue(avant, {}, "Mon idée"), null);
});

test("presentation : la discussion se replie quand le cahier attend son verdict", async () => {
  const {presentation} = await import("../ui/fonctionnalite.js");
  const cahier = {id: "f1", decisions: [{id: "d1", genre: "valider_cahier", texte: "T"}]};
  const sans = {id: "f1", decisions: []};
  assert.deepEqual(presentation(cahier, true, false), {discussionOuverte: false, envoiCorrection: false});
  assert.deepEqual(presentation(cahier, true, true), {discussionOuverte: true, envoiCorrection: true});
  assert.deepEqual(presentation(sans, true, true), {discussionOuverte: true, envoiCorrection: false});
  assert.deepEqual(presentation(cahier, false, false), {discussionOuverte: true, envoiCorrection: false});  // sans agir
  assert.deepEqual(presentation(null, true, false), {discussionOuverte: true, envoiCorrection: false});    // nouvelle
});
