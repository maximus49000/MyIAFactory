// L'analyse des blocages par le Chef au bureau : la case du réglage, les blocages qu'il pose au Directeur (sa
// recommandation en premier), l'outil refusé qu'il recommande d'autoriser ou de refuser, les anomalies du logiciel.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };

const {contenuDecisionsV4} = await import("../ui/decisions.js");
const {enregistrerAnalyseBlocages, AIDE_ANALYSE_BLOCAGES, anomaliesAMontrer} = await import("../ui/directeur.js");
const {demandeBlocageAnalyse, demandeAnomalie} = await import("../ui/actions.js");

function rendre(etat) {
  const demandes = [];
  const ctx = {etat, ouvrirFonctionnalite() {},
    barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }, nouveauProjet: () => false}};
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctx, contenu);
  return {contenu, demandes};
}
const boutons = (c) => c.tous((n) => n.tagName === "button");
const cliquer = async (b) => { for (const f of b.auteurs.click || []) await f(); };

const BLOCAGE = {id: "d7", genre: "blocage_analyse", tache: "t3", motif: "echec",
  texte: "La tâche « Tests : Repos » est bloquée (l'agent n'a pas pu finir). Faut-il changer d'image d'émulateur ?",
  analyse: "Le jeu affiche un écran noir sur cette image.", question: "Faut-il changer d'image d'émulateur ?",
  recommandation: "Oui, prendre une image plus récente."};

test("un blocage analysé montre l'analyse et met la recommandation en premier", async () => {
  const {contenu, demandes} = rendre({agir: true, agents: [], fonctionnalites: [], decisions_projet: [BLOCAGE]});
  const texte = contenu.textContent;
  assert.match(texte, /Blocages analysés par le Chef/);
  assert.match(texte, /Analyse du Chef : Le jeu affiche un écran noir/);
  assert.match(texte, /Recommandation du Chef : Oui, prendre une image plus récente\./);
  const siens = boutons(contenu).map((b) => b.textContent)
    .filter((t) => ["Suivre la recommandation (recommandé)", "Répondre autrement", "Laisser bloquée"].includes(t));
  assert.deepEqual(siens, ["Suivre la recommandation (recommandé)", "Répondre autrement", "Laisser bloquée"]);
  await cliquer(boutons(contenu).find((b) => b.textContent.startsWith("Suivre")));
  assert.deepEqual(demandes, [{type: "blocage_analyse", decision: "d7", verdict: "suivre"}]);
});

test("sans blocage analysé, pas de section", () => {
  const {contenu} = rendre({agir: true, agents: [], fonctionnalites: [], decisions_projet: []});
  assert.doesNotMatch(contenu.textContent, /Blocages analysés/);
});

test("outil refusé : le verdict recommandé par le Chef vient en premier, marqué", () => {
  const outil = {id: "d2", genre: "outil_agent", agent: "a1", tache: "t3", outil: "Bash(C:/Sdk/emulator.exe:*)",
    programme: "C:/Sdk/emulator.exe", texte: "Hugo est arrêté.", analyse: "Les tests ont besoin de l'émulateur.",
    recommandation: "Autoriser.", verdict_recommande: "autoriser"};
  let {contenu} = rendre({agir: true, agents: [], fonctionnalites: [], decisions_projet: [outil]});
  const libelles = (c) => boutons(c).map((b) => b.textContent).filter((t) => /Autoriser|Refuser/.test(t));
  assert.deepEqual(libelles(contenu), ["Autoriser ce programme pour cet agent (recommandé)", "Refuser"]);
  assert.match(contenu.textContent, /Analyse du Chef : Les tests ont besoin/);
  ({contenu} = rendre({agir: true, agents: [], fonctionnalites: [], decisions_projet: [{...outil, verdict_recommande: "refuser"}]}));
  assert.deepEqual(libelles(contenu), ["Refuser (recommandé)", "Autoriser ce programme pour cet agent"]);
  ({contenu} = rendre({agir: true, agents: [], fonctionnalites: [], decisions_projet: [{...outil, analyse: undefined,
    recommandation: undefined, verdict_recommande: undefined}]}));
  assert.deepEqual(libelles(contenu), ["Autoriser ce programme pour cet agent", "Refuser"]);    // comme avant
});

test("les demandes : répondre autrement porte le texte, l'anomalie son état", () => {
  assert.deepEqual(demandeBlocageAnalyse(BLOCAGE, "preciser", "  Garder l'image.  "),
    {type: "blocage_analyse", decision: "d7", verdict: "preciser", texte: "Garder l'image."});
  assert.deepEqual(demandeBlocageAnalyse(BLOCAGE, "laisser"), {type: "blocage_analyse", decision: "d7", verdict: "laisser"});
  assert.deepEqual(demandeAnomalie({id: "a1"}, "reglee"), {type: "anomalie", anomalie: "a1", etat: "reglee"});
});

test("les anomalies : les plus récentes d'abord, les réglées à la fin", () => {
  const etat = {anomalies_logiciel: [{id: "a1", etat: "reglee"}, {id: "a2", etat: "nouvelle"}, {id: "a3", etat: "vue"}]};
  assert.deepEqual(anomaliesAMontrer(etat).map((a) => a.id), ["a3", "a2", "a1"]);
  assert.deepEqual(anomaliesAMontrer({}), []);
});

test("la case « Analyse intelligente des blocages » écrit analyse_blocages", async () => {
  assert.match(AIDE_ANALYSE_BLOCAGES, /n'ouvre jamais un outil/);
  const vus = [];
  const r = await enregistrerAnalyseBlocages(false, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  assert.equal(r.ok, true);
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.deepEqual(JSON.parse(vus[0][1].body), {analyse_blocages: false});
  const coupe = await enregistrerAnalyseBlocages(true, async () => { throw new Error("réseau"); });
  assert.deepEqual(coupe, {ok: false, message: "Serveur du bureau injoignable."});
});
