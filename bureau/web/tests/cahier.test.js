// « Ouvrir le cahier des charges » / « Ouvrir la méthode » : la liste du bureau de direction n'a plus de bouton de
// validation, la fenêtre montre le contenu en entier, et la réponse (Valider ou Demander une correction) n'est envoyée
// qu'une fois. Faux DOM avec focus, classes du body et écouteurs du document.
import test from "node:test";
import assert from "node:assert/strict";

class Liste {
  constructor() { this.s = new Set(); }
  add(c) { this.s.add(c); } remove(c) { this.s.delete(c); } contains(c) { return this.s.has(c); }
}
class Noeud {
  constructor(tag) {
    this.tagName = tag; this.enfants = []; this.parent = null; this._texte = ""; this.hidden = false; this.auteurs = {};
    this.attributs = {}; this.disabled = false; this.classList = new Liste(); this.value = ""; this.dataset = {}; this.style = {};
  }
  set className(v) { this.classList = new Liste(); for (const c of String(v).split(/\s+/).filter(Boolean)) this.classList.add(c); }
  get className() { return [...this.classList.s].join(" "); }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  get childElementCount() { return this.enfants.length; }
  get childNodes() { return this.enfants; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === document.documentElement; }
  get offsetParent() { return this.isConnected ? {} : null; }
  append(...e) { for (const x of e) { x.parent = this; this.enfants.push(x); } }
  replaceChildren(...e) { this._texte = ""; this.enfants = []; this.append(...e); }
  remove() { if (this.parent) { this.parent.enfants = this.parent.enfants.filter((x) => x !== this); this.parent = null; } if (document.activeElement && !document.activeElement.isConnected) document.activeElement = null; }
  contains(x) { for (let n = x; n; n = n.parent) if (n === this) return true; return false; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  focus() { if (this.isConnected) document.activeElement = this; }
  click() { return Promise.all((this.auteurs.click || []).map((f) => f({target: this, stopPropagation() {}}))); }
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
const memoireLocale = new Map();
globalThis.localStorage = {getItem: (k) => (memoireLocale.has(k) ? memoireLocale.get(k) : null), setItem: (k, v) => memoireLocale.set(k, String(v))};
function touche(key) {
  const ev = {key, shiftKey: false, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}};
  for (const e of [...ecouteurs]) if (e.n === "keydown") e.f(ev);
  return ev;
}

const {contenuDecisionsV4} = await import("../ui/decisions.js");
const {contenuCahierMethode, ouvrirCahier, partenairesDuCahier, resumeCahier} = await import("../ui/cahier.js");
const V = await import("../ui/validation.js");

const CAHIER = {maquette: [{chemin: "pieces/accueil.png", legende: "L'écran d'accueil"}, "pieces/menu.png"],
  etapes: ["Ouvrir le jeu", "Choisir un niveau", "Jouer"], partenaires: [{id: "tripo", mode: "direct"}, {id: "suno", mode: "inscrit"}]};
const ANCIEN = {maquette: ["pieces/v1.png"], etapes: ["Ancienne étape"], remplace_le: "2026-11-10T10:00:00+01:00"};
const DECISION_CAHIER = {id: "dc1", genre: "valider_cahier", texte: "Le cahier des charges de « Accueil » attend votre validation."};
const DECISION_METHODE = {id: "dm1", genre: "valider_methode", texte: "La méthode de « Accueil » attend votre validation."};
const etatDe = (decisions, plus = {}) => ({agir: true, images_ok: true, agents: [],
  partenaires: {categories: {"3d": [{id: "tripo", nom: "Tripo"}], "son": [{id: "suno", nom: "Suno"}]}},
  fonctionnalites: [{id: "f1", nom: "Accueil", etape: "cahier", cahier: CAHIER, cahiers_precedents: [ANCIEN], decisions,
    methode: {version: 2, chemin: "docs/methode.md"},
    documents: [{chemin: "pieces/proto.png", titre: "Le prototype", date: "2026-11-11"},
                {chemin: "build/jeu.apk", titre: "L'apk du prototype", livrable: true, taille: 2048, date: "2026-11-11"},
                {chemin: "notes/brouillon.txt", titre: "brut", date: "2026-11-11"}],
    ...plus}], ...plus.etat});
const nb = (cls) => corps.tous((n) => n.classList.contains(cls)).length;
const boutons = (c) => c.tous((n) => n.tagName === "button");
const lien = (c, t) => [...boutons(c), ...c.tous((n) => n.tagName === "a")].find((b) => b.textContent === t);
const attente = () => new Promise((r) => setTimeout(r, 0));

function liste(etat, plus = {}) {
  const demandes = [];
  const ctx = {etat, ouvrirFonctionnalite() {}, ...plus,
    barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }}};
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctx, contenu);
  return {contenu, demandes, ctx};
}

