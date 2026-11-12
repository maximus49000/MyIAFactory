// La visionneuse plein écran, seule et dans la fenêtre de validation (bug : image agrandie sans issue). Faux DOM avec
// focus, classes du body, écouteurs du document en capture et ordre de livraison des touches.
import test from "node:test";
import assert from "node:assert/strict";

class Liste {
  constructor() { this.s = new Set(); }
  add(c) { this.s.add(c); } remove(c) { this.s.delete(c); } contains(c) { return this.s.has(c); }
  toggle(c) { this.s.has(c) ? this.s.delete(c) : this.s.add(c); }
}
class Noeud {
  constructor(tag) {
    this.tagName = tag; this.enfants = []; this.parent = null; this._classe = ""; this._texte = ""; this.hidden = false;
    this.auteurs = {}; this.attributs = {}; this.disabled = false; this.classList = new Liste();
  }
  set className(v) { this._classe = v; this.classList = new Liste(); for (const c of String(v).split(/\s+/).filter(Boolean)) this.classList.add(c); }
  get className() { return [...this.classList.s].join(" "); }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === document.documentElement; }
  get offsetParent() { return this.isConnected ? {} : null; }
  append(...e) { for (const x of e) { x.parent = this; this.enfants.push(x); } }
  remove() { if (this.parent) { this.parent.enfants = this.parent.enfants.filter((x) => x !== this); this.parent = null; } if (document.activeElement && !document.activeElement.isConnected) document.activeElement = null; }
  contains(x) { for (let n = x; n; n = n.parent) if (n === this) return true; return false; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  focus() { if (this.isConnected) document.activeElement = this; }
  click() { for (const f of this.auteurs.click || []) f({target: this, stopPropagation() {}}); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
  querySelectorAll(sel) {
    const classes = [...sel.matchAll(/\.([\w-]+)/g)].map((m) => m[1]);
    if (sel.includes("button")) return this.tous((n) => n.tagName === "button" && !n.disabled);
    return this.tous((n) => classes.length && classes.every((c) => n.classList.contains(c)));
  }
}
const racine = new Noeud("html");
const corps = new Noeud("body");
racine.append(corps);
const ecouteurs = [];
globalThis.document = {
  documentElement: racine, body: corps, activeElement: null,
  createElement: (t) => new Noeud(t),
  addEventListener: (n, f, capture) => ecouteurs.push({n, f, capture}),
  removeEventListener: (n, f) => { const i = ecouteurs.findIndex((e) => e.n === n && e.f === f); if (i >= 0) ecouteurs.splice(i, 1); },
  querySelector: (sel) => corps.querySelectorAll(sel)[0] || null,
};
// Livre une touche comme le navigateur : écouteurs du document en capture, dans l'ordre d'enregistrement ; s'arrête
// après un stopImmediatePropagation (pas après un simple stopPropagation, qui ne coupe pas le même noeud).
function touche(key, extra = {}) {
  const ev = {key, shiftKey: false, ...extra, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}};
  for (const e of [...ecouteurs]) if (e.n === "keydown") e.f(ev);
  return ev;
}

const {ouvrirVisionneuse, fermerVisionneuse, visionneuseOuverte} = await import("../ui/visionneuse.js");
const V = await import("../ui/validation.js");

const url = (c) => "/api/image?chemin=" + c;
const nb = (cls) => corps.tous((n) => n.classList.contains(cls)).length;
const IMAGES = [{chemin: "a.png", legende: "A"}, {chemin: "b.png", legende: "B"}];
function remettre() { fermerVisionneuse(); corps.enfants = []; corps.classList = new Liste(); ecouteurs.length = 0; document.activeElement = null; }

test("seule : bouton Fermer (×) nommé, Échap, clic sur le fond et sur l'image ferment ; le focus revient ; le défilement est rétabli", () => {
  for (const comment of ["fermer", "echap", "fond", "image"]) {
    remettre();
    const vignette = document.createElement("button");
    corps.append(vignette);
    vignette.focus();
    ouvrirVisionneuse(IMAGES, 0, url, vignette);
    const fond = corps.tous((n) => n.classList.contains("visionneuse"))[0];
    assert.ok(fond, "ouverte");
    assert.ok(corps.classList.contains("visionneuse-ouverte"), "défilement bloqué");
    const bouton = fond.tous((n) => n.classList.contains("visionneuse-fermer"))[0];
    assert.equal(bouton.textContent, "×");
    assert.equal(bouton.attributs["aria-label"], "Fermer");
    assert.equal(document.activeElement, bouton, "le focus est sur Fermer");
    if (comment === "fermer") bouton.click();
    if (comment === "echap") assert.ok(touche("Escape").defaultPrevented);
    if (comment === "fond") fond.auteurs.click[0]({target: fond});
    if (comment === "image") fond.tous((n) => n.tagName === "img")[0].click();
    assert.equal(nb("visionneuse"), 0, comment);
    assert.equal(corps.classList.contains("visionneuse-ouverte"), false, comment);
    assert.equal(document.activeElement, vignette, "focus rendu à la vignette : " + comment);
    assert.equal(ecouteurs.length, 0, "plus d'écouteur de clavier");
    assert.equal(visionneuseOuverte(), false);
  }
});

