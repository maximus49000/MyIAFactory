import test from "node:test";
import assert from "node:assert/strict";
import {TYPES, ACCEPT, MAX_FICHIERS, MAX_OCTETS_FICHIER, MAX_OCTETS_TOTAL, extension, categorie, typeEnvoye, estPhoto, nomValide,
        verifierChoix, tailleBase64, tailleLisible, badge, affichage, fichiersAMontrer} from "../ui/pieces.js";

const Mo = 1024 * 1024;
const f = (name, size = 100, type = "") => ({name, type, size});

test("la liste blanche : images, vidéos, sons, documents, archives, modèles 3D", () => {
  assert.deepEqual(Object.keys(TYPES).sort(), [".csv", ".docx", ".fbx", ".flac", ".gif", ".glb", ".gltf", ".jpeg", ".jpg", ".json",
    ".md", ".mp3", ".mp4", ".mtl", ".obj", ".ogg", ".pdf", ".png", ".pptx", ".txt", ".wav", ".webm", ".webp", ".xlsx", ".zip"]);
  assert.ok(ACCEPT.includes(".glb") && ACCEPT.includes(".fbx") && ACCEPT.includes(".obj"));
  assert.equal(MAX_FICHIERS, 8);
  assert.equal(MAX_OCTETS_FICHIER, 25 * Mo);
  assert.equal(MAX_OCTETS_TOTAL, 40 * Mo);
  assert.match(ACCEPT, /^image\/\*,\.png/);
  assert.ok(ACCEPT.includes(".zip") && ACCEPT.includes(".docx") && ACCEPT.includes(".mp4"));
  assert.ok(!ACCEPT.includes(".exe") && !ACCEPT.includes(".html"));
});

test("extension, catégorie et type envoyé viennent du nom", () => {
  assert.equal(extension("Plan.FINAL.ZIP"), ".zip");
  assert.equal(extension("dossier/a.PDF"), ".pdf");
  assert.equal(extension(".gitignore"), "");
  assert.equal(extension("sans"), "");
  assert.equal(categorie("a.gif"), "animation");
  assert.equal(categorie("a.mp3"), "son");
  assert.equal(categorie("a.exe"), null);
  assert.equal(typeEnvoye("a.zip"), "application/zip");
  assert.equal(typeEnvoye("a.exe"), null);
});

test("estPhoto : une image fixe à réduire, jamais un GIF ni un SVG", () => {
  assert.ok(estPhoto(f("a.heic", 1, "image/heic")));
  assert.ok(estPhoto(f("IMG_1.HEIC", 1, "")));
  assert.ok(estPhoto(f("a.png", 1, "image/png")));
  assert.ok(estPhoto(f("a.webp", 1, "image/webp")));
  assert.ok(!estPhoto(f("a.gif", 1, "image/gif")));
  assert.ok(!estPhoto(f("a.gif", 1, "")));
  assert.ok(!estPhoto(f("a.svg", 1, "image/svg+xml")));
  assert.ok(!estPhoto(f("a.zip", 1, "application/zip")));
});

