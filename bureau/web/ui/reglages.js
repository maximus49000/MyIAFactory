// La page « Réglages » : chaque réglage se règle à trois niveaux (global, type de projet, projet) ; le plus précis l'emporte.
// L'état vient de `etat.reglages_page` ; une écriture passe par le serveur du bureau, qui valide et renvoie la ligne à jour.
// Tout texte venu du serveur passe par textContent (l'aide `el`).

import {el} from "./dom.js";
import {urlProjet, projetCourant} from "./projets.js";
import {sectionLieux} from "./lieux.js";
import {boutonDemande} from "./decisions.js";
import {blocApercu, blocConso} from "./deport.js";
import {sectionPartage} from "./partage.js";

// Le niveau édité est un état de vue (pas de donnée) : il survit aux redessins de `rouvrir()`.
let niveauEdite = "projet";
export const definirNiveauEdite = (n) => { niveauEdite = ["global", "type", "projet"].includes(n) ? n : "projet"; };
export const niveauEditeActuel = () => niveauEdite;

const LIEUX = {poste: "Poste", github: "GitHub", serveur: "Serveur"};
const SECTIONS = [["actions", "Où tournent les actions"], ["automatisations", "Automatisations"]];

// POST d'une valeur à un niveau (`valeur: null` : retour à l'hérité). {ok, message, ligne?}, sans jamais lever.
export async function enregistrerNiveau(niveau, id, valeur, fetchFn = fetch) {
  try {
    const r = await fetchFn(urlProjet("/api/reglages/niveau"), {
      method: "POST",
      headers: {"X-Bureau": "1", "Content-Type": "application/json"},
      body: JSON.stringify({niveau, id, valeur}),
    });
    if (r.ok) {
      let ligne;
      try { ligne = await r.json(); } catch { /* corps illisible : l'état se relira à la réouverture */ }
      return {ok: true, message: "Réglage enregistré.", ligne};
    }
    let erreur = "";
    try { erreur = (await r.json())?.erreur || ""; } catch { /* corps illisible */ }
    return {ok: false, message: `Refusé : ${erreur || "le serveur a répondu " + r.status}`};
  } catch {
    return {ok: false, message: "Serveur du bureau injoignable."};
  }
}

const aNiveau = (l, niveau) => l.valeurs && Object.prototype.hasOwnProperty.call(l.valeurs, niveau);

// La valeur montrée au niveau édité : la sienne, sinon celle dont il hérite (estompée).
function valeurAffichee(l, niveau) {
  if (niveau === "projet") return {valeur: l.valeur, propre: aNiveau(l, "projet")};
  if (aNiveau(l, niveau)) return {valeur: l.valeurs[niveau], propre: true};
  if (niveau === "type" && aNiveau(l, "global")) return {valeur: l.valeurs.global, propre: false};
  const defaut = l.origine === "defaut" ? l.valeur : (l.forme === "lieu" && (l.choix || []).includes("poste") ? "poste" : null);
  return {valeur: defaut, propre: false};
}

function pastille(l, niveau) {
  let texte;
  if (niveau === "projet") {
    const o = String(l.origine || "defaut");
    texte = o === "projet" ? "propre au projet" : o === "global" ? "hérité du global"
      : o.startsWith("type:") ? `hérité du type ${o.slice(5)}` : "défaut";
  } else {
    texte = aNiveau(l, niveau) ? "défini ici" : "pas défini ici";
  }
  return el("span", "pastille-origine", texte);
}

