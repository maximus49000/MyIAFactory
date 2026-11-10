import test from "node:test";
import assert from "node:assert/strict";
import {filtrerElements, compteurs, utilisationsKit, estCouleur, cadrage, demandeRetourElement, pageDe,
        sansAccents} from "../ui/catalogue.js";

const cat = {
  groupes: [{id: "g1", nom: "Nord"}, {id: "g2", nom: "Sud"}],
  elements: [
    {id: "e1", nom: "Église Saint-Pierre", groupe: "g1", etat: "valide", passes: [1, 2], kit: ["k1"],
     a_reevaluer: ["l2"], note: "Clocher carré"},
    {id: "e2", nom: "Moulin", groupe: "g1", etat: "a_revoir", passes: [2], kit: ["k1", "k2"],
     doute: {raison: "photo floue"}},
    {id: "e3", nom: "Pont", groupe: "g2", etat: "a_revoir", passes: [1], note: "Arches en ÉGLISE"},
    {id: "x-église", nom: "Halle", groupe: "g2"},
  ],
  kit: [{id: "k1", nom: "Fenêtre"}, {id: "k2", nom: "Porte"}, {id: "k3", nom: "Toit"}],
};
const ids = (l) => l.map((e) => e.id);

test("filtrerElements : chaque filtre", () => {
  assert.deepEqual(ids(filtrerElements(cat, {})), ["e1", "e2", "e3", "x-église"]);
  assert.deepEqual(ids(filtrerElements(cat, {groupe: "g2"})), ["e3", "x-église"]);
  assert.deepEqual(ids(filtrerElements(cat, {passe: 1})), ["e1", "e3"]);
  assert.deepEqual(ids(filtrerElements(cat, {aReevaluer: true})), ["e1"]);
  assert.deepEqual(ids(filtrerElements(cat, {doutes: true})), ["e2"]);
  assert.deepEqual(ids(filtrerElements(cat, {etat: "a_revoir"})), ["e2", "e3"]);
  assert.deepEqual(ids(filtrerElements(cat, {groupe: "g1", etat: "a_revoir", doutes: true})), ["e2"]);
  assert.deepEqual(ids(filtrerElements(cat, {recherche: "   "})), ["e1", "e2", "e3", "x-église"]);
  assert.deepEqual(filtrerElements({}, {}), []);
  assert.deepEqual(filtrerElements(null, {recherche: "a"}), []);
});

test("filtrerElements : recherche sans casse ni accents sur nom, id et note", () => {
  assert.equal(sansAccents("Église À"), "eglise a");
  assert.deepEqual(ids(filtrerElements(cat, {recherche: "eglise"})), ["e1", "e3", "x-église"]);
  assert.deepEqual(ids(filtrerElements(cat, {recherche: "CLOCHER"})), ["e1"]);
  assert.deepEqual(ids(filtrerElements(cat, {recherche: "e2"})), ["e2"]);
  assert.deepEqual(ids(filtrerElements(cat, {recherche: "introuvable"})), []);
});

test("filtrerElements : 5 000 éléments en moins de 50 ms", () => {
  const elements = Array.from({length: 5000}, (_, i) => ({
    id: "el-" + i, nom: (i % 7 ? "Maison " : "Église ") + i, groupe: "g" + (i % 4),
    etat: i % 3 ? "valide" : "a_revoir", passes: [i % 5], note: "Une note un peu longue numéro " + i,
    a_reevaluer: i % 11 ? [] : ["l1"],
  }));
  const grand = {elements};
  filtrerElements(grand, {recherche: "eglise"});   // premier passage (mise en cache des textes)
  const debut = performance.now();
  const r = filtrerElements(grand, {groupe: "g1", recherche: "eglise", etat: "valide"});
  const duree = performance.now() - debut;
  assert.ok(r.length > 0 && r.every((e) => e.groupe === "g1" && e.etat === "valide" && e.nom.startsWith("Église")));
  assert.ok(duree < 50, `trop lent : ${duree} ms`);
  const debut2 = performance.now();
  filtrerElements({elements: elements.map((e) => ({...e}))}, {recherche: "maison 4999"});   // sans cache
  assert.ok(performance.now() - debut2 < 50);
});

