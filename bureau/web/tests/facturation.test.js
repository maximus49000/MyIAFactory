import test from "node:test";
import assert from "node:assert/strict";
import {lignesTaches, lignesModeles, serviceFacture, coutEnClair, coutDeTache, MARQUE_LOT, lignesDiscussions, totalProjet,
        demandeParallelisme, resumeParallelisme, resumeRecrutement, demandeRecrutementManuel, apercuAuto,
        limiteAuto, propositionsDuLieu, demandeRecrutementAuto, demandeDepot, PLAFOND_PAR_DEFAUT, REGLE_PLAFOND,
        ligneApercu} from "../ui/facturation.js";

const REC = (extra = {}) => ({recrutement: {
  roles: [{role: "dev", nom: "Développement", modele: "Sonnet", agents: 1, cloud: 0, travail: 4}],
  places: {cloud: 2, locaux: 1},
  propositions: [{role: "dev", modele: "Sonnet", lieu: "cloud", raison: "a"}, {role: "dev", modele: "Sonnet", lieu: "cloud", raison: "b"},
                 {role: "dev", modele: "Sonnet", lieu: "local", raison: "c"}],
  notes: [], depot: {git: true, github: true, url: "https://github.com/moi/jeu", creable: false}, cloud_impossible: null,
  ...extra}});

test("recrutement : plafond Opus par défaut, la règle en une ligne, l'aperçu dit plafond et modèle des tâches", () => {
  assert.equal(PLAFOND_PAR_DEFAUT, "Opus");
  assert.match(REGLE_PLAFOND, /plafond/);
  assert.ok(!REGLE_PLAFOND.includes("\n"));
  assert.equal(ligneApercu({role: "dev", modele: "Opus", modele_necessaire: "Sonnet", lieu: "cloud", raison: "r"}),
               "dev · plafond Opus · tâches en Sonnet · cloud — r");
  assert.equal(ligneApercu({role: "dev", modele: "Opus", lieu: "local", raison: "r"}), "dev · plafond Opus · local — r");
});

test("resumeRecrutement : sans dépôt GitHub, le cloud est impossible et le dépôt se crée", () => {
  assert.equal(resumeRecrutement({}), null);
  const ok = resumeRecrutement(REC());
  assert.deepEqual([ok.github, ok.cloudPossible, ok.creable, ok.url], [true, true, false, "https://github.com/moi/jeu"]);
  const sans = resumeRecrutement(REC({depot: {git: false, github: false, url: null, creable: true},
                                      cloud_impossible: "Le projet n'est pas un dépôt git."}));
  assert.deepEqual([sans.cloudPossible, sans.creable, sans.raisonCloud], [false, true, "Le projet n'est pas un dépôt git."]);
  const plein = resumeRecrutement(REC({places: {cloud: 0, locaux: 0}}));
  assert.match(plein.raisonCloud, /Agents cloud en même temps/);
});

test("demandeRecrutementManuel : rôle du projet, modèle, Fable avec l'accord, cloud seulement s'il est possible", () => {
  const r = resumeRecrutement(REC());
  assert.deepEqual(demandeRecrutementManuel(r, {role: "dev", modele: "Opus", lieu: "cloud"}),
                   {type: "recruter", mode: "manuel", agents: [{role: "dev", modele: "Opus", lieu: "cloud"}]});
  assert.ok(demandeRecrutementManuel(r, {role: "x", modele: "Opus", lieu: "local"}).erreur);
  assert.match(demandeRecrutementManuel(r, {role: "dev", modele: "Fable", lieu: "local"}).erreur, /accord/);
  assert.deepEqual(demandeRecrutementManuel(r, {role: "dev", modele: "Fable", lieu: "local", fable: true}).agents,
                   [{role: "dev", modele: "Fable", lieu: "local", fable: true}]);
  const sans = resumeRecrutement(REC({depot: {git: false, github: false, url: null, creable: true}, cloud_impossible: "Pas de dépôt."}));
  assert.equal(demandeRecrutementManuel(sans, {role: "dev", modele: "Opus", lieu: "cloud"}).erreur, "Pas de dépôt.");
  assert.equal(demandeRecrutementManuel(sans, {role: "dev", modele: "Opus", lieu: "local"}).type, "recruter");
});

