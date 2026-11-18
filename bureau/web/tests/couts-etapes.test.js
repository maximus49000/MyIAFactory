import test from "node:test";
import assert from "node:assert/strict";
import {regrouperParEtape, raisonDuPassage, libelleMinutes, libelleModeles, nomCourtModele} from "../ui/couts-etapes.js";

const CORR = {id: "f1", nature: "correction"};
const ligne = (id, etape, total, extra = {}) => ({id, etape, total, sans_prix: 0, modeles: {sonnet: total}, ...extra});

test("une correction : les passages regroupés dans l'ordre Diagnostic → Correctif → Validation → Livraison", () => {
  const taches = [ligne("t1", "cadrage", 1.0, {debut: "2026-11-16T14:00:00Z", fin: "2026-11-16T14:14:00Z"}),
                  ligne("t4", "flux:f1-correctif", 0.2), ligne("t10", "validation:f1-validation", 0.01),
                  ligne("t5", "flux:f1-correctif", 0.3), ligne("t18", "flux:f1-livraison", 0.49)];
  const g = regrouperParEtape(taches, CORR, {});
  assert.deepEqual(g.map((x) => [x.libelle, x.passages]), [["Diagnostic", 1], ["Correctif", 2], ["Validation", 1],
                                                          ["Livraison", 1]]);
  assert.equal(Math.round(g[1].total * 100), 50);
  assert.equal(Math.round(g[1].part * 100), 25);
  assert.equal(g[0].minutes, 14);
  assert.equal(g[1].inconnues, 2);                         // sans début ni fin : durée inconnue, jamais inventée
  assert.equal(libelleMinutes(g[1].minutes, g[1].inconnues, g[1].passages), null);
  assert.equal(libelleMinutes(65), "1 h 05");
});

test("une fonctionnalité : ses étapes dans l'ordre où elles ont eu lieu, noms des colonnes, retours ensemble", () => {
  const e = {colonnes: [{id: "f2-dev", nom: "Développement"}, {id: "f2-qa", nom: "Recette"}]};
  const taches = [ligne("t1", "cadrage", 1), ligne("t2", "prototype", 1), ligne("t3", "flux:f2-dev", 1),
                  ligne("t4", "retour", 1), ligne("t5", "correction", 1), ligne("t6", "flux:f2-qa", 1),
                  ligne("t7", "bizarre", 1)];
  const g = regrouperParEtape(taches, {id: "f2"}, e);
  assert.deepEqual(g.map((x) => x.libelle), ["Cadrage", "Prototype", "Développement", "Retours et reprises", "Recette",
                                             "Autres"]);
  assert.equal(g[3].passages, 2);
});

test("la raison d'un passage refait se lit dans le journal de la tâche", () => {
  assert.equal(raisonDuPassage({journal: [{texte: "Rien à valider : ton rapport n'a donné…"}]}), "refait : rien à valider");
  assert.equal(raisonDuPassage({journal: [{texte: "Retour de l'utilisateur : refais la capture"}]}), "retour du Directeur");
  assert.equal(raisonDuPassage({journal: [{texte: "Terminé."}]}), null);
  assert.equal(raisonDuPassage(undefined), null);
});

test("les modèles d'un passage : le prix de chacun, le plus cher d'abord ; un seul modèle, son nom seul", () => {
  const e = (v) => v.toFixed(2) + " €";
  assert.equal(nomCourtModele("claude-haiku-4-5-20251001"), "Haiku 4.5");
  assert.equal(nomCourtModele("claude-sonnet-5"), "Sonnet 5");
  assert.equal(nomCourtModele("modele-inconnu"), "modele-inconnu");
  assert.equal(libelleModeles({"claude-haiku-4-5-20251001": 0.15, "claude-sonnet-5": 2.1}, e),
               "Sonnet 5 : 2.10 € · Haiku 4.5 : 0.15 €");
  assert.equal(libelleModeles({"claude-sonnet-5-5": 2.1}, e), "Sonnet 5.5");
  assert.equal(libelleModeles({}, e), "");
});
