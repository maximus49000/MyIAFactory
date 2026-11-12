// Les décisions au bureau du Directeur, rendues sur un faux DOM : les trois issues d'une demande d'un autre genre,
// l'environnement à compléter, l'ouverture du formulaire de création.
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

const GENRE = {id: "g1", genre: "genre_fonctionnalite", texte: "Ce n'est pas un jeu web.", propose: "jeu-mobile",
  genres_connus: ["jeu-web", "jeu-mobile"], incertain: true};
const ETAT = {agir: true, agents: [], fonctionnalites: [
  {id: "f1", nom: "Casse-briques", etape: "cadrage", decisions: [GENRE,
    {id: "e1", genre: "environnement", texte: "Le JDK ne s'est pas installé.", environnement: [{outil: "JDK"}, "Gradle"]}]}]};

function rendre(etat, barre) {
  const demandes = [];
  const ctx = {etat, ouvrirFonctionnalite() {},
    barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }, nouveauProjet: barre?.nouveauProjet || (() => false)}};
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctx, contenu);
  return {contenu, demandes};
}
const boutons = (c) => c.tous((n) => n.tagName === "button");
const bouton = (c, libelle) => boutons(c).find((b) => b.textContent === libelle);

test("decision genre_fonctionnalite trois issues, rendues", () => {
  const {contenu} = rendre(ETAT);
  assert.deepEqual(boutons(contenu).map((b) => b.textContent).filter((t) => ["Nouveau projet", "Dans ce projet", "C'est le même genre"].includes(t)),
    ["Nouveau projet", "Dans ce projet", "C'est le même genre"]);
  assert.match(contenu.textContent, /Genre proposé : jeu-mobile \(le moteur hésite\)/);
});

test("Dans ce projet envoie le genre choisi ; C'est le même genre n'en envoie pas", async () => {
  const {contenu, demandes} = rendre(ETAT);
  const menu = contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0];
  menu.value = "jeu-mobile";
  await bouton(contenu, "Dans ce projet").auteurs.click[0]();
  await bouton(contenu, "C'est le même genre").auteurs.click[0]();
  assert.deepEqual(demandes, [
    {type: "genre_fonctionnalite", decision: "g1", fonctionnalite: "f1", choix: "ici", genre: "jeu-mobile"},
    {type: "genre_fonctionnalite", decision: "g1", fonctionnalite: "f1", choix: "meme"}]);
});

test("Nouveau projet ouvre le formulaire avec la décision et le genre", () => {
  const ouvertures = [];
  const {contenu} = rendre(ETAT, {nouveauProjet: (o) => { ouvertures.push(o); return true; }});
  contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0].value = "jeu-mobile";
  bouton(contenu, "Nouveau projet").auteurs.click[0]();
  assert.equal(ouvertures.length, 1);
  assert.deepEqual(ouvertures[0].decision, {id: "g1", fonctionnalite: "f1", nom: "Casse-briques"});
  assert.equal(ouvertures[0].genre, "jeu-mobile");
});

test("un genre nouveau demande sa description avant l'envoi", async () => {
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [{...ETAT.fonctionnalites[0], decisions: [
    {...GENRE, propose: "appli-android", incertain: false}]}]});
  contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0].value = "appli-android";   // un vrai menu choisit le premier
  await bouton(contenu, "Dans ce projet").auteurs.click[0]();
  assert.deepEqual(demandes, []);
  assert.match(contenu.textContent, /demande une description/);
  assert.equal(bouton(contenu, "C'est le même genre"), undefined);   // le moteur n'hésitait pas
});

test("environnement : ce qui manque, « C'est fait » et « Continuer sans »", async () => {
  const {contenu, demandes} = rendre(ETAT);
  assert.match(contenu.textContent, /Il manque : JDK, Gradle\./);
  await bouton(contenu, "C'est fait").auteurs.click[0]();
  await bouton(contenu, "Continuer sans").auteurs.click[0]();
  assert.deepEqual(demandes.map((d) => [d.type, d.verdict, d.fonctionnalite]), [["environnement", "fait", "f1"], ["environnement", "continuer", "f1"]]);
});
