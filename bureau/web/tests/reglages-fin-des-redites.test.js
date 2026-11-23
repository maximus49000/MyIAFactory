// « Un réglage, un seul endroit » : les six réglages à cases ne sont plus dans Direction ni dans Facturation ;
// ils vivent dans la page Réglages. Le serveur garde ses clés ; `ctx.etat` porte toujours les valeurs effectives.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const inseres = [];   // tout ce que Direction a inséré « après » le titre de « Leçons à valider »
class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; this.disabled = false; this.checked = false; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  after(...e) { inseres.push(...e); }
  replaceChildren(...e) { this.enfants = e; }
  get selectedOptions() { return []; }
  querySelector() { return new Noeud("h3"); }
  querySelectorAll() { return []; }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };
globalThis.window = globalThis.window || {confirm: () => true};

const {contenuDirecteur} = await import("../ui/directeur.js");
import {enregistrerCloudDossierApprouve, demandeRelancerSession} from "../ui/actions.js";
const lire = (chemin) => readFileSync(new URL(chemin, import.meta.url), "utf8");

const LIBELLES = [/Valider les leçons automatiquement/, /Analyse intelligente des blocages/, /Livrer seulement sur demande/,
  /Évolution moyenne : une seule session/, /Dossier approuvé pour les sessions cloud/, /Livrer automatiquement sur GitHub/,
  /Partager les connaissances/, /Partage des connaissances/];

const ETAT = {version: 4, agir: true, decisions: 0, lecons_auto: true, analyse_blocages: true, livraison_sur_demande: true,
  une_session_moyenne: true, cloud_dossier_approuve: true, livraison_github: true,
  lecons: [{id: "l1", texte: "Toujours lancer les tests touchés.", etage: "projet", verdict_demande: null}]};

test("Direction : aucune case des six réglages, ni « Partager les connaissances »", () => {
  inseres.length = 0;
  const contenu = new Noeud("div");
  contenuDirecteur({etat: ETAT, barre: {demander: async () => ({ok: true})}}, contenu);
  for (const re of LIBELLES) assert.doesNotMatch(contenu.textContent, re);
  assert.equal(contenu.tous((n) => n.tagName === "input").length, 0, "aucune case dans Direction");
  assert.equal(inseres.length, 0, "rien n'est inséré sous le titre « Leçons à valider »");
});

test("Direction : le code des cases et du partage a disparu", () => {
  const src = lire("../ui/directeur.js");
  assert.doesNotMatch(src, /caseReglage|caseLeconsAuto|caseAnalyseBlocages|caseLivraisonSurDemande|caseUneSessionMoyenne|caseCloudDossier/);
  assert.doesNotMatch(src, /enregistrer(LeconsAuto|AnalyseBlocages|LivraisonSurDemande|UneSessionMoyenne)|AIDE_/);
  assert.doesNotMatch(src, /sectionPartage|partage\.js/);
});

test("Facturation : plus de case « Livrer automatiquement sur GitHub », « Publier maintenant » reste", () => {
  const src = lire("../ui/facturation.js");
  assert.doesNotMatch(src, /livraison_github|enregistrerLivraisonGithub|AIDE_LIVRAISON_GITHUB|Livrer automatiquement/);
  assert.match(src, /Publier maintenant/);
});

test("les écritures des réglages à cases ne sont plus dans les modules de Direction/Facturation", () => {
  assert.match(lire("../ui/actions.js"), /export function enregistrerCloudDossierApprouve/);   // la carte de décision l'utilise
  assert.match(lire("../ui/decisions.js"), /enregistrerCloudDossierApprouve/);
});

test("la page Réglages porte toujours les six lignes (cadenas pour les deux « projet seulement ») et le partage au niveau Global", () => {
  const src = lire("../ui/reglages.js");
  assert.match(src, /Partage des connaissances/);
  assert.match(src, /sectionPartage\(null, fetchFn\)/);
  assert.doesNotMatch(src, /from "\.\/directeur\.js"/);   // la page lit l'aide du registre, pas de Direction
});

test("l'approbation du dossier cloud (carte de décision) écrit toujours cloud_dossier_approuve", async () => {
  const vus = [];
  const r = await enregistrerCloudDossierApprouve(true, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  assert.equal(r.ok, true);
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.deepEqual(JSON.parse(vus[0][1].body), {cloud_dossier_approuve: true});
  await enregistrerCloudDossierApprouve(false, async (_, options) => { vus.push([_, options]); return {ok: true}; });
  assert.deepEqual(JSON.parse(vus[1][1].body), {cloud_dossier_approuve: false});
  assert.deepEqual(demandeRelancerSession("s1"), {type: "session_cloud", decision: "s1", verdict: "relancer"});
});

test("Direction : sans validation automatique et avec deux leçons en attente, « Tout valider / Tout invalider » suit le titre « Leçons à valider »", () => {
  const ancienApres = Noeud.prototype.after, ancienCherche = Noeud.prototype.querySelector;
  const posees = [];   // [le nœud après lequel on a inséré, ce qui a été inséré]
  Noeud.prototype.after = function (...e) { posees.push([this, e]); };
  Noeud.prototype.querySelector = function (sel) {
    return sel === "h3" ? this.tous((n) => n.tagName === "h3")[0] || null : null;   // le vrai titre créé, pas un nœud neuf
  };
  try {
    const etat = {...ETAT, lecons_auto: false, lecons: [
      {id: "l1", texte: "Toujours lancer les tests touchés.", etage: "projet", verdict_demande: null},
      {id: "l2", texte: "Ne jamais pousser sans relire.", etage: "projet", verdict_demande: null}]};
    const contenu = new Noeud("div");
    contenuDirecteur({etat, barre: {demander: async () => ({ok: true})}}, contenu);
    assert.equal(posees.length, 1, "une seule rangée insérée");
    const [apres, [rangee]] = posees[0];
    assert.equal(apres.tagName, "h3");
    assert.match(apres.textContent, /Leçons à valider/, "ancrée après le titre de la section");
    assert.ok(contenu.tous((n) => n === apres).length === 1, "le titre est bien dans le panneau");
    assert.match(rangee.className, /tout/);
    const libelles = rangee.enfants.map((b) => b.textContent);
    assert.deepEqual(libelles, ["Tout valider (2)", "Tout invalider (2)"]);
  } finally {
    Noeud.prototype.after = ancienApres; Noeud.prototype.querySelector = ancienCherche;
  }
});
