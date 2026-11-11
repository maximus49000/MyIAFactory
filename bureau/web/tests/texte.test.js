import test from "node:test";
import assert from "node:assert/strict";
import {COLS} from "./donnees.js";
import {tronquer, voyant, libelleCharge, dureeEnClair, ilYA, filtrer, imagesUrl, dateFr, imagesVisibles, listeDisponible, phrasesDirectionV1, notesValides, filtresEtat, filtreEtatEffectif, filtreDeListe, elementsDeFile, fileDepliable, resteNonListe, resteApresVisibles} from "../ui/texte.js";

const MAINTENANT = new Date("2026-11-10T12:00:00Z");
const ilYa = (minutes) => new Date(MAINTENANT.getTime() - minutes * 60000).toISOString();

test("tronquer", () => {
  assert.equal(tronquer("x".repeat(300), 40), "x".repeat(40) + "…");
  assert.equal(tronquer(null, 5), "");
  assert.equal(tronquer(undefined, 5), "");
  assert.equal(tronquer("abc", 5), "abc");
  assert.equal(tronquer("abcde", 5), "abcde");
});

test("tronquer garde le texte hostile tel quel", () => {
  const t = tronquer("<img src=x onerror=alert(1)>" + "y".repeat(300), 60);
  assert.ok(t.startsWith("<img src=x onerror=alert(1)>"));
  assert.ok(t.endsWith("…"));
  assert.equal(t.length, 61);
});

test("dureeEnClair", () => {
  assert.deepEqual([45, 60, 125, 47 * 60, 48 * 60, 5000].map(dureeEnClair),
                   ["45 min", "1 h", "2 h", "47 h", "2 j", "3 j"]);
});

test("voyant", () => {
  assert.deepEqual(voyant({etat: "en marche", inactive: false}, null), {libelle: "En marche", ton: "ok"});
  assert.deepEqual(voyant({etat: "en pause"}, null), {libelle: "En pause", ton: "pause"});
  assert.equal(voyant({etat: "en marche", inactive: true, derniere_activite: ilYa(125)}, null, MAINTENANT).libelle,
               "En marche, sans activité depuis 2 h");
  assert.equal(voyant({etat: "en marche", inactive: true, derniere_activite: null}, null, MAINTENANT).libelle,
               "En marche, sans activité");
  assert.equal(voyant({etat: "inconnu"}, "fichier absent").ton, "alerte");
  assert.equal(voyant({etat: "inconnu"}, "fichier absent").libelle, "Relevé indisponible");
  assert.equal(voyant(null, null).ton, "alerte");
});

test("libelleCharge", () => {
  assert.equal(libelleCharge({disponible: true, charge: 62, cpu: 12.4, memoire: 61.6}), "Charge 62 % · processeur 12 %, mémoire 62 %");
  assert.equal(libelleCharge({disponible: false}), "Mesure indisponible");
  assert.equal(libelleCharge(null), "Mesure indisponible");
  assert.equal(libelleCharge({disponible: true, charge: 62, cpu: 12.4, memoire: 61.6}, 3),
    "Charge 62 % · processeur 12 %, mémoire 62 % · 3 agents locaux au plus");
  assert.equal(libelleCharge(null, 2), "Mesure indisponible · 2 agents locaux au plus");
  assert.equal(libelleCharge(null, null), "Mesure indisponible");
});

test("ilYA", () => {
  assert.equal(ilYA(ilYa(5), MAINTENANT), "il y a 5 min");
  assert.equal(ilYA(ilYa(125), MAINTENANT), "il y a 2 h");
  assert.equal(ilYA(ilYa(0), MAINTENANT), "à l'instant");
  assert.equal(ilYA("", MAINTENANT), "inconnue");
  assert.equal(ilYA("hier", MAINTENANT), "inconnue");
  assert.equal(ilYA(null, MAINTENANT), "inconnue");
});

const TACHES = [
  {id: "a", active: true, type: "bug"}, {id: "b", active: false, type: "bug"},
  {id: "c", active: true, type: "fonction"}, {id: "d", active: false, type: null},
];