function ligneReglage(ctx, l, niveau, message, groupe, fetchFn) {
  const permis = Array.isArray(l.niveaux) && l.niveaux.includes(niveau);
  const inapplicable = l.applicable === false;
  const verrou = !permis || (inapplicable && niveau === "projet");
  const {valeur, propre} = valeurAffichee(l, niveau);
  const rang = el("div", "ligne-reglage" + (propre ? "" : " herite") + (inapplicable ? " inapplicable" : "") + (permis ? "" : " verrouille"));
  rang.append(el("span", "deport-nom", l.libelle || l.id));
  if (l.aide) rang.append(el("span", "note", " " + l.aide));
  const controles = [];

  // un refus ou une panne : les contrôles redisent l'état réel de la ligne
  const redire = () => {
    const v = valeurAffichee(l, niveau).valeur;
    controles.forEach((c) => { if (c.type === "checkbox") c.checked = v === true; else c.checked = c.value === v; });
  };
  const ecrire = async (voulu) => {
    message.textContent = "";
    groupe.forEach((x) => { x.disabled = true; });
    const rep = await enregistrerNiveau(niveau, l.id, voulu, fetchFn);
    groupe.forEach((x) => { x.disabled = x.grise; });
    if (rep.ok) {
      if (rep.ligne && typeof rep.ligne === "object" && rep.ligne.id === l.id) Object.assign(l, rep.ligne);
      else if (voulu === null) { if (l.valeurs) delete l.valeurs[niveau]; }
      else (l.valeurs ||= {})[niveau] = voulu;
      ctx.rouvrir?.();
    } else redire();
    message.textContent = rep.message;
  };

  if (l.forme === "booleen") {
    const label = el("label", "lecons-auto-label");
    const c = document.createElement("input");
    c.type = "checkbox";
    c.checked = valeur === true;
    c.disabled = verrou;
    c.grise = verrou;
    c.addEventListener("change", () => ecrire(c.checked));
    controles.push(c);
    groupe.push(c);
    label.append(c);
    rang.append(label);
  } else {
    for (const lieu of Array.isArray(l.choix) ? l.choix : []) {
      const label = el("label", "lecons-auto-label deport-choix");
      const r = document.createElement("input");
      r.type = "radio";
      r.name = "reglage-" + l.id;
      r.value = lieu;
      r.checked = valeur === lieu;
      r.disabled = verrou;
      r.grise = verrou;
      r.addEventListener("change", () => ecrire(lieu));
      controles.push(r);
      groupe.push(r);
      label.append(r, el("span", "", " " + (LIEUX[lieu] || lieu)));
      rang.append(label);
    }
  }

  rang.append(pastille(l, niveau));
  if (permis && aNiveau(l, niveau)) {
    const b = el("button", "secondaire", "hérité");
    b.type = "button";
    b.addEventListener("click", () => ecrire(null));
    rang.append(b);
  }
  if (!permis) {
    rang.append(el("span", "note", niveau === "projet" ? "Projet seulement : accord permanent" : "Projet seulement : jamais hérité"));
  } else if (Array.isArray(l.niveaux) && l.niveaux.length === 1 && l.niveaux[0] === "projet") {
    rang.append(el("span", "note", "Projet seulement : accord permanent"));
  }
  if (inapplicable) rang.append(el("span", "note", " non applicable à ce projet"));
  return rang;
}

function barreNiveaux(ctx, page) {
  const barre = el("div", "reglages-niveaux");
  barre.setAttribute("role", "group");
  barre.setAttribute("aria-label", "Niveau de réglage");
  const defs = [
    ["global", "Global", false],
    ["type", `Type : ${page.genre || "aucun"}`, !page.type_disponible],
    ["projet", `Projet : ${projetCourant() || "ce projet"}`, false],
  ];
  for (const [niveau, libelle, grise] of defs) {
    const b = el("button", "onglet-niveau" + (niveau === niveauEdite ? " actif" : ""), libelle);
    b.type = "button";
    b.disabled = grise;
    b.setAttribute("aria-pressed", niveau === niveauEdite ? "true" : "false");
    b.addEventListener("click", () => { definirNiveauEdite(niveau); ctx.rouvrir?.(); });
    barre.append(b);
  }
  return barre;
}

// Le contenu de la page ; `contenu` est le conteneur à remplir (renvoyé). `fetchFn` seulement pour les tests.
export function contenuReglages(ctx, contenu, fetchFn = fetch) {
  const page = ctx.etat?.reglages_page;
  if (!page || ctx.etat.reglages_page_erreur) {
    contenu.append(el("p", "note", ctx.etat?.reglages_page_erreur || "Page Réglages indisponible."));
    return contenu;
  }
  // un type sans genre ne s'édite pas : on retombe sur le projet
  if (niveauEdite === "type" && !page.type_disponible) niveauEdite = "projet";
  const lignes = Array.isArray(page.lignes) ? page.lignes : [];
  const message = el("p", "note", "");
  message.setAttribute("aria-live", "polite");
  const groupe = [];
  contenu.append(barreNiveaux(ctx, page));

  for (const [section, titre] of SECTIONS) {
    const de = lignes.filter((l) => l.section === section);
    if (!de.length) continue;
    const bloc = el("section", "partie reglages-section");
    bloc.append(el("h4", "", titre));
    for (const l of de) bloc.append(ligneReglage(ctx, l, niveauEdite, message, groupe, fetchFn));
    if (section === "actions" && de.some((l) => (l.valeur === "github" && niveauEdite === "projet") || l.valeurs?.[niveauEdite] === "github")) {
      bloc.append(blocApercu(fetchFn));
      if (ctx.etat.deport?.conso) bloc.append(blocConso(ctx.etat.deport.conso));
    }
    contenu.append(bloc);
  }

  const lieux = sectionLieux(ctx, boutonDemande);
  if (lieux) {
    const bloc = el("section", "partie reglages-section");
    bloc.append(el("h4", "", "Agents : local ou cloud"), lieux);
    contenu.append(bloc);
  }
  if (niveauEdite === "global" && ctx.etat.agir === true) {
    const bloc = el("section", "partie reglages-section");
    bloc.append(el("h4", "", "Partage des connaissances"), sectionPartage(null, fetchFn));
    contenu.append(bloc);
  }
  contenu.append(message);
  return contenu;
}
