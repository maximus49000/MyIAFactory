import test from "node:test";
import assert from "node:assert/strict";
import {vignetteUrl, vignettesVoulues, Vignettes} from "../logique/vignettes.js";

const T1 = {id: "t1", maj: "2026-11-10T09:00:00", images: [{chemin: "img/a b.png"}, {chemin: "img/b.png"}]};
const T2 = {id: "t2", maj: "m", images: []};
const T3 = {id: "t3", maj: "m", images: [{chemin: "c.png"}]};

test("vignetteUrl : la première image, seulement si les images sont servies", () => {
  assert.equal(vignetteUrl(true, T1), "/api/image?chemin=img%2Fa%20b.png&t=2026-11-10T09%3A00%3A00");
  assert.equal(vignetteUrl(false, T1), null);
  assert.equal(vignetteUrl(undefined, T1), null);
  assert.equal(vignetteUrl(true, T2), null);
  assert.equal(vignetteUrl(true, {id: "x"}), null);
  assert.equal(vignetteUrl(true, null), null);
});

test("vignettesVoulues : une adresse par post-it visible qui a une image", () => {
  const taches = [T1, T2, T3];
  const v = vignettesVoulues(true, taches, ["t1", "t2", "t9"]);
  assert.deepEqual([...v.keys()], ["t1"]);   // t2 sans image, t9 inconnue
  assert.equal(v.get("t1"), vignetteUrl(true, T1));
  assert.equal(vignettesVoulues(false, taches, ["t1", "t3"]).size, 0);   // aucune requête sans images_ok
  assert.equal(vignettesVoulues(true, taches, []).size, 0);              // t3 n'a pas de post-it visible
  assert.deepEqual([...vignettesVoulues(true, taches, ["t3", "t1", "t3"]).keys()], ["t3", "t1"]);
  assert.equal(vignettesVoulues(true, null, ["t1"]).size, 0);
});

// Doublures : un chargeur dont on décide quand il répond, et un « moteur 3D » qui note ce qu'il crée et libère.
function banc(options = {}) {
  const b = {attentes: [], crees: [], retires: [], jetees: [], t: 0};
  b.charger = (url, ok, ko) => { b.attentes.push({url, ok, ko}); };
  b.creer = (cle, image) => { if (b.refuser) return null; const o = {cle, image}; b.crees.push(o); return o; };
  b.retirer = (cle, objet) => { b.retires.push(objet); };
  b.jeter = (image) => { b.jetees.push(image); };
  b.v = new Vignettes({charger: b.charger, creer: b.creer, retirer: b.retirer, jeter: b.jeter,
                       maintenant: () => b.t, delaiEssaiMs: 60000, ...options});
  b.repondre = (k, image) => b.attentes[k].ok(image);
  b.echouer = (k) => b.attentes[k].ko();
  return b;
}
const voulu = (o) => new Map(Object.entries(o));

test("Vignettes : une requête par adresse, la texture est créée à l'arrivée, rien n'est redemandé", () => {
  const b = banc();
  b.v.synchroniser(voulu({a: "u1"}));
  b.v.synchroniser(voulu({a: "u1"}));
  assert.equal(b.attentes.length, 1);
  b.repondre(0, "img1");
  assert.deepEqual(b.crees.map((o) => o.image), ["img1"]);
  b.v.synchroniser(voulu({a: "u1"}));
  assert.equal(b.attentes.length, 1);
  assert.equal(b.retires.length, 0);
});

test("Vignettes : changement d'image, l'ancienne reste jusqu'à l'arrivée de la nouvelle, puis est libérée", () => {
  const b = banc();
  b.v.synchroniser(voulu({a: "u1"}));
  b.repondre(0, "img1");
  b.v.synchroniser(voulu({a: "u2"}));
  assert.equal(b.attentes.length, 2);
  assert.equal(b.retires.length, 0);          // pas de clignotement : l'ancienne est toujours là
  b.repondre(1, "img2");
  assert.deepEqual(b.retires.map((o) => o.image), ["img1"]);
  assert.deepEqual(b.crees.map((o) => o.image), ["img1", "img2"]);
});

test("Vignettes : le post-it disparaît (ou images_ok devient faux) : texture libérée, chargement en cours abandonné", () => {
  const b = banc();
  b.v.synchroniser(voulu({a: "u1", b: "u2"}));
  b.repondre(0, "img1");
  b.v.synchroniser(voulu({}));
  assert.deepEqual(b.retires.map((o) => o.image), ["img1"]);
  b.repondre(1, "img2");                       // arrive après la disparition de b
  assert.deepEqual(b.jetees, ["img2"]);
  assert.equal(b.crees.length, 1);
  b.v.synchroniser(voulu({}));
  assert.equal(b.attentes.length, 2);
});

test("Vignettes : course, une réponse en retard pour une ancienne adresse est jetée", () => {
  const b = banc();
  b.v.synchroniser(voulu({a: "u1"}));
  b.v.synchroniser(voulu({a: "u2"}));
  b.repondre(0, "tardive");
  assert.deepEqual(b.jetees, ["tardive"]);
  assert.equal(b.crees.length, 0);
  b.repondre(1, "bonne");
  assert.deepEqual(b.crees.map((o) => o.image), ["bonne"]);
  // retour à l'adresse affichée pendant qu'une autre charge : la réponse de l'autre est jetée
  b.v.synchroniser(voulu({a: "u3"}));
  b.v.synchroniser(voulu({a: "u2"}));
  b.repondre(2, "inutile");
  assert.deepEqual(b.jetees, ["tardive", "inutile"]);
  assert.equal(b.retires.length, 0);
});

test("Vignettes : un post-it qui n'existe plus à l'arrivée : l'image est jetée", () => {
  const b = banc();
  b.refuser = true;
  b.v.synchroniser(voulu({a: "u1"}));
  b.repondre(0, "img");
  assert.deepEqual(b.jetees, ["img"]);
  assert.equal(b.retires.length, 0);
});

test("Vignettes : oublier libère tout de suite et abandonne le chargement", () => {
  const b = banc();
  b.v.synchroniser(voulu({a: "u1", b: "u2"}));
  b.repondre(0, "img1");
  b.v.oublier("a");
  b.v.oublier("b");
  assert.equal(b.retires.length, 1);
  b.repondre(1, "img2");
  assert.deepEqual(b.jetees, ["img2"]);
});

test("Vignettes : échec, pas de nouvelle tentative avant le délai, puis une seule", () => {
  const b = banc();
  b.v.synchroniser(voulu({a: "u1"}));
  b.echouer(0);
  b.v.synchroniser(voulu({a: "u1"}));
  assert.equal(b.attentes.length, 1);
  b.t = 59999;
  b.v.synchroniser(voulu({a: "u1"}));
  assert.equal(b.attentes.length, 1);
  b.t = 60000;
  b.v.synchroniser(voulu({a: "u1"}));
  assert.equal(b.attentes.length, 2);
  b.v.synchroniser(voulu({a: "u1"}));
  assert.equal(b.attentes.length, 2);          // l'essai est en cours
  b.echouer(1);
  b.v.synchroniser(voulu({a: "u2"}));          // une autre adresse : tout de suite
  assert.equal(b.attentes.length, 3);
});
