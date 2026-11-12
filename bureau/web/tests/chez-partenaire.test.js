// « À faire chez <partenaire> » au bureau de direction, rendu sur un faux DOM : le prompt à copier, le lien du partenaire, les
// réglages, le mode opératoire, ce qu'il faut rapporter, puis le retour (« Fait » avec le résultat joint, ou « Je n'ai pas pu »).
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; this.attributs = {}; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };

const {contenuDecisionsV4} = await import("../ui/decisions.js");
const {demandeChezPartenaire, attendUneAutre, nomPartenaire, promptACopier} = await import("../ui/chez-partenaire.js");
const {decisionsDirecteur} = await import("../ui/actions.js");

const CHEZ = {id: "d4", genre: "faire_chez_partenaire", texte: "À faire chez Tripo : Le dragon", agent: "dev-1", tache: "t3",
  partenaire: "tripo", nom_partenaire: "Tripo", site: "https://www.tripo3d.ai", quoi: "Le dragon et son œuf",
  prompt: "Un dragon vert couché sur son œuf.\nStyle cartoon.", reglages: ["Qualité : ultra", "Texture : oui"],
  mode_operatoire: ["Ouvrir le site de Tripo", "Coller le prompt", "Lancer la génération"],
  a_rapporter: {description: "Le modèle 3D en .zip", nom: "dragon.zip"}, elements: ["dragon", "œuf"]};
const ETAT = {agir: true, agents: [], fonctionnalites: [], decisions_projet: [CHEZ]};

function rendre(etat = ETAT) {
  const demandes = [];
  const ctx = {etat, ouvrirFonctionnalite() {}, barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }}};
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctx, contenu);
  return {contenu, demandes};
}
const boutons = (c) => c.tous((n) => n.tagName === "button");
const bouton = (c, libelle) => boutons(c).find((b) => b.textContent === libelle);
const champ = (c, classe) => c.tous((n) => n.className === classe)[0];

test("la demande est rangée dans « À faire chez un partenaire », absente sans demande", () => {
  assert.equal(decisionsDirecteur(ETAT).chezPartenaires.length, 1);
  const {contenu} = rendre();
  assert.match(contenu.textContent, /À faire chez un partenaire/);
  assert.match(contenu.textContent, /À faire chez Tripo/);
  assert.doesNotMatch(rendre({...ETAT, decisions_projet: []}).contenu.textContent, /À faire chez un partenaire/);
});

test("le prompt, les réglages, le mode opératoire et ce qu'il faut rapporter sont montrés", () => {
  const {contenu} = rendre();
  const t = contenu.textContent;
  assert.match(t, /pour : Le dragon et son œuf/);
  assert.match(t, /Prompt \(49 caractères\)/);
  assert.equal(champ(contenu, "chez-prompt").value, CHEZ.prompt);
  assert.equal(champ(contenu, "chez-prompt").readOnly, true);
  assert.match(t, /Qualité : ultra/);
  assert.match(t, /Texture : oui/);
  assert.match(t, /Éléments groupés dans cette génération : dragon, œuf/);
  assert.deepEqual(champ(contenu, "chez-etapes").enfants.map((e) => e.textContent), CHEZ.mode_operatoire);
  assert.match(t, /À rapporter : Le modèle 3D en \.zip \(nom attendu : dragon\.zip\)/);
  assert.match(t, /glb, fbx, obj/);       // un type non accepté : un zip, ou le dossier du projet
});

test("lien vers le site du partenaire : https seulement, en nouvel onglet sans fuite", () => {
  const lien = rendre().contenu.tous((n) => n.tagName === "a")[0];
  assert.equal(lien.textContent, "Ouvrir Tripo");
  assert.equal(lien.href, "https://www.tripo3d.ai");
  assert.equal(lien.rel, "noopener noreferrer");
  assert.equal(lien.target, "_blank");
  for (const mauvais of ["javascript:alert(1)", "http://tripo3d.ai", "data:text/html,x", undefined]) {
    const {contenu} = rendre({...ETAT, decisions_projet: [{...CHEZ, site: mauvais}]});
    assert.equal(contenu.tous((n) => n.tagName === "a").length, 0, String(mauvais));
  }
});

test("Copier le prompt met le prompt, et seulement lui, dans le presse-papiers", async () => {
  const copies = [];
  Object.defineProperty(globalThis, "navigator", {configurable: true, value: {clipboard: {writeText: async (t) => { copies.push(t); }}}});
  const {contenu} = rendre();
  await bouton(contenu, "Copier le prompt").auteurs.click[0]();
  assert.deepEqual(copies, [CHEZ.prompt]);
  assert.equal(promptACopier(CHEZ), CHEZ.prompt);
  assert.match(contenu.textContent, /Prompt copié\./);
  Object.defineProperty(globalThis, "navigator", {configurable: true, value: {clipboard: {writeText: async () => { throw new Error("refusé"); }}}});
  const autre = rendre().contenu;
  await bouton(autre, "Copier le prompt").auteurs.click[0]();
  assert.match(autre.textContent, /La copie n'a pas pu se faire/);
});

test("texte hostile : littéral (textContent), jamais du HTML", () => {
  const {contenu} = rendre({...ETAT, decisions_projet: [{...CHEZ, prompt: "<img src=x onerror=alert(1)>", reglages: ["<b>gras</b>"]}]});
  assert.equal(champ(contenu, "chez-prompt").value, "<img src=x onerror=alert(1)>");
  assert.match(contenu.textContent, /<b>gras<\/b>/);
  assert.equal(contenu.tous((n) => n.tagName === "img" || n.tagName === "b").length, 0);
});

test("« Fait » sans rien d'autre : la demande ne porte ni texte ni fichier", async () => {
  const {contenu, demandes} = rendre();
  await bouton(contenu, "Fait").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "faire_chez_partenaire", decision: "d4", verdict: "fait"}]);
});