test("verifierChoix : types, nombre, tailles, total", () => {
  assert.equal(verifierChoix([], [f("a.zip", 3 * Mo), f("b.pdf"), f("c.mp4", 20 * Mo), f("d.gif"), f("e.md"), f("f.txt")]), null);
  assert.equal(verifierChoix([], []), null);
  assert.equal(verifierChoix([], [f("a.heic", 12 * Mo, "image/heic")]), null);
  assert.match(verifierChoix([], [f("a.exe")]), /pas accepté/);
  assert.match(verifierChoix([], [f("a.html", 10, "text/html")]), /pas accepté/);
  assert.match(verifierChoix([], [f("a")]), /pas accepté/);
  assert.match(verifierChoix([], [f("a.svg", 10, "image/svg+xml")]), /pas accepté/);
  assert.match(verifierChoix([], [f("gros.zip", 26 * Mo)]), /dépasse 25 Mo/);
  assert.equal(verifierChoix([], [f("juste.zip", 25 * Mo)]), null);
  assert.match(verifierChoix([], [f("vide.txt", 0)]), /vide/);
  assert.match(verifierChoix([], [f("énorme.jpg", 200 * Mo, "image/jpeg")]), /trop lourde/);
  assert.match(verifierChoix([], Array.from({length: 9}, (_, i) => f(`${i}.txt`))), /8 fichiers/);
  assert.match(verifierChoix(Array.from({length: 7}, (_, i) => ({nom: `${i}.txt`, taille: 1, categorie: "texte"})), [f("a.txt"), f("b.txt")]), /8 fichiers/);
  assert.match(verifierChoix([], Array.from({length: 5}, (_, i) => f(`${i}.png`, 1, "image/png"))), /4 images/);
  assert.match(verifierChoix([{nom: "a.png", taille: 1, categorie: "image"}], [f("b.jpg"), f("c.jpg"), f("d.jpg"), f("e.jpg")]), /4 images/);
  assert.equal(verifierChoix([], Array.from({length: 6}, (_, i) => f(`${i}.gif`, 1, "image/gif"))), null);   // un GIF n'est pas une image fixe
  assert.match(verifierChoix([], [f("a.zip", 20 * Mo), f("b.zip", 20 * Mo), f("c.zip", 5 * Mo)]), /40 Mo en tout/);
  assert.match(verifierChoix([{nom: "a.zip", taille: 30 * Mo, categorie: "archive"}], [f("b.zip", 11 * Mo)]), /40 Mo en tout/);
  assert.match(verifierChoix([], [f("x/y.txt")]), /nom/);
  assert.match(verifierChoix([], [f("a".repeat(77) + ".txt")]), /nom/);
  assert.match(verifierChoix([], [f("a:b.txt")]), /nom/);
  assert.match(verifierChoix([], [f("a..b.txt")]), /nom/);
});

test("nomValide", () => {
  assert.ok(nomValide("Mon plan (v2).zip"));
  for (const n of ["", "  ", "a/b", "a\\b", "a..b", "a\u0001b", 'a"b', "x".repeat(81), null]) assert.ok(!nomValide(n), String(n));
});

test("tailles et badge", () => {
  assert.equal(tailleBase64("QUJD"), 3);
  assert.equal(tailleBase64("QUI="), 2);
  assert.equal(tailleBase64("QQ=="), 1);
  assert.equal(tailleBase64(""), 0);
  assert.equal(tailleLisible(2048), "2,0 Ko");
  assert.equal(tailleLisible(12 * Mo), "12 Mo");
  assert.equal(tailleLisible(512), "512 octets");
  assert.equal(tailleLisible(null), "");
  assert.equal(badge("Plan.zip"), "ZIP");
  assert.equal(badge("a.docx"), "DOCX");
  assert.equal(badge("sans"), "FICHI");
});

test("affichage : comment chaque fichier joint se montre", () => {
  assert.equal(affichage("a.gif"), "vignette");
  assert.equal(affichage("a.webp"), "vignette");
  assert.equal(affichage("a.mp4"), "video");
  assert.equal(affichage("a.webm"), "video");
  for (const n of ["a.mp3", "a.ogg", "a.wav", "a.flac"]) assert.equal(affichage(n), "son", n);
  assert.equal(affichage("a.md"), "markdown");
  for (const n of ["a.zip", "a.pdf", "a.docx", "a.txt", "a.json", "a.csv", "a.xlsx", "a.pptx"]) assert.equal(affichage(n), "fichier", n);
});

test("fichiersAMontrer : sans ce qui est déjà montré par `images`, sans entrée mal formée", () => {
  const m = {images: ["pieces/f1/1-a.png"], fichiers: [
    {chemin: "pieces/f1/1-a.png", nom: "a.png", type: "image/png", taille: 5},
    {chemin: "pieces/f1/2-b.zip", nom: "b.zip", type: "application/zip", taille: 7},
    {nom: "sans chemin"}, null, {chemin: "pieces/f1/3-c.gif"}]};
  assert.deepEqual(fichiersAMontrer(m), [
    {chemin: "pieces/f1/2-b.zip", nom: "b.zip", type: "application/zip", taille: 7},
    {chemin: "pieces/f1/3-c.gif", nom: "3-c.gif", type: "", taille: null}]);
  assert.deepEqual(fichiersAMontrer({}), []);
  assert.deepEqual(fichiersAMontrer(null), []);
});