test("la liste : le résumé et « Ouvrir … » seulement, aucun bouton Valider ni Corriger", () => {
  const ouvertes = [];
  const etat = etatDe([DECISION_CAHIER, DECISION_METHODE]);
  const {contenu, demandes, ctx} = liste(etat, {ouvrirCahier: (c, d, b) => ouvertes.push([c, d, b])});
  assert.match(contenu.textContent, /Le cahier des charges de « Accueil » attend votre validation/);
  assert.match(contenu.textContent, /2 maquettes · 3 étapes · 2 partenaires/);
  assert.match(contenu.textContent, /Méthode, version 2/);
  const libelles = boutons(contenu).map((b) => b.textContent);
  for (const interdit of ["Valider le cahier", "Valider la méthode", "Valider", "Demander une correction", "Corriger"]) {
    assert.ok(!libelles.includes(interdit), interdit);
  }
  assert.doesNotMatch(contenu.textContent, /Ouvrir le jeu|Choisir un niveau/);          // le contenu est dans la fenêtre
  const b = lien(contenu, "Ouvrir le cahier des charges");
  b.auteurs.click[0]();
  assert.ok(lien(contenu, "Ouvrir la méthode"));
  lien(contenu, "Ouvrir la méthode").auteurs.click[0]();
  assert.equal(ouvertes.length, 2);
  assert.equal(ouvertes[0][0], ctx);
  assert.equal(ouvertes[0][1].id, "dc1");
  assert.equal(ouvertes[0][1].fonctionnalite, "f1");
  assert.equal(ouvertes[1][1].id, "dm1");
  assert.deepEqual(demandes, []);                                                      // ouvrir n'envoie rien
});

test("la liste : une entrée déjà répondue disparaît (cahier comme méthode)", () => {
  const etat = etatDe([{...DECISION_CAHIER, id: "dc-envoyee"}, {...DECISION_METHODE, id: "dm-envoyee"}]);
  assert.ok(lien(liste(etat).contenu, "Ouvrir le cahier des charges"));
  V.marquerEnvoyee("dc-envoyee");
  V.marquerEnvoyee("dm-envoyee");
  const apres = liste(etat).contenu;
  assert.equal(lien(apres, "Ouvrir le cahier des charges"), undefined);
  assert.equal(lien(apres, "Ouvrir la méthode"), undefined);
  assert.match(apres.textContent, /Aucun cahier ni méthode à valider/);
  V.oublierEnvoyee("dc-envoyee");
  V.oublierEnvoyee("dm-envoyee");
  assert.ok(lien(liste(etat).contenu, "Ouvrir le cahier des charges"));                 // l'envoi a échoué : elle revient
});