test("compteurs : total et par état, pour un groupe ou tous", () => {
  assert.deepEqual(compteurs(cat, null), {total: 4, parEtat: {valide: 1, a_revoir: 2, "": 1}});
  assert.deepEqual(compteurs(cat, "g2"), {total: 2, parEtat: {a_revoir: 1, "": 1}});
  assert.deepEqual(compteurs(cat, "inconnu"), {total: 0, parEtat: {}});
  assert.deepEqual(compteurs({}, null), {total: 0, parEtat: {}});
});

test("utilisationsKit : chaque élément commun et ceux qui l'utilisent", () => {
  const u = utilisationsKit(cat);
  assert.ok(u instanceof Map);
  assert.deepEqual([...u.keys()], ["k1", "k2", "k3"]);
  assert.deepEqual(u.get("k1"), ["e1", "e2"]);
  assert.deepEqual(u.get("k2"), ["e2"]);
  assert.deepEqual(u.get("k3"), []);
  // Un id utilisé mais non déclaré apparaît aussi (après les déclarés).
  const u2 = utilisationsKit({kit: [{id: "a"}], elements: [{id: "x", kit: ["b", "a"]}]});
  assert.deepEqual([...u2.entries()], [["a", ["x"]], ["b", ["x"]]]);
  assert.equal(utilisationsKit({}).size, 0);
});

test("estCouleur", () => {
  for (const v of ["#abc", "#A1B2C3", "rgb(1, 2, 3)", "rgb(255,255,255)"]) assert.equal(estCouleur(v), true, v);
  for (const v of ["#abcd", "abc", "red", "rgb(1,2)", "rgb(1,2,3);background:url(x)", "url(#abc)", 12, null,
                   "#abc;", " #abc"]) assert.equal(estCouleur(v), false, String(v));
});

test("cadrage : points alignés, un seul point, traces comprises", () => {
  // Points alignés à l'horizontale : l'échelle vient de la largeur ; tout tient dans le cadre.
  const els = [{position: {x: 0, y: 5}}, {position: {x: 100, y: 5}}, {}];
  const c = cadrage(els, [], 200, 100);
  assert.ok(Number.isFinite(c.echelle) && c.echelle > 0);
  const ecran = (p) => [p.x * c.echelle + c.dx, c.dy - p.y * c.echelle];
  for (const p of [{x: 0, y: 5}, {x: 100, y: 5}]) {
    const [x, y] = ecran(p);
    assert.ok(x >= 0 && x <= 200 && y >= 0 && y <= 100, `${x},${y}`);
  }
  assert.ok(Math.abs(ecran({x: 0, y: 5})[1] - 50) < 1e-9);   // centré verticalement
  // Un seul point : au centre, échelle finie.
  const u = cadrage([{position: {x: 7, y: -3}}], [], 300, 200);
  assert.ok(Number.isFinite(u.echelle) && u.echelle > 0);
  assert.ok(Math.abs(7 * u.echelle + u.dx - 150) < 1e-9);
  assert.ok(Math.abs(u.dy - -3 * u.echelle - 100) < 1e-9);
  // Les traces élargissent le cadre ; le nord est en haut (y plus grand → plus haut à l'écran).
  const t = cadrage([{position: {x: 0, y: 0}}], [{points: [[0, 0], [10, 10]]}], 100, 100);
  assert.ok(10 * t.echelle + t.dx <= 100 && t.dy - 10 * t.echelle >= 0);
  assert.ok(t.dy - 10 * t.echelle < t.dy);
  // Rien à placer : une échelle neutre.
  assert.deepEqual(cadrage([], [], 100, 100), {echelle: 1, dx: 50, dy: 50});
});

test("demandeRetourElement : champs exacts", () => {
  assert.deepEqual(demandeRetourElement("f1", "e2", "Le toit est trop haut"),
    {type: "retour_element", fonctionnalite: "f1", element: "e2", texte: "Le toit est trop haut"});
});

test("pageDe : pages de 100, bornées", () => {
  const liste = Array.from({length: 250}, (_, i) => i);
  assert.deepEqual(pageDe(liste, 0).elements, liste.slice(0, 100));
  const p = pageDe(liste, 2);
  assert.deepEqual([p.page, p.pages, p.elements.length, p.elements[0]], [2, 3, 50, 200]);
  assert.equal(pageDe(liste, 9).page, 2);
  assert.equal(pageDe(liste, -3).page, 0);
  assert.deepEqual(pageDe(liste, 1, 10).elements, liste.slice(10, 20));
  assert.deepEqual(pageDe([], 0), {elements: [], page: 0, pages: 1, total: 0});
});
