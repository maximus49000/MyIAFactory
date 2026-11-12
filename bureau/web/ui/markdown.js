// Un document .md se lit dans la page au lieu de se télécharger : un bloc repliable (flèche ▸ / ▾, replié par défaut avec
// l'aperçu des premières lignes, « Afficher tout » / « Réduire »), le Markdown rendu simplement et SANS RISQUE : aucun
// HTML brut n'est interprété (tout texte passe par textContent), seuls les liens http(s) deviennent des liens (nouvel
// onglet, sans référent), un lien javascript:, data: ou autre reste du texte. Le contenu est lu à la demande depuis
// la route qui sert déjà le fichier, jusqu'à 512 Ko ; au-delà, seul le téléchargement reste.
// Les fonctions pures sont testées avec node.

import {el} from "./dom.js";

export const MAX_MARKDOWN = 512 * 1024;
export const LIGNES_APERCU = 6;

export const estMarkdown = (chemin) => /\.md$/i.test(String(chemin || ""));

// Le lien d'un texte Markdown : l'adresse seulement si elle est http(s), sinon `null`.
export function lienSur(adresse) {
  try {
    const u = new URL(String(adresse).trim());
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}

const brut = (t) => el("span", "", t);      // du texte, jamais du HTML
let texteVers = null;      // le crochet de la page en cours de rendu : le texte brut -> des éléments (termes du glossaire…)
const brutes = (t) => (texteVers ? texteVers(t) : [brut(t)]);
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*|__[^_\n]+?__)|(\*[^*\s][^*\n]*?\*|(?<![\w])_[^_\s][^_\n]*?_(?![\w]))|(\[[^\]\n]+\]\((?:[^()\s]|\([^()\s]*\))+\))/;

// Le texte d'une ligne en éléments : code, gras, italique, lien. Tout le reste est du texte brut.
export function inline(texte, profondeur = 0) {
  const sortie = [];
  let reste = String(texte);
  while (reste) {
    const m = INLINE.exec(reste);
    if (!m) { sortie.push(...brutes(reste)); break; }
    if (m.index > 0) sortie.push(...brutes(reste.slice(0, m.index)));
    const [tout] = m;
    if (m[1]) sortie.push(el("code", "md-code", tout.slice(1, -1)));
    else if (m[2]) sortie.push(profondeur ? el("strong", "", tout.slice(2, -2)) : noeud("strong", tout.slice(2, -2), profondeur));
    else if (m[3]) sortie.push(profondeur ? el("em", "", tout.slice(1, -1)) : noeud("em", tout.slice(1, -1), profondeur));
    else {
      const [, libelle, adresse] = /^\[([^\]]+)\]\((.+)\)$/.exec(tout);
      const sur = lienSur(adresse);
      if (sur) {
        const a = el("a", "md-lien", libelle);
        a.href = sur;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        sortie.push(a);
      } else sortie.push(brut(libelle));        // javascript:, data:, adresse relative… : du texte, pas un lien
    }
    reste = reste.slice(m.index + tout.length);
  }
  return sortie;
}
function noeud(balise, texte, profondeur) {
  const n = el(balise, "");
  n.append(...inline(texte, profondeur + 1));
  return n;
}
function ajouter(parent, morceaux) {
  for (const m of morceaux) parent.append(m);
}
const ligneEl = (balise, classe, texte) => { const n = el(balise, classe); ajouter(n, inline(texte)); return n; };

// --- Les tableaux (GFM) ------------------------------------------------------------------------------------------------

// Les cellules d'une ligne de tableau : barres de bord facultatives, `\|` est une barre dans la cellule.
function cellules(ligne) {
  let t = ligne.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|") && !t.endsWith("\\|")) t = t.slice(0, -1);
  const sortie = [];
  let cellule = "";
  for (let i = 0; i < t.length; i++) {
    if (t[i] === "\\" && t[i + 1] === "|") { cellule += "|"; i += 1; }
    else if (t[i] === "|") { sortie.push(cellule.trim()); cellule = ""; }
    else cellule += t[i];
  }
  sortie.push(cellule.trim());
  return sortie;
}
const estSeparateur = (ligne) => ligne.includes("|") && ligne.includes("-") && cellules(ligne).every((c) => /^:?-+:?$/.test(c));
// Un tableau commence ici : une ligne d'en-tête, puis la ligne de séparation `|---|---|` avec le même nombre de colonnes.
const debutTableau = (lignes, i) => i + 1 < lignes.length && lignes[i].includes("|") && estSeparateur(lignes[i + 1])
  && cellules(lignes[i]).length === cellules(lignes[i + 1]).length;
const alignement = (c) => (/^:-+:$/.test(c) ? "md-centre" : /-:$/.test(c) ? "md-droite" : /^:/.test(c) ? "md-gauche" : "");

