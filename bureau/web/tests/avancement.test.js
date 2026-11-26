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

test("l'attente d'une exécution distante se dit en clair : pause, puis alerte si elle est trop longue", () => {
  const a = avancementEnClair({...base, etat: "attente_deportee",
                               etat_texte: "en attente de l'APK (GitHub, depuis 12 min), durée habituelle inconnue"});
  assert.equal(a.ton, "pause");
  assert.match(a.etatTexte, /en attente de l'APK \(GitHub, depuis 12 min\)/);
  assert.equal(avancementEnClair({...base, etat: "attente_longue", etat_texte: "attente anormalement longue (35 min)"}).ton,
               "alerte");
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

test("« termine » dans la ligne en cours ne fait pas croire la tâche finie : l'agent vérifie encore", () => {
  for (const mot of ["termine", "Terminé.", " fini ", "done"]) {
    assert.equal(avancementEnClair({...base, en_cours: mot}).enCours, "vérifications finales et compte rendu");
  }
  assert.equal(avancementEnClair({...base, en_cours: "terminer les tests"}).enCours, "terminer les tests");
  assert.equal(avancementEnClair({...base, en_cours: "  "}).enCours, null);
});

test("attenteTestsEnClair : la position dans la file des tests, sans position si elle est incohérente", async () => {
  const {attenteTestsEnClair} = await import("../ui/texte.js");
  assert.equal(attenteTestsEnClair({rang: 1, total: 2}), "En attente pour lancer les tests · position 1 sur 2");
  assert.equal(attenteTestsEnClair({rang: 3, total: 2}), "En attente pour lancer les tests");
  assert.equal(attenteTestsEnClair({}), "En attente pour lancer les tests");
  assert.equal(attenteTestsEnClair(null), null);
});

test("l'historique des appels : tableau sûr, jamais undefined, éléments mal formés écartés", () => {
  assert.deepEqual(avancementEnClair(base).historique, []);
  const a = avancementEnClair({...base, historique: [{t: "2026-11-26T10:00:00+01:00", texte: "lit a.py"}, {texte: 3}, null, {t: null, texte: "lance python"}]});
  assert.deepEqual(a.historique.map((h) => h.texte), ["lit a.py", "lance python"]);
});

// Faux DOM minimal : le texte d'un appel passe toujours par textContent.
class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.hidden = false; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n.textContent = t; return n; }};
Object.defineProperty(Noeud.prototype, "innerHTML", {get() { return ""; }, set() { throw new Error("innerHTML interdit"); }});

test("la fiche montre 20 appels, puis tous après « Voir tout », en texte simple", async () => {
  const {blocHistorique} = await import("../ui/detail.js");
  const h = Array.from({length: 30}, (_, i) => ({t: null, texte: i === 0 ? "<b>lit a.py</b>" : `lit f${i}.py`}));
  const bloc = blocHistorique(h);
  const lignes = () => bloc.tous((n) => n.className === "historique-appel");
  assert.equal(lignes().length, 20);
  assert.ok(bloc.textContent.includes("<b>lit a.py</b>"));           // du texte, jamais du HTML
  const bouton = bloc.tous((n) => n.tagName === "button")[0];
  assert.ok(bouton.textContent.includes("Voir tout"));
  bouton.auteurs.click[0]();
  assert.equal(lignes().length, 30);
  assert.equal(blocHistorique([]), null);
  assert.equal(blocHistorique(Array.from({length: 5}, () => ({t: null, texte: "x"}))).tous((n) => n.tagName === "button").length, 0);
});