test("le cahier ouvert : maquettes légendées, étapes numérotées, partenaires, versions précédentes repliées", () => {
  const ctx = {etat: etatDe([DECISION_CAHIER]), barre: {}};
  const {boite} = contenuCahierMethode(ctx, {...DECISION_CAHIER, fonctionnalite: "f1"});
  assert.match(boite.textContent, /Cahier des charges : Accueil/);
  assert.match(boite.textContent, /L'écran d'accueil/);                                  // la légende
  const vignettes = boite.tous((n) => n.classList.contains("val-vignette"));
  assert.equal(vignettes.length, 3);                                                     // 2 maquettes + 1 de la version précédente
  assert.match(boite.tous((n) => n.tagName === "img")[0].src, /api\/image\?chemin=pieces%2Faccueil\.png/);
  const etapes = boite.tous((n) => n.tagName === "ol" && n.classList.contains("val-etapes"));
  assert.deepEqual(etapes[0].enfants.map((li) => li.textContent), ["Ouvrir le jeu", "Choisir un niveau", "Jouer"]);
  assert.match(boite.textContent, /Partenaires choisis/);
  assert.match(boite.textContent, /Tripo : appelé directement par l'agent/);
  assert.match(boite.textContent, /Suno : à faire par vous, sur son site/);
  const versions = boite.tous((n) => n.tagName === "details" && n.classList.contains("val-versions"))[0];
  assert.ok(versions, "versions repliées dans un <details>");
  assert.notEqual(versions.open, true);
  assert.match(versions.textContent, /Versions précédentes \(1\)/);
  assert.match(versions.textContent, /Ancienne étape/);
  assert.ok(!boite.tous((n) => n.classList.contains("val-partie")).some((s) => s.textContent.includes("Ancienne étape")));
});

test("sans partenaire ni version précédente, rien n'est inventé", () => {
  const etat = etatDe([DECISION_CAHIER]);
  etat.fonctionnalites[0].cahier = {maquette: [], etapes: ["Seule étape"]};
  etat.fonctionnalites[0].cahiers_precedents = [];
  const {boite} = contenuCahierMethode({etat, barre: {}}, {...DECISION_CAHIER, fonctionnalite: "f1"});
  assert.doesNotMatch(boite.textContent, /Partenaires choisis|Versions précédentes/);
  assert.equal(boite.tous((n) => n.classList.contains("val-vignette")).length, 0);
  assert.deepEqual(partenairesDuCahier(etat, etat.fonctionnalites[0].cahier), []);
  assert.equal(resumeCahier(etat, {...DECISION_CAHIER, fonctionnalite: "f1"}), "1 étape");
});

test("partenairesDuCahier : nom du catalogue, sinon l'identifiant", () => {
  const e = etatDe([]);
  assert.deepEqual(partenairesDuCahier(e, {partenaires: [{id: "tripo", mode: "direct"}, {id: "inconnu", mode: "aucun"}]}).map((p) => [p.nom, p.libelle]),
    [["Tripo", "appelé directement par l'agent"], ["inconnu", "écarté : pas de partenaire pour ce besoin"]]);
});

test("la méthode ouverte : son contenu en Markdown (tableau compris), son prototype, ses livrables", async () => {
  const lus = [];
  globalThis.fetch = async (url) => { lus.push(url); return {ok: true, text: async () => "# Méthode\n\nUn **texte**.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"}; };
  const ctx = {etat: etatDe([DECISION_METHODE]), barre: {}};
  const {boite} = contenuCahierMethode(ctx, {...DECISION_METHODE, fonctionnalite: "f1"});
  await attente();
  assert.match(boite.textContent, /Méthode : Accueil/);
  assert.match(boite.textContent, /Méthode \(version 2\)/);
  assert.match(lus[0], /api\/methode\?fonctionnalite=f1/);
  assert.equal(boite.tous((n) => n.tagName === "table").length, 1);
  assert.equal(boite.tous((n) => n.tagName === "strong")[0]?.textContent !== undefined, true);
  assert.match(boite.textContent, /Un texte\./);
  assert.equal(boite.tous((n) => n.classList.contains("val-vignette")).length, 1);        // l'image du prototype
  assert.match(boite.tous((n) => n.tagName === "img")[0].src, /api\/document\?fonctionnalite=f1&chemin=pieces%2Fproto\.png/);
  const dl = boite.tous((n) => n.tagName === "a" && n.textContent === "Télécharger");
  assert.equal(dl.length, 2);                                                            // l'apk et le .txt téléchargeable
  assert.ok(dl.some((a) => /api\/telecharger\?fonctionnalite=f1&chemin=build%2Fjeu\.apk/.test(a.href)));
  assert.match(boite.textContent, /L'apk du prototype/);
});

test("la méthode illisible : un message, la fenêtre reste utilisable", async () => {
  globalThis.fetch = async () => { throw new Error("réseau"); };
  const ctx = {etat: etatDe([DECISION_METHODE]), barre: {}};
  const {boite} = contenuCahierMethode(ctx, {...DECISION_METHODE, fonctionnalite: "f1"});
  await attente();
  assert.match(boite.textContent, /Méthode illisible ici/);
  assert.ok(lien(boite, "Valider"));
});

test("Valider : une seule demande, l'entrée disparaît dès l'envoi, la fenêtre se ferme", async () => {
  const demandes = [], vus = [];
  let fermee = 0;
  const etat = etatDe([{...DECISION_CAHIER, id: "dc-v"}]);
  const ctx = {etat, barre: {demander: async (d) => {
    demandes.push(d);
    vus.push(V.appliquerEnvoyees(etat).fonctionnalites[0].decisions.length);              // pendant l'envoi : déjà retirée
    return {ok: true};
  }}};
  const {boite} = contenuCahierMethode(ctx, {...etat.fonctionnalites[0].decisions[0], fonctionnalite: "f1"}, {fermer: () => { fermee++; }});
  await lien(boite, "Valider").click();
  assert.deepEqual(demandes, [{type: "cahier", fonctionnalite: "f1", verdict: "valider"}]);
  assert.deepEqual(vus, [0]);
  assert.equal(fermee, 1);
  assert.equal(liste(etat).contenu.tous((n) => n.tagName === "button" && n.textContent.startsWith("Ouvrir")).length, 0);
  V.oublierEnvoyee("dc-v");
});

test("Valider la méthode : demande « methode » / valider", async () => {
  globalThis.fetch = async () => ({ok: true, text: async () => "x"});
  const demandes = [];
  const etat = etatDe([{...DECISION_METHODE, id: "dm-v"}]);
  const ctx = {etat, barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }}};
  const {boite} = contenuCahierMethode(ctx, {...DECISION_METHODE, id: "dm-v", fonctionnalite: "f1"});
  await lien(boite, "Valider").click();
  assert.deepEqual(demandes, [{type: "methode", fonctionnalite: "f1", verdict: "valider"}]);
  V.oublierEnvoyee("dm-v");
});