// Un tableau aplati : quand les retours à la ligne d'un compte rendu ont été perdus (projet existant), le tableau tient sur
// UNE ligne : « Titre | A | B | |---|---| | 1 | 2 | | 3 | 4 | ». Heuristique : une ligne qui porte, après une barre, une
// séparation `|---|…|` (3 tirets au moins par colonne) est découpée en titre, en-tête (les n dernières cellules avant la
// séparation, n étant le nombre de colonnes de la séparation), séparation, puis les lignes de données, coupées sur
// « | | » (la barre qui ferme une ligne, un espace, celle qui ouvre la suivante). Une cellule vide entre deux barres
// séparées d'un espace est donc prise pour une fin de ligne : on reconstruit au mieux, sans rien promettre.
const SEPARATION_PLATE = /(?:\|\s*:?-{3,}:?\s*)+\|/;
export function deplierTableau(ligne) {
  const m = SEPARATION_PLATE.exec(ligne);
  if (!m) return [ligne];
  const avant = ligne.slice(0, m.index).trimEnd();
  const n = m[0].split("|").length - 2;
  if (!avant.endsWith("|")) return [ligne];
  const morceaux = avant.split("|");
  if (morceaux.length - 1 < n) return [ligne];
  const titre = morceaux.slice(0, morceaux.length - 1 - n).join("|").trim();
  const entete = morceaux.slice(morceaux.length - 1 - n, -1).map((c) => c.trim());
  let reste = ligne.slice(m.index + m[0].length).trim();
  const sortie = titre ? [titre, ""] : [];
  sortie.push("| " + entete.join(" | ") + " |", m[0].trim());
  if (reste.startsWith("|")) {
    reste = reste.slice(1);
    if (reste.endsWith("|")) reste = reste.slice(0, -1);
    for (const r of reste.split(/\|\s+\|/)) if (r.trim()) sortie.push("| " + r.trim() + " |");
  } else if (reste) sortie.push("", reste);
  return sortie;
}

function tableauEl(lignes) {
  const colonnes = cellules(lignes[0]).length;
  const classes = cellules(lignes[1]).map(alignement);
  const rangee = (balise, texte) => {
    const tr = el("tr", "");
    const c = cellules(texte);
    for (let k = 0; k < colonnes; k++) tr.append(ligneEl(balise, classes[k], c[k] ?? ""));
    return tr;
  };
  const tete = el("thead", ""), corps = el("tbody", ""), table = el("table", "md-table");
  tete.append(rangee("th", lignes[0]));
  for (const l of lignes.slice(2)) corps.append(rangee("td", l));
  table.append(tete, corps);
  const defile = el("div", "md-tableau");      // au téléphone, un tableau large défile au lieu de déborder
  defile.append(table);
  return defile;
}

// Le Markdown en éléments : titres, paragraphes, listes (à puces ou numérotées), citations, blocs de code, filet,
// tableaux. Options : `sauts` garde les retours à la ligne d'un paragraphe (un compte rendu) ; `texte` : crochet qui
// transforme chaque morceau de texte brut en éléments (les termes du glossaire).
export function rendreMarkdown(source, options = {}) {
  const avant = texteVers;
  texteVers = options.texte || null;
  try { return rendre(source, options.sauts === true); } finally { texteVers = avant; }
}

// Un texte venu d'un agent (compte rendu, message, journal) rendu comme un document .md, en gardant ses retours à la ligne :
// un bloc `<div class="classe md-rendu">`. Même rendu sûr ; `options` comme `rendreMarkdown`.
export function rendreTexte(classe, source, options = {}) {
  const bloc = el("div", (classe ? classe + " " : "") + "md-rendu");
  bloc.append(...rendreMarkdown(source, {...options, sauts: true}));
  return bloc;
}