test("un clic sur un bouton de la visionneuse (pas sur le fond) ne la ferme pas ; les flèches font le tour", () => {
  remettre();
  ouvrirVisionneuse(IMAGES, 0, url);
  const fond = corps.tous((n) => n.classList.contains("visionneuse"))[0];
  const img = fond.tous((n) => n.tagName === "img")[0];
  fond.auteurs.click[0]({target: img});     // un clic qui monte de l'image : l'image a son propre écouteur
  assert.equal(img.src, "/api/image?chemin=a.png");
  touche("ArrowRight");
  assert.equal(img.src, "/api/image?chemin=b.png");
  touche("ArrowRight");
  assert.equal(img.src, "/api/image?chemin=a.png");
});

test("dans la fenêtre de validation : au-dessus (dans le body, après la fenêtre), Échap ferme la visionneuse seule, la fenêtre reste utilisable", () => {
  remettre();
  const D = {id: "v7", genre: "valider_etape", texte: "x", fonctionnalite: "f1", element: {id: "e1", nom: "Jeu"},
    fichiers: [{chemin: "p/menu.png", titre: "Le menu"}, {chemin: "p/aide.png", titre: "L'aide"}], points: ["Le jeu se lance"]};
  const ctx = {etat: {agir: true}, barre: {demander: async () => ({ok: true})}};
  const declencheur = document.createElement("button");
  corps.append(declencheur);
  declencheur.focus();
  const fermerFenetre = V.ouvrirValidation(ctx, D, declencheur);
  assert.ok(corps.classList.contains("val-ouverte"));
  const vignettes = corps.tous((n) => n.classList.contains("val-vignette"));
  assert.equal(vignettes.length, 2);
  vignettes[1].focus();
  vignettes[1].click();
  const visio = corps.tous((n) => n.classList.contains("visionneuse"))[0];
  assert.ok(visio, "visionneuse ouverte");
  assert.ok(corps.enfants.indexOf(visio) > corps.enfants.indexOf(corps.tous((n) => n.classList.contains("val-fond"))[0]),
    "après la fenêtre dans le body (et z-index plus haut dans la feuille de style)");
  assert.ok(visio.tous((n) => n.classList.contains("visionneuse-fermer")).length === 1, "bouton Fermer présent");
  // Tab ne ramène pas le focus dans la fenêtre : il reste entre les boutons de la visionneuse
  touche("Tab");
  assert.ok(visio.contains(document.activeElement));
  // Échap : la visionneuse seule
  touche("Escape");
  assert.equal(nb("visionneuse"), 0);
  assert.equal(nb("val-fond"), 1, "la fenêtre reste ouverte");
  assert.ok(corps.classList.contains("val-ouverte"), "page de fond toujours bloquée");
  assert.equal(corps.classList.contains("visionneuse-ouverte"), false);
  assert.equal(document.activeElement, vignettes[1], "focus rendu à la vignette");
  // la fenêtre répond encore : un second Échap la ferme
  touche("Escape");
  assert.equal(nb("val-fond"), 0);
  assert.equal(corps.classList.contains("val-ouverte"), false, "défilement rétabli");
  assert.equal(document.activeElement, declencheur);
  assert.equal(ecouteurs.length, 0);
  fermerFenetre();   // déjà fermée : sans effet fâcheux
});

test("chemin inverse : fermer la fenêtre pendant que la visionneuse est ouverte ferme les deux, défilement rétabli", () => {
  remettre();
  const D = {id: "v8", genre: "valider_etape", texte: "x", fonctionnalite: "f1", element: {id: "e1", nom: "Jeu"},
    fichiers: [{chemin: "p/menu.png", titre: "Le menu"}], points: ["Le jeu se lance"]};
  const fermerFenetre = V.ouvrirValidation({etat: {agir: true}, barre: {demander: async () => ({ok: true})}}, D, null);
  corps.tous((n) => n.classList.contains("val-vignette"))[0].click();
  assert.equal(nb("visionneuse"), 1);
  fermerFenetre();
  assert.equal(nb("visionneuse"), 0);
  assert.equal(nb("val-fond"), 0);
  assert.equal(corps.classList.contains("val-ouverte"), false);
  assert.equal(corps.classList.contains("visionneuse-ouverte"), false);
  assert.equal(ecouteurs.length, 0);
  assert.equal(visionneuseOuverte(), false);
});

test("rouvrir une visionneuse remplace la précédente ; la feuille de style la met au-dessus de la fenêtre et agrandit le ×", async () => {
  remettre();
  ouvrirVisionneuse(IMAGES, 0, url);
  ouvrirVisionneuse(IMAGES, 1, url);
  assert.equal(nb("visionneuse"), 1);
  assert.equal(ecouteurs.length, 1);
  const {readFileSync} = await import("node:fs");
  const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
  const z = (re) => Number(css.match(re)[1]);
  assert.ok(z(/\n\.visionneuse \{[^}]*z-index: (\d+)/) > z(/\n\.val-fond \{[^}]*z-index: (\d+)/));
  assert.ok(z(/\.visionneuse-fermer \{[^}]*width: (\d+)px/) >= 44, "assez grand au doigt");
  assert.match(css, /body\.val-ouverte, body\.visionneuse-ouverte \{ overflow: hidden/);
  assert.doesNotMatch(css, /val-image\.agrandie/);
});
