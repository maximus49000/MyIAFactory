import test from "node:test";
import assert from "node:assert/strict";
import {estMobile, zoomPincement, decalageBorne, dimensionsReduites, formatEnvoye, qualitePour, ZOOM_MIN, ZOOM_MAX}
  from "../logique/mobile.js";

test("estMobile : sous 768 px, ou pointeur grossier", () => {
  const cas = [[375, false, true], [767, false, true], [768, false, false], [1280, false, false],
               [1280, true, true], [820, true, true], [NaN, false, false], [undefined, false, false], [500, undefined, true]];
  for (const [largeur, grossier, attendu] of cas) assert.equal(estMobile(largeur, grossier), attendu, `${largeur} ${grossier}`);
});

test("zoomPincement : proportionnel à l'écart des doigts, borné", () => {
  assert.equal(zoomPincement(100, 200, 1, 1, 4), 2);
  assert.equal(zoomPincement(200, 100, 2, 1, 4), 1);
  assert.equal(zoomPincement(100, 1000, 1, 1, 4), 4);       // plafond
  assert.equal(zoomPincement(1000, 100, 2, 1, 4), 1);       // plancher
  assert.equal(zoomPincement(100, 100, 1.7, 1, 4), 1.7);    // doigts immobiles
  assert.equal(zoomPincement(0, 100, 2, 1, 4), 2);          // écart de départ nul : rien ne change
  assert.equal(zoomPincement(100, NaN, 2, 1, 4), 2);
  assert.equal(zoomPincement(100, 150, 9, 1, 4), 4);        // un zoom hors bornes est ramené dans les bornes
  assert.equal(zoomPincement(100, 150, NaN, 1, 4), 1.5);
  assert.deepEqual([ZOOM_MIN, ZOOM_MAX], [1, 4]);
});

test("decalageBorne : à zoom 1 la vue reste centrée, zoomée elle ne sort pas du bâtiment", () => {
  assert.deepEqual(decalageBorne([5, -5], 1, [10, 6]), [0, 0]);
  assert.deepEqual(decalageBorne([1, 1], 2, [10, 6]), [1, 1]);
  assert.deepEqual(decalageBorne([99, -99], 2, [10, 6]), [5, -3]);   // la moitié du cadrage à zoom 2
  assert.deepEqual(decalageBorne([99, -99], 4, [10, 6]), [7.5, -4.5]);
  assert.deepEqual(decalageBorne(undefined, 2, [10, 6]), [0, 0]);
  assert.deepEqual(decalageBorne([1, 1], 0.5, [10, 6]), [0, 0]);    // un zoom sous 1 n'ouvre aucune marge
});

test("dimensionsReduites : 4032 × 3024 → 2048 × 1536 ; petite image inchangée", () => {
  assert.deepEqual(dimensionsReduites(4032, 3024), [2048, 1536]);
  assert.deepEqual(dimensionsReduites(3024, 4032), [1536, 2048]);
  assert.deepEqual(dimensionsReduites(800, 600), [800, 600]);
  assert.deepEqual(dimensionsReduites(2048, 2048), [2048, 2048]);
  assert.deepEqual(dimensionsReduites(12000, 100), [2048, 17]);
  assert.deepEqual(dimensionsReduites(4000, 3000, 1000), [1000, 750]);
  assert.deepEqual(dimensionsReduites(0, 100), [1, 1]);
  assert.deepEqual(dimensionsReduites(NaN, 100), [1, 1]);
});

test("formatEnvoye : le PNG est gardé, tout le reste en JPEG", () => {
  assert.equal(formatEnvoye("image/png"), "image/png");
  assert.equal(formatEnvoye("IMAGE/PNG"), "image/png");
  for (const t of ["image/jpeg", "image/heic", "image/heif", "image/webp", "image/gif", "image/avif", "", undefined]) {
    assert.equal(formatEnvoye(t), "image/jpeg", String(t));
  }
});

test("qualitePour : plus l'original pèse, plus on comprime ; toujours entre 0,5 et 0,95", () => {
  const Mo = 1024 * 1024;
  const q = [0, 1 * Mo, 3 * Mo, 8 * Mo, 12 * Mo, 20 * Mo, 80 * Mo].map(qualitePour);
  assert.deepEqual(q, [...q].sort((a, b) => b - a));            // jamais croissante
  assert.ok(q.every((v) => v >= 0.5 && v <= 0.95), String(q));
  assert.ok(qualitePour(12 * Mo) > qualitePour(80 * Mo));
  assert.equal(qualitePour(NaN), qualitePour(0));
});

import {nomEnvoye} from "../logique/mobile.js";

test("nomEnvoye : l'extension suit le format envoyé, rien qui ressemble à un chemin", () => {
  assert.equal(nomEnvoye("IMG_0042.HEIC", "image/jpeg"), "IMG_0042.jpg");
  assert.equal(nomEnvoye("capture.png", "image/png"), "capture.png");
  assert.equal(nomEnvoye("photo.webp", "image/webp"), "photo.jpg");
  assert.ok(!/[/\\:]|\.\./.test(nomEnvoye("../../etc/passwd.png", "image/png")));
  assert.equal(nomEnvoye("a/b\\c:d.png", "image/png"), "a_b_c_d.png");
  assert.equal(nomEnvoye("", "image/jpeg"), "photo.jpg");
  assert.equal(nomEnvoye(".png", "image/png"), "photo.png");
  assert.ok(nomEnvoye("x".repeat(200) + ".jpg", "image/jpeg").length <= 80);
  assert.ok(!nomEnvoye("a..b.jpg", "image/jpeg").includes(".."));
});
