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

import {prefixesDeRepetition, titreAffiche} from "../ui/repetitions.js";

test("les tâches refaites au même titre : Retour 1, Retour 2 (renvoi du Directeur), Reprise sinon", () => {
  const titre = "Conception des personnages et cartes : 2e passe graphique Tripo";
  const e = {taches: [
    {id: "t30", titre, journal: [{texte: "L'agent n'a pas rendu de rapport"}]},
    {id: "t43", titre, journal: [{texte: "Remarque du Directeur : points à revoir : …"}]},
    {id: "t46", titre, journal: [{texte: "Remarque du Directeur : points à revoir : …"}]},
    {id: "t50", titre, journal: [{texte: "Reprise après une panne"}]},
    {id: "t9", titre: "Unique"}]};
  const p = prefixesDeRepetition(e);
  assert.equal(p.get("t30"), undefined);
  assert.equal(titreAffiche(e, e.taches[1], p), "Retour 1 – " + titre);
  assert.equal(titreAffiche(e, e.taches[2], p), "Retour 2 – " + titre);
  assert.equal(p.get("t50"), "Reprise 1");
  assert.equal(titreAffiche(e, e.taches[4], p), "Unique");
});

import {tachesDuService} from "../ui/dossier.js";

test("les tâches d'un service : en cours puis réalisées, d'après ses agents ou le service de la tâche", () => {
  const e = {agents: [{id: "dev", service: "developpement"}, {id: "chef", chef: true, service: "developpement"}],
    taches: [{id: "orchestration", agent: "chef", active: true, colonne: "cadrage"},
      {id: "t1", agent: "dev", active: true, colonne: "dev", maj: "2026-11-13T11:00"},
      {id: "t2", agent: "dev", colonne: "fait", maj: "2026-11-12T10:00"},
      {id: "t3", agent: "dev", colonne: "fait", maj: "2026-11-13T09:00"},
      {id: "t4", agent: null, service: "developpement", colonne: "fait", maj: "2026-11-11T09:00"},
      {id: "t5", agent: "qa", colonne: "fait"}]};
  const {enCours, faites} = tachesDuService(e, "developpement");
  assert.deepEqual(enCours.map((t) => t.id), ["t1"]);
  assert.deepEqual(faites.map((t) => t.id), ["t3", "t2", "t4"]);
});

import {minutesDeTache, libelleDuree, totalDesTaches, libelleTotal} from "../ui/couts.js";

test("le temps d'une tâche : de son départ à sa fin ; en cours, jusqu'ici", () => {
  const maintenant = new Date("2026-11-13T12:00:00+01:00");
  const finie = {id: "a", colonne: "fait", debut: "2026-11-13T10:00:00+01:00", fin: "2026-11-13T11:05:00+01:00"};
  assert.equal(minutesDeTache(finie, maintenant), 65);
  assert.equal(libelleDuree(finie, maintenant), "1 h 05");
  const enCours = {id: "b", colonne: "dev", travail: {depuis: "2026-11-13T11:48:00+01:00"}};
  assert.equal(libelleDuree(enCours, maintenant), "12 min jusqu'ici");
  assert.equal(libelleDuree({id: "c", colonne: "fait"}, maintenant), null);
  const tot = totalDesTaches([finie, enCours, {id: "c", colonne: "fait"}], {a: {total: 1, sans_prix: 0}, c: {total: 0.5, sans_prix: 0}}, maintenant);
  assert.deepEqual(tot, {euros: 1.5, sans_prix: 0, minutes: 77, inconnues: 1});
  assert.equal(libelleTotal(tot), "Total : ≈ 1,50 € · 1 h 17 (dont 1 sans durée connue)");
});
