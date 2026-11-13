// Où s'exécutent les étapes : le lieu de chaque étape d'agent (local, cloud, indifférent), la proposition de découpage
// d'un workflow selon le poste, et la carte de décision qui la montre avant/après. Chaque action envoie une demande au
// projet, jamais un changement direct. Un projet dont le relevé ne publie pas `etapes_lieux` ne montre rien.

import {el} from "./dom.js";

export const LIEUX = [{valeur: "local", libelle: "Local"}, {valeur: "cloud", libelle: "Cloud"},
  {valeur: "indifférent", libelle: "Indifférent"}];
export const AIDE_LIEUX = "Local : seul un agent local la prend (elle attend sinon). Cloud : seul un agent cloud. " +
  "Indifférent : le premier agent libre.";
export const PHRASE_PROPOSER = "Lance un appel Sonnet (une dépense) : il propose de séparer, dans chaque étape, ce qui " +
  "exige le poste ; rien ne change avant votre validation.";

const plein = (t) => typeof t === "string" && t.trim() !== "";

// `lieu` : « local », « cloud », « indifférent », ou null (le métier décide).
export function demandeLieuEtape(etape, lieu) {
  return {type: "lieu_etape", etape, lieu: lieu === "" || lieu === undefined ? null : lieu};
}

export function demandeProposerDecoupage() {
  return {type: "proposer_decoupage"};
}

export function demandeDecoupage(decision, verdict) {
  return {type: "decoupage_lieux", decision: decision.id, verdict};
}

// Les étapes du relevé qui ont un sélecteur (pas les validations du Directeur).
export function etapesAvecLieu(etat) {
  return (Array.isArray(etat?.etapes_lieux) ? etat.etapes_lieux : []).filter((x) => x && plein(x.id));
}

export function decoupageEnAttente(etat) {
  return (Array.isArray(etat?.decisions_projet) ? etat.decisions_projet : []).filter((d) => d?.genre === "decoupage_lieux");
}

// « poste local » / « cloud » / « cloud possible » : ce que dit le badge d'une étape de la carte.
export function libelleLieu(lieu) {
  if (lieu === "local") return "poste local";
  if (lieu === "cloud") return "cloud";
  return "cloud possible";
}

function selecteur(ctx, e) {
  const menu = el("select", "lieu-choix");
  menu.setAttribute("aria-label", `Lieu de l'étape ${e.nom || e.id}`);
  if (e.exige_poste === true) {      // exige les logiciels du poste : figé sur Local
    menu.append(new Option("Local", "local"));
    menu.value = "local";
    menu.disabled = true;
    return menu;
  }
  if (e.lieu === null || e.lieu === undefined) menu.append(new Option("Selon le métier", ""));
  for (const l of LIEUX) menu.append(new Option(l.libelle, l.valeur));
  menu.value = e.lieu ?? "";
  menu.disabled = ctx.etat.agir !== true;
  let courant = menu.value;
  menu.addEventListener("change", async () => {
    const voulu = menu.value;
    menu.disabled = true;
    const r = await ctx.barre.demander(demandeLieuEtape(e.id, voulu));
    menu.disabled = false;
    if (r?.ok) courant = voulu;
    else menu.value = courant;      // refusé : le choix d'avant reste affiché
  });
  return menu;
}

// La section de l'espace de direction ; `null` quand le relevé ne publie pas le lieu des étapes.
export function sectionLieux(ctx, boutonDemande) {
  const etapes = etapesAvecLieu(ctx.etat);
  if (!Array.isArray(ctx.etat?.etapes_lieux)) return null;
  const s = el("section", "partie partie-lieux");
  s.append(el("h3", "", "Où s'exécutent les étapes"), el("p", "lecon-meta", AIDE_LIEUX));
  const ul = el("ul", "liste-partie");
  if (!etapes.length) ul.append(el("li", "vide", "Aucune étape d'agent pour l'instant"));
  for (const e of etapes) {
    const li = el("li", "etape-lieu");
    li.append(el("span", "etape-nom", e.nom || e.id));
    if (e.validation === true) {
      li.append(el("span", "lecon-meta", " · validation du Directeur"));
    } else {
      li.append(selecteur(ctx, e));
      if (e.exige_poste === true) li.append(el("span", "lecon-meta", " exige les logiciels du poste"));
    }
    ul.append(li);
  }
  s.append(ul);
  if (ctx.etat.agir === true && etapes.some((e) => e.validation !== true)) {
    const attend = decoupageEnAttente(ctx.etat).length > 0;
    const b = boutonDemande(ctx, "Proposer le découpage", "bouton secondaire", () => demandeProposerDecoupage());
    if (attend) b.disabled = true;
    s.append(b, el("p", "lecon-meta", attend ? "Une proposition attend déjà votre décision." : PHRASE_PROPOSER));
  }
  return s;
}

function listeAvantApres(titre, etapes, nouvelles) {
  const bloc = el("div", "decoupage-colonne");
  bloc.append(el("strong", "", titre));
  const ul = el("ul", "liste-partie");
  for (const e of Array.isArray(etapes) ? etapes : []) {
    const li = el("li", "");
    li.append(el("span", "etape-nom", e.nom || e.id));
    if (e.validation !== true) li.append(el("span", "badge-lieu", " · " + libelleLieu(e.lieu)));
    if (nouvelles?.has(e.id)) li.append(el("span", "lecon-meta", " · nouvelle partie locale"));
    ul.append(li);
  }
  bloc.append(ul);
  return bloc;
}

// La carte « Découper les étapes selon le poste » : l'avant et l'après, Valider ou Refuser.
export function carteDecoupage(ctx, d, boutonDemande) {
  const li = el("li", "decision-decoupage");
  li.append(el("div", "decision-texte", d.texte || "Découper les étapes selon le poste"));
  if (plein(d.message)) li.append(el("div", "lecon-meta", d.message));
  const avant = new Set((Array.isArray(d.avant) ? d.avant : []).map((x) => x.id));
  const nouvelles = new Set((Array.isArray(d.apres) ? d.apres : []).filter((x) => !avant.has(x.id)).map((x) => x.id));
  const cols = el("div", "decoupage");
  cols.append(listeAvantApres("Avant", d.avant, null), listeAvantApres("Après", d.apres, nouvelles));
  li.append(cols);
  if (ctx.etat.agir) {
    const rangee = el("div", "lecon-boutons");
    rangee.append(boutonDemande(ctx, "Valider", "bouton", () => demandeDecoupage(d, "valider")),
      boutonDemande(ctx, "Refuser", "bouton secondaire", () => demandeDecoupage(d, "refuser")));
    li.append(rangee);
  }
  return li;
}
