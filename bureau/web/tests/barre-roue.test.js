// La barre du haut (maquette validée par le Directeur) : l'heure et la date à gauche, une seule ligne à toutes les
// largeurs, une roue crantée à droite qui ouvre le menu « Réglages », « Serveurs de travail », « Associer un téléphone »
// et, quand la place manque, le groupe « Actions ».
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

class Noeud {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.enfants = []; this.parent = null; this.attrs = {}; this.auteurs = {};
    this.hidden = false; this._texte = ""; this.className = ""; this.dataset = {}; this.style = {}; this.disabled = false;
    const soi = this;
    this.classList = {
      liste: () => soi.className.split(/\s+/).filter(Boolean),
      contains: (c) => soi.classList.liste().includes(c),
      add: (...cs) => { soi.className = [...new Set([...soi.classList.liste(), ...cs])].join(" "); },
      remove: (...cs) => { soi.className = soi.classList.liste().filter((x) => !cs.includes(x)).join(" "); },
      toggle: (c, oui) => { (oui ?? !soi.classList.contains(c)) ? soi.classList.add(c) : soi.classList.remove(c); },
    };
  }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  get children() { return this.enfants; }
  append(...es) { for (let e of es) { if (typeof e === "string") { const t = new Noeud("#texte"); t._texte = e; e = t; } e.parent = this; this.enfants.push(e); } }
  replaceChildren(...es) { this.enfants = []; this.append(...es); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(n, f) { (this.auteurs[n] ||= []).push(f); }
  removeEventListener(n, f) { this.auteurs[n] = (this.auteurs[n] || []).filter((g) => g !== f); }
  emettre(n, ev = {}) {
    ev.target ??= this; ev.type = n;
    ev.stopPropagation ??= () => { ev.arrete = true; };
    ev.preventDefault ??= () => { ev.empeche = true; };
    for (const f of this.auteurs[n] || []) f.call(this, ev);
    if (ev.arrete) return ev;
    if (this.parent) this.parent.emettre(n, ev);
    else if (this !== document) document.emettre(n, ev);
    return ev;
  }
  click() { this.emettre("click"); }
  focus() { document.activeElement = this; }
  contains(n) { for (; n; n = n.parent) if (n === this) return true; return false; }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = new Noeud("#document");
document.createElement = (t) => new Noeud(t);
document.createElementNS = (ns, t) => { const n = new Noeud(t); n.ns = ns; return n; };
document.activeElement = null;

const {formaterHeure, creerMenuParametres, resserrer} = await import("../ui/barre-parametres.js");
const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");
const panneaux = readFileSync(new URL("../ui/panneaux.js", import.meta.url), "utf8");

const roueDe = (menu) => menu.racine.tous((n) => n.tagName === "BUTTON" && n.getAttribute("aria-label") === "Paramètres")[0];
const listeDe = (menu) => menu.racine.tous((n) => n.getAttribute("role") === "menu")[0];
const entrees = (menu) => menu.racine.tous((n) => n.getAttribute("role") === "menuitem");
const entree = (menu, debut) => entrees(menu).find((n) => n.textContent.startsWith(debut));
const rien = () => {};
const menuSimple = (o = {}) => creerMenuParametres({ouvrirReglages: rien, ouvrirServeurs: rien, associerTelephone: rien, actions: () => [], ...o});

test("formaterHeure_donne_HH_MM_et_date_courte", () => {
  assert.deepEqual(formaterHeure(new Date(2026, 10, 23, 14, 32)), {heure: "14:32", date: "lun. 23 nov."});
  assert.deepEqual(formaterHeure(new Date(2026, 4, 3, 7, 5)), {heure: "07:05", date: "dim. 3 mai"});
  assert.deepEqual(formaterHeure(new Date(2026, 1, 28, 0, 0)), {heure: "00:00", date: "sam. 28 févr."});
});

test("la_roue_a_les_attributs_aria_et_ouvre_le_menu", () => {
  const m = menuSimple();
  const roue = roueDe(m);
  assert.ok(roue, "la roue « Paramètres »");
  assert.equal(roue.getAttribute("aria-haspopup"), "menu");
  assert.equal(roue.getAttribute("aria-expanded"), "false");
  const svg = roue.tous((n) => n.tagName === "SVG")[0];
  assert.ok(svg && svg.ns === "http://www.w3.org/2000/svg", "icône SVG en ligne");
  assert.equal(svg.getAttribute("aria-hidden"), "true");
  const liste = listeDe(m);
  assert.ok(liste.hidden);
  assert.equal(roue.getAttribute("aria-controls"), liste.getAttribute("id"));
  roue.click();
  assert.equal(roue.getAttribute("aria-expanded"), "true");
  assert.equal(liste.hidden, false);
  roue.click();   // un second clic referme
  assert.equal(roue.getAttribute("aria-expanded"), "false");
  assert.ok(liste.hidden);
});

test("le_menu_propose_les_trois_entrees_et_ferme_sur_echap", () => {
  const m = menuSimple();
  const roue = roueDe(m);
  roue.click();
  assert.ok(entree(m, "Réglages").textContent.includes("Global, type, projet"));
  assert.ok(entree(m, "Serveurs de travail").textContent.includes("État et aptitude des lieux"));
  assert.ok(entree(m, "Associer un téléphone"));
  assert.equal(document.activeElement, entree(m, "Réglages"), "le focus va à la première entrée");
  const ev = entree(m, "Serveurs de travail").emettre("keydown", {key: "Escape"});
  assert.ok(listeDe(m).hidden);
  assert.equal(roue.getAttribute("aria-expanded"), "false");
  assert.equal(document.activeElement, roue, "la roue reprend le focus");
  assert.ok(ev.arrete, "Échap ne ferme pas aussi le panneau de droite");
});

test("un_clic_ailleurs_ferme_le_menu", () => {
  const m = menuSimple();
  roueDe(m).click();
  const ailleurs = new Noeud("div");
  document.emettre("click", {target: ailleurs});
  assert.ok(listeDe(m).hidden);
  m.fermer();   // fermer un menu fermé : sans effet
  assert.ok(listeDe(m).hidden);
});

test("choisir_reglages_appelle_ouvrirReglages_et_ferme", () => {
  const appels = [];
  const m = menuSimple({ouvrirReglages: () => appels.push("reglages"), ouvrirServeurs: () => appels.push("serveurs"),
                        associerTelephone: () => appels.push("telephone")});
  roueDe(m).click();
  entree(m, "Réglages").click();
  assert.deepEqual(appels, ["reglages"]);
  assert.ok(listeDe(m).hidden);
  roueDe(m).click();
  entree(m, "Serveurs de travail").click();
  roueDe(m).click();
  entree(m, "Associer un téléphone").click();
  assert.deepEqual(appels, ["reglages", "serveurs", "telephone"]);
});

test("une_entree_sans_action_n_est_pas_proposee", () => {
  const m = menuSimple({associerTelephone: null});
  roueDe(m).click();
  assert.ok(entree(m, "Associer un téléphone").hidden);
});

test("la_barre_est_nowrap", () => {
  const regles = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)].map(([, sel, corps]) => ({sel: sel.trim(), corps}));
  const de = (cible) => regles.filter((r) => r.sel.split(",").some((s) => s.trim().split(/\s+/).pop() === cible));
  assert.ok(de("#barre").some((r) => /flex-wrap:\s*nowrap/.test(r.corps)), "#barre en nowrap");
  for (const cible of ["#barre", ".barre-actions"]) {
    for (const r of de(cible)) assert.doesNotMatch(r.corps, /flex-wrap:\s*wrap/, `${r.sel} passe à la ligne`);
  }
  assert.match(barre, /ResizeObserver/);
  assert.match(barre, /--hauteur-barre/);
  // la largeur du menu est une variable
  assert.match(css, /--largeur-menu-parametres:/);
});

