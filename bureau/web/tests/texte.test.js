import test from "node:test";
import assert from "node:assert/strict";
import {tronquer, voyant, libelleCharge, dureeEnClair, ilYA, filtrer, imagesUrl, dateFr, imagesVisibles, listeDisponible, phrasesDirectionV1, notesValides} from "../ui/texte.js";

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