function rendre(source, sauts) {
  const brutes_ = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  const lignes = [];
  let dedans = null;
  for (const l of brutes_) {      // les tableaux aplatis sont dépliés, hors blocs de code
    const f = /^\s*(```|~~~)/.exec(l);
    if (f && (!dedans || l.trim().startsWith(dedans))) dedans = dedans ? null : f[1];
    if (dedans || f) lignes.push(l); else lignes.push(...deplierTableau(l));
  }
  const sortie = [];
  let i = 0;
  const vide = (l) => l.trim() === "";
  while (i < lignes.length) {
    const l = lignes[i];
    if (vide(l)) { i += 1; continue; }
    const code = /^\s*(```|~~~)/.exec(l);
    if (code) {
      const corps = [];
      i += 1;
      while (i < lignes.length && !lignes[i].trim().startsWith(code[1])) corps.push(lignes[i++]);
      i += 1;
      const pre = el("pre", "md-pre");
      pre.append(el("code", "", corps.join("\n")));
      sortie.push(pre);
      continue;
    }
    const titre = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(l);
    if (titre) {
      sortie.push(ligneEl(titre[1].length <= 2 ? "h4" : titre[1].length === 3 ? "h5" : "h6", "md-titre", titre[2]));
      i += 1;
      continue;
    }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(l)) { sortie.push(el("hr", "md-filet")); i += 1; continue; }
    if (/^\s{0,3}>/.test(l)) {
      const corps = [];
      while (i < lignes.length && /^\s{0,3}>/.test(lignes[i])) corps.push(lignes[i++].replace(/^\s{0,3}>\s?/, ""));
      const q = el("blockquote", "md-citation");
      ajouter(q, inline(corps.join(" ")));
      sortie.push(q);
      continue;
    }
    const puce = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(l);
    if (puce) {
      const numerote = /\d/.test(puce[1]);
      const liste = el(numerote ? "ol" : "ul", "md-liste");
      while (i < lignes.length) {
        const p = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lignes[i]);
        if (!p || /\d/.test(p[1]) !== numerote) break;
        liste.append(ligneEl("li", "", p[2]));
        i += 1;
      }
      sortie.push(liste);
      continue;
    }
    if (debutTableau(lignes, i)) {
      const t = [lignes[i], lignes[i + 1]];
      i += 2;
      while (i < lignes.length && !vide(lignes[i]) && lignes[i].includes("|")) t.push(lignes[i++]);
      sortie.push(tableauEl(t));
      continue;
    }
    const para = [];
    while (i < lignes.length && !vide(lignes[i]) && !/^\s*(```|~~~|#{1,6}\s|>|([-*+]|\d+[.)])\s)/.test(lignes[i])
           && !(para.length && debutTableau(lignes, i))) para.push(lignes[i++].trim());
    if (!para.length) { para.push(lignes[i++].trim()); }
    sortie.push(ligneEl("p", sauts ? "md-para md-sauts" : "md-para", para.join(sauts ? "\n" : " ")));
  }
  return sortie;
}

// L'aperçu : les premières lignes non vides du texte (un bloc de code entamé est refermé).
export function apercu(source, n = LIGNES_APERCU) {
  const lignes = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  const prises = [];
  let compte = 0, dedans = false;
  for (const l of lignes) {
    if (compte >= n) break;
    if (/^\s*(```|~~~)/.test(l)) dedans = !dedans;
    prises.push(l);
    if (l.trim() !== "") compte += 1;
  }
  const coupe = prises.length < lignes.length && lignes.slice(prises.length).some((l) => l.trim() !== "");
  return {texte: prises.join("\n") + (dedans ? "\n```" : ""), coupe};
}

const cache = new Map();      // adresse -> {texte} | {trop: true} | {erreur}
export function oublierMarkdowns() { cache.clear(); }

// La lecture d'un document : texte, ou `trop` (plus de 512 Ko), ou `erreur`. `lire` remplaçable pour les tests.
export async function lireMarkdown(adresse, lire = globalThis.fetch?.bind(globalThis)) {
  if (cache.has(adresse)) return cache.get(adresse);
  let r;
  try {
    const reponse = await lire(adresse, {cache: "no-store"});
    const taille = Number(reponse.headers?.get?.("Content-Length"));
    if (reponse.status === 413 || (Number.isFinite(taille) && taille > MAX_MARKDOWN)) r = {trop: true};
    else if (!reponse.ok) r = {erreur: "Document illisible ici."};
    else {
      const texte = await reponse.text();
      r = texte.length > MAX_MARKDOWN ? {trop: true} : {texte};
    }
  } catch { r = {erreur: "Document illisible ici."}; }
  if (!r.erreur) cache.set(adresse, r);
  return r;
}

// Le bloc repliable d'un document .md : titre, flèche, aperçu, « Afficher tout » / « Réduire ». `lien` (facultatif) est
// le lien « Télécharger », mis à côté. Rend l'élément tout de suite ; le contenu s'y met quand il est lu.
export function blocMarkdown({titre, adresse, lien = null, lire}) {
  const bloc = el("div", "md-bloc");
  const tete = el("div", "md-tete");
  const bascule = el("button", "md-bascule", "▸ " + titre);
  bascule.type = "button";
  bascule.setAttribute("aria-expanded", "false");
  tete.append(bascule);
  if (lien) tete.append(lien);
  const corps = el("div", "md-corps");
  corps.append(el("p", "note", "Chargement…"));
  bloc.append(tete, corps);
  let plein = false, pret = null;
  const afficher = () => {
    if (!pret) return;
    bascule.textContent = (plein ? "▾ " : "▸ ") + titre;
    bascule.setAttribute("aria-expanded", String(plein));
    bloc.className = "md-bloc" + (plein ? " ouvert" : "");
    corps.replaceChildren(...(plein ? pret.tout : pret.debut));
    if (pret.coupe) {
      const b = el("button", "bouton secondaire petit md-tout", plein ? "Réduire" : "Afficher tout");
      b.type = "button";
      b.addEventListener("click", () => { plein = !plein; afficher(); });
      corps.append(b);
    }
  };
  bascule.addEventListener("click", () => { if (pret) { plein = !plein; afficher(); } });
  lireMarkdown(adresse, lire).then((r) => {
    if (r.texte === undefined) {
      corps.replaceChildren(el("p", "note", r.trop ? "Document trop long pour être lu ici : téléchargez-le." : r.erreur));
      return;
    }
    const a = apercu(r.texte);
    pret = {debut: rendreMarkdown(a.texte), tout: rendreMarkdown(r.texte), coupe: a.coupe};
    afficher();
  });
  return bloc;
}
