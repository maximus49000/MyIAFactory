// Pourquoi une tâche prête ne part pas (dit par le moteur, servi par le bureau) : la barre (« 12 tâches en attente »
// et une pastille par famille), la ligne courte de la carte du Kanban, l'encadré « Pourquoi elle attend » de la fiche.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {raisonAttente, ligneAttente, pourquoiElleAttend, retenues} from "../ui/texte.js";
import {colonnesKanban} from "../ui/kanban-plein.js";

const PREREQUIS = {genre: "prerequis", motif: "prérequis", texte: "prérequis — Validation du prototype",
  detail: ["1 élément pas encore validé — « Événements, boutique, reliques et or », refait par Léa (en cours depuis 1 h 27)"],
  ensuite: ["elle exige le poste local ; 1 place locale, occupée par Léa"],
  quand: "quand vous aurez validé « Validation du prototype » pour cet élément"};

test("raisonAttente : une raison bien formée, rien sinon (rien de faux)", () => {
  assert.deepEqual(raisonAttente({attente_raison: PREREQUIS}), PREREQUIS);
  assert.equal(raisonAttente({}), null);
  assert.equal(raisonAttente({attente_raison: {genre: "inconnu", texte: "x"}}), null);
  assert.equal(raisonAttente({attente_raison: {genre: "agent", texte: "  "}}), null);
  assert.deepEqual(raisonAttente({attente_raison: {genre: "agent", texte: "poste local occupé", detail: ["a", 3, ""]}}),
    {genre: "agent", motif: "poste local occupé", texte: "poste local occupé", detail: ["a"], ensuite: [], quand: null});
});

test("ligneAttente : la raison sur la carte, sinon l'ancienne attente de charge", () => {
  assert.equal(ligneAttente({attente_raison: PREREQUIS}), "En attente : prérequis — Validation du prototype");
  assert.equal(ligneAttente({attente: "En attente : charge 90 % (plafond 70 %)"}), "En attente : charge 90 % (plafond 70 %)");
  assert.equal(ligneAttente({attente_raison: PREREQUIS, attente: "En attente : charge"}),
    "En attente : prérequis — Validation du prototype");
  assert.equal(ligneAttente({}), null);
});

test("pourquoiElleAttend : la raison, ce qui la retient, ce qu'il lui faudra ensuite, quand elle partira", () => {
  const p = pourquoiElleAttend({attente_raison: PREREQUIS});
  assert.equal(p.titre, "Pourquoi elle attend");
  assert.equal(p.famille, "Prérequis");
  assert.equal(p.raison, "Prérequis — Validation du prototype");
  assert.deepEqual(p.retient, PREREQUIS.detail);
  assert.deepEqual(p.ensuite, PREREQUIS.ensuite);
  assert.equal(p.quand, "Elle partira quand vous aurez validé « Validation du prototype » pour cet élément");
  assert.equal(pourquoiElleAttend({}), null);
  assert.equal(pourquoiElleAttend({attente_raison: {genre: "pause", texte: "projet en pause"}}).quand, null);
});

test("la barre : « 12 tâches en attente » et une pastille par famille, à la place de l'attente de charge", () => {
  const etat = {
    attente_charge: {texte: "En attente : charge 90 % (plafond 70 %)"},
    attente_validation: {texte: "2 places libres : en attente de votre validation « Essai »"},
    attentes: {texte: "12 tâches en attente", total: 12, familles: [
      {genre: "prerequis", motif: "prérequis", n: 10, texte: "10 prérequis"},
      {genre: "agent", motif: "poste local occupé", n: 1, texte: "1 poste local occupé"},
      {genre: "decision", motif: "décision à prendre", n: 1, texte: "1 décision à prendre"},
      {genre: "bizarre", n: 1, texte: "1 x"}]}};
  assert.deepEqual(retenues(etat), [
    {ton: "attentes", texte: "12 tâches en attente", pastilles: [
      {genre: "prerequis", texte: "10 prérequis"}, {genre: "agent", texte: "1 poste local occupé"},
      {genre: "decision", texte: "1 décision à prendre"}]},
    {ton: "attente", texte: "2 places libres : en attente de votre validation « Essai »"}]);
  // sans raisons servies (un moteur d'avant) : la barre d'avant
  assert.deepEqual(retenues({attente_charge: etat.attente_charge}), [{ton: "attente", texte: etat.attente_charge.texte}]);
  assert.deepEqual(retenues({attentes: null}), []);
});

test("la carte du Kanban porte la ligne courte de son attente", () => {
  const etat = {colonnes: [{id: "b", nom: "Recette"}],
                taches: [{id: "t1", titre: "Un", colonne: "b", attente_raison: PREREQUIS}, {id: "t2", titre: "Deux", colonne: "b"}]};
  const [c] = colonnesKanban(etat);
  assert.deepEqual(c.taches.map((t) => [t.id, t.attente]),
    [["t1", "En attente : prérequis — Validation du prototype"], ["t2", null]]);
});

test("la barre, la fiche et les styles affichent les attentes", () => {
  const lire = (f) => readFileSync(new URL(f, import.meta.url), "utf8");
  assert.match(lire("../ui/barre.js"), /pastilles/);
  assert.match(lire("../ui/detail.js"), /pourquoiElleAttend\(t\)/);
  const css = lire("../style.css");
  assert.match(css, /\.pastille-attente/);
  assert.match(css, /\.pourquoi-attente/);
});
