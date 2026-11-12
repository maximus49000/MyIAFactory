// Les fichiers joints d'un échange : préparer un fichier choisi, et les montrer dans la discussion (vignette, vidéo, son,
// Markdown lu en ligne, bouton « Télécharger »). Faux DOM.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.attributs = {}; this.value = ""; this.dataset = {};
    const n = this; this.classList = {add: (c) => { n.className = (n.className + " " + c).trim(); }, contains: (c) => n.className.split(" ").includes(c), toggle() {}}; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
globalThis.localStorage = {getItem: () => null, setItem() {}};

const F = await import("../ui/fonctionnalite.js");

const Mo = 1024 * 1024;
const fichier = (name, type, size, octets = [1, 2, 3]) => ({name, type, size, arrayBuffer: async () => new Uint8Array(octets).buffer});
const par = (n, tag) => n.tous((x) => x.tagName === tag);
const classe = (n, c) => n.tous((x) => x.className.split(" ").includes(c));

test("preparerFichier : un zip, un pdf, un md partent tels quels, sous le type de la liste blanche", async () => {
  const zip = await F.preparerFichier(fichier("Plan.ZIP", "application/x-zip-compressed", 3 * Mo));
  assert.deepEqual({...zip}, {nom: "Plan.ZIP", type: "application/zip", donnees: Buffer.from([1, 2, 3]).toString("base64"), taille: 3, categorie: "archive"});
  const md = await F.preparerFichier(fichier("notes.md", "", 10));
  assert.equal(md.type, "text/markdown");
  assert.equal(md.categorie, "texte");
  const gif = await F.preparerFichier(fichier("anim.gif", "image/gif", 2 * Mo));       // un GIF n'est pas réencodé : il reste animé
  assert.deepEqual([gif.type, gif.categorie], ["image/gif", "animation"]);
  const video = await F.preparerFichier(fichier("clip.mp4", "video/mp4", 20 * Mo));
  assert.equal(video.categorie, "video");
});

test("preparerFichier : une photo est réduite comme avant, le reste est refusé avec un message clair", async () => {
  const moyens = {decoder: async () => ({width: 4000, height: 3000, close() {}}),
                  encoder: async () => ({size: 1 * Mo, arrayBuffer: async () => new Uint8Array([9, 9]).buffer})};
  const photo = await F.preparerFichier(fichier("IMG_1.HEIC", "image/heic", 12 * Mo), moyens);
  assert.deepEqual([photo.nom, photo.type, photo.categorie, photo.taille], ["IMG_1.jpg", "image/jpeg", "image", 2]);
  await assert.rejects(() => F.preparerFichier(fichier("virus.exe", "application/x-msdownload", 10)), /pas accepté/);
  await assert.rejects(() => F.preparerFichier(fichier("gros.zip", "application/zip", 26 * Mo)), /dépasse 25 Mo/);
});

const ETAT = {images_ok: true};
const joint = (nom, type = "", taille = 2048) => ({chemin: `pieces/f1/20261112-100000-${nom}`, nom, type, taille});

test("discussion : image fixe d'abord, puis gif en vignette, vidéo, son, md lu en ligne, le reste en « Télécharger »", () => {
  const m = {id: "m1", auteur: "utilisateur", texte: "Voici", images: ["pieces/f1/20261112-100000-a.png"],
    fichiers: [joint("a.png", "image/png"), joint("anim.gif", "image/gif"), joint("clip.mp4", "video/mp4"), joint("voix.mp3", "audio/mpeg"),
               joint("notes.md", "text/markdown"), joint("plan.zip", "application/zip"), joint("dossier.pdf", "application/pdf")]};
  const li = F.messageDe(m, ETAT, [], "f1");
  const zone = classe(li, "fichiers-joints");
  assert.equal(zone.length, 1);
  // la vignette du GIF (et non du PNG, montré avec les images) ; lien sûr vers la route de téléchargement avec lecture
  const imgs = par(zone[0], "img");
  assert.equal(imgs.length, 1);
  assert.match(imgs[0].src, /^\/api\/telecharger\?.*fonctionnalite=f1.*anim\.gif.*&lecture=1$/);
  assert.equal(imgs[0].alt, "anim.gif");
  // la vidéo : lecteur à la demande, rien n'est chargé tant qu'on n'appuie pas sur lecture
  const [video] = par(zone[0], "video");
  assert.equal(video.controls, true);
  assert.equal(video.preload, "none");
  assert.match(video.src, /clip\.mp4.*&lecture=1$/);
  // le son
  const [audio] = par(zone[0], "audio");
  assert.equal(audio.controls, true);
  assert.equal(audio.preload, "none");
  assert.match(audio.src, /voix\.mp3.*&lecture=1$/);
  // le .md : bloc repliable lu en ligne
  assert.equal(classe(zone[0], "md-bloc").length, 1);
  assert.match(classe(zone[0], "md-bloc")[0].textContent, /notes\.md/);
  // zip et pdf : une ligne avec le nom, la taille et « Télécharger » ; ni lecteur ni lecture en ligne
  const lignes = classe(zone[0], "fichier-ligne");
  assert.equal(lignes.length, 2);
  assert.match(lignes[0].textContent, /ZIP.*plan\.zip.*2,0 Ko.*Télécharger/);
  assert.match(lignes[1].textContent, /PDF.*dossier\.pdf/);
  const liens = par(lignes[0], "a");
  assert.equal(liens.length, 1);
  assert.match(liens[0].href, /^\/api\/telecharger\?fonctionnalite=f1&chemin=.*plan\.zip$/);
  assert.ok(!liens[0].href.includes("lecture"));
  assert.equal(liens[0].attributs.download, "plan.zip");
  // chaque fichier gardé en lecture a aussi son « Télécharger »
  assert.ok(par(zone[0], "a").length >= 5);
});

test("discussion : un message sans fichier ou hors fonctionnalité n'a pas de zone de fichiers", () => {
  assert.equal(classe(F.messageDe({id: "m1", auteur: "utilisateur", texte: "x"}, ETAT, [], "f1"), "fichiers-joints").length, 0);
  assert.equal(F.fichiersDuMessage({fichiers: [joint("a.zip")]}, null), null);
  assert.equal(F.fichiersDuMessage({fichiers: [joint("a.png")], images: [joint("a.png").chemin]}, "f1"), null);   // déjà montré
});

test("un nom hostile reste du texte : aucun HTML interprété", () => {
  const li = F.messageDe({id: "m1", auteur: "utilisateur", texte: "x",
    fichiers: [{chemin: "pieces/f1/1-a.zip", nom: "<img src=x onerror=alert(1)>.zip", type: "application/zip", taille: 5}]}, ETAT, [], "f1");
  assert.equal(par(li, "img").length, 0);
  assert.match(li.textContent, /<img src=x onerror=alert\(1\)>\.zip/);
});

test("texteACopier : les fichiers joints avec leur chemin", () => {
  const m = {texte: "Voici", fichiers: [joint("plan.zip")]};
  assert.equal(F.texteACopier(m), "Voici\n\nFichiers joints :\n- pieces/f1/20261112-100000-plan.zip");
});