test("Demander une correction : le texte est obligatoire, puis il part avec le verdict (cahier : corriger, méthode : revoir)", async () => {
  globalThis.fetch = async () => ({ok: true, text: async () => "x"});
  const demandes = [];
  const etat = etatDe([DECISION_CAHIER, DECISION_METHODE]);
  const ctx = {etat, barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }}};
  const c = contenuCahierMethode(ctx, {...DECISION_CAHIER, id: "dc-c", fonctionnalite: "f1"}).boite;
  const zone = c.tous((n) => n.tagName === "textarea")[0];
  zone.value = "   ";
  await lien(c, "Demander une correction").click();
  assert.deepEqual(demandes, []);                                                        // rien ne part sans texte
  assert.match(c.textContent, /Écrivez ce qu'il faut corriger/);
  assert.equal(V.estEnvoyee("dc-c"), false);                                             // et l'entrée reste
  zone.value = " Ajouter un écran d'aide. ";
  await lien(c, "Demander une correction").click();
  assert.deepEqual(demandes, [{type: "cahier", fonctionnalite: "f1", verdict: "corriger", texte: "Ajouter un écran d'aide."}]);
  assert.equal(V.estEnvoyee("dc-c"), true);
  const m = contenuCahierMethode(ctx, {...DECISION_METHODE, id: "dm-c", fonctionnalite: "f1"}).boite;
  m.tous((n) => n.tagName === "textarea")[0].value = "Le mode opératoire est trop long.";
  await lien(m, "Demander une correction").click();
  assert.deepEqual(demandes[1], {type: "methode", fonctionnalite: "f1", verdict: "revoir", texte: "Le mode opératoire est trop long."});
  V.oublierEnvoyee("dc-c");
  V.oublierEnvoyee("dm-c");
});

