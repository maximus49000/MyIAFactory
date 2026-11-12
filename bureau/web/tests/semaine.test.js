import test from "node:test";
import assert from "node:assert/strict";
import {SEP, plafond, paliers, valeurA, finDeCourbe, graduationsJours, chemin, niveaux, apresChoix, marquesDe,
        marquesSelection, totalSelection, lignesListe, bandes, dessiner, trouver, rythmeA, ecartRythme, phraseEcart, ligneRythme, RYTHME_COULEUR} from "../ui/semaine.js";
import {ouvrirSemaines, ligneTotal, LEGENDE, LEGENDE_RYTHME} from "../ui/semaine-vue.js";
import {definirAbonnement} from "../ui/abonnement.js";

// Un DOM minimal : assez pour construire la fenêtre, la fermer au clavier et vérifier que les textes passent par textContent.
class Noeud {
  constructor(tag, ns = null) {
    this.tagName = tag; this.ns = ns; this.enfants = []; this.attributs = {}; this.ecouteurs = {};
    this.className = ""; this._texte = ""; this.hidden = false; this.disabled = false; this.value = "";
    this.dataset = {}; this.parent = null; this.id = ""; this.title = "";
    const style = {}; style.setProperty = (k, v) => { style[k] = v; }; this.style = style;
    this.clientWidth = 640;
  }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  set innerHTML(v) { throw new Error("innerHTML interdit"); }
  append(...e) { for (const x of e) { x.parent = this; this.enfants.push(x); } }
  replaceChildren(...e) { this.enfants = []; this._texte = ""; this.append(...e); }
  remove() { if (this.parent) this.parent.enfants = this.parent.enfants.filter((x) => x !== this); this.parent = null; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === globalThis.document.body; }
  contains(n) { for (let x = n; x; x = x.parent) if (x === this) return true; return false; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  getAttribute(k) { return this.attributs[k] ?? null; }
  addEventListener(t, f) { (this.ecouteurs[t] ||= []).push(f); }
  focus() { globalThis.document.activeElement = this; }
  getBoundingClientRect() { return {left: 0, width: 640}; }
  get classList() {
    const n = this;
    return { add: (c) => { n.className = [...new Set([...n.className.split(" ").filter(Boolean), c])].join(" "); },
             remove: (c) => { n.className = n.className.split(" ").filter((x) => x && x !== c).join(" "); },
             toggle: (c, on) => { n.classList[on ? "add" : "remove"](c); } };
  }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
  querySelectorAll() { return this.tous((n) => ["button", "select", "summary"].includes(n.tagName) && !n.disabled); }
  declencher(type, ev = {}) { for (const f of this.ecouteurs[type] || []) f({preventDefault() {}, stopPropagation() {}, ...ev}); }
}
const ecouteursDoc = {};
globalThis.document = {
  createElement: (t) => new Noeud(t),
  createElementNS: (ns, t) => new Noeud(t, ns),
  body: Object.assign(new Noeud("body"), {}),
  activeElement: null,
  addEventListener: (t, f) => { (ecouteursDoc[t] ||= []).push(f); },
  removeEventListener: (t, f) => { ecouteursDoc[t] = (ecouteursDoc[t] || []).filter((x) => x !== f); },
};
globalThis.window = {addEventListener() {}, removeEventListener() {}};
const touche = (key, extra = {}) => { for (const f of ecouteursDoc.keydown || []) f({key, preventDefault() { touche.pd = true; }, stopPropagation() {}, ...extra}); };

const T0 = 1_800_000_000 - 7 * 86400, T1 = 1_800_000_000;
const SEMAINE = {debut: T0, remise: T1, courante: true};
const M = (t, duree = null, euros = 0.1) => ({t, euros, modele: "sonnet", duree});

// Un arbre de deux projets : Alpha (fonctionnalité Accueil : tâches Écran et Menu) et Beta.
const ARBRE = {euros: 1.0, sans_prix: 0, n: 5, sujets: [
  {id: "a", nom: "Alpha", genre: "projet", euros: 0.7, sans_prix: 0, n: 3, marques: [], enfants: [
    {id: ["a", "f:f1"].join(SEP), nom: "Accueil", genre: "fonctionnalite", euros: 0.7, sans_prix: 0, n: 3, marques: [], enfants: [
      {id: ["a", "f:f1", "t:t1"].join(SEP), nom: "Écran", genre: "tache", euros: 0.5, sans_prix: 0, n: 2, marques: [], enfants: [
        {id: ["a", "f:f1", "t:t1", "e:Tests"].join(SEP), nom: "Tests", genre: "etape", euros: 0.5, sans_prix: 0, n: 2,
         marques: [M(T0 + 86400), M(T0 + 2 * 86400, 600)], enfants: []}]},
      {id: ["a", "f:f1", "t:t2"].join(SEP), nom: "Menu", genre: "tache", euros: 0.2, sans_prix: 0, n: 1, marques: [], enfants: [
        {id: ["a", "f:f1", "t:t2", "e:"].join(SEP), nom: "Sans étape", genre: "etape", euros: 0.2, sans_prix: 0, n: 1,
         marques: [M(T0 + 3 * 86400)], enfants: []}]}]}]},
  {id: "b", nom: "Beta", genre: "projet", euros: 0.3, sans_prix: 0, n: 2, marques: [], enfants: [
    {id: ["b", "direction"].join(SEP), nom: "Direction", genre: "groupe", euros: 0.3, sans_prix: 0, n: 2,
     marques: [M(T0 + 4 * 86400), M(T0 + 5 * 86400)], enfants: []}]}]};
const ID = (...m) => m.join(SEP);

test("le haut de l'axe s'adapte à la valeur (palier supérieur avec de l'air)", () => {
  assert.equal(plafond(0), 5);
  assert.equal(plafond(4), 5);
  assert.equal(plafond(5), 10);
  assert.equal(plafond(41), 50);
  assert.equal(plafond(54), 60);
  assert.equal(plafond(55), 80);
  assert.equal(plafond(99), 100);
  assert.equal(plafond(NaN), 5);
});

test("les paliers : la valeur tient jusqu'au point suivant, puis jusqu'à maintenant", () => {
  const pts = [{t: 10, pourcent: 1}, {t: 20, pourcent: 3}];
  assert.deepEqual(paliers(pts, 30), [[10, 1], [20, 1], [20, 3], [30, 3]]);
  assert.deepEqual(paliers(pts, 15 - 100), [[10, 1], [20, 1], [20, 3]]);
  assert.deepEqual(paliers([], 30), []);
  assert.equal(valeurA(pts, 5), null);
  assert.equal(valeurA(pts, 15), 1);
  assert.equal(valeurA(pts, 99), 3);
});

test("la courbe s'arrête à maintenant (semaine en cours) ou à la dernière lecture (semaine passée)", () => {
  assert.equal(finDeCourbe({...SEMAINE}, T0 + 100), T0 + 100);
  assert.equal(finDeCourbe({...SEMAINE}, T1 + 100), T1);
  assert.equal(finDeCourbe({...SEMAINE, courante: false, vu: T0 + 500}, T1), T0 + 500);
  assert.equal(finDeCourbe({...SEMAINE, courante: false}, T1), T1);
});

test("les jours de la semaine", () => {
  const j = graduationsJours(T0, T1);
  assert.ok(j.length >= 7 && j.length <= 8);
  assert.ok(j.every((x) => typeof x.libelle === "string" && x.libelle));
});

test("filtres en cascade : une liste par niveau, alimentée par le niveau du dessus", () => {
  const sujets = ARBRE.sujets;
  let n = niveaux(sujets, "");
  assert.deepEqual(n.map((x) => x.libelle), ["Projet", "Fonctionnalité", "Tâche", "Sous-tâche"]);
  assert.deepEqual(n[0].options.map((o) => o.nom), ["Alpha", "Beta"]);
  assert.deepEqual(n.slice(1).map((x) => x.actif), [false, false, false]);
  n = niveaux(sujets, ID("a"));
  assert.equal(n[0].valeur, "a");
  assert.deepEqual(n[1].options.map((o) => o.nom), ["Accueil"]);
  n = niveaux(sujets, ID("a", "f:f1", "t:t1"));
  assert.deepEqual(n.map((x) => x.valeur), ["a", ID("a", "f:f1"), ID("a", "f:f1", "t:t1"), ""]);
  assert.deepEqual(n[3].options.map((o) => o.nom), ["Tests"]);
  // « Tous » à un niveau revient au niveau du dessus ; au premier niveau, à tout
  assert.equal(apresChoix(sujets, ID("a", "f:f1", "t:t1"), 2, ""), ID("a", "f:f1"));
  assert.equal(apresChoix(sujets, ID("a", "f:f1"), 0, ""), "");
  assert.equal(apresChoix(sujets, "", 0, "b"), "b");
  assert.deepEqual(chemin(sujets, ID("a", "f:f1")).map((x) => x.nom), ["Alpha", "Accueil"]);
  assert.deepEqual(chemin(sujets, "inconnu"), []);
});

test("chaque niveau de filtre donne ses marques et son total", () => {
  assert.equal(marquesSelection(ARBRE, "").length, 5);                         // tous les projets
  assert.equal(marquesSelection(ARBRE, "a").length, 3);                         // un projet
  assert.equal(marquesSelection(ARBRE, ID("a", "f:f1")).length, 3);             // une fonctionnalité
  assert.equal(marquesSelection(ARBRE, ID("a", "f:f1", "t:t1")).length, 2);     // une tâche
  assert.equal(marquesSelection(ARBRE, ID("a", "f:f1", "t:t1", "e:Tests")).length, 2);   // une sous-tâche
  assert.equal(marquesSelection(ARBRE, "b").length, 2);
  assert.deepEqual(marquesDe(trouver(ARBRE.sujets, "a")).map((m) => m.t), [T0 + 86400, T0 + 2 * 86400, T0 + 3 * 86400]);
  assert.deepEqual(totalSelection(ARBRE, ""), {nom: "Tous les projets", euros: 1.0, sans_prix: 0, n: 5, co2: undefined});
  const t = totalSelection(ARBRE, ID("a", "f:f1", "t:t1"));
  assert.deepEqual([t.nom, t.euros, t.n], ["Alpha › Accueil › Écran", 0.5, 2]);
});

test("la liste : les descendants de la sélection, en profondeur, avec le chemin des parents", () => {
  const tout = lignesListe(ARBRE, "");
  assert.deepEqual(tout.map((l) => l.noeud.nom), ["Alpha", "Accueil", "Écran", "Tests", "Menu", "Sans étape", "Beta", "Direction"]);
  assert.deepEqual(tout.map((l) => l.profondeur), [0, 1, 2, 3, 2, 3, 0, 1]);
  const sous = lignesListe(ARBRE, ID("a", "f:f1"));
  assert.deepEqual(sous.map((l) => [l.noeud.nom, l.profondeur, l.parents.join(" › ")]),
    [["Accueil", 0, "Alpha"], ["Écran", 1, "Alpha › Accueil"], ["Tests", 2, "Alpha › Accueil › Écran"], ["Menu", 1, "Alpha › Accueil"],
     ["Sans étape", 2, "Alpha › Accueil › Menu"]]);
});

test("les bandes : largeur proportionnelle à la durée, trait fin si elle est inconnue, bornées à la fenêtre", () => {
  const b = bandes([M(T0 + 86400, 3600), M(T0 + 2 * 86400), M(T0 - 5), M(T1 + 5), M(T1 - 1, 99999)], T0, T1, 700);
  assert.equal(b.length, 3);
  assert.ok(Math.abs(b[0].l - 3600 * 700 / (7 * 86400)) < 3.01 && b[0].l >= 3);
  assert.equal(b[1].l, 3);
  assert.ok(b[2].x + b[2].l <= 700);
});

test("le dessin : aire, ligne, maintenant en pointillé, bandes de la sélection et traits discrets pour le reste", () => {
  const pts = [{t: T0 + 100, pourcent: 2}, {t: T0 + 86400, pourcent: 9}];
  const svg = dessiner({semaine: SEMAINE, points: pts, maintenant: T0 + 2 * 86400, largeur: 600, hauteur: 260,
                        marques: [M(T0 + 86400)], autres: [M(T0 + 3 * 86400), M(T0 + 4 * 86400)]});
  const classes = svg.tous((n) => n.attributs.class).map((n) => n.attributs.class);
  assert.equal(classes.filter((c) => c === "sem-bande").length, 1);
  assert.equal(classes.filter((c) => c === "sem-bande-discrete").length, 2);
  for (const c of ["sem-aire", "sem-ligne", "sem-maintenant", "sem-raz"]) assert.ok(classes.includes(c), c);
  assert.match(svg.attributs["aria-label"], /Quota de la semaine : 9 % utilisé/);
  assert.equal(svg.geometrie.haut, 100);      // l'axe va toujours jusqu'à 100 % (la droite du rythme idéal)
  // une semaine passée n'a pas de ligne « maintenant »
  const passee = dessiner({semaine: {...SEMAINE, courante: false}, points: pts, largeur: 600, hauteur: 260});
  assert.ok(!passee.tous((n) => n.attributs.class === "sem-maintenant").length);
  // sans mesure : pas de courbe, pas d'erreur
  assert.doesNotThrow(() => dessiner({semaine: SEMAINE, points: [], largeur: 300, hauteur: 120, compact: true}));
});

test("le rythme idéal : de 0 % au début à 100 % à la remise", () => {
  assert.equal(rythmeA(SEMAINE, T0), 0);
  assert.equal(rythmeA(SEMAINE, T1), 100);
  assert.equal(rythmeA(SEMAINE, T0 + 3.5 * 86400), 50);
  assert.equal(rythmeA(SEMAINE, T0 - 100), 0);
  assert.equal(rythmeA(SEMAINE, T1 + 100), 100);
  // début absent : remise − 7 jours
  assert.equal(rythmeA({remise: T1}, T1 - 3.5 * 86400), 50);
});

test("l'écart au rythme et ses phrases", () => {
  const pts = [{t: T0 + 100, pourcent: 60}];
  assert.equal(ecartRythme(SEMAINE, pts, T0 + 3.5 * 86400), 10);
  assert.equal(ecartRythme(SEMAINE, pts, T0 + 7 * 86400 - 1) < 0, true);
  assert.equal(ecartRythme(SEMAINE, pts, T0 + 50), null);   // avant la première mesure
  assert.equal(phraseEcart(12.34), "Au-dessus du rythme de 12,3 points");
  assert.equal(phraseEcart(-4), "En dessous de 4 points");
  assert.equal(phraseEcart(-1), "En dessous de 1 point");
  assert.equal(phraseEcart(0.02), "Sur le rythme idéal");
  assert.equal(phraseEcart(null), "");
  assert.equal(ligneRythme(SEMAINE, pts, T0 + 3.5 * 86400), "Rythme : en avance de 10 points");
  assert.equal(ligneRythme(SEMAINE, [{t: T0 + 100, pourcent: 30}], T0 + 3.5 * 86400), "Rythme : en retard de 20 points");
  assert.equal(ligneRythme(SEMAINE, [{t: T0 + 100, pourcent: 50}], T0 + 3.5 * 86400), "Rythme : sur le rythme idéal");
  assert.equal(ligneRythme(SEMAINE, [], T0 + 3.5 * 86400), "");
  assert.equal(ligneRythme({...SEMAINE, courante: false}, pts, T0 + 3.5 * 86400), "");
});

test("le dessin : une droite rouge en tirets, sans remplissage, de (début, 0) à (remise, 100), graduée jusqu'à 100 %", () => {
  for (const compact of [false, true]) {
    const svg = dessiner({semaine: SEMAINE, points: [{t: T0 + 100, pourcent: 2}], maintenant: T0 + 86400, largeur: 600, hauteur: 260, compact});
    const l = svg.tous((n) => n.attributs.class === "sem-rythme");
    assert.equal(l.length, 1);
    assert.equal(l[0].tagName, "line");
    const g = svg.geometrie;
    assert.equal(Number(l[0].attributs.x1), g.X(T0));
    assert.equal(Number(l[0].attributs.y1), g.Y(0));
    assert.equal(Number(l[0].attributs.x2), g.X(T1));
    assert.equal(Number(l[0].attributs.y2), g.Y(100));
    assert.equal(g.haut, 100);
    const etiquettes = svg.tous((n) => n.attributs.class === "sem-etiquette" && /%$/.test(n.textContent)).map((n) => n.textContent);
    assert.ok(etiquettes.includes("100 %") && etiquettes.includes("0 %") && etiquettes.length >= 3, etiquettes.join());
  }
  // sur une semaine passée aussi
  const passee = dessiner({semaine: {...SEMAINE, courante: false}, points: [], largeur: 300, hauteur: 120, compact: true});
  assert.equal(passee.tous((n) => n.attributs.class === "sem-rythme").length, 1);
  assert.equal(RYTHME_COULEUR, "#d03b3b");
});

test("la ligne de total : euros, part de la semaine, CO₂, appels", () => {
  definirAbonnement({pourcent_par_euro: {seven_day: 4}});
  const l = ligneTotal({nom: "Alpha › Accueil", euros: 0.5, sans_prix: 1, n: 2, co2: {min: 1, max: 2}});
  assert.equal(l, "Alpha › Accueil : ≈ 0,50 € + 1 à prix inconnu · ≈ 2,0 % semaine · ≈ 1,0 à 2,0 g CO₂e · 2 appels");
  assert.equal(ligneTotal({nom: "Beta", euros: 0, sans_prix: 0, n: 1}), "Beta : ≈ 0,00 € · 1 appel");
});

// --- La fenêtre.

function simulerReseau() {
  globalThis.fetch = async (url) => {
    const rep = (corps) => ({ok: true, json: async () => corps});
    if (url.startsWith("/api/semaines")) {
      return rep({maintenant: T0 + 3 * 86400, semaines: [
        {id: "2026-11-15", debut: T0, remise: T1, courante: true, max: 9, n: 2},
        {id: "2026-11-08", debut: T0 - 7 * 86400, remise: T0, courante: false, max: 40, n: 5}]});
    }
    if (url.startsWith("/api/semaine?")) {
      return rep({id: "x", debut: T0, remise: T1, vu: T0 + 3 * 86400, points: [{t: T0 + 100, pourcent: 2, source: "compte"}, {t: T0 + 86400, pourcent: 9, source: "moteur"}]});
    }
    if (url.startsWith("/api/sujets")) return rep({semaine: "x", debut: T0, remise: T1, ...ARBRE});
    return {ok: false};
  };
}
const attendre = () => new Promise((r) => setTimeout(r, 20));
const lignesVisibles = (fond) => fond.tous((n) => n.className.split(" ").includes("sem-item"));
const bandesFortes = (fond) => fond.tous((n) => n.attributs.class === "sem-bande").length;
const selects = (fond) => fond.tous((n) => n.tagName === "select");

test("« Voir plus » : fenêtre modale, graphique, listes, légende, total ; la sélection met en évidence ses appels", async () => {
  simulerReseau();
  definirAbonnement({pourcent_par_euro: {seven_day: 2}});
  const bouton = new Noeud("button");
  document.body.append(bouton);
  const v = ouvrirSemaines({declencheur: bouton});
  await attendre();
  const fond = v.fond;
  assert.ok(fond.isConnected);
  assert.equal(fond.enfants[0].attributs["aria-modal"], "true");
  assert.equal(fond.enfants[0].attributs.role, "dialog");
  assert.equal(selects(fond).length, 5);                        // semaine + projet + fonctionnalité + tâche + sous-tâche
  assert.ok(fond.textContent.includes(LEGENDE));
  assert.match(fond.textContent, /Tous les projets : ≈ 1,00 € · ≈ 2,0 % semaine · 5 appels/);
  assert.equal(lignesVisibles(fond).length, 8);
  assert.equal(bandesFortes(fond), 5);                           // sans sélection : tous les appels
  // cliquer un sujet : ses appels seulement, les autres en traits discrets, filtres réglés, total et liste restreints
  const ligne = (nom) => lignesVisibles(fond).map((l) => l.enfants[0])
    .find((b) => b.tous((x) => x.className === "sem-sujet-nom")[0]._texte === nom);
  ligne("Écran").declencher("click");
  assert.equal(bandesFortes(fond), 2);
  assert.equal(fond.tous((n) => n.attributs.class === "sem-bande-discrete").length, 5);
  assert.deepEqual(selects(fond).map((s) => s.value), ["2026-11-15", "a", ID("a", "f:f1"), ID("a", "f:f1", "t:t1"), ""]);
  assert.match(fond.textContent, /Alpha › Accueil › Écran : ≈ 0,50 € · ≈ 1,0 % semaine · 2 appels/);
  assert.equal(lignesVisibles(fond).length, 2);                  // la tâche (surlignée) et son étape
  const choisi = fond.tous((n) => n.className.includes("choisi") || n.attributs["aria-pressed"] === "true");
  assert.ok(choisi.length >= 1);
  // une liste déroulante : « Tous » au niveau tâche revient à la fonctionnalité
  const tache = selects(fond)[3];
  tache.value = "";
  tache.declencher("change");
  assert.equal(bandesFortes(fond), 3);
  assert.equal(selects(fond)[2].value, ID("a", "f:f1"));
  // les trois autres niveaux, par les listes
  selects(fond)[1].value = "b";
  selects(fond)[1].declencher("change");
  assert.equal(bandesFortes(fond), 2);
  // « Tout » enlève la sélection
  fond.tous((n) => n.className.includes("sem-tout"))[0].declencher("click");
  assert.equal(bandesFortes(fond), 5);
  assert.match(fond.textContent, /Tous les projets/);
  // resélectionner le même sujet l'enlève
  ligne("Alpha").declencher("click");
  assert.equal(bandesFortes(fond), 3);
  ligne("Alpha").declencher("click");
  assert.equal(bandesFortes(fond), 5);
  v.fermer();
});

test("la fenêtre : légende du rythme idéal et écart au rythme à l'instant survolé", async () => {
  simulerReseau();
  const v = ouvrirSemaines({});
  await attendre();
  assert.ok(v.fond.textContent.includes(LEGENDE_RYTHME));
  assert.equal(LEGENDE_RYTHME, "Rythme idéal (0 % restant à la remise)");
  const svg = v.fond.tous((n) => n.tagName === "svg")[0];
  const bulle = v.fond.tous((n) => n.className === "sem-bulle")[0];
  const g = svg.geometrie;
  // au 2e jour (largeur du faux DOM 640 = viewBox)
  svg.declencher("pointermove", {clientX: ((g.marges.g + g.w * 2 / 7) / g.largeur) * 640});
  assert.equal(bulle.hidden, false);
  assert.match(bulle.textContent, /En dessous de 19,6 points/);   // 9 % mesurés, 28,6 % attendus
  // au-delà de la courbe (après maintenant) : pas d'écart
  svg.declencher("pointermove", {clientX: ((g.marges.g + g.w * 6 / 7) / g.largeur) * 640});
  assert.doesNotMatch(bulle.textContent, /points/);
  // avant la première mesure : pas d'écart
  svg.declencher("pointermove", {clientX: (g.marges.g / g.largeur) * 640});
  assert.doesNotMatch(bulle.textContent, /du rythme|points/);
  v.fermer();
});

test("changer de semaine recharge la courbe et remet la sélection à zéro", async () => {
  simulerReseau();
  const v = ouvrirSemaines({});
  await attendre();
  lignesVisibles(v.fond)[0].enfants[0].declencher("click");
  assert.notEqual(v.etat.selection, "");
  const semaine = selects(v.fond)[0];
  semaine.value = "2026-11-08";
  semaine.declencher("change");
  await attendre();
  assert.equal(v.etat.selection, "");
  assert.equal(v.etat.semaine, "2026-11-08");
  assert.equal(v.etat.serie.courante, false);
  v.fermer();
});

test("fermeture : Échap, bouton, clic hors fenêtre ; le focus est rendu au bouton ; le focus reste dans la fenêtre", async () => {
  ecouteursDoc.keydown = [];   // aucune fenêtre laissée ouverte par un autre essai
  simulerReseau();
  const bouton = new Noeud("button");
  document.body.append(bouton);
  const v = ouvrirSemaines({declencheur: bouton});
  await attendre();
  assert.equal(document.activeElement, v.fond.tous((n) => n.className.includes("sem-fermer"))[0]);
  // Tab sur le dernier élément revient au premier ; Maj+Tab sur le premier va au dernier
  const f = v.fond.enfants[0].querySelectorAll();
  f[f.length - 1].focus();
  touche("Tab");
  assert.equal(document.activeElement, f[0]);
  touche("Tab", {shiftKey: true});
  assert.equal(document.activeElement, f[f.length - 1]);
  // un focus tombé hors de la fenêtre y est ramené
  bouton.focus();
  touche("Tab");
  assert.equal(document.activeElement, f[0]);
  touche("Escape");
  assert.ok(!v.fond.isConnected);
  assert.equal(document.activeElement, bouton);
  assert.equal((ecouteursDoc.keydown || []).length, 0);          // plus d'écouteur : rien ne traîne

  const w = ouvrirSemaines({declencheur: bouton});
  w.fond.declencher("mousedown", {target: w.fond.enfants[0]});    // dans la fenêtre : reste ouverte
  assert.ok(w.fond.isConnected);
  w.fond.declencher("mousedown", {target: w.fond});               // hors fenêtre : ferme
  assert.ok(!w.fond.isConnected);
  const x = ouvrirSemaines({declencheur: bouton});
  x.fond.tous((n) => n.className.includes("sem-fermer"))[0].declencher("click");
  assert.ok(!x.fond.isConnected);
});

test("sans semaine archivée ni réseau : un message, pas d'erreur ; les textes du serveur passent par textContent", async () => {
  globalThis.fetch = async () => { throw new Error("réseau coupé"); };
  const v = ouvrirSemaines({});
  await attendre();
  assert.match(v.fond.textContent, /Aucune semaine archivée/);
  v.fermer();
  simulerReseau();
  const hostile = JSON.parse(JSON.stringify(ARBRE));
  hostile.sujets[0].nom = "<img src=x onerror=alert(1)>";
  const base = globalThis.fetch;
  globalThis.fetch = async (u) => (u.startsWith("/api/sujets") ? {ok: true, json: async () => ({semaine: "x", ...hostile})} : base(u));
  const w = ouvrirSemaines({});
  await attendre();
  assert.ok(w.fond.textContent.includes("<img src=x onerror=alert(1)>"));
  w.fermer();
});
