// Le catalogue d'une fonctionnalité : la page (groupes, vue de haut, compteurs, demandes, passes, leçons,
// filtres, liste par pages de 100, kit) et la fiche d'un élément (captures, comparaison, connaissance, doute,
// « Demander à modifier »). Les fonctions pures sont testées avec node.
// Le catalogue est lu à la demande (`/api/catalogue`) ; tout texte qui en vient passe par textContent ;
// une partie sans donnée n'est pas montrée. Le geste « Demander à modifier » est une demande au projet.

import {el} from "./dom.js";
import {dateFr} from "./texte.js";
import {lienSur} from "./actions.js";
import {urlProjet} from "./projets.js";
import {cadrage, creerVueDeHaut} from "./vue-de-haut.js";

export {cadrage};

export const TAILLE_PAGE = 100;
const MAX_TEXTE = 3500;
const MAX_NOTE_CARTE = 220;

// --- Fonctions pures.
export function sansAccents(texte) {
  return String(texte ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

const textes = new WeakMap();   // élément -> texte de recherche (nom, id, note), calculé une fois
function texteDe(e) {
  let t = textes.get(e);
  if (t === undefined) {
    t = sansAccents([e.nom, e.id, e.note].filter((x) => typeof x === "string").join("\n"));
    textes.set(e, t);
  }
  return t;
}

const liste = (v) => (Array.isArray(v) ? v : []);

// Les éléments qui passent tous les filtres donnés (un filtre absent, nul ou faux ne filtre pas).
export function filtrerElements(cat, {groupe = null, passe = null, aReevaluer = false, doutes = false,
                                      etat = null, recherche = ""} = {}) {
  const mots = sansAccents(recherche).trim();
  return liste(cat?.elements).filter((e) => {
    if (groupe !== null && groupe !== undefined && e.groupe !== groupe) return false;
    if (passe !== null && passe !== undefined && !liste(e.passes).includes(passe)) return false;
    if (aReevaluer && !liste(e.a_reevaluer).length) return false;
    if (doutes && !e.doute) return false;
    if (etat !== null && etat !== undefined && (e.etat ?? "") !== etat) return false;
    return !mots || texteDe(e).includes(mots);
  });
}

// Le nombre d'éléments d'un groupe (null : tous), et par état ("" : sans état).
export function compteurs(cat, groupe) {
  const parEtat = Object.create(null);   // un état « constructor » ou « __proto__ » reste un état
  let total = 0;
  for (const e of liste(cat?.elements)) {
    if (groupe !== null && groupe !== undefined && e.groupe !== groupe) continue;
    total++;
    const k = e.etat ?? "";
    parEtat[k] = (parEtat[k] || 0) + 1;
  }
  return {total, parEtat: {...parEtat}};
}

// Chaque élément commun (ceux déclarés d'abord, dans l'ordre) -> les ids des éléments qui l'utilisent.
export function utilisationsKit(cat) {
  const u = new Map();
  for (const k of liste(cat?.kit)) if (k && typeof k.id === "string" && !u.has(k.id)) u.set(k.id, []);
  for (const e of liste(cat?.elements)) {
    for (const k of liste(e.kit)) {
      if (!u.has(k)) u.set(k, []);
      const ids = u.get(k);
      if (ids[ids.length - 1] !== e.id) ids.push(e.id);
    }
  }
  return u;
}

// Une valeur de caractéristique qui est une couleur sûre à poser en style (#rgb, #rrggbb, rgb(r, g, b)).
export function estCouleur(v) {
  return typeof v === "string"
    && (/^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(v) || /^rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)$/i.test(v));
}

export function demandeRetourElement(fonc, element, texte) {
  return {type: "retour_element", fonctionnalite: fonc, element, texte};
}

// La page n (à partir de 0, bornée) d'une liste.
export function pageDe(lst, n, taille = TAILLE_PAGE) {
  const total = lst.length;
  const pages = Math.max(1, Math.ceil(total / taille));
  const page = Math.min(pages - 1, Math.max(0, Math.floor(Number(n) || 0)));
  return {elements: lst.slice(page * taille, (page + 1) * taille), page, pages, total};
}

// La teinte d'un élément sur la carte et dans la légende : doute, validé, à revoir, ou autre.
const ETATS_OK = new Set(["valide", "validé", "fait", "termine", "terminé", "ok"]);
const ETATS_A_FAIRE = new Set(["a_revoir", "a_faire", "en_cours", "todo"]);
export function teinte(e) {
  if (e?.doute) return "doute";
  const s = sansAccents(e?.etat ?? "");
  if (ETATS_OK.has(s)) return "ok";
  if (ETATS_A_FAIRE.has(s)) return "a-faire";
  return "autre";
}
const LIBELLES_ETAT = {valide: "validé", a_revoir: "à revoir", a_faire: "à faire", en_cours: "en cours", fait: "fait",
                       termine: "terminé", "": "sans état"};
export function libelleEtat(etat) {
  const k = etat ?? "";
  return Object.hasOwn(LIBELLES_ETAT, k) ? LIBELLES_ETAT[k] : String(k).replace(/_/g, " ");
}

// --- La vue (navigateur seulement).
const urlImage = (chemin) => urlProjet(`/api/image?chemin=${encodeURIComponent(chemin)}`);

function bouton(texte, classe = "cat-bouton") {
  const b = el("button", classe, texte);
  b.type = "button";
  return b;
}

function image(ctx, chemin, alt) {
  if (ctx.etat.images_ok !== true) return el("div", "cat-sans-image", "Image non affichable");
  const img = document.createElement("img");
  img.loading = "lazy";
  img.decoding = "async";
  img.src = urlImage(chemin);
  img.alt = alt;
  img.addEventListener("error", () => img.replaceWith(el("div", "cat-sans-image", "Image introuvable")), {once: true});
  return img;
}

function lienExterne(url, texte) {
  const a = el("a", "", texte);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

const derniereCapture = (e) => {
  const c = liste(e.captures);
  if (!c.length) return null;
  return c.reduce((m, x) => ((x.passe ?? -Infinity) >= (m.passe ?? -Infinity) ? x : m));
};

function plaque(texte, balise = "h3") {
  const p = el(balise, "cat-plaque", texte);
  p.title = texte;
  return p;
}

function puce(texte, titre) {
  const s = el("span", "cat-puce", texte);
  if (titre) s.title = titre;
  return s;
}

// Lecture du catalogue : une fois par ouverture (ou « Actualiser »), gardée dans ctx.catalogues.
async function charger(ctx, fonc) {
  const entree = {statut: "chargement"};
  ctx.catalogues.set(fonc, entree);
  try {
    const r = await fetch(urlProjet(`/api/catalogue?fonctionnalite=${encodeURIComponent(fonc)}`),
      {cache: "no-store", signal: AbortSignal.timeout(60000)});
    let j = null;
    try { j = await r.json(); } catch { /* corps illisible */ }
    if (r.ok && j && j.catalogue) Object.assign(entree, {statut: "ok", cat: j.catalogue, avertissements: liste(j.avertissements)});
    else Object.assign(entree, {statut: "erreur", erreur: j?.erreur || `Catalogue indisponible (${r.status}).`});
  } catch {
    Object.assign(entree, {statut: "erreur", erreur: "Serveur du bureau injoignable."});
  }
  if (ctx.catalogues.get(fonc) === entree && ctx.estOuvert("catalogue", fonc)) ctx.rouvrir();
}

// Les retours envoyés que le catalogue n'a pas encore repris (clé fonc + élément).
const cleRetour = (fonc, id) => fonc + "\u0000" + id;
function retoursLocaux(ctx, fonc, e) {
  const cle = cleRetour(fonc, e.id);
  const repris = new Set(liste(e.retours).map((r) => String(r.texte).trim()));
  const restes = (ctx.retoursEnvoyes.get(cle) || []).filter((t) => !repris.has(t));
  if (restes.length) ctx.retoursEnvoyes.set(cle, restes); else ctx.retoursEnvoyes.delete(cle);
  return restes;
}

// ctx : {etat, barre, catalogues, vuesCatalogue, retoursEnvoyes, rouvrir, grand, basculerGrand, ouvrirFonctionnalite}
export function contenuCatalogue(ctx, contenu, f) {
  const fonc = f.id;
  if (!ctx.vuesCatalogue.has(fonc)) {
    ctx.vuesCatalogue.set(fonc, {groupe: null, passe: null, aReevaluer: false, doutes: false, etat: null,
                                 recherche: "", page: 0, fiche: null, carte: {t: null}, defilement: 0});
  }
  const ui = ctx.vuesCatalogue.get(fonc);
  const entree = ctx.catalogues.get(fonc);
  if (!entree) charger(ctx, fonc);
  contenu.classList.add("catalogue");

  const tete = el("div", "cat-tete");
  tete.append(el("h2", "", "Catalogue · " + f.nom));
  const outils = el("div", "cat-outils");
  const retour = bouton("← " + "Fonctionnalité");
  retour.addEventListener("click", () => ctx.ouvrirFonctionnalite(fonc));
  const agrandir = bouton(ctx.grand() ? "Réduire" : "Agrandir");
  agrandir.title = ctx.grand() ? "Revenir au panneau (Échap)" : "Plein écran (Échap pour revenir)";
  agrandir.addEventListener("click", () => ctx.basculerGrand());
  const actualiser = bouton("Actualiser");
  actualiser.addEventListener("click", () => { ctx.catalogues.delete(fonc); ctx.rouvrir(); });
  outils.append(retour, actualiser, agrandir);
  tete.append(outils);
  contenu.append(tete);

  if (!entree || entree.statut === "chargement") {
    contenu.append(el("p", "cat-discret", "Lecture du catalogue…"));
    return;
  }
  if (entree.statut === "erreur") {
    contenu.append(el("p", "cat-erreur", entree.erreur));
    return;
  }
  const cat = entree.cat;
  const parId = new Map(liste(cat.elements).map((e) => [e.id, e]));
  if (ui.fiche !== null && parId.has(ui.fiche)) {
    contenuFiche(ctx, contenu, f, cat, parId.get(ui.fiche), ui);
    return;
  }
  ui.fiche = null;
  contenuPage(ctx, contenu, f, cat, entree, ui, parId);
}

// --- La page du catalogue.
function contenuPage(ctx, contenu, f, cat, entree, ui, parId) {
  const elements = liste(cat.elements);
  const groupes = liste(cat.groupes);
  const nomGroupe = new Map(groupes.map((g) => [g.id, g.nom]));
  const lecons = liste(cat.lecons);
  const passes = liste(cat.passes);
  const parPasse = new Map(), parLecon = new Map();   // un seul passage sur les éléments
  for (const e of elements) {
    for (const n of new Set(liste(e.passes))) parPasse.set(n, (parPasse.get(n) || 0) + 1);
    for (const l of new Set(liste(e.a_reevaluer))) parLecon.set(l, (parLecon.get(l) || 0) + 1);
  }
  const ouvrirFiche = (id) => {
    ui.defilement = contenu.closest(".panneau")?.scrollTop || 0;
    ui.fiche = id;
    ui.hautDeFiche = true;
    ctx.rouvrir();
  };

  if (entree.avertissements.length) {
    const d = el("details", "cat-avertissements");
    d.append(el("summary", "", `${entree.avertissements.length} avertissement${entree.avertissements.length > 1 ? "s" : ""} à la lecture du catalogue`));
    const ul = el("ul", "");
    for (const a of entree.avertissements) ul.append(el("li", "", a));
    d.append(ul);
    contenu.append(d);
  }
  if (!elements.length) {
    contenu.append(el("p", "cat-discret", "Le catalogue est vide pour l'instant."));
    return;
  }

  // Le choix du groupe, avec ses compteurs.
  if (groupes.length) {
    const barreGroupes = el("div", "cat-filtres cat-groupes");
    barreGroupes.setAttribute("role", "group");
    barreGroupes.setAttribute("aria-label", "Choisir un groupe");
    const choix = (id, nom) => {
      const c = compteurs(cat, id);
      const b = bouton("", "cat-filtre");
      b.append(nom + " ", el("span", "n", String(c.total)));
      b.title = Object.entries(c.parEtat).map(([k, n]) => `${libelleEtat(k)} : ${n}`).join(" · ");
      b.setAttribute("aria-pressed", String(ui.groupe === id));
      b.addEventListener("click", () => {
        Object.assign(ui, {groupe: id, page: 0, etat: null, doutes: false, aReevaluer: false});
        ctx.rouvrir();
      });
      barreGroupes.append(b);
    };
    choix(null, "Tous");
    for (const g of groupes) choix(g.id, g.nom);
    contenu.append(barreGroupes);
  }

  const dansGroupe = ui.groupe === null ? elements : elements.filter((e) => e.groupe === ui.groupe);
  const filtres = () => ({groupe: ui.groupe, passe: ui.passe, aReevaluer: ui.aReevaluer, doutes: ui.doutes,
                          etat: ui.etat, recherche: ui.recherche});

  // La vue de haut, si des éléments ont une position.
  const places = dansGroupe.filter((e) => Number.isFinite(e.position?.x) && Number.isFinite(e.position?.y));
  let carte = null;
  if (places.length) {
    const section = el("section", "cat-section");
    section.append(el("h3", "", "Vue de haut"));
    section.append(el("p", "cat-discret", "Chaque point est un élément : un clic mène à sa fiche. Molette ou boutons pour zoomer, glisser pour se déplacer."));
    const outilsCarte = el("div", "cat-outils-carte");
    const plus = bouton("+"), moins = bouton("−"), tout = bouton("Tout voir");
    plus.setAttribute("aria-label", "Zoomer");
    moins.setAttribute("aria-label", "Dézoomer");
    const legende = el("span", "cat-legende");
    const presentes = new Set(places.map(teinte));
    const NOMS = {ok: "validé", "a-faire": "à faire ou à revoir", autre: "autre état", doute: "doute"};
    for (const k of ["ok", "a-faire", "autre", "doute"]) {
      if (!presentes.has(k)) continue;
      const s = el("span", "");
      s.append(el("i", "cat-pastille " + k), NOMS[k]);
      legende.append(s);
    }
    if (liste(cat.trace).length) {
      const s = el("span", "");
      s.append(el("i", "cat-pastille trace"), "tracé");
      legende.append(s);
    }
    outilsCarte.append(plus, moins, tout, legende);
    ui.carte.groupe !== ui.groupe && (ui.carte = {t: null, groupe: ui.groupe});
    const correspond = new Set(filtrerElements(cat, filtres()).map((e) => e.id));
    ui.vueDeHaut?.detruire();
    carte = ui.vueDeHaut = creerVueDeHaut({
      elements: places, traces: liste(cat.trace), vue: ui.carte,
      teinte,
      estompe: (e) => !correspond.has(e.id),
      libelle: (e) => `${e.nom} · ${libelleEtat(e.etat)}`,
      surChoix: (e) => ouvrirFiche(e.id),
    });
    plus.addEventListener("click", () => carte.zoomer(1.5));
    moins.addEventListener("click", () => carte.zoomer(1 / 1.5));
    tout.addEventListener("click", () => carte.toutVoir());
    section.append(outilsCarte, carte.element);
    contenu.append(section);
  }

  // Les compteurs généraux (du groupe choisi).
  const c = compteurs(cat, ui.groupe);
  const ligneCompteurs = el("p", "cat-compteurs");
  const compte = (n, singulier, pluriel = singulier) => {
    if (!n) return;
    const s = el("span", "");
    s.append(el("b", "", String(n)), " " + (n > 1 ? pluriel : singulier));
    ligneCompteurs.append(s);
  };
  compte(c.total, "élément", "éléments");
  for (const [k, n] of Object.entries(c.parEtat)) if (k !== "" || Object.keys(c.parEtat).length > 1) compte(n, libelleEtat(k));
  compte(dansGroupe.filter((e) => e.doute).length, "doute", "doutes");
  compte(dansGroupe.filter((e) => liste(e.a_reevaluer).length).length, "à réévaluer");
  compte(dansGroupe.filter((e) => e.evenement).length, "avec événement");
  compte(dansGroupe.reduce((n, e) => n + liste(e.captures).length, 0), "capture", "captures");
  contenu.append(ligneCompteurs);

  // Les demandes de modification et leurs réponses (les plus récentes d'abord).
  const demandes = [];
  for (const e of elements) for (const r of liste(e.retours)) demandes.push({e, r});
  if (demandes.length) {
    demandes.sort((a, b) => String(b.r.t || "").localeCompare(String(a.r.t || "")));
    const section = el("section", "cat-section");
    section.append(el("h3", "", `Demandes de modification (${demandes.length})`));
    const d = el("details", "");
    d.open = demandes.length <= 5;
    d.append(el("summary", "", "Voir les demandes"));
    const ul = el("ul", "cat-demandes");
    for (const {e, r} of demandes.slice(0, TAILLE_PAGE)) ul.append(ligneRetour(r, e, () => ouvrirFiche(e.id)));
    if (demandes.length > TAILLE_PAGE) ul.append(el("li", "cat-discret", `… et ${demandes.length - TAILLE_PAGE} autres (sur les fiches).`));
    d.append(ul);
    section.append(d);
    contenu.append(section);
  }

  // Les passes : les versions de la méthode.
  if (passes.length) {
    const section = el("section", "cat-section");
    section.append(el("h3", "", "Les passes"));
    const ul = el("ul", "cat-passes");
    for (const p of [...passes].sort((a, b) => b.numero - a.numero)) {
      const li = el("li", "");
      const n = parPasse.get(p.numero) || 0;
      li.append(el("b", "", `Passe ${p.numero}`));
      if (p.titre) li.append(" · " + p.titre);
      li.append(" ", el("span", "cat-quand", [p.date ? dateFr(p.date) : null, `${n} élément${n > 1 ? "s" : ""}`].filter(Boolean).join(" · ")));
      ul.append(li);
    }
    section.append(ul);
    contenu.append(section);
  }

  // Ce que j'ai appris : les leçons, avec leur portée.
  if (lecons.length) {
    const section = el("section", "cat-section");
    section.append(el("h3", "", "Ce que j'ai appris"));
    const aReeval = elements.filter((e) => liste(e.a_reevaluer).length).length;
    section.append(el("p", "cat-discret", "Chaque leçon tirée d'une correction, avec sa portée. Une leçon apprise après la reprise d'un élément et qui le concerne le met « à réévaluer »"
      + (aReeval ? ` (${aReeval} aujourd'hui).` : ".")));
    const d = el("details", "");
    d.append(el("summary", "", `Voir les ${lecons.length} leçon${lecons.length > 1 ? "s" : ""}`));
    d.addEventListener("toggle", () => {   // la liste n'est construite qu'à l'ouverture
      if (!d.open || d.dataset.fait) return;
      d.dataset.fait = "1";
      const ul = el("ul", "cat-lecons");
      for (const l of lecons) {
        const li = el("li", "");
        li.append(el("b", "", l.titre ? `${l.id} · ${l.titre}` : l.id));
        const n = parLecon.get(l.id) || 0;
        const quand = [l.passe !== undefined ? `passe ${l.passe}` : null, l.portee || null, n ? `${n} à réévaluer` : null].filter(Boolean);
        if (quand.length) li.append(" ", el("span", "cat-quand", quand.join(" · ")));
        if (l.texte) li.append(el("div", "", l.texte));
        ul.append(li);
      }
      d.append(ul);
    });
    section.append(d);
    contenu.append(section);
  }

  // Les filtres et la recherche.
  const zoneListe = el("div", "");
  const majListe = () => {
    dessinerListe(ctx, zoneListe, cat, filtrerElements(cat, filtres()), ui, nomGroupe, ouvrirFiche);
    if (carte) {
      const correspond = new Set(filtrerElements(cat, filtres()).map((e) => e.id));
      carte.filtrer((e) => !correspond.has(e.id));
    }
  };
  const pressions = [];
  const filtre = (barre, texte, n, actif, changer) => {
    const b = bouton("", "cat-filtre");
    b.append(texte);
    if (n !== undefined) b.append(" ", el("span", "n", String(n)));
    const maj = () => b.setAttribute("aria-pressed", String(actif()));
    maj();
    pressions.push(maj);
    b.addEventListener("click", () => { changer(); ui.page = 0; pressions.forEach((p) => p()); majListe(); });
    barre.append(b);
  };
  if (passes.length) {
    const barrePasses = el("div", "cat-filtres");
    barrePasses.setAttribute("role", "group");
    barrePasses.setAttribute("aria-label", "Filtrer par passe");
    filtre(barrePasses, "Toutes les passes", undefined, () => ui.passe === null, () => { ui.passe = null; });
    for (const p of [...passes].sort((a, b) => a.numero - b.numero)) {
      const n = dansGroupe.filter((e) => liste(e.passes).includes(p.numero)).length;
      filtre(barrePasses, `Passe ${p.numero}`, n, () => ui.passe === p.numero, () => { ui.passe = p.numero; });
    }
    contenu.append(barrePasses);
  }
  const barreFiltres = el("div", "cat-filtres");
  barreFiltres.setAttribute("role", "search");
  const recherche = document.createElement("input");
  recherche.type = "search";
  recherche.placeholder = "Chercher un nom, un identifiant, une note";
  recherche.setAttribute("aria-label", "Chercher un élément");
  recherche.value = ui.recherche;
  let minuteur = null;
  recherche.addEventListener("input", () => {
    clearTimeout(minuteur);
    minuteur = setTimeout(() => { ui.recherche = recherche.value; ui.page = 0; majListe(); }, 150);
  });
  barreFiltres.append(recherche);
  if (Object.keys(c.parEtat).length >= 2 || ui.etat !== null) {
    filtre(barreFiltres, "Tous", undefined, () => ui.etat === null, () => { ui.etat = null; });
  }
  for (const [k, n] of Object.entries(c.parEtat)) {
    if (Object.keys(c.parEtat).length < 2) break;
    filtre(barreFiltres, libelleEtat(k), n, () => ui.etat === k, () => { ui.etat = ui.etat === k ? null : k; });
  }
  const nReeval = dansGroupe.filter((e) => liste(e.a_reevaluer).length).length;
  if (nReeval || ui.aReevaluer) filtre(barreFiltres, "À réévaluer", nReeval, () => ui.aReevaluer, () => { ui.aReevaluer = !ui.aReevaluer; });
  const nDoutes = dansGroupe.filter((e) => e.doute).length;
  if (nDoutes || ui.doutes) filtre(barreFiltres, "Doutes", nDoutes, () => ui.doutes, () => { ui.doutes = !ui.doutes; });
  contenu.append(barreFiltres, zoneListe);
  dessinerListe(ctx, zoneListe, cat, filtrerElements(cat, filtres()), ui, nomGroupe, ouvrirFiche);

  // Le kit : chaque élément commun, le nombre et la liste de ceux qui l'utilisent.
  const usages = utilisationsKit(cat);
  if (usages.size) {
    const section = el("section", "cat-section");
    section.append(el("h3", "", "Le kit"));
    section.append(el("p", "cat-discret", "Chaque élément commun, le nombre d'éléments qui l'utilisent et leur liste."));
    const grille = el("div", "cat-kit");
    const parKit = new Map(liste(cat.kit).map((k) => [k.id, k]));
    for (const [id, ids] of [...usages].slice(0, TAILLE_PAGE)) {
      const k = parKit.get(id) || {id};
      const art = el("article", "cat-kit-element");
      const h = el("h4", "", k.nom || id);
      h.append(el("span", "cat-nombre", String(ids.length)));
      art.append(h);
      if (k.description) art.append(el("p", "", k.description));
      if (ids.length) {
        const d = el("details", "");
        d.append(el("summary", "", `Voir ${ids.length > 1 ? `les ${ids.length} éléments` : "l'élément"}`));
        d.addEventListener("toggle", () => {   // la liste n'est construite qu'à l'ouverture
          if (!d.open || d.dataset.fait) return;
          d.dataset.fait = "1";
          const p = el("p", "cat-utilisateurs");
          ids.slice(0, TAILLE_PAGE).forEach((x, i) => {
            if (i) p.append(", ");
            const b = bouton(parId.get(x)?.nom || x, "cat-lien");
            b.addEventListener("click", () => ouvrirFiche(x));
            p.append(b);
          });
          if (ids.length > TAILLE_PAGE) p.append(` … et ${ids.length - TAILLE_PAGE} autres.`);
          d.append(p);
        });
        art.append(d);
      }
      grille.append(art);
    }
    section.append(grille);
    if (usages.size > TAILLE_PAGE) section.append(el("p", "cat-discret", `… et ${usages.size - TAILLE_PAGE} autres éléments communs.`));
    contenu.append(section);
  }

  // Revenir d'une fiche : retrouver l'endroit où l'on était.
  if (ui.defilement) {
    const y = ui.defilement;
    ui.defilement = 0;
    requestAnimationFrame(() => { const p = contenu.closest(".panneau"); if (p) p.scrollTop = y; });
  }
}

// La liste filtrée, par pages de 100 : une carte par élément.
function dessinerListe(ctx, zone, cat, filtres, ui, nomGroupe, ouvrirFiche) {
  const p = pageDe(filtres, ui.page);
  ui.page = p.page;
  zone.replaceChildren();
  const avecImages = liste(cat.elements).some((e) => liste(e.captures).length);
  const pied = () => {
    const nav = el("div", "cat-pages");
    nav.append(el("span", "cat-discret", `${p.total} résultat${p.total > 1 ? "s" : ""}` + (p.pages > 1 ? ` · page ${p.page + 1} sur ${p.pages}` : "")));
    if (p.pages > 1) {
      const avant = bouton("← Précédents"), apres = bouton("Suivants →");
      avant.disabled = p.page === 0;
      apres.disabled = p.page >= p.pages - 1;
      avant.addEventListener("click", () => { ui.page--; dessinerListe(ctx, zone, cat, filtres, ui, nomGroupe, ouvrirFiche); zone.scrollIntoView({block: "start"}); });
      apres.addEventListener("click", () => { ui.page++; dessinerListe(ctx, zone, cat, filtres, ui, nomGroupe, ouvrirFiche); zone.scrollIntoView({block: "start"}); });
      nav.append(avant, apres);
    }
    return nav;
  };
  zone.append(pied());
  const grille = el("div", "cat-grille");
  for (const e of p.elements) {
    const carte = el("article", "cat-carte-element");
    const ouvrir = bouton("", "cat-ouvrir");
    ouvrir.setAttribute("aria-label", "Ouvrir la fiche : " + e.nom);
    ouvrir.append(plaque(e.nom, "span"));
    ouvrir.addEventListener("click", () => ouvrirFiche(e.id));
    carte.append(ouvrir);
    if (avecImages) {
      const fig = el("figure", "cat-figure");
      const cap = derniereCapture(e);
      if (cap) {
        fig.append(image(ctx, cap.chemin, "Capture : " + e.nom));
        if (cap.passe !== undefined) fig.append(el("span", "cat-badge", `Passe ${cap.passe}`));
        fig.addEventListener("click", () => ouvrirFiche(e.id));
      } else fig.append(el("div", "cat-sans-image", "Capture à venir"));
      carte.append(fig);
    }
    const corps = el("div", "cat-corps");
    corps.append(meta(e, nomGroupe));
    if (e.note) corps.append(el("p", "cat-note", e.note.length > MAX_NOTE_CARTE ? e.note.slice(0, MAX_NOTE_CARTE - 1) + "…" : e.note));
    if (e.evenement) corps.append(el("p", "cat-evenement", e.evenement));
    if (e.doute) corps.append(el("p", "cat-doute", "Doute" + (e.doute.raison ? " : " + e.doute.raison : "")));
    if (liste(e.a_reevaluer).length) corps.append(el("p", "cat-reevaluer", "À réévaluer"));
    carte.append(corps);
    grille.append(carte);
  }
  zone.append(grille);
  if (p.pages > 1) zone.append(pied());
}

function meta(e, nomGroupe) {
  const m = el("p", "cat-meta");
  m.append(el("code", "", e.id));
  if (e.groupe) m.append(" · " + (nomGroupe.get(e.groupe) || e.groupe));
  if (e.etat !== undefined) m.append(" · ", el("span", "cat-etat " + teinte(e), libelleEtat(e.etat)));
  for (const n of liste(e.passes)) m.append(" ", el("span", "cat-passe", `Passe ${n}`));
  return m;
}

function ligneRetour(r, e, ouvrir) {
  const li = el("li", "");
  if (e) {
    const b = bouton(e.nom, "cat-lien");
    b.addEventListener("click", ouvrir);
    li.append(b, " · ");
  }
  li.append(el("span", "cat-quand", [r.t ? dateFr(r.t) : null, r.etat || null].filter(Boolean).join(" · ") || "demande"));
  li.append(el("p", "", r.texte));
  if (r.reponse) li.append(el("p", "cat-reponse", r.reponse));
  return li;
}

// --- La fiche d'un élément.
function contenuFiche(ctx, contenu, f, cat, e, ui) {
  const nomGroupe = new Map(liste(cat.groupes).map((g) => [g.id, g.nom]));
  const retour = bouton("← Retour au catalogue", "cat-bouton cat-retour");
  retour.addEventListener("click", () => { ui.fiche = null; ctx.rouvrir(); });
  contenu.append(retour);
  const fiche = el("article", "cat-fiche");
  fiche.append(plaque(e.nom, "h3"), meta(e, nomGroupe));

  // La capture principale (la plus récente), avec sa passe et le nombre de passes ; l'évolution au clic.
  const captures = liste(e.captures);
  const principale = derniereCapture(e);
  if (principale) {
    const fig = el("figure", "cat-figure cat-principale");
    fig.append(image(ctx, principale.chemin, "Capture : " + e.nom));
    const nPasses = Math.max(new Set(captures.map((c) => c.passe).filter((x) => x !== undefined)).size,
                             new Set(liste(e.passes)).size);
    const badge = [principale.passe !== undefined ? `Passe ${principale.passe}` : null,
                   nPasses > 1 ? `${nPasses} passes` : null].filter(Boolean).join(" · ");
    if (badge) fig.append(el("span", "cat-badge", badge));
    fiche.append(fig);
    if (captures.length > 1) {
      const d = el("details", "cat-evolution");
      d.append(el("summary", "", "Voir l'évolution"));
      d.addEventListener("toggle", () => {
        if (!d.open || d.dataset.fait) return;
        d.dataset.fait = "1";
        const grille = el("div", "cat-evo");
        for (const c of [...captures].sort((a, b) => (a.passe ?? 0) - (b.passe ?? 0))) {
          const fg = el("figure", "");
          fg.append(image(ctx, c.chemin, `Capture, passe ${c.passe ?? "?"} : ${e.nom}`));
          fg.append(el("figcaption", "", c.passe !== undefined ? `Passe ${c.passe}` : "Capture"));
          grille.append(fg);
        }
        d.append(grille);
      });
      fiche.append(d);
    }
  }

  // La comparaison avec la référence, à plusieurs prises de vues.
  const vues = liste(e.comparaisons).filter((c) => c.reel || c.produit);
  if (vues.length) fiche.append(comparaison(ctx, e, vues));

  const corps = el("div", "cat-corps");
  if (e.note) corps.append(el("p", "cat-note", e.note));
  if (e.evenement) corps.append(el("p", "cat-evenement", e.evenement));
  if (e.doute) {
    const d = el("div", "cat-doute");
    d.append(el("b", "", "Doute" + (e.doute.date ? " · " + dateFr(e.doute.date) : "")));
    if (e.doute.raison) d.append(el("p", "", e.doute.raison));
    if (e.doute.leve_par) d.append(el("p", "", "Ce qui le lèverait : " + e.doute.leve_par));
    corps.append(d);
  }

  // La connaissance : les leçons appliquées, et celles, plus récentes, qui le mettent « à réévaluer ».
  const parLecon = new Map(liste(cat.lecons).map((l) => [l.id, l]));
  const appliquees = liste(e.lecons_appliquees), reeval = liste(e.a_reevaluer);
  if (appliquees.length || reeval.length) {
    const k = el("div", "cat-connaissance" + (reeval.length ? " a-reevaluer" : ""));
    const tete = el("p", "");
    tete.append(el("b", "", "Connaissance"), ` ${appliquees.length} leçon${appliquees.length > 1 ? "s" : ""} appliquée${appliquees.length > 1 ? "s" : ""}`
      + (parLecon.size ? ` sur ${parLecon.size}` : ""));
    k.append(tete);
    const puces = (ids) => {
      const p = el("p", "cat-puces");
      for (const id of ids) {
        const l = parLecon.get(id);
        p.append(puce(l?.titre ? `${id} ${l.titre}` : id, l?.texte));
      }
      return p;
    };
    if (appliquees.length) k.append(puces(appliquees));
    if (reeval.length) {
      k.append(el("p", "", "À réévaluer, avec ces leçons plus récentes :"));
      k.append(puces(reeval));
    }
    corps.append(k);
  }

  // Les caractéristiques (une pastille si la valeur est une couleur).
  const caracs = liste(e.caracteristiques);
  if (caracs.length) {
    const dl = el("dl", "cat-caracs");
    for (const c of caracs) {
      const dd = el("dd", "");
      if (estCouleur(c.valeur)) {
        const s = el("span", "cat-echantillon");
        s.style.background = c.valeur;
        dd.append(s);
      }
      dd.append(String(c.valeur));
      dl.append(el("dt", "", c.libelle), dd);
    }
    corps.append(dl);
  }

  // Les éléments communs qu'il utilise.
  if (liste(e.kit).length) {
    const parKit = new Map(liste(cat.kit).map((k) => [k.id, k]));
    const p = el("p", "cat-puces");
    for (const id of e.kit) p.append(puce(parKit.get(id)?.nom || id, parKit.get(id)?.description));
    corps.append(el("h4", "", "Kit"), p);
  }

  // Les liens de référence (seulement ceux que `lienSur` accepte : https, http, claude).
  const liens = liste(e.liens).filter((l) => lienSur(l.url));
  if (liens.length) {
    const p = el("p", "cat-liens");
    liens.forEach((l, i) => { if (i) p.append(" · "); p.append(lienExterne(l.url, l.libelle || "Lien")); });
    corps.append(p);
  }
  fiche.append(corps);

  // Les retours : ceux du catalogue, puis ceux envoyés que le catalogue n'a pas encore repris.
  const retours = liste(e.retours);
  const locaux = retoursLocaux(ctx, f.id, e);
  if (retours.length || locaux.length) {
    const section = el("section", "cat-section");
    section.append(el("h4", "", "Demandes de modification"));
    const ul = el("ul", "cat-demandes");
    for (const r of retours) ul.append(ligneRetour(r, null));
    for (const t of locaux) {
      const li = el("li", "cat-local");
      li.append(el("span", "cat-quand", "envoyée · en attente du catalogue"), el("p", "", t));
      ul.append(li);
    }
    section.append(ul);
    fiche.append(section);
  }
  if (ctx.etat.agir === true) fiche.append(demanderModifier(ctx, f, e));
  contenu.append(fiche);
  if (ui.hautDeFiche) {   // une fiche qu'on vient d'ouvrir commence en haut ; un redessin garde l'endroit
    ui.hautDeFiche = false;
    requestAnimationFrame(() => { const p = contenu.closest(".panneau"); if (p) p.scrollTop = 0; });
  }
}

// La comparaison : un sélecteur d'angle, une barre à glisser entre « Produit » et « Réel », le crédit.
function comparaison(ctx, e, vues) {
  const bloc = el("div", "cat-comparaison");
  const angles = el("div", "cat-angles");
  angles.setAttribute("role", "group");
  angles.setAttribute("aria-label", "Prise de vue");
  const zone = el("div", "");
  let position = 50;
  const montrer = (i) => {
    [...angles.children].forEach((b, j) => b.setAttribute("aria-pressed", String(i === j)));
    const v = vues[i];
    zone.replaceChildren();
    const cadre = el("div", "cat-compare");
    if (v.reel && v.produit) {
      const reel = el("div", "cat-calque");
      reel.append(image(ctx, v.reel, "Référence réelle : " + e.nom));
      const produit = el("div", "cat-calque produit");
      produit.append(image(ctx, v.produit, "Produit : " + e.nom));
      const curseur = document.createElement("input");
      curseur.type = "range";
      curseur.min = "0"; curseur.max = "100"; curseur.value = String(position);
      curseur.setAttribute("aria-label", "Glisser entre Produit et Réel");
      const poser = () => { position = Number(curseur.value); cadre.style.setProperty("--pos", position + "%"); };
      curseur.addEventListener("input", poser);
      poser();
      cadre.append(reel, produit, el("span", "cat-etiquette gauche", "Produit"), el("span", "cat-etiquette droite", "Réel"), curseur);
    } else {
      const seule = el("div", "cat-calque");
      seule.append(image(ctx, v.reel || v.produit, (v.reel ? "Référence réelle : " : "Produit : ") + e.nom));
      cadre.append(seule, el("span", "cat-etiquette gauche", v.reel ? "Réel" : "Produit"));
    }
    zone.append(cadre);
    if (v.credit || (v.lien && lienSur(v.lien))) {
      const credit = el("p", "cat-credit", v.credit || "");
      if (v.lien && lienSur(v.lien)) { if (v.credit) credit.append(" · "); credit.append(lienExterne(v.lien, "source")); }
      zone.append(credit);
    }
  };
  vues.forEach((v, i) => {
    const b = bouton(v.angle || `Vue ${i + 1}`, "cat-filtre");
    b.addEventListener("click", () => montrer(i));
    angles.append(b);
  });
  if (vues.length > 1) bloc.append(angles);
  bloc.append(zone);
  montrer(0);
  return bloc;
}

// « Demander à modifier » : la demande part à la commande d'actions du projet ; le suivi apparaît sur la fiche.
function demanderModifier(ctx, f, e) {
  const bloc = el("section", "cat-demander");
  const ouvrir = bouton("Demander à modifier", "cat-bouton principal");
  const formulaire = el("div", "cat-formulaire");
  formulaire.hidden = true;
  const etiquette = el("label", "cat-discret", "Ce qui ne va pas et ce qu'il faut changer :");
  const zone = document.createElement("textarea");
  zone.maxLength = MAX_TEXTE;
  zone.rows = 5;
  zone.id = "cat-texte-" + Math.random().toString(36).slice(2);
  etiquette.htmlFor = zone.id;
  const compte = el("div", "cat-compte", `0 / ${MAX_TEXTE}`);
  const statut = el("p", "cat-discret", "");
  statut.setAttribute("role", "status");
  const annuler = bouton("Annuler");
  const envoyer = bouton("Envoyer", "cat-bouton principal");
  envoyer.disabled = true;
  const rangee = el("div", "cat-rangee");
  rangee.append(annuler, envoyer);
  formulaire.append(etiquette, zone, compte, statut, rangee);
  ouvrir.addEventListener("click", () => { formulaire.hidden = false; ouvrir.hidden = true; zone.focus(); });
  annuler.addEventListener("click", () => { formulaire.hidden = true; ouvrir.hidden = false; });
  zone.addEventListener("input", () => {
    compte.textContent = `${zone.value.length} / ${MAX_TEXTE}`;
    envoyer.disabled = !zone.value.trim();
  });
  let enCours = false;
  envoyer.addEventListener("click", async () => {
    if (enCours || !zone.value.trim()) return;   // un double clic ne crée qu'une demande
    enCours = true;
    envoyer.disabled = true;
    const texte = zone.value.trim();
    const r = await ctx.barre.demander(demandeRetourElement(f.id, e.id, texte), envoyer);
    enCours = false;
    if (r?.ok) {
      const cle = cleRetour(f.id, e.id);
      ctx.retoursEnvoyes.set(cle, [...(ctx.retoursEnvoyes.get(cle) || []), texte]);
      ctx.rouvrir();
    } else {
      statut.textContent = "La demande n'a pas été envoyée.";
      envoyer.disabled = !zone.value.trim();
    }
  });
  bloc.append(ouvrir, formulaire);
  return bloc;
}
