import {test} from "node:test";
import assert from "node:assert/strict";
import {avancementEnClair, cleTravail} from "../ui/texte.js";

const base = {etat: "avance", etat_texte: "avance", points: [], en_cours: null, phase: "tests", passe_s: 1080,
              cumul_s: 3900, reste: {min_s: 360, max_s: 960}, reste_texte: "6 à 16 min"};

test("les points, la ligne en cours et les temps se disent en clair", () => {
  const a = avancementEnClair({...base, points: [{texte: "APK reconstruit", fait: true}, {texte: "Note", fait: false}],
                               en_cours: "réécrit la note"});
  assert.deepEqual(a.points, [{texte: "APK reconstruit", fait: true}, {texte: "Note", fait: false}]);
  assert.equal(a.enCours, "réécrit la note");
  assert.equal(a.passe, "18 min");
  assert.equal(a.cumul, "1 h 05");
  assert.equal(a.reste, "6 à 16 min");
  assert.equal(a.sansListe, false);
});

test("sans liste de l'agent, la phase déduite du flux est dite", () => {
  const a = avancementEnClair(base);
  assert.equal(a.sansListe, true);
  assert.equal(a.phase, "tests");
  assert.deepEqual(a.points, []);
});

test("un temps restant inconnu est dit inconnu", () => {
  const a = avancementEnClair({...base, reste: null, reste_texte: "inconnu"});
  assert.equal(a.reste, "inconnu");
  assert.equal(avancementEnClair({...base, reste_texte: undefined, reste: null}).reste, "inconnu");
});

test("l'état se colore : vert, orange, rouge", () => {
  assert.equal(avancementEnClair(base).ton, "ok");
  assert.equal(avancementEnClair({...base, etat: "commande_longue"}).ton, "pause");
  for (const etat of ["sans_action", "termine_non_lu", "moteur_arrete"]) {
    assert.equal(avancementEnClair({...base, etat}).ton, "alerte");
  }
});

test("sans avancement, rien n'est rendu", () => {
  assert.equal(avancementEnClair(undefined), null);
  assert.equal(avancementEnClair(null), null);
});

test("un changement d'état ou de liste redessine la fiche", () => {
  const t = {travail: {depuis: new Date().toISOString(), action: "x"}, avancement: base};
  const avant = JSON.stringify(cleTravail(t));
  const apres = JSON.stringify(cleTravail({...t, avancement: {...base, etat: "sans_action",
                                                              points: [{texte: "a", fait: true}]}}));
  assert.notEqual(avant, apres);
  assert.ok(cleTravail({avancement: {...base, etat: "termine_non_lu"}}));      // même sans agent au travail
});

test("lot et attente du verrou de tests : à son tour, pas une alerte", () => {
  // essai réel du 2026-11-18 (lot L5) : t68 finie, la même session faisait t69 ; Hugo attendait le verrou de tests
  const faite = avancementEnClair({...base, etat: "lot_faite", etat_texte: "faite ; l'agent poursuit le lot"});
  assert.equal(faite.ton, "ok");
  assert.equal(faite.dansLeLot, true);
  assert.equal(avancementEnClair({...base, etat: "lot_a_venir"}).ton, "pause");
  assert.equal(avancementEnClair({...base, etat: "attente_tests"}).ton, "pause");
  assert.equal(avancementEnClair(base).dansLeLot, false);
});