test("envoi refusé : l'entrée revient avec le message ; « déjà reçu » reste masquée", async () => {
  const reponses = [{ok: false, message: "Le moteur est occupé."}, {ok: false, message: "Demande déjà reçue."}];
  const etat = etatDe([{...DECISION_CAHIER, id: "dc-e"}]);
  const ctx = {etat, barre: {demander: async () => reponses.shift()}};
  let fermee = 0;
  const {boite} = contenuCahierMethode(ctx, {...DECISION_CAHIER, id: "dc-e", fonctionnalite: "f1"}, {fermer: () => { fermee++; }});
  await lien(boite, "Valider").click();
  assert.match(boite.textContent, /Le moteur est occupé/);
  assert.equal(V.estEnvoyee("dc-e"), false);                                             // revenue
  assert.equal(lien(boite, "Valider").disabled, false);
  assert.equal(fermee, 0);
  await lien(boite, "Valider").click();
  assert.equal(V.estEnvoyee("dc-e"), true);                                              // 409 : reste masquée
  V.oublierEnvoyee("dc-e");
});

test("appliquerEnvoyees : cahier et méthode retirés des décisions de la fonctionnalité, compteurs ajustés, purge quand levée", () => {
  const etat = {...etatDe([{...DECISION_CAHIER, id: "x1"}, {...DECISION_METHODE, id: "x2"}, {id: "x3", genre: "environnement", texte: "t"}]),
    decisions_projet: [], directeur: {total: 5, projet: 0, fonctionnalites: 3}};
  V.marquerEnvoyee("x1");
  const vu = V.appliquerEnvoyees(etat);
  assert.deepEqual(vu.fonctionnalites[0].decisions.map((d) => d.id), ["x2", "x3"]);
  assert.deepEqual([vu.directeur.total, vu.directeur.fonctionnalites, vu.directeur.projet], [4, 2, 0]);
  assert.equal(etat.fonctionnalites[0].decisions.length, 3);                             // l'état servi n'est pas modifié
  const levee = {...etat, fonctionnalites: [{...etat.fonctionnalites[0], decisions: [etat.fonctionnalites[0].decisions[2]]}]};
  V.appliquerEnvoyees(levee);                                                            // x1 n'est plus servie : oubliée
  assert.equal(V.estEnvoyee("x1"), false);
});

test("ouvrirCahier : fenêtre par-dessus le bureau, Échap ferme, focus rendu, visionneuse d'une maquette au-dessus", () => {
  const ctx = {etat: etatDe([DECISION_CAHIER]), barre: {demander: async () => ({ok: true})}};
  const declencheur = new Noeud("button");
  corps.append(declencheur);
  declencheur.focus();
  const fermer = ouvrirCahier(ctx, {...DECISION_CAHIER, fonctionnalite: "f1"}, declencheur);
  assert.equal(nb("val-fond"), 1);
  assert.ok(corps.classList.contains("val-ouverte"));
  assert.equal(corps.tous((n) => n.classList.contains("val-boite"))[0].attributs["aria-modal"], "true");
  const vignette = corps.tous((n) => n.classList.contains("val-vignette"))[1];
  vignette.focus();
  vignette.click();
  assert.equal(nb("visionneuse"), 1);
  touche("Escape");                                                                      // la visionneuse seule
  assert.equal(nb("visionneuse"), 0);
  assert.equal(nb("val-fond"), 1);
  assert.equal(document.activeElement, vignette);
  touche("Escape");
  assert.equal(nb("val-fond"), 0);
  assert.equal(corps.classList.contains("val-ouverte"), false);
  assert.equal(document.activeElement, declencheur);
  assert.equal(ecouteurs.length, 0);
  fermer();
});