test("le_resserrement_suit_l_ordre_icones_charge_puis_repli", () => {
  // Une barre factice : chaque étape fait gagner de la place ; un élément replié aussi.
  const entete = new Noeud("header");
  const elements = ["a", "b", "c"].map((id) => { const n = new Noeud("button"); n.id = id; return n; });
  let largeurContenu;
  const mesure = () => largeurContenu - (entete.classList.contains("barre-icones") ? 100 : 0)
    - (entete.classList.contains("barre-compacte") ? 50 : 0) - elements.filter((e) => e.classList.contains("replie")).length * 40;
  Object.defineProperty(entete, "scrollWidth", {get: mesure});
  entete.clientWidth = 1000;

  largeurContenu = 900;
  assert.deepEqual(resserrer(entete, elements), []);
  assert.ok(!entete.classList.contains("barre-icones"));

  largeurContenu = 1080;
  assert.deepEqual(resserrer(entete, elements), []);
  assert.ok(entete.classList.contains("barre-icones") && !entete.classList.contains("barre-compacte"));

  largeurContenu = 1140;
  assert.deepEqual(resserrer(entete, elements), []);
  assert.ok(entete.classList.contains("barre-compacte"));

  largeurContenu = 1220;   // il faut replier deux éléments, en partant de la droite
  assert.deepEqual(resserrer(entete, elements).map((e) => e.id), ["b", "c"]);
  assert.ok(!elements[0].classList.contains("replie"));

  assert.ok(!entete.classList.contains("barre-etroite"));
  largeurContenu = 1400;   // tout replié et encore trop large : quatrième étape
  assert.deepEqual(resserrer(entete, elements).map((e) => e.id), ["a", "b", "c"]);
  assert.ok(entete.classList.contains("barre-etroite"));

  largeurContenu = 900;    // la place revient : tout est remis
  assert.deepEqual(resserrer(entete, elements), []);
  assert.ok(elements.every((e) => !e.classList.contains("replie")));
  assert.ok(!entete.classList.contains("barre-icones") && !entete.classList.contains("barre-etroite"));

  elements[1].hidden = true;   // un bouton caché n'est jamais replié dans le menu
  assert.deepEqual(resserrer(entete, elements, {telephone: true}).map((e) => e.id), ["a", "c"]);
});