test("filtrer", () => {
  assert.deepEqual([...filtrer(TACHES, {enCours: false, type: null})], ["a", "b", "c", "d"]);
  assert.deepEqual([...filtrer(TACHES, {enCours: true, type: null})], ["a", "c"]);
  assert.deepEqual([...filtrer(TACHES, {enCours: false, type: "bug"})], ["a", "b"]);
  assert.deepEqual([...filtrer(TACHES, {enCours: true, type: "bug"})], ["a"]);
  assert.deepEqual([...filtrer(TACHES, {enCours: false, type: "inconnu"})], []);
  assert.deepEqual([...filtrer([], {enCours: true, type: null})], []);
  assert.deepEqual([...filtrer(TACHES, {})], ["a", "b", "c", "d"]);
});

test("imagesUrl encode &, espaces et #", () => {
  const u = imagesUrl({maj: "2026-11-10T09:00:00+01:00",
                       images: [{chemin: "img/a b&c#d.png", legende: "L"}, {chemin: "x.png"}]});
  assert.equal(u[0].url, "/api/image?chemin=img%2Fa%20b%26c%23d.png&t=2026-11-10T09%3A00%3A00%2B01%3A00");
  assert.equal(u[0].legende, "L");
  assert.equal(u[1].legende, "");
  assert.equal(imagesUrl({images: [{chemin: "x.png"}]})[0].url, "/api/image?chemin=x.png&t=");
  assert.deepEqual(imagesUrl({}), []);
  assert.deepEqual(imagesUrl(null), []);
});

test("dateFr garde un texte illisible tel quel", () => {
  assert.equal(dateFr("hier soir"), "hier soir");
  assert.equal(dateFr(null), "");
  assert.match(dateFr("2026-11-10T09:30:00"), /09:30/);
  assert.equal(dateFr("2026-10-01"), "1 oct.");  // une date sans heure reste une date, sans décalage horaire
});

test("imagesVisibles : pas de vignettes sans racine d'images déclarée", () => {
  const t = {images: [{chemin: "a.png"}]};
  assert.equal(imagesVisibles({images_ok: true}, t), true);
  assert.equal(imagesVisibles({images_ok: false}, t), false);
  assert.equal(imagesVisibles({}, t), false);
  assert.equal(imagesVisibles({images_ok: true}, {images: []}), false);
  assert.equal(imagesVisibles({images_ok: true}, {}), false);
});

test("listeDisponible : la vue liste n'existe pas en version 1", () => {
  assert.equal(listeDisponible({version: 1}), false);
  assert.equal(listeDisponible({}), false);
  assert.equal(listeDisponible(null), false);
  assert.equal(listeDisponible({version: 2}), true);
});

test("phrasesDirectionV1 : le texte d'avant, au singulier et au pluriel", () => {
  assert.deepEqual(phrasesDirectionV1({decisions: 0}), [
    {classe: "decisions", texte: "Aucune décision n'attend le Directeur."},
    {classe: "note", texte: "La liste détaillée des décisions arrivera avec le projet 2."}]);
  assert.equal(phrasesDirectionV1({decisions: 1})[0].texte, "1 décision attend le Directeur.");
  assert.equal(phrasesDirectionV1({decisions: 3})[0].texte, "3 décisions attendent le Directeur.");
  assert.equal(phrasesDirectionV1({})[0].texte, "Aucune décision n'attend le Directeur.");
});

test("notesValides : seules les notes bien formées, texte gardé tel quel", () => {
  const t = {notes: [{libelle: "À savoir", texte: "a\nb"}, {libelle: "", texte: "x"}, {libelle: "L"}, null, 3,
                     {libelle: "<b>", texte: "<img>"}]};
  assert.deepEqual(notesValides(t), [{libelle: "À savoir", texte: "a\nb"}, {libelle: "<b>", texte: "<img>"}]);
  assert.deepEqual(notesValides({}), []);
  assert.deepEqual(notesValides(null), []);
  assert.deepEqual(notesValides({notes: "x"}), []);
});

