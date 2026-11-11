import test from "node:test";
import assert from "node:assert/strict";
import {verifierSelection, preparerImage} from "../ui/fonctionnalite.js";

const Mo = 1024 * 1024;

// Un faux fichier choisi, et de faux moyens de décodage et d'encodage qui notent ce qu'on leur demande.
function fichier(nom, type, size) {
  return {name: nom, type, size, arrayBuffer: async () => new Uint8Array(4).buffer};
}
function moyens(largeur, hauteur, poids) {
  const appels = [];
  return {
    appels,
    decoder: async () => ({width: largeur, height: hauteur, close() { appels.push("close"); }}),
    encoder: async (image, l, h, type, qualite) => {
      appels.push({l, h, type, qualite});
      const size = typeof poids === "function" ? poids(type, qualite, appels.length) : poids;
      return {size, arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer};
    },
  };
}

test("verifierSelection : de vraies images, 4 au plus, HEIC sans type reconnu à l'extension", () => {
  assert.equal(verifierSelection([fichier("a.heic", "image/heic", 12 * Mo)]), null);
  assert.equal(verifierSelection([fichier("a.webp", "image/webp", 3 * Mo), fichier("b.png", "image/png", 1)]), null);
  assert.equal(verifierSelection([fichier("IMG_1.HEIC", "", 9 * Mo)]), null);
  assert.equal(verifierSelection([]), null);
  assert.match(verifierSelection([fichier("a.pdf", "application/pdf", 10)]), /n'est pas une image/);
  assert.match(verifierSelection([fichier("a.txt", "", 10)]), /n'est pas une image/);
  assert.match(verifierSelection(Array.from({length: 5}, (_, i) => fichier(`${i}.png`, "image/png", 1))), /4 images/);
  assert.match(verifierSelection([fichier("énorme.jpg", "image/jpeg", 200 * Mo)]), /trop lourde/);
});

test("preparerImage : une photo HEIC de 12 Mo en 4032 × 3024 devient un JPEG de 2048 × 1536 sous 5 Mo", async () => {
  const m = moyens(4032, 3024, 1.4 * Mo);
  const r = await preparerImage(fichier("IMG_0042.HEIC", "image/heic", 12 * Mo), m);
  assert.deepEqual(m.appels[0], {l: 2048, h: 1536, type: "image/jpeg", qualite: 0.8});
  assert.equal(r.type, "image/jpeg");
  assert.equal(r.nom, "IMG_0042.jpg");
  assert.equal(r.donnees, Buffer.from([1, 2, 3]).toString("base64"));
  assert.ok(m.appels.includes("close"));   // l'image décodée est libérée
});

test("preparerImage : un WebP devient du JPEG, un PNG de taille raisonnable est gardé tel quel", async () => {
  const webp = moyens(1000, 800, 200000);
  assert.equal((await preparerImage(fichier("a.webp", "image/webp", 90000), webp)).type, "image/jpeg");
  const png = moyens(1000, 800, 1);
  const r = await preparerImage(fichier("capture.png", "image/png", 300000), png);
  assert.equal(r.type, "image/png");
  assert.equal(r.nom, "capture.png");
  assert.equal(png.appels.filter((a) => typeof a === "object").length, 0);   // pas de réencodage : octets d'origine
  assert.equal(r.donnees, Buffer.from(new Uint8Array(4)).toString("base64"));
});

test("preparerImage : un JPEG de petite définition et léger est gardé, un JPEG trop lourd est réduit", async () => {
  const leger = moyens(800, 600, 1);
  const r = await preparerImage(fichier("a.jpg", "image/jpeg", 200000), leger);
  assert.equal(r.type, "image/jpeg");
  assert.equal(leger.appels.filter((a) => typeof a === "object").length, 0);
  const lourd = moyens(1600, 1200, 1 * Mo);
  await preparerImage(fichier("b.jpg", "image/jpeg", 8 * Mo), lourd);
  assert.equal(lourd.appels.filter((a) => typeof a === "object").length, 1);
});

test("preparerImage : un PNG trop lourd même réduit repasse en JPEG ; un JPEG trop lourd se comprime davantage", async () => {
  const png = moyens(4000, 3000, (type) => (type === "image/png" ? 9 * Mo : 2 * Mo));
  const r = await preparerImage(fichier("plan.png", "image/png", 30 * Mo), png);
  assert.equal(r.type, "image/jpeg");
  assert.equal(r.nom, "plan.jpg");
  const jpeg = moyens(4000, 3000, (type, qualite) => (qualite > 0.7 ? 6 * Mo : 4 * Mo));
  await preparerImage(fichier("p.jpg", "image/jpeg", 20 * Mo), jpeg);
  const qualites = jpeg.appels.filter((a) => typeof a === "object").map((a) => a.qualite);
  assert.deepEqual(qualites, [0.72, 0.7]);   // d'abord la qualité d'après le poids, puis plus bas
});

test("preparerImage : une image qui reste trop lourde, ou illisible : un message clair, jamais en silence", async () => {
  await assert.rejects(() => preparerImage(fichier("monstre.jpg", "image/jpeg", 90 * Mo), moyens(4000, 3000, 9 * Mo)),
    /dépasse 5 Mo/);
  const illisible = {decoder: async () => { throw new Error("format"); }, encoder: async () => { throw new Error("jamais"); }};
  await assert.rejects(() => preparerImage(fichier("a.heic", "image/heic", 5 * Mo), illisible), /ne sait pas lire ce format/);
});