test("les_actions_repliees_sont_dans_le_groupe_Actions_du_menu", () => {
  const cliques = [];
  const nouvelle = new Noeud("button"); nouvelle.click = () => cliques.push("nouvelle");
  const liste = new Noeud("button"); liste.click = () => cliques.push("liste");
  const m = menuSimple({actions: () => [{libelle: "+ Nouvelle fonctionnalité", element: nouvelle},
                                         {libelle: "Toutes les tâches", element: liste, desactive: true}]});
  roueDe(m).click();
  const groupe = m.racine.tous((n) => n.getAttribute("role") === "group" && n.getAttribute("aria-label") === "Actions")[0];
  assert.ok(groupe && !groupe.hidden, "le groupe « Actions »");
  const dans = groupe.tous((n) => n.getAttribute("role") === "menuitem");
  assert.deepEqual(dans.map((n) => n.textContent), ["+ Nouvelle fonctionnalité", "Toutes les tâches"]);
  assert.ok(dans[1].disabled);
  dans[0].click();
  assert.deepEqual(cliques, ["nouvelle"], "l'entrée clique le bouton d'origine");
  assert.ok(listeDe(m).hidden);
  // sans action repliée, pas de groupe
  const vide = menuSimple();
  roueDe(vide).click();
  const g = vide.racine.tous((n) => n.getAttribute("role") === "group")[0];
  assert.ok(!g || g.hidden);
  // la barre replie les cinq actions nommées et ne duplique pas leur comportement
  for (const nom of ["boutonNouvelle", "boutonCorrection", "boutonQuestion", "boutonFonctions", "boutonListe"]) {
    assert.match(barre, new RegExp(`pliables[^;]*${nom}`, "s"), `${nom} repliable`);
  }
  assert.match(barre, /creerMenuParametres\(/);
  assert.match(barre, /creerHorloge\(/);   // l'horloge de barre-parametres.js (formaterHeure, toutes les 15 s)
});

test("la_retenue_repliee_ouvre_le_menu_en_lecture_seule", () => {
  let lignes = ["Pause : installation de Godot Engine"];
  const m = menuSimple({retenue: () => lignes});
  roueDe(m).click();
  const bloc = m.racine.tous((n) => n.getAttribute("role") === "group" && n.getAttribute("aria-label") === "Retenu")[0];
  assert.ok(bloc, "le bloc « Retenu »");
  assert.equal(listeDe(m).enfants[0], bloc, "en tête du menu");
  const ligne = bloc.enfants[0];
  assert.equal(ligne.textContent, "Retenu : Pause : installation de Godot Engine");
  assert.equal(ligne.getAttribute("aria-disabled"), "true");
  assert.notEqual(document.activeElement, ligne, "une information, pas une entrée où va le focus");
  m.fermer();
  lignes = [];   // la barre a de nouveau la place : plus rien dans le menu
  roueDe(m).click();
  assert.equal(m.racine.tous((n) => n.getAttribute("aria-label") === "Retenu").length, 0);
  // la barre la passe au menu quand elle est cachée (téléphone ou barre étroite)
  assert.match(barre, /retenue: \(\) => \(!retenue\.hidden && \(telephone\(\) \|\| entete\.classList\.contains\(CLASSE_ETROITE\)\)/);
});

test("le_rond_de_consommation_precede_l_heure_et_n_est_jamais_cache", () => {
  // Le bloc de consommation est le premier enfant de la barre, l'heure le suit, puis le séparateur ; il ne porte que le rond.
  assert.match(barre, /entete\.append\(blocAbonnement, horloge\.racine, separateur, titre,/);
  assert.match(barre, /blocAbonnement\.append\(creerConso\(\)\);/);
  assert.doesNotMatch(barre, /jauges/);
  // Aucune règle ne cache le bloc, le rond ou son bouton, à aucune largeur (téléphone et barre étroite compris).
  const regles = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)].map(([, sel, corps]) => ({sel: sel.trim(), corps}));
  for (const r of regles) {
    if (!/display:\s*none|visibility:\s*hidden/.test(r.corps)) continue;
    for (const s of r.sel.split(",")) {
      const dernier = s.trim().split(/\s+/).pop();
      assert.ok(![".bloc-abonnement", ".conso", ".conso-rond", ".conso-chiffre"].includes(dernier), `« ${s.trim()} » cache le rond`);
    }
  }
  assert.doesNotMatch(css, /\.mobile[^{]*\.bloc-abonnement[^{]*\{/);
  assert.doesNotMatch(css, /barre-etroite[^{]*\.bloc-abonnement[^{]*\{/);
});

test("le_selecteur_de_projets_n_est_jamais_cache_par_la_feuille", () => {
  // Plusieurs projets : le sélecteur est le seul accès pour changer de projet ou en créer un ; il se resserre, jamais caché.
  const regles = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)].map(([, sel, corps]) => ({sel: sel.trim(), corps}));
  for (const r of regles) {
    if (!/display:\s*none|visibility:\s*hidden/.test(r.corps)) continue;
    for (const s of r.sel.split(",")) {
      const dernier = s.trim().split(/\s+/).pop().replace(/::?[a-z-]+(\([^)]*\))?$/i, "");
      assert.ok(!/^\.barre-(choix|titre)/.test(dernier) || /::before|::after/.test(s), `« ${s.trim()} » cache le sélecteur`);
    }
  }
  assert.match(css, /#barre \.barre-choix \{ min-width: var\(--choix-min\); text-overflow: ellipsis; \}/);
  assert.match(css, /\.mobile #barre > \.barre-titre, #barre\.barre-minimale > \.barre-titre \{[^}]*overflow: hidden/);
});

test("en_mode_telephone_la_barre_garde_le_rond_et_le_selecteur_et_replie_les_actions", async () => {
  // La vraie barre, montée dans le faux DOM : le rond reste le premier enfant de la barre, le sélecteur de projets reste
  // affiché même au dernier resserrement, les actions passent dans le menu.
  globalThis.window = {addEventListener() {}, matchMedia: () => ({matches: false}), confirm: () => true, dispatchEvent() {}};
  globalThis.fetch = () => new Promise(() => {});        // aucune réponse : la barre garde son état de départ
  globalThis.setInterval = () => 0;
  globalThis.ResizeObserver = class { constructor(f) { this.f = f; } observe() {} };
  globalThis.location = {reload() {}};
  document.documentElement = new Noeud("html");
  document.documentElement.classList.add("mobile");
  document.documentElement.style.setProperty = () => {};
  document.body = new Noeud("body");
  document.hidden = false;
  Noeud.prototype.after = function (...e) { this.apres = e; };
  Noeud.prototype.querySelector = function (s) { return this.querySelectorAll(s)[0] || null; };
  Noeud.prototype.querySelectorAll = function (s) {
    const tags = s.split(",").map((x) => x.trim().toUpperCase());
    return this.tous((n) => n !== this && tags.includes(n.tagName));
  };
  Noeud.prototype.closest = function () { return null; };
  const {creerBarre} = await import("../ui/barre.js");
  const entete = new Noeud("header");
  let contenu = 300;
  Object.defineProperty(entete, "scrollWidth", {get: () => contenu});
  entete.clientWidth = 375;
  const b = creerBarre(entete, new Noeud("div"));
  const enfants = entete.enfants;
  assert.ok(enfants[0].classList.contains("bloc-abonnement"), "le rond est le premier enfant de la barre");
  assert.ok(enfants[1].classList.contains("barre-horloge"), "l'heure le suit");
  assert.ok(enfants[2].classList.contains("barre-separateur"), "puis le séparateur");
  assert.ok(enfants[0].tous((n) => n.classList.contains("conso-rond")).length === 1);
  assert.equal(entete.tous((n) => n.classList.contains("jauges")).length, 0, "pas de jauges dans la barre");
  b.majProjets(true, [{id: "a", nom: "Alpha"}, {id: "b", nom: "Bêta"}], "a");
  contenu = 2000;   // la barre déborde à tous les niveaux : les cinq étapes sont posées
  b.majEtat({projet: "Alpha", version: 4, agir: true, factory: {etat: "en marche"}});
  assert.ok(entete.classList.contains("barre-minimale"), "dernier resserrement atteint");
  assert.ok(!enfants[0].classList.contains("replie"));
  assert.ok(b.boutonNouvelle.classList.contains("replie"), "les actions passent dans le menu sur téléphone");
  const choix = entete.tous((n) => n.tagName === "SELECT")[0];
  assert.ok(choix && choix.hidden === false && !choix.classList.contains("replie"), "le sélecteur reste dans la barre");
  assert.ok(!choix.parent.hidden && !choix.parent.classList.contains("replie"));
  assert.deepEqual(choix.enfants.map((o) => o.textContent), ["Alpha", "Bêta", "Nouveau projet…"]);
});

test("serveurs_de_travail_n_est_propose_que_si_le_bureau_peut_agir", async () => {
  // la carte n'est montée (panneau Direction) qu'avec `etat.agir === true` : sans elle, l'entrée ne mènerait nulle part
  const {creerBarre} = await import("../ui/barre.js");
  const entete = new Noeud("header");
  Object.defineProperty(entete, "scrollWidth", {get: () => 300});
  entete.clientWidth = 375;
  const b = creerBarre(entete, new Noeud("div"));
  const appels = [];
  b.brancherMenu({ouvrirReglages: () => appels.push("reglages"), ouvrirServeurs: () => appels.push("serveurs")});
  const roue = entete.tous((n) => n.tagName === "BUTTON" && n.getAttribute("aria-label") === "Paramètres")[0];
  const serveurs = () => entete.tous((n) => n.getAttribute("role") === "menuitem" && n.textContent.startsWith("Serveurs de travail"))[0];
  const reglages = () => entete.tous((n) => n.getAttribute("role") === "menuitem" && n.textContent.startsWith("Réglages"))[0];
  b.majEtat({projet: "Alpha", version: 4, agir: false, factory: {etat: "en marche"}});
  roue.click();
  assert.ok(serveurs().hidden, "sans `agir`, pas d'entrée « Serveurs de travail »");
  assert.equal(reglages().hidden, false, "la page Réglages reste proposée");
  roue.click();
  b.majEtat({projet: "Alpha", version: 4, agir: true, factory: {etat: "en marche"}});
  roue.click();
  assert.equal(serveurs().hidden, false);
  serveurs().click();
  assert.deepEqual(appels, ["serveurs"]);
});

test("panneaux_branche_le_menu_de_la_roue", () => {
  assert.match(panneaux, /barre\.brancherMenu\(\{/);
  assert.match(panneaux, /ouvrirReglages: \(\) => ouvrirPanneau\("reglages", null\)/);
  assert.match(panneaux, /ouvrirPanneau\("direction", null\)[\s\S]*carte-serveurs/);
});