test("apercuAuto : les N premières propositions, puis la demande confirmée ; le dépôt sur clic", () => {
  const r = resumeRecrutement(REC());
  assert.deepEqual(apercuAuto(r, "2").map((p) => p.raison), ["a", "b"]);
  for (const n of [0, "x", 1.5]) assert.deepEqual(apercuAuto(r, n), [], String(n));
  assert.equal(apercuAuto(r, 4).length, 3);       // au-delà du possible : toutes celles possibles
  assert.deepEqual(demandeRecrutementAuto(apercuAuto(r, 3)), {type: "recruter", mode: "auto", lieu: "mieux", agents: [
    {role: "dev", modele: "Sonnet", lieu: "cloud"}, {role: "dev", modele: "Sonnet", lieu: "cloud"},
    {role: "dev", modele: "Sonnet", lieu: "local"}]});
  assert.equal(demandeRecrutementAuto([]), null);
  assert.deepEqual(demandeDepot(), {type: "depot_git", confirme: true});
});

test("demandeParallelisme : des entiers dans les bornes, sinon rien ne part", () => {
  assert.deepEqual(demandeParallelisme("3", " 1 "), {type: "parallelisme", agents_locaux_max: 3, agents_cloud_max: 1});
  assert.deepEqual(demandeParallelisme(16, 0), {type: "parallelisme", agents_locaux_max: 16, agents_cloud_max: 0});
  for (const [l, c] of [[0, 0], [17, 0], [2, -1], [2, 17], ["2.5", 0], ["", 0], [2, "x"], [true, 0]]) {
    assert.equal(demandeParallelisme(l, c), null, `${l} ${c}`);
  }
});

test("resumeParallelisme : réglages, agents recrutés par lieu, attente d'une validation", () => {
  const etat = {agents_locaux_max: 3, agents_cloud_max: 2, agents: [
    {id: "chef", chef: true, lieu: "local"}, {id: "dev1", lieu: "local"}, {id: "qa1", lieu: "local"}],
    attente_validation: {texte: "1 place libre : en attente de votre validation « DA »"}};
  const r = resumeParallelisme(etat);
  assert.deepEqual([r.locaux, r.cloud, r.recrutes], [3, 2, {locaux: 2, cloud: 0}]);
  assert.match(r.notes[0], /Aucun agent cloud recruté/);
  assert.equal(r.attente, "1 place libre : en attente de votre validation « DA »");
  const defaut = resumeParallelisme({agents: []});
  assert.deepEqual([defaut.locaux, defaut.cloud, defaut.attente], [2, 0, null]);
  assert.doesNotMatch(defaut.notes.join(" "), /Aucun agent cloud/);
});

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

test("lieu de la répartition : Cloud et Local limités à leurs places, avec ce qui est possible et la raison", () => {
  const cloud = [{role: "dev", modele: "Opus", lieu: "cloud", raison: "x"}, {role: "dev", modele: "Haiku", lieu: "cloud", raison: "y"}];
  const r = resumeRecrutement(REC({propositions_par_lieu: {mieux: REC().recrutement.propositions, cloud, local: [cloud[0]]},
                                   notes_par_lieu: {mieux: [], cloud: ["Plus de place cloud libre."], local: []}}));
  assert.deepEqual(apercuAuto(r, 3, "cloud").map((p) => p.raison), ["x", "y"]);
  assert.equal(propositionsDuLieu(r, "local").length, 1);
  assert.match(limiteAuto(r, 3, "cloud"), /Seulement 2 agents cloud possibles \(3 demandés\)\. Plus de place cloud libre/);
  assert.equal(limiteAuto(r, 2, "cloud"), "");
  assert.deepEqual(demandeRecrutementAuto(apercuAuto(r, 2, "cloud"), "cloud"),
                   {type: "recruter", mode: "auto", lieu: "cloud", agents: [
                     {role: "dev", modele: "Opus", lieu: "cloud"}, {role: "dev", modele: "Haiku", lieu: "cloud"}]});
  // Sans GitHub : aucune proposition cloud, la raison est dite.
  const sans = resumeRecrutement(REC({depot: {git: false, github: false, url: null, creable: true},
                                      cloud_impossible: "Le projet n'est pas un dépôt git.",
                                      propositions_par_lieu: {mieux: [], cloud: [], local: []}}));
  assert.deepEqual(apercuAuto(sans, 3, "cloud"), []);
  assert.match(limiteAuto(sans, 3, "cloud"), /Aucun agent cloud possible : Le projet n'est pas un dépôt git/);
  // Un relevé d'avant (sans propositions_par_lieu) : « au mieux » garde les propositions, cloud/local rien.
  assert.equal(apercuAuto(resumeRecrutement(REC()), 2).length, 2);
  assert.deepEqual(apercuAuto(resumeRecrutement(REC()), 2, "cloud"), []);
});
