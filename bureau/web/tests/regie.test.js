import {test} from "node:test";
import assert from "node:assert/strict";
import {changements} from "../logique/diff.js";
import {creerPlan} from "../logique/plan.js";
import {Regie} from "../logique/regie.js";
import {E1, E2, COLS, SERVICES, copie, modifier, sansAgent, statut} from "./donnees.js";

const plan = creerPlan(SERVICES, COLS);
const pres = (a, p) => Math.hypot(a.x - p.x, a.z - p.z) < 1e-6;

function avancerJusqua(r, condition, secondes, chaquePas = () => {}) {
  for (let t = 0; t <= secondes; t += 0.1) {
    if (condition()) return;
    r.avancer(0.1);
    chaquePas();
  }
  assert.ok(condition(), `condition non atteinte en ${secondes} s`);
}

test("premier appliquer : au travail au poste, libre au café, chef à sa place", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  const dev1 = r.acteurs.get("dev1"), qa1 = r.acteurs.get("qa1"), chef = r.acteurs.get("chef");
  assert.ok(pres(dev1, plan.poste("dev", 0)));
  assert.equal(dev1.action, "assis");
  assert.equal(dev1.agent.id, "dev1");
  assert.ok(pres(qa1, plan.cafe(0)));
  assert.equal(qa1.action, "cafe");
  assert.ok(pres(chef, plan.chef));
  assert.equal(chef.action, "debout");
  assert.deepEqual(r.postits.get("t1"), {colonne: "encours", rang: 0});
  assert.deepEqual(r.postits.get("t2"), {colonne: "afaire", rang: 0});
  assert.equal(r.postits.has("t9"), false);
});

test("mission : l'agent marche, pose, et le post-it ne change qu'à la pose", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  assert.equal(r.postits.get("t1").colonne, "encours");
  r.avancer(0.1);
  assert.equal(r.acteurs.get("dev1").action, "marche");
  avancerJusqua(r, () => r.acteurs.get("dev1").action === "postit", 60);
  assert.equal(r.postits.get("t1").colonne, "encours");
  avancerJusqua(r, () => r.postits.get("t1").colonne === "revue", 5);
  avancerJusqua(r, () => r.acteurs.get("dev1").action === "cafe", 60);   // plus de tâche active -> café
});

test("deux missions : un seul agent devant le tableau à la fois", () => {
  const r = new Regie(plan);
  const e1 = statut(modifier(E1, "t2", {agent: "qa1"}), "qa1", "travail");
  r.appliquer(e1, []);
  const e2 = modifier(modifier(e1, "t1", {colonne: "revue"}), "t2", {colonne: "fait"});
  r.appliquer(e2, changements(e1, e2));
  let vus = 0;
  avancerJusqua(r, () => r.postits.get("t1").colonne === "revue" && r.postits.get("t2").colonne === "fait", 120, () => {
    const n = [...r.acteurs.values()].filter((a) => a.action === "postit").length;
    assert.ok(n <= 1, "deux agents posent en même temps");
    vus += n;
  });
  assert.ok(vus > 0);
});

test("rafale de 20 changements : 6 missions, 14 post-its déplacés tout de suite", () => {
  const avant = copie(E1);
  for (let i = 0; i < 20; i++)
    avant.taches.push({id: "r" + i, titre: "R" + i, colonne: "afaire", agent: "dev1", etape: "", maj: "", postit: true});
  const apres = copie(avant);
  for (const t of apres.taches) if (t.id.startsWith("r")) t.colonne = "fait";
  const r = new Regie(plan);
  r.appliquer(avant, []);
  r.appliquer(apres, changements(avant, apres));
  const ids = apres.taches.filter((t) => t.id.startsWith("r")).map((t) => t.id);
  assert.equal(ids.filter((id) => r.postits.get(id).colonne === "fait").length, 14);
  assert.equal(ids.filter((id) => r.postits.get(id).colonne === "afaire").length, 6);
  avancerJusqua(r, () => ids.every((id) => r.postits.get(id).colonne === "fait"), 120);
});

test("une nouvelle tâche n'apparaît qu'une fois posée par le chef", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  const e2 = copie(E1);
  e2.taches.push({id: "t3", titre: "Nouvelle", colonne: "afaire", agent: null, etape: "", maj: "", postit: true});
  r.appliquer(e2, changements(E1, e2));
  assert.equal(r.postits.has("t3"), false);
  avancerJusqua(r, () => r.acteurs.get("chef").action === "postit", 30);
  avancerJusqua(r, () => r.postits.has("t3"), 5);
  assert.deepEqual(r.postits.get("t3"), {colonne: "afaire", rang: 1});
  avancerJusqua(r, () => pres(r.acteurs.get("chef"), plan.chef), 30);
});

test("tâche disparue : son post-it et sa mission disparaissent", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  const e3 = copie(E2);
  e3.taches = e3.taches.filter((t) => t.id !== "t1");
  r.appliquer(e3, changements(E2, e3));
  assert.equal(r.postits.has("t1"), false);
  avancerJusqua(r, () => r.acteurs.get("dev1").action === "cafe", 60);
  assert.equal(r.postits.has("t1"), false);
});

