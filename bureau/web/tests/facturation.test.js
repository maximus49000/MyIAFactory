import test from "node:test";
import assert from "node:assert/strict";
import {lignesTaches, lignesModeles, serviceFacture, coutEnClair, coutDeTache, MARQUE_LOT, lignesDiscussions, totalProjet} from "../ui/facturation.js";

const f = {
  services: {
    prod: {total: 3, taches: {t1: {total: 1, etapes: {code: 0.6, "": 0.4}}, "": {total: 2, etapes: {"": 2}}},
            modeles: {a: 1, b: 2}, usages: []},
  },
  direction: {total: 5, taches: {}, modeles: {}, usages: []},
};

test("serviceFacture : service, direction, absent", () => {
  assert.equal(serviceFacture(f, "prod").total, 3);
  assert.equal(serviceFacture(f, "autre"), null);
  assert.equal(serviceFacture(null, "prod"), null);
});

test("lignesTaches : tri décroissant, « hors tâche » et « sans étape »", () => {
  const l = lignesTaches(f.services.prod, [{id: "t1", titre: "<img onerror=x>"}]);
  assert.deepEqual(l.map((x) => x.titre), ["Hors tâche", "<img onerror=x>"]);
  assert.deepEqual(l[1].etapes, [{nom: "code", total: 0.6}, {nom: "Sans étape", total: 0.4}]);
});

test("lignesModeles : tri décroissant", () => {
  assert.deepEqual(lignesModeles(f.services.prod), [{nom: "b", total: 2}, {nom: "a", total: 1}]);
});

// --- Relecture finale : prix inconnu visible à chaque niveau, discussions, total du projet.

const g = {
  total: 9, sans_prix: [{modele: "mystere", tokens: 1500, usages: 2}],
  services: {
    prod: {
      total: 3, sans_prix: [{modele: "mystere", tokens: 1500, usages: 2}],
      taches: {t1: {total: 3, sans_prix: 1, etapes: {code: 3}}, t2: {total: 0, sans_prix: 1, etapes: {}}},
      modeles: {a: 3},
      usages: [
        {id: "u1", tache: "t1", agent: "p1", modele: "a", etape: "code", t: "2026-11-09T10:00:00",
         tokens: {entree: 1000, sortie: 200, cache_lecture: 300, cache_ecriture: 0}, cout: 3, prix_du: "2026-11-01", ancien: true},
        {id: "u2", tache: "t1", agent: "p1", modele: "mystere", etape: null, t: "2026-11-09T12:00:00",
         tokens: {entree: 1000, sortie: 0, cache_lecture: 0, cache_ecriture: 0}, cout: null, prix_du: null, ancien: false},
        {id: "u3", tache: null, agent: "parti", modele: "mystere", etape: "x", t: "2026-11-08T12:00:00",
         tokens: {entree: 500, sortie: 0, cache_lecture: 0, cache_ecriture: 0}, cout: null, prix_du: null, ancien: false},
      ],
    },
  },
  direction: {total: 6, sans_prix: [], taches: {}, modeles: {}, usages: []},
};

test("coutEnClair : un coût incomplet ne passe jamais pour complet", () => {
  assert.equal(coutEnClair({total: 3, sans_prix: 0}), "≈ 3,00 €");
  assert.equal(coutEnClair({total: 3}), "≈ 3,00 €");
  assert.equal(coutEnClair({total: 3, sans_prix: 1}), "≈ 3,00 € + prix inconnu");
  assert.equal(coutEnClair({total: 0, sans_prix: 2}), "prix inconnu");
  assert.equal(coutEnClair({total: 3, sans_prix: [{modele: "m", tokens: 1, usages: 1}]}), "≈ 3,00 € + prix inconnu");
  assert.equal(coutEnClair({total: 3, sans_prix: []}), "≈ 3,00 €");
});

test("lignesTaches : porte la marque « prix inconnu » de chaque tâche", () => {
  const l = lignesTaches(g.services.prod, []);
  assert.deepEqual(l.map((x) => [x.id, x.sansPrix]), [["t1", 1], ["t2", 1]]);
  assert.equal(lignesTaches(f.services.prod, [])[0].sansPrix, 0);
});

test("lignesDiscussions : la plus récente d'abord, prénom, titre, tokens, prix inconnu", () => {
  const etat = {agents: [{id: "p1", prenom: "<b>Zoé</b>"}], taches: [{id: "t1", titre: "Export"}]};
  const l = lignesDiscussions(g.services.prod, etat);
  assert.deepEqual(l.map((x) => x.id), ["u2", "u1", "u3"]);
  assert.deepEqual(l[1], {id: "u1", t: "2026-11-09T10:00:00", agent: "<b>Zoé</b>", tache: "Export", modele: "a",
                          etape: "code", tokens: 1500, cout: 3, prixDu: "2026-11-01", ancien: true});
  assert.equal(l[0].cout, null);
  assert.equal(l[0].etape, "Sans étape");
  assert.deepEqual([l[2].agent, l[2].tache], ["parti", "Hors tâche"]);
  assert.deepEqual(lignesDiscussions(null, etat), []);
});

test("totalProjet : le total général et la part de la direction", () => {
  assert.deepEqual(totalProjet(g), {total: 9, direction: 6, orchestration: 0, sansPrix: true});
  assert.equal(totalProjet({...g, orchestration: {total: 0.04}}).orchestration, 0.04);
  assert.deepEqual(totalProjet({total: 2, direction: {total: 0, sans_prix: []}, sans_prix: []}),
                   {total: 2, direction: 0, orchestration: 0, sansPrix: false});
});

test("coutDeTache : « estimé (part d'un lot) » seulement pour une part répartie", () => {
  const l = lignesTaches({taches: {t1: {total: 1.2, etapes: {}, reparti: true}, t2: {total: 2, etapes: {}}}}, []);
  const par = Object.fromEntries(l.map((x) => [x.id, x]));
  assert.equal(coutDeTache(par.t1), `≈ 1,20 € · ${MARQUE_LOT}`);
  assert.equal(coutDeTache(par.t2), "≈ 2,00 €");
  assert.equal(coutDeTache({total: 0, sansPrix: 1, reparti: true}), `prix inconnu · ${MARQUE_LOT}`);
  assert.equal(MARQUE_LOT, "estimé (part d'un lot)");
});

test("lignesDiscussions : la répartition d'un lot est portée", () => {
  const u = {id: "u1", tache: "t1", agent: "p1", modele: "a", etape: "code", t: "2026-11-09T10:00:00",
             tokens: {entree: 10}, cout: 1, reparti: "temps"};
  const [x, y] = lignesDiscussions({usages: [u, {...u, id: "u2", reparti: undefined}]}, {});
  assert.equal(x.reparti, "temps");
  assert.equal("reparti" in y, false);
});