const COLS_T = [{id: "af", nom: "À faire"}, {id: "ec", nom: "En cours"}, {id: "fait", nom: "Fait", terminee: true}];
const TACHES_T = [
  {id: "a", active: true, colonne: "ec", type: "bug"}, {id: "b", active: false, colonne: "af", type: "bug"},
  {id: "c", active: true, colonne: "fait", type: "fonction"}, {id: "d", active: false, colonne: "fait", type: null},
  {id: "e", active: false, colonne: "ec", type: null, bloquee: "raison"},
];

test("filtrer : « Non terminées » = toutes celles qui ne sont pas dans une colonne terminée", () => {
  assert.deepEqual([...filtrer(TACHES_T, {nonTerminees: true}, COLS_T)], ["a", "b", "e"]);
  assert.deepEqual([...filtrer(TACHES_T, {nonTerminees: true, type: "bug"}, COLS_T)], ["a", "b"]);
  assert.deepEqual([...filtrer(TACHES_T, {enCours: true}, COLS_T)], ["a", "c"]);   // « En cours » ne change pas
  assert.deepEqual([...filtrer(TACHES_T, {}, COLS_T)], ["a", "b", "c", "d", "e"]);
  assert.deepEqual([...filtrer(TACHES_T, {nonTerminees: true}, [])], ["a", "b", "c", "d", "e"]);
  assert.deepEqual([...filtrer(TACHES_T, {nonTerminees: true})], ["a", "b", "c", "d", "e"]);
});

test("filtresEtat : « Non terminées » en premier, seulement si une colonne est terminée", () => {
  assert.deepEqual(filtresEtat({colonnes: COLS_T}).map((f) => f.id), ["non_terminees", "toutes", "en_cours"]);
  assert.equal(filtresEtat({colonnes: COLS_T})[0].libelle, "Non terminées");
  assert.deepEqual(filtresEtat({colonnes: COLS.map((c) => ({...c, terminee: false}))}).map((f) => f.id), ["toutes", "en_cours"]);
  assert.deepEqual(filtresEtat({colonnes: [{id: "x", nom: "X", terminee: null}]}).map((f) => f.id), ["toutes", "en_cours"]);
  assert.deepEqual(filtresEtat({}).map((f) => f.id), ["toutes", "en_cours"]);
  assert.deepEqual(filtresEtat(null).map((f) => f.id), ["toutes", "en_cours"]);
});

test("filtreEtatEffectif : défaut « Non terminées » s'il y a une colonne terminée, le choix de l'utilisateur d'abord", () => {
  assert.equal(filtreEtatEffectif({colonnes: COLS_T}, null), "non_terminees");
  assert.equal(filtreEtatEffectif({colonnes: COLS_T}, undefined), "non_terminees");
  assert.equal(filtreEtatEffectif({colonnes: COLS_T}, "toutes"), "toutes");
  assert.equal(filtreEtatEffectif({colonnes: COLS_T}, "en_cours"), "en_cours");
  assert.equal(filtreEtatEffectif({colonnes: COLS_T}, "non_terminees"), "non_terminees");
  assert.equal(filtreEtatEffectif({colonnes: COLS}, null), "toutes");
  assert.equal(filtreEtatEffectif({colonnes: COLS}, "non_terminees"), "toutes");   // plus de colonne terminée
  assert.equal(filtreEtatEffectif({colonnes: COLS}, "en_cours"), "en_cours");
  assert.equal(filtreEtatEffectif({colonnes: COLS_T}, "n'importe quoi"), "non_terminees");
});

test("filtreDeListe : le filtre prêt pour filtrer()", () => {
  assert.deepEqual(filtreDeListe({colonnes: COLS_T}, {etat: null, type: null}),
                   {enCours: false, nonTerminees: true, type: null});
  assert.deepEqual(filtreDeListe({colonnes: COLS_T}, {etat: "en_cours", type: "bug"}),
                   {enCours: true, nonTerminees: false, type: "bug"});
  assert.deepEqual(filtreDeListe({colonnes: COLS_T}, {etat: "toutes", type: null}),
                   {enCours: false, nonTerminees: false, type: null});
  assert.deepEqual(filtreDeListe({colonnes: COLS}, {etat: null, type: null}),
                   {enCours: false, nonTerminees: false, type: null});
});

