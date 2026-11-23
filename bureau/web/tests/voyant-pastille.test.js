// Le voyant de la barre : la pastille de couleur seule ; son texte est le nom accessible (aria-label, pas de title : il
// doublerait la bulle) et une bulle (role="tooltip") qui paraît au survol, au focus et au toucher ; un clic la bascule ;
// Échap (écouté sur le document tant qu'elle est ouverte) ou un clic ailleurs la ferme. Une région vive cachée annonce
// les changements d'état.
// La liste déroulante des projets est plus large qu'avant et n'est jamais cachée.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

class Noeud {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.enfants = []; this.parent = null; this.attrs = {}; this.auteurs = {};
    this.hidden = false; this._texte = ""; this.className = ""; this.dataset = {}; this.style = {}; this.title = "";
  }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...es) { for (const e of es) { e.parent = this; this.enfants.push(e); } }
  remove() { if (this.parent) this.parent.enfants = this.parent.enfants.filter((e) => e !== this); this.parent = null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener(n, f) { (this.auteurs[n] ||= []).push(f); }
  removeEventListener(n, f) { this.auteurs[n] = (this.auteurs[n] || []).filter((g) => g !== f); }
  emettre(n, ev = {}) {
    ev.target ??= this; ev.type = n;
    ev.stopPropagation ??= () => { ev.arrete = true; };
    for (const f of this.auteurs[n] || []) f.call(this, ev);
    if (!ev.arrete && this.parent) this.parent.emettre(n, ev);
    else if (!ev.arrete && this !== document) document.emettre(n, ev);
    return ev;
  }
  contains(n) { for (; n; n = n.parent) if (n === this) return true; return false; }
  getBoundingClientRect() { return {left: 300, bottom: 40, top: 10, right: 330, width: 30, height: 30}; }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = new Noeud("#document");
document.createElement = (t) => new Noeud(t);
document.body = new Noeud("body");
globalThis.window = {innerWidth: 375};

const {creerVoyant} = await import("../ui/voyant.js");
const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");
const bulles = () => document.body.tous((n) => n.getAttribute("role") === "tooltip");
const TEXTE = "En marche, sans activité depuis 14 j";

test("la_pastille_porte_le_texte_en_nom_accessible_sans_title_ni_libelle_visible", () => {
  const v = creerVoyant();
  v.maj(TEXTE, "ok");
  assert.equal(v.racine.title, "", "pas de title : l'infobulle native doublerait la bulle");
  assert.equal(v.racine.getAttribute("title"), null);
  assert.equal(v.racine.getAttribute("aria-label"), TEXTE);
  assert.equal(v.racine.getAttribute("role"), "img");
  assert.equal(v.racine.getAttribute("tabindex"), "0", "focusable : le texte est lisible au clavier et au toucher");
  assert.equal(v.racine.dataset.ton, "ok");
  assert.equal(v.racine.textContent, "", "aucun texte visible dans la barre");
  assert.equal(v.racine.tous((n) => n.className === "voyant-libelle").length, 0);
  v.maj("Relevé indisponible", "alerte");   // la mise à jour vive
  assert.equal(v.racine.getAttribute("aria-label"), "Relevé indisponible");
  assert.equal(v.racine.dataset.ton, "alerte");
});

test("un_changement_d_etat_est_annonce_par_une_region_vive_cachee", () => {
  const v = creerVoyant();
  assert.equal(v.annonce.getAttribute("role"), "status");
  assert.equal(v.annonce.getAttribute("aria-live"), "polite");
  assert.equal(v.annonce.className, "sr-seulement");
  v.maj(TEXTE, "ok");
  assert.equal(v.annonce.textContent, TEXTE);
  v.maj("En pause", "pause");
  assert.equal(v.annonce.textContent, "En pause");
  assert.equal(v.racine.getAttribute("role"), "img", "la pastille garde role=img et son nom accessible");
  assert.match(css, /\.sr-seulement \{[^}]*clip: rect/);
  assert.match(barre, /leVoyant\.annonce/, "la barre pose la région vive à côté de la pastille");
});

test("echap_ferme_la_bulle_ouverte_au_survol_et_l_ecouteur_ne_fuit_pas", () => {
  const v = creerVoyant();
  document.body.append(v.racine);
  v.maj(TEXTE, "ok");
  const ecouteurs = () => (document.auteurs.keydown || []).length;
  const avant = ecouteurs();
  v.racine.emettre("mouseenter");
  assert.equal(bulles().length, 1);
  assert.equal(ecouteurs(), avant + 1, "Échap est écouté sur le document tant que la bulle est ouverte");
  document.emettre("keydown", {key: "Escape", target: new Noeud("div")});   // sans que la pastille ait le focus
  assert.equal(bulles().length, 0);
  assert.equal(ecouteurs(), avant, "l'écouteur est retiré à la fermeture");
  v.racine.emettre("mouseenter"); v.racine.emettre("mouseleave");
  assert.equal(ecouteurs(), avant);
  document.emettre("keydown", {key: "Escape", target: new Noeud("div")});   // rien d'ouvert : sans effet
  assert.equal(bulles().length, 0);
});

test("un_second_clic_sur_la_pastille_ferme_la_bulle", () => {
  const v = creerVoyant();
  document.body.append(v.racine);
  v.maj(TEXTE, "ok");
  v.racine.emettre("click");
  assert.equal(bulles().length, 1);
  v.racine.emettre("click");
  assert.equal(bulles().length, 0, "le clic bascule");
  v.racine.emettre("click");
  assert.equal(bulles().length, 1);
  v.racine.emettre("mouseenter");   // le geste du toucher : survol puis clic ne referme pas
  v.racine.emettre("click");
  assert.equal(bulles().length, 1);
  v.cacher();
});

test("la_bulle_paraît_au_focus_au_clic_et_au_survol_et_se_ferme_avec_echap_ou_un_clic_ailleurs", () => {
  const v = creerVoyant();
  document.body.append(v.racine);
  v.maj(TEXTE, "ok");
  assert.equal(bulles().length, 0);
  v.racine.emettre("focus");
  assert.equal(bulles().length, 1);
  assert.equal(bulles()[0].textContent, TEXTE, "textContent seulement");
  assert.equal(bulles()[0].parent, document.body, "dans le body : la barre (overflow: hidden) ne la coupe pas");
  assert.equal(bulles()[0].style.top, "48px");
  v.maj("En pause", "pause");   // le texte suit l'état pendant que la bulle est là
  assert.equal(bulles()[0].textContent, "En pause");
  v.racine.emettre("keydown", {key: "Escape"});
  assert.equal(bulles().length, 0);
  v.racine.emettre("click");
  assert.equal(bulles().length, 1, "le toucher l'ouvre (le title ne s'affiche pas sur téléphone)");
  document.emettre("click", {target: new Noeud("div")});
  assert.equal(bulles().length, 0, "un clic ailleurs la ferme");
  v.racine.emettre("mouseenter");
  assert.equal(bulles().length, 1);
  v.racine.emettre("mouseleave");
  assert.equal(bulles().length, 0);
  v.racine.emettre("focus");
  v.racine.emettre("blur");
  assert.equal(bulles().length, 0);
});

test("la_barre_n_a_plus_de_libelle_de_voyant", () => {
  assert.doesNotMatch(css, /voyant-libelle/);
  assert.doesNotMatch(barre, /voyant-libelle/);
  assert.match(css, /\.voyant-bulle \{[^}]*position: fixed[^}]*z-index/);
  assert.match(css, /\.voyant-lampe \{ width: 1[4-6]px; height: 1[4-6]px;/);
});

test("la_liste_des_projets_est_plus_large_et_jamais_cachee", () => {
  const corps = css.match(/\n\.barre-choix \{([^}]*)\}/)[1];
  assert.match(corps, /min-width: 12em/);
  assert.match(corps, /max-width: 18em/);
  assert.match(css, /\.mobile \.barre-choix \{ max-width: 46vw; \}/);
  assert.match(css, /--choix-min: 12em;/);
  assert.match(css, /#barre\.barre-minimale \{ --choix-min: 6em; \}/, "le plancher redescend au dernier resserrement");
  assert.doesNotMatch(corps, /display:\s*none/);   // (barre-roue.test.js vérifie qu'aucune autre règle ne le cache)
});
