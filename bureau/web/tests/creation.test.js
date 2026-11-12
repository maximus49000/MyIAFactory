import test from "node:test";
import assert from "node:assert/strict";
import {verifierNom, verifierCreation, motsInterdits, corpsCreation, envoyerCreation, aLire, apresCreation} from "../ui/creation.js";
import {optionsProjets, ENTREE_NOUVEAU, lireProjets} from "../ui/projets.js";
import {decisionsDirecteur, issuesGenreFonctionnalite, demandeGenreFonctionnalite, demandeEnvironnement} from "../ui/actions.js";
import {libelleEtape} from "../ui/fonctionnalite.js";

test("verifierNom : vide, trop long, caractères et noms réservés Windows", () => {
  for (const n of ["", "   ", "a/b", "a\\b", "a:b", "a*b", "a?b", "a<b", "..", ".", "fin.", "CON", "nul", "Com1", "lpt3.txt", "x".repeat(101)]) {
    assert.ok(verifierNom(n), `« ${n} » devrait être refusé`);
  }
  assert.equal(verifierNom("Casse-briques"), null);
  assert.equal(verifierNom("  Jeu Été  "), null);
  assert.equal(verifierNom(undefined) !== null, true);
});

test("verifierCreation : le dossier parent et le nom sont demandés", () => {
  assert.match(verifierCreation({parent: "", nom: "A"}), /dossier/);
  assert.match(verifierCreation({parent: "C:/p", nom: ""}), /nom/i);
  assert.equal(verifierCreation({parent: "C:/p", nom: "A"}), null);
});

test("motsInterdits : virgules et retours à la ligne, sans vides ni doublons", () => {
  assert.deepEqual(motsInterdits(" a, b ,,a\nc "), ["a", "b", "c"]);
  assert.deepEqual(motsInterdits(null), []);
});

test("corpsCreation : sans décision, la description part ; avec, la décision et le genre", () => {
  const champs = {parent: " C:/p ", nom: " Jeu ", mots: "x, y", facturation: true, github: false, description: " Un jeu. "};
  assert.deepEqual(corpsCreation(champs, {origine: "a"}), {parent: "C:/p", nom: "Jeu", mots_interdits: ["x", "y"],
    facturation: true, github: false, origine: "a", description: "Un jeu."});
  const dec = {id: "g1", fonctionnalite: "f2"};
  assert.deepEqual(corpsCreation(champs, {origine: "a", decision: dec, genre: "jeu-mobile", genreDescription: " Jeux mobiles "}),
    {parent: "C:/p", nom: "Jeu", mots_interdits: ["x", "y"], facturation: true, github: false, origine: "a",
     decision: "g1", fonctionnalite: "f2", genre: "jeu-mobile", genre_description: "Jeux mobiles"});
  assert.equal("description" in corpsCreation(champs, {decision: dec}), false);
});

test("envoyerCreation : réponse, refus lisible, serveur injoignable", async () => {
  const rep = (status, corps) => async () => ({ok: status < 400, status, json: async () => corps});
  assert.deepEqual(await envoyerCreation({}, rep(200, {ok: true, projet: "jeu"})), {ok: true, projet: "jeu"});
  assert.deepEqual(await envoyerCreation({}, rep(400, {erreur: "Le nom existe déjà."})), {ok: false, message: "Le nom existe déjà."});
  assert.match((await envoyerCreation({}, async () => { throw new Error("x"); })).message, /injoignable/);
});

test("aLire : GitHub non fait ou demande non déplacée à lire avant de basculer", () => {
  assert.equal(aLire({ok: true, github: "fait"}), false);
  assert.equal(aLire({ok: true, github: "non demandé"}), false);
  assert.equal(aLire({ok: true, github: "GitHub n'a pas été fait : gh"}), true);
  assert.equal(aLire({ok: true, github: "fait", demande_deposee: false}), true);
});