const FILE = {visibles: [{id: "q1", titre: "Un"}, {id: "q2", titre: "Deux"}], suite: [{id: "q3", titre: "Trois"}, {id: "q4", titre: null}], reste: 7};

test("elementsDeFile : les visibles puis la suite, une seule fois chacun", () => {
  assert.deepEqual(elementsDeFile(FILE).map((q) => q.id), ["q1", "q2", "q3", "q4"]);
  assert.deepEqual(elementsDeFile(FILE).map((q) => q.visible), [true, true, false, false]);
  assert.equal(elementsDeFile(FILE)[3].titre, "q4");   // sans titre, l'identifiant fait office de titre
  assert.deepEqual(elementsDeFile({visibles: [{id: "a", titre: "A"}], suite: [{id: "a", titre: "A bis"}, null, {titre: "x"}]}).map((q) => q.id), ["a"]);
  assert.deepEqual(elementsDeFile({visibles: [{id: "a", titre: "A"}]}).map((q) => q.id), ["a"]);
  assert.deepEqual(elementsDeFile({suite: "x", visibles: 3}), []);
  assert.deepEqual(elementsDeFile({}), []);
  assert.deepEqual(elementsDeFile(null), []);
});

test("fileDepliable : le « + n » ouvre la file seulement s'il y a quelque chose au-delà des visibles", () => {
  assert.equal(fileDepliable(FILE), true);
  assert.equal(fileDepliable({visibles: [{id: "a", titre: "A"}], reste: 3}), true);
  assert.equal(fileDepliable({visibles: [{id: "a", titre: "A"}], suite: [{id: "b", titre: "B"}], reste: 0}), true);
  assert.equal(fileDepliable({visibles: [{id: "a", titre: "A"}], reste: 0}), false);
  assert.equal(fileDepliable({}), false);
  assert.equal(fileDepliable(null), false);
});

test("resteNonListe : ce qui dépasse la suite fournie", () => {
  assert.equal(resteNonListe(FILE), 5);   // 7 au-delà des visibles, 2 listés
  assert.equal(resteNonListe({visibles: [], suite: [{id: "a", titre: "A"}], reste: 1}), 0);
  assert.equal(resteNonListe({visibles: [], suite: [{id: "a", titre: "A"}], reste: 0}), 0);
  assert.equal(resteNonListe({visibles: [], reste: 4}), 4);
  assert.equal(resteNonListe(null), 0);
});

test("resteApresVisibles : le plus grand de `reste` et de la longueur de la suite", () => {
  assert.equal(resteApresVisibles({visibles: [], reste: 7, suite: [{id: "a"}]}), 7);
  assert.equal(resteApresVisibles({visibles: [], reste: 0, suite: [{id: "a"}, {id: "b"}]}), 2);
  assert.equal(resteApresVisibles({reste: "x"}), 0);
  assert.equal(resteApresVisibles(null), 0);
});

import {euros, tokens, libellePeriode} from "../ui/texte.js";

test("euros", () => {
  assert.equal(euros(1.42), "≈ 1,42 €");
  assert.equal(euros(0), "≈ 0,00 €");
  assert.equal(euros(1234.5), "≈ 1234,50 €");
  assert.equal(euros(null), "—");
  assert.equal(euros(undefined), "—");
  assert.equal(euros(0.004), "≈ 0,00 €");
});

test("tokens", () => {
  assert.equal(tokens(12400), "12,4 k");
  assert.equal(tokens(1300000), "1,3 M");
  assert.equal(tokens(850), "850");
  assert.equal(tokens(0), "0");
  assert.equal(tokens(null), "—");
});

test("libellePeriode", () => {
  assert.equal(libellePeriode("aujourdhui"), "Aujourd'hui");
  assert.equal(libellePeriode("7j"), "7 jours");
  assert.equal(libellePeriode("30j"), "30 jours");
  assert.equal(libellePeriode("x"), "7 jours");
});