test("ouvrirCahier : un clic hors de la fenêtre la ferme ; le bouton × aussi", () => {
  const ctx = {etat: etatDe([DECISION_CAHIER]), barre: {}};
  ouvrirCahier(ctx, {...DECISION_CAHIER, fonctionnalite: "f1"});
  const fond = corps.tous((n) => n.classList.contains("val-fond"))[0];
  fond.auteurs.mousedown[0]({target: corps});                                            // dans la page, pas sur le fond
  assert.equal(nb("val-fond"), 1);
  fond.auteurs.mousedown[0]({target: fond});
  assert.equal(nb("val-fond"), 0);
  ouvrirCahier(ctx, {...DECISION_CAHIER, fonctionnalite: "f1"});
  corps.tous((n) => n.classList.contains("val-fermer"))[0].click();
  assert.equal(nb("val-fond"), 0);
});

test("sans le droit d'agir ou déjà répondu : le contenu se lit, aucun bouton de réponse", () => {
  const lecture = contenuCahierMethode({etat: {...etatDe([DECISION_CAHIER]), agir: false}, barre: {}}, {...DECISION_CAHIER, fonctionnalite: "f1"}).boite;
  assert.equal(lien(lecture, "Valider"), undefined);
  assert.match(lecture.textContent, /se lit seulement/);
  V.marquerEnvoyee("dc-deja");
  const deja = contenuCahierMethode({etat: etatDe([DECISION_CAHIER]), barre: {}}, {...DECISION_CAHIER, id: "dc-deja", fonctionnalite: "f1"}).boite;
  assert.equal(lien(deja, "Valider"), undefined);
  assert.match(deja.textContent, /Réponse envoyée/);
  V.oublierEnvoyee("dc-deja");
});

test("le panneau de la fonctionnalité : « Ouvrir … » à la place des boutons de validation directe", async () => {
  const {contenuFonctionnalite} = await import("../ui/fonctionnalite.js");
  globalThis.requestAnimationFrame = (f) => f();
  globalThis.fetch = async () => ({ok: true, text: async () => "x"});
  const etat = etatDe([DECISION_CAHIER, DECISION_METHODE]);
  const ouvertes = [];
  const ctx = {etat, barre: {demander: async () => ({ok: true})}, corrections: new Set(), envoyes: new Map(), nouvelle: {},
    brouillons: new Map(), envois: new Map(), rouvrir() {}, ouvrirCahier: (c, d, b) => ouvertes.push(d)};
  const contenu = new Noeud("div");
  try { contenuFonctionnalite(ctx, contenu, etat.fonctionnalites[0]); } catch (e) { assert.fail("rendu du panneau : " + e.stack); }
  const libelles = boutons(contenu).map((b) => b.textContent);
  assert.ok(libelles.includes("Ouvrir le cahier des charges"));
  assert.ok(libelles.includes("Ouvrir la méthode"));
  for (const interdit of ["Valider le cahier des charges", "Valider la méthode", "Demander une correction", "Annuler la correction"]) {
    assert.ok(!libelles.includes(interdit), interdit);
  }
  await lien(contenu, "Ouvrir le cahier des charges").click();
  await lien(contenu, "Ouvrir la méthode").click();
  assert.deepEqual(ouvertes.map((d) => [d.id, d.genre, d.fonctionnalite]), [["dc1", "valider_cahier", "f1"], ["dm1", "valider_methode", "f1"]]);
});
