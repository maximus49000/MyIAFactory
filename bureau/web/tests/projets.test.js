import test from "node:test";
import assert from "node:assert/strict";
import {avecProjet, projetInitial, livrables} from "../ui/projets.js";

test("avecProjet : url sans paramètre, avec paramètre, id avec espace", () => {
  assert.equal(avecProjet("/api/etat", "a"), "/api/etat?projet=a");
  assert.equal(avecProjet("/api/kpi?periode=7j", "b"), "/api/kpi?periode=7j&projet=b");
  assert.equal(avecProjet("/api/etat?projet=a", "b"), "/api/etat?projet=b");
  assert.equal(avecProjet("/api/kpi?projet=a&periode=7j", "b"), "/api/kpi?periode=7j&projet=b");
  assert.equal(avecProjet("/api/etat", "mon projet&x"), "/api/etat?projet=mon%20projet%26x");
  assert.equal(avecProjet("/api/etat", null), "/api/etat");
  assert.equal(avecProjet("/api/etat?projet=a", null), "/api/etat?projet=a");
});

test("projetInitial : le mémorisé s'il existe encore, sinon le premier", () => {
  const liste = [{id: "a"}, {id: "b"}];
  assert.equal(projetInitial(liste, "b"), "b");
  assert.equal(projetInitial(liste, "disparu"), "a");
  assert.equal(projetInitial(liste, null), "a");
  assert.equal(projetInitial([], "b"), null);
  assert.equal(projetInitial(null, "b"), null);
});

test("livrables : ordre, lien javascript: écarté, chemin", () => {
  const etat = {
    livrable: {libelle: "Projet", lien: "https://exemple.org/p", date: "2026-11-01"},
    fonctionnalites: [
      {id: "f1", nom: "F1", livrable: {libelle: "Maquette", chemin: "sortie/m.png", date: "2026-11-05"}},
      {id: "f2", livrable: {libelle: "Piège", lien: "javascript:alert(1)", date: "2026-11-09"}},
      {id: "f3", livrable: null},
      {id: "f4", livrable: {libelle: "Sans date", chemin: "x.zip", date: null}},
    ],
  };
  const l = livrables(etat, null);
  assert.deepEqual(l.map((x) => x.libelle), ["Maquette", "Projet", "Sans date"]);
  assert.equal(l[0].url, "/api/livrable?fonctionnalite=f1");
  assert.equal(l[1].url, "https://exemple.org/p");
  assert.equal(livrables(etat, "p 2")[0].url, "/api/livrable?fonctionnalite=f1&projet=p%202");
  assert.deepEqual(livrables({}, null), []);
});

test("livrables du projet par chemin", () => {
  const l = livrables({livrable: {libelle: "Zip", chemin: "a.zip", date: "2026-11-01"}}, "p");
  assert.equal(l[0].url, "/api/livrable?projet=p");
});