test("apres creation bascule sur le nouveau projet", () => {
  const notes = [];
  assert.equal(apresCreation({ok: true, projet: "casse-briques"}, {garder: (id) => notes.push(["garder", id]), recharger: () => notes.push(["recharger"])}), true);
  assert.deepEqual(notes, [["garder", "casse-briques"], ["recharger"]]);
  const rien = [];
  assert.equal(apresCreation({ok: false, message: "non"}, {garder: () => rien.push(1), recharger: () => rien.push(2)}), false);
  assert.deepEqual(rien, []);
});

test("liste propose Nouveau projet", () => {
  const o = optionsProjets([{id: "a", nom: "A", attente: 2}, {id: "b", nom: "B", attente: 0, erreur: "x"}], "b");
  assert.deepEqual(o.map((x) => [x.value, x.libelle, x.selected]),
    [["a", "A (2)", false], ["b", "B ⚠", true], [ENTREE_NOUVEAU, "Nouveau projet…", false]]);
  assert.deepEqual(optionsProjets([], null).map((x) => x.value), [ENTREE_NOUVEAU]);
});

test("lireProjets rend aussi les dossiers parents suggérés", async () => {
  const ok = async () => ({ok: true, json: async () => ({multi: true, projets: [{id: "a"}], parents: ["C:/p", 3]})});
  assert.deepEqual(await lireProjets(ok), {multi: true, projets: [{id: "a"}], parents: ["C:/p"]});
  assert.deepEqual(await lireProjets(async () => { throw new Error("x"); }), {multi: false, projets: [], parents: []});
});

test("decision genre_fonctionnalite trois issues", () => {
  const d = {id: "g1", genre: "genre_fonctionnalite", propose: "x", genres_connus: ["x"], incertain: true};
  assert.deepEqual(issuesGenreFonctionnalite(d, true).map((i) => i.choix), ["nouveau_projet", "ici", "meme"]);
  assert.deepEqual(issuesGenreFonctionnalite({...d, incertain: false}, true).map((i) => i.libelle), ["Nouveau projet", "Dans ce projet"]);
  assert.deepEqual(issuesGenreFonctionnalite(d, false), []);
});

test("decisionsDirecteur range les décisions de genre et d'environnement, et ignore une fonctionnalité partie", () => {
  const etat = {fonctionnalites: [
    {id: "f1", nom: "Badge", etape: "cadrage", decisions: [{id: "g1", genre: "genre_fonctionnalite"}, {id: "e1", genre: "environnement"}]},
    {id: "f2", nom: "Partie", etape: "deplacee", decisions: [{id: "g2", genre: "genre_fonctionnalite"}]}]};
  const d = decisionsDirecteur(etat);
  assert.deepEqual(d.genresDemandes.map((x) => [x.id, x.fonctionnalite, x.nom]), [["g1", "f1", "Badge"]]);
  assert.deepEqual(d.environnements.map((x) => x.id), ["e1"]);
});

test("demandes de genre de fonctionnalité et d'environnement", () => {
  const d = {id: "g1", fonctionnalite: "f1"};
  assert.deepEqual(demandeGenreFonctionnalite(d, "ici", {genre: "jeu-mobile", description: " Jeux "}),
    {type: "genre_fonctionnalite", decision: "g1", fonctionnalite: "f1", choix: "ici", genre: "jeu-mobile", description: " Jeux "});
  assert.deepEqual(demandeGenreFonctionnalite(d, "meme"), {type: "genre_fonctionnalite", decision: "g1", fonctionnalite: "f1", choix: "meme"});
  assert.deepEqual(demandeGenreFonctionnalite(d, "nouveau_projet", {projetCree: "C:/p/.factory/reglages.json"}).projet_cree, "C:/p/.factory/reglages.json");
  assert.deepEqual(demandeEnvironnement(d, "fait"), {type: "environnement", decision: "g1", fonctionnalite: "f1", verdict: "fait"});
});

test("une demande abandonnée s'affiche comme telle, pas comme partie dans un projet", () => {
  assert.equal(libelleEtape({etape: "deplacee", deplacee_vers: "(demande abandonnée)"}), "Demande abandonnée");
  assert.equal(libelleEtape({etape: "deplacee", deplacee_vers: "Casse-briques"}), "Partie dans le projet Casse-briques");
});
