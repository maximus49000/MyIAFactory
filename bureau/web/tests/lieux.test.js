// Où s'exécutent les étapes : la section de l'espace de direction, la carte de découpage et la mention de la fiche.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; this.disabled = false; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };

const {sectionLieux, carteDecoupage, demandeLieuEtape, demandeProposerDecoupage, demandeDecoupage, libelleLieu} = await import("../ui/lieux.js");
const {boutonDemande, contenuDecisionsV4} = await import("../ui/decisions.js");
const {contenuTache} = await import("../ui/detail.js");

const ETAPES = [
  {id: "proto", nom: "Prototype", role: "dev", validation: false, lieu: null, suggeree: true},
  {id: "build", nom: "Build", role: "dev", validation: false, lieu: "local", exige_poste: true},
  {id: "tests", nom: "Tests", role: "qa", validation: false, lieu: "indifférent"},
  {id: "essai", nom: "Essai", validation: true, lieu: null}];
const DECISION = {id: "d1", genre: "decoupage_lieux", texte: "Découper les étapes selon le poste.", message: "Le build exige Godot.",
  avant: [{id: "build", nom: "Build", role: "dev"}, {id: "essai", nom: "Essai", validation: true}],
  apres: [{id: "build", nom: "Build : code", role: "dev", lieu: "indifférent"}, {id: "build-local", nom: "Build : poste", role: "dev", lieu: "local"},
    {id: "essai", nom: "Essai", validation: true}]};

function ctxDe(etat, reponse = {ok: true}) {
  const demandes = [];
  return {demandes, etat: {agir: true, version: 4, ...etat},
    barre: {demander: async (d) => { demandes.push(d); return reponse; }, nouveauProjet: () => false}, ouvrirFonctionnalite() {}};
}
const boutons = (c) => c.tous((n) => n.tagName === "button");
const bouton = (c, l) => boutons(c).find((b) => b.textContent === l);
const menus = (c) => c.tous((n) => n.tagName === "select");

test("sans etapes_lieux, aucune section", () => {
  assert.equal(sectionLieux(ctxDe({}), boutonDemande), null);
});

test("un sélecteur par étape de flux, aucun pour une validation", () => {
  const s = sectionLieux(ctxDe({etapes_lieux: ETAPES}), boutonDemande);
  assert.equal(menus(s).length, 3);
  assert.match(s.textContent, /Où s'exécutent les étapes/);
  assert.match(s.textContent, /seul un agent local/);
  assert.match(s.textContent, /validation du Directeur/);
  const choix = menus(s)[2].enfants.map((o) => o.textContent);
  assert.deepEqual(choix, ["Local", "Cloud", "Indifférent"]);
  assert.equal(menus(s)[2].value, "indifférent");
});

test("une étape qui exige le poste est figée sur Local, désactivée, avec sa raison", () => {
  const s = sectionLieux(ctxDe({etapes_lieux: ETAPES}), boutonDemande);
  const m = menus(s)[1];
  assert.equal(m.value, "local");
  assert.equal(m.disabled, true);
  assert.match(s.textContent, /exige les logiciels du poste/);
});

test("changer le lieu envoie lieu_etape tout de suite ; un refus remet le choix d'avant", async () => {
  const c = ctxDe({etapes_lieux: ETAPES});
  const s = sectionLieux(c, boutonDemande);
  const m = menus(s)[2];
  m.value = "cloud";
  await m.auteurs.change[0]();
  assert.deepEqual(c.demandes, [{type: "lieu_etape", etape: "tests", lieu: "cloud"}]);
  const refus = ctxDe({etapes_lieux: ETAPES}, {ok: false});
  const m2 = menus(sectionLieux(refus, boutonDemande))[2];
  m2.value = "local";
  await m2.auteurs.change[0]();
  assert.equal(m2.value, "indifférent");
});

test("Proposer le découpage : demande et phrase sur l'appel Sonnet ; grisé si une proposition attend", async () => {
  const c = ctxDe({etapes_lieux: ETAPES});
  const s = sectionLieux(c, boutonDemande);
  assert.match(s.textContent, /appel Sonnet/);
  await bouton(s, "Proposer le découpage").auteurs.click[0]();
  assert.deepEqual(c.demandes, [{type: "proposer_decoupage"}]);
  const attend = sectionLieux(ctxDe({etapes_lieux: ETAPES, decisions_projet: [DECISION]}), boutonDemande);
  assert.equal(bouton(attend, "Proposer le découpage").disabled, true);
});

test("pas de bouton ni de sélecteur actif quand on ne peut pas agir", () => {
  const s = sectionLieux(ctxDe({etapes_lieux: ETAPES, agir: false}), boutonDemande);
  assert.equal(bouton(s, "Proposer le découpage"), undefined);
  assert.equal(menus(s)[0].disabled, true);
});

test("la carte du découpage montre avant et après, et envoie Valider / Refuser", async () => {
  const c = ctxDe({decisions_projet: [DECISION], fonctionnalites: []});
  const contenu = new Noeud("div");
  contenuDecisionsV4(c, contenu);
  assert.match(contenu.textContent, /Découper les étapes selon le poste/);
  assert.match(contenu.textContent, /Build : poste · poste local · nouvelle partie locale/);
  assert.match(contenu.textContent, /Build : code · cloud possible/);
  await bouton(contenu, "Valider").auteurs.click[0]();
  await bouton(contenu, "Refuser").auteurs.click[0]();
  assert.deepEqual(c.demandes, [{type: "decoupage_lieux", decision: "d1", verdict: "valider"},
    {type: "decoupage_lieux", decision: "d1", verdict: "refuser"}]);
});

test("aucune carte sans proposition", () => {
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctxDe({fonctionnalites: []}), contenu);
  assert.doesNotMatch(contenu.textContent, /Découper les étapes selon le poste/);
});

test("fabriques et libellés", () => {
  assert.deepEqual(demandeLieuEtape("e", null), {type: "lieu_etape", etape: "e", lieu: null});
  assert.deepEqual(demandeProposerDecoupage(), {type: "proposer_decoupage"});
  assert.deepEqual(demandeDecoupage({id: "x"}, "refuser"), {type: "decoupage_lieux", decision: "x", verdict: "refuser"});
  assert.deepEqual([libelleLieu("local"), libelleLieu("cloud"), libelleLieu("indifférent"), libelleLieu(undefined)],
    ["poste local", "cloud", "cloud possible", "cloud possible"]);
});

test("la fiche d'une tâche dit où elle s'exécute, seulement quand le relevé le dit", () => {
  const rendre = (lieu) => {
    const t = {id: "t1", titre: "Build", colonne: "a", agent: null, etape: "", journal: [], liens: [], retours: [], images: [], notes: [], maj: "", ...(lieu ? {lieu} : {})};
    const e = {agir: false, colonnes: [{id: "a", nom: "A"}], agents: [], taches: [t], types: []};
    const contenu = new Noeud("div");
    contenuTache({etat: e}, contenu, t);
    return contenu.textContent;
  };
  assert.match(rendre("local"), /Sur le poste local/);
  assert.match(rendre("cloud"), /Dans le cloud/);
  assert.doesNotMatch(rendre(null), /poste local|Dans le cloud/);
});