test("deux changements successifs d'une tâche avant la pose : le post-it finit dans la dernière colonne", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  const e3 = modifier(E2, "t1", {colonne: "fait"});
  r.appliquer(e3, changements(E2, e3));
  avancerJusqua(r, () => r.postits.get("t1").colonne === "fait", 60);
  r.avancer(30);
  assert.equal(r.postits.get("t1").colonne, "fait");
});

test("agent retiré pendant sa mission : le chef la termine", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  r.avancer(1);
  const e3 = sansAgent(E2, "dev1");
  r.appliquer(e3, changements(E2, e3));
  assert.equal(r.acteurs.has("dev1"), false);
  avancerJusqua(r, () => r.acteurs.get("chef").action === "postit", 30);
  avancerJusqua(r, () => r.postits.get("t1").colonne === "revue", 5);
});

test("un agent libre à qui on confie une tâche quitte le café pour son poste", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  const e2 = statut(modifier(E1, "t2", {agent: "qa1"}), "qa1", "travail");
  r.appliquer(e2, changements(E1, e2));
  r.avancer(0.1);
  assert.equal(r.acteurs.get("qa1").action, "marche");
  avancerJusqua(r, () => r.acteurs.get("qa1").action === "assis", 60);
  assert.ok(pres(r.acteurs.get("qa1"), plan.poste("qa", 0)));
});

test("plus d'agents que de postes : places distinctes", () => {
  const e = copie(E1);
  for (let i = 0; i < 9; i++)
    e.agents.push({...e.agents[1], id: "c" + i, lieu: "cloud", statut: "travail"});
  const r = new Regie(plan);
  r.appliquer(e, []);
  const pts = [...r.acteurs.values()];
  for (let i = 0; i < pts.length; i++)
    for (let j = i + 1; j < pts.length; j++)
      assert.ok(Math.hypot(pts[i].x - pts[j].x, pts[i].z - pts[j].z) >= 0.6);
});

test("reinitialiser : tout est posé à sa place sans animation", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  r.reinitialiser(E2);
  assert.equal(r.postits.get("t1").colonne, "revue");
  assert.ok(pres(r.acteurs.get("dev1"), plan.cafe(0)) || r.acteurs.get("dev1").action === "cafe");
  assert.ok(pres(r.acteurs.get("qa1"), plan.poste("qa", 0)));
});

test("avancer(0) et avancer(3600) ne plantent pas et laissent tout le monde à une position finie", () => {
  const r = new Regie(plan);
  r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  r.avancer(0);
  r.avancer(3600);
  for (const a of r.acteurs.values()) assert.ok(Number.isFinite(a.x) && Number.isFinite(a.z) && Number.isFinite(a.cap));
  assert.equal(r.postits.get("t1").colonne, "revue");
});

test("un agent qui change de service prend une place libre de son nouveau service", () => {
  const r = new Regie(plan);
  const e1 = statut(copie(E1), "qa1", "travail");   // dev1 au poste dev 0, qa1 au poste qa 0
  r.appliquer(e1, []);
  const e2 = copie(e1);
  e2.agents.find((a) => a.id === "dev1").service = "qa";
  r.appliquer(e2, changements(e1, e2));
  avancerJusqua(r, () => r.acteurs.get("dev1").action !== "marche" && pres(r.acteurs.get("dev1"), r._destination(r.acteurs.get("dev1"))), 30);
  const dev1 = r.acteurs.get("dev1"), qa1 = r.acteurs.get("qa1");
  assert.ok(pres(qa1, plan.poste("qa", 0)));
  assert.ok(pres(dev1, plan.poste("qa", 1)), "dev1 doit être au poste qa 1, pas sur qa1 ni dans le bureau dev");
});

test("agent polyvalent change de pièce avec sa tâche, libre il va au café", () => {
  const r = new Regie(plan);
  const base = copie(E1);
  const dev1 = base.agents.find((a) => a.id === "dev1");
  Object.assign(dev1, {polyvalent: true, modele: "?", service: null, taches: ["t1"]});
  base.taches.find((t) => t.id === "t1").service = "dev";     // le service ne vient que de la tâche (relevé sans service d'agent)
  r.appliquer(base, []);
  assert.ok(pres(r.acteurs.get("dev1"), plan.poste("dev", 0)), "assis dans la pièce du service de sa tâche");
  // sa tâche suivante est du service qa
  const e2 = copie(base);
  e2.taches.find((t) => t.id === "t1").service = "qa";
  r.appliquer(e2, changements(base, e2));
  avancerJusqua(r, () => pres(r.acteurs.get("dev1"), r._destination(r.acteurs.get("dev1"))) && r.acteurs.get("dev1").action !== "marche", 30);
  assert.ok(pres(r.acteurs.get("dev1"), plan.poste("qa", 0)), "dans la pièce qa avec sa nouvelle tâche");
  // plus de tâche : au café
  const e3 = statut(copie(e2), "dev1", "libre");
  e3.agents.find((a) => a.id === "dev1").taches = [];
  r.appliquer(e3, changements(e2, e3));
  avancerJusqua(r, () => r.acteurs.get("dev1").action === "cafe", 30);
});
