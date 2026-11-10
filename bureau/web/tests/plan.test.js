import {test} from "node:test";
import assert from "node:assert/strict";
import {creerPlan} from "../logique/plan.js";
import {COLS} from "./donnees.js";

const NOMS = ["Métier", "Dev", "QA", "Intégration", "Facturation", "Support"];
const services = (n) => NOMS.slice(0, n).map((nom, i) => ({id: "s" + i, nom}));
const dist = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
const dans = (p, r, marge = 0) =>
  Math.abs(p.x - r.x) <= r.largeur / 2 - marge + 1e-9 && Math.abs(p.z - r.z) <= r.profondeur / 2 - marge + 1e-9;
const chevauche = (a, b) =>
  Math.abs(a.x - b.x) < (a.largeur + b.largeur) / 2 - 1e-9 && Math.abs(a.z - b.z) < (a.profondeur + b.profondeur) / 2 - 1e-9;
const dansBatiment = (p, plan) => [...plan.pieces, plan.openspace].some((r) => dans(p, r));

function distinctes(pts, ecart = 0.6) {
  for (let i = 0; i < pts.length; i++)
    for (let j = i + 1; j < pts.length; j++)
      assert.ok(dist(pts[i], pts[j]) >= ecart, `places ${i} et ${j} trop proches`);
}

test("pièces sans chevauchement, 1 à 6 services", () => {
  for (let n = 1; n <= 6; n++) {
    const p = creerPlan(services(n), COLS);
    const types = p.pieces.map((r) => r.type);
    assert.equal(types.filter((t) => t === "service").length, n);
    assert.ok(types.includes("direction") && types.includes("cafe"));
    const toutes = [...p.pieces, p.openspace];
    for (let i = 0; i < toutes.length; i++)
      for (let j = i + 1; j < toutes.length; j++)
        assert.ok(!chevauche(toutes[i], toutes[j]), `n=${n} : ${toutes[i].id} chevauche ${toutes[j].id}`);
    assert.ok(dans(p.kanban, p.openspace, 0.5), "le Kanban est dans l'open space");
  }
});

test("9 agents dans un service : 9 places distinctes", () => {
  const p = creerPlan([{id: "dev", nom: "Dev"}], COLS);
  distinctes(Array.from({length: 9}, (_, i) => p.poste("dev", i)));
});

test("22 places distinctes dans un service, 4 assises puis debout", () => {
  const p = creerPlan([{id: "dev", nom: "Dev"}], COLS);
  const pts = Array.from({length: 22}, (_, i) => p.poste("dev", i));
  distinctes(pts);
  assert.deepEqual(pts.map((q) => q.assis), pts.map((_, i) => i < 4));
});

test("20 places de café distinctes", () => {
  const p = creerPlan(services(3), COLS);
  distinctes(Array.from({length: 20}, (_, i) => p.cafe(i)));
});

test("places de café au-delà de la pièce : toujours distinctes et dans le bâtiment", () => {
  const p = creerPlan(services(6), COLS);
  const pts = Array.from({length: 40}, (_, i) => p.cafe(i));
  distinctes(pts);
  for (const q of pts) assert.ok(dansBatiment(q, p));
});

test("les places sont dans leur pièce", () => {
  for (let n = 1; n <= 6; n++) {
    const p = creerPlan(services(n), COLS);
    const piece = (id) => p.pieces.find((r) => r.id === id);
    for (const s of services(n))
      for (let i = 0; i < 22; i++) assert.ok(dans(p.poste(s.id, i), piece(s.id), 0.2), `${s.id} place ${i}`);
    for (let i = 0; i < 20; i++) assert.ok(dans(p.cafe(i), piece("cafe"), 0.2), `café ${i}`);
    assert.ok(dans(p.directeur, piece("direction"), 0.2));
    assert.ok(dans(p.chef, p.openspace, 0.3));
    assert.ok(dans(p.kanban.devant, p.openspace, 0.3));
    for (let i = 0; i < 6; i++) assert.ok(dans(p.kanban.attente(i), p.openspace, 0.3));
  }
});

test("chemin : part de a, arrive à b, aucun point hors du bâtiment", () => {
  for (let n = 1; n <= 6; n++) {
    const p = creerPlan(services(n), COLS);
    const lieux = [p.chef, p.kanban.devant, p.kanban.attente(3), p.cafe(0), p.cafe(25), p.directeur,
                   ...services(n).flatMap((s) => [p.poste(s.id, 0), p.poste(s.id, 7)])];
    for (const a of lieux)
      for (const b of lieux) {
        const c = p.chemin(a, b);
        assert.deepEqual(c[0], {x: a.x, z: a.z});
        assert.deepEqual(c.at(-1), {x: b.x, z: b.z});
        for (let k = 0; k < c.length; k++) {
          assert.ok(dansBatiment(c[k], p), `point hors du bâtiment ${JSON.stringify(c[k])}`);
          // aucun segment ne passe au milieu d'un mur : milieu et quarts aussi dans le bâtiment
          if (k > 0) for (const f of [0.25, 0.5, 0.75]) {
            const m = {x: c[k - 1].x + f * (c[k].x - c[k - 1].x), z: c[k - 1].z + f * (c[k].z - c[k - 1].z)};
            assert.ok(dansBatiment(m, p), `segment hors du bâtiment ${JSON.stringify(m)}`);
          }
        }
      }
  }
});

test("chemin : ne traverse pas le tableau", () => {
  const p = creerPlan(services(6), COLS);
  const k = p.kanban;
  const s0 = p.poste("s0", 0), s5 = p.poste("s5", 0);
  for (const [a, b] of [[s0, p.cafe(0)], [p.directeur, s0], [s5, p.poste("s1", 2)], [p.chef, p.kanban.attente(4)]]) {
    const c = p.chemin(a, b);
    for (let i = 1; i < c.length; i++)
      for (let f = 0; f <= 1; f += 0.02) {
        const m = {x: c[i - 1].x + f * (c[i].x - c[i - 1].x), z: c[i - 1].z + f * (c[i].z - c[i - 1].z)};
        assert.ok(!(Math.abs(m.x - k.x) < k.largeur / 2 && Math.abs(m.z - k.z) < 0.15), "traverse le tableau");
      }
  }
});

test("post-its : une case par colonne et par rang, rang plafonné", () => {
  const p = creerPlan(services(2), COLS);
  const a = p.postit(0, 0), b = p.postit(1, 0), c = p.postit(0, 1);
  assert.ok(b.u > a.u && c.v > a.v);
  assert.deepEqual(p.postit(0, 50), p.postit(0, p.kanban.lignes - 1));
  for (let i = 0; i < COLS.length; i++) {
    const q = p.postit(i, 0);
    assert.ok(q.u > 0 && q.u < p.kanban.largeur);
  }
});