test("« Fait » avec un mot et le résultat joint : fichiers lus en base64, nom d'origine gardé", async () => {
  const {contenu, demandes} = rendre();
  const octets = Uint8Array.from([80, 75, 3, 4, 1, 2, 3]);       // « PK\x03\x04… » : un zip
  const fichier = {name: "dragon.zip", size: octets.length, type: "application/zip", arrayBuffer: async () => octets.buffer};
  const entree = champ(contenu, "chez-fichiers");
  entree.files = [fichier];
  await entree.auteurs.change[0]();
  assert.match(contenu.textContent, /Joints : dragon\.zip/);
  champ(contenu, "chez-texte").value = "  Qualité ultra, deux essais.  ";
  await bouton(contenu, "Fait").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "faire_chez_partenaire", decision: "d4", verdict: "fait", texte: "Qualité ultra, deux essais.",
    fichiers: [{nom: "dragon.zip", type: "application/zip", donnees: Buffer.from(octets).toString("base64")}]}]);
});

test("un fichier d'un type refusé n'est pas joint, et le dit", async () => {
  const {contenu, demandes} = rendre();
  const entree = champ(contenu, "chez-fichiers");
  entree.files = [{name: "virus.exe", size: 10, type: "application/octet-stream", arrayBuffer: async () => new ArrayBuffer(10)}];
  await entree.auteurs.change[0]();
  assert.match(contenu.textContent, /pas accepté/);
  await bouton(contenu, "Fait").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "faire_chez_partenaire", decision: "d4", verdict: "fait"}]);
});

test("« Je n'ai pas pu » demande de dire ce qui a bloqué, puis l'envoie sans fichier", async () => {
  const {contenu, demandes} = rendre();
  await bouton(contenu, "Je n'ai pas pu").auteurs.click[0]();
  assert.deepEqual(demandes, []);
  assert.match(contenu.textContent, /Dites ce qui a bloqué/);
  champ(contenu, "chez-texte").value = "Plus de crédits ce mois-ci.";
  await bouton(contenu, "Je n'ai pas pu").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "faire_chez_partenaire", decision: "d4", verdict: "impossible", texte: "Plus de crédits ce mois-ci."}]);
});

test("une génération à la fois : la demande qui vient après n'a pas de boutons de retour, jusqu'à ce que l'autre soit faite", () => {
  const suivante = {...CHEZ, id: "d5", quoi: "Le loup", apres: "d4"};
  const etat = {...ETAT, decisions_projet: [CHEZ, suivante]};
  assert.equal(attendUneAutre(suivante, etat.decisions_projet), true);
  assert.equal(attendUneAutre(CHEZ, etat.decisions_projet), false);
  const {contenu} = rendre(etat);
  assert.match(contenu.textContent, /cette demande vient après la demande d4/);
  assert.equal(boutons(contenu).filter((b) => b.textContent === "Fait").length, 1);        // celle de d4 seulement
  assert.equal(boutons(contenu).filter((b) => b.textContent === "Copier le prompt").length, 2);   // mais le prompt reste lisible
  const seule = rendre({...ETAT, decisions_projet: [suivante]}).contenu;                   // d4 est faite : d5 vient
  assert.equal(boutons(seule).filter((b) => b.textContent === "Fait").length, 1);
  assert.doesNotMatch(seule.textContent, /vient après/);
});

test("sans le droit d'agir : tout est lisible, aucun bouton de retour", () => {
  const {contenu} = rendre({...ETAT, agir: false});
  assert.match(contenu.textContent, /À faire chez Tripo/);
  assert.equal(boutons(contenu).filter((b) => ["Fait", "Je n'ai pas pu"].includes(b.textContent)).length, 0);
});

test("demandeChezPartenaire : le texte est taillé, les fichiers réduits à nom, type et données", () => {
  assert.deepEqual(demandeChezPartenaire(CHEZ, "fait", "   "), {type: "faire_chez_partenaire", decision: "d4", verdict: "fait"});
  assert.deepEqual(demandeChezPartenaire(CHEZ, "fait", " ok ", [{nom: "a.zip", type: "application/zip", donnees: "AAAA", taille: 3, categorie: "archive"}]),
    {type: "faire_chez_partenaire", decision: "d4", verdict: "fait", texte: "ok", fichiers: [{nom: "a.zip", type: "application/zip", donnees: "AAAA"}]});
  assert.equal(demandeChezPartenaire(CHEZ, "impossible", "non", [{nom: "a.zip", type: "x", donnees: "A"}]).fichiers, undefined);
  assert.equal(nomPartenaire({partenaire: "tripo"}), "tripo");
});
