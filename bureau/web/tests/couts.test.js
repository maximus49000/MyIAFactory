import {test} from "node:test";
import assert from "node:assert/strict";
import {libelleCout} from "../ui/couts.js";
import {tachesFaites, serviceDeTache} from "../ui/directeur.js";

test("le coût d'une tâche : en cours il évolue, finie il vient de l'historique", () => {
  assert.match(libelleCout({id: "t1", travail: {cout: {total: 0.1234, sans_prix: 0}}}, null), /0,12 € jusqu'ici .*évolue/);
  assert.equal(libelleCout({id: "t2", colonne: "fait"}, {t2: {total: 1.5, sans_prix: 0}}), "≈ 1,50 €");
  assert.equal(libelleCout({id: "t3", colonne: "fait"}, {}), "aucune consommation notée");
  assert.equal(libelleCout({id: "t3", colonne: "fait"}, null), "indisponible");
});

test("l'historique d'un agent : ses tâches faites, les plus récentes d'abord, avec leur service", () => {
  const e = {services: [{id: "dev", nom: "Développement"}], taches: [
    {id: "a", agent: "dev", colonne: "fait", maj: "2026-11-12T10:00:00"},
    {id: "b", agent: "dev", colonne: "fait", maj: "2026-11-13T10:00:00"},
    {id: "c", agent: "dev", colonne: "en-cours"}, {id: "d", agent: "qa", colonne: "fait"}]};
  assert.deepEqual(tachesFaites(e, "dev").map((t) => t.id), ["b", "a"]);
  assert.equal(serviceDeTache(e, {}, {service: "dev"}), "Développement");
});
