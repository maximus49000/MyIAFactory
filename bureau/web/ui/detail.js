// Les panneaux de la page qui montrent des tâches : le détail d'une tâche, un élément de la file, la vue liste.
// Chaque fonction remplit `contenu` ; les gestes passent par `ctx.barre.demander` (une demande au projet).

import {el, ligne} from "./dom.js";
import {tronquer, ilYA, auTravail, dateFr,filtrer, filtresEtat, filtreEtatEffectif, filtreDeListe, imagesUrl, imagesVisibles, notesValides, elementsDeFile, resteNonListe} from "./texte.js";
import {lienSur, libelleMontee, libelleModeleNecessaire, libelleLot} from "./actions.js";
import {reessayerImage} from "./reessai.js";
import {rendreTexte} from "./markdown.js";

export const MAX_RETOUR = 3500;
const MAX_TITRE = 90;

function nomColonne(e, id) {
  return (e.colonnes || []).find((c) => c.id === id)?.nom || "—";
}

export function prenomAgent(e, id) {
  return (e.agents || []).find((a) => a.id === id)?.prenom || "personne";
}

// Le prénom de l'agent, sinon sa clé (un agent pas encore venu au bureau, par exemple une fiche cloud qui attend sa
// session) ; « personne » s'il n'y a pas d'agent.
export function nomAgent(e, id) {
  return (e?.agents || []).find((a) => a.id === id)?.prenom || (typeof id === "string" && id ? id : "personne");
}

// Le menu « Déplacer vers… » : une demande `deplacer`, jamais un changement direct.
function menuDeplacer(ctx, tacheId, colonneActuelle) {
  const menu = el("select", "deplacer");
  menu.setAttribute("aria-label", "Déplacer vers…");
  menu.append(new Option("Déplacer vers…", ""));
  for (const c of ctx.etat.colonnes || []) {
    if (c.id !== colonneActuelle) menu.append(new Option(tronquer(c.nom, 30), c.id));
  }
  menu.addEventListener("change", async () => {
    const colonne = menu.value;
    menu.value = "";
    if (!colonne) return;
    menu.disabled = true;
    try { await ctx.barre.demander({type: "deplacer", tache: tacheId, colonne}); } finally { menu.disabled = false; }
  });
  return menu;
}

// « Relancer » une tâche bloquée : un retour sans consigne nouvelle. Le moteur reprend la tâche (même agent, même
// élément) ; pour une validation bloquée, il refait l'étape d'avant puis repose la validation.
export const TEXTE_RELANCE = "Relance demandée par le Directeur (même consigne).";
const relancees = new Set();     // demandées depuis cette page : le bouton reste « Relance demandée » jusqu'au déblocage
export function boutonRelancer(ctx, t) {
  if (!t.bloquee) relancees.delete(t.id);
  const b = el("button", "bouton secondaire", relancees.has(t.id) ? "Relance demandée" : "Relancer");
  b.type = "button";
  b.disabled = relancees.has(t.id) || !ctx.etat?.agir;
  b.addEventListener("click", async () => {
    b.disabled = true;
    const r = await ctx.barre.demander({type: "retour", tache: t.id, texte: TEXTE_RELANCE});
    if (r?.ok) { relancees.add(t.id); b.textContent = "Relance demandée"; } else b.disabled = false;
  });
  return b;
}

// La zone « Faire un retour » ; le brouillon survit aux rafraîchissements du panneau.
// `textes` : {titre, invite} pour un autre usage (la question au Chef).
export function blocRetour(ctx, tacheId, textes = {}) {
  const bloc = el("section", "retour-saisie");
  bloc.append(el("h3", "", textes.titre || "Faire un retour"));
  const zone = document.createElement("textarea");
  zone.rows = 4;
  zone.maxLength = MAX_RETOUR;
  zone.placeholder = textes.invite || "Écrire un retour pour l'orchestrateur…";
  zone.value = ctx.brouillons.get(tacheId) || "";
  const compteur = el("span", "retour-compteur", "");
  const envoyer = el("button", "bouton", "Envoyer");
  envoyer.type = "button";
  function maj() {
    compteur.textContent = `${zone.value.length} / ${MAX_RETOUR}`;
    envoyer.disabled = !zone.value.trim();
  }
  zone.addEventListener("input", () => {
    if (zone.value) ctx.brouillons.set(tacheId, zone.value); else ctx.brouillons.delete(tacheId);
    maj();
  });
  envoyer.addEventListener("click", async () => {
    const texte = zone.value;
    envoyer.disabled = true;
    const r = await ctx.barre.demander({type: "retour", tache: tacheId, texte});
    if (r.ok) {
      if (ctx.brouillons.get(tacheId) === texte) ctx.brouillons.delete(tacheId);
      if (zone.value === texte) zone.value = "";
    }
    maj();
  });
  maj();
  const pied = el("div", "retour-pied");
  pied.append(compteur, envoyer);
  bloc.append(zone, pied);
  return bloc;
}

function blocImages(t) {
  const vignettes = el("div", "vignettes");
  for (const i of imagesUrl(t)) {
    const fig = el("figure", "vignette");
    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = i.url;
    img.alt = i.legende || "Image de la tâche";
    reessayerImage(img);
    fig.addEventListener("click", () => fig.classList.toggle("agrandie"));
    fig.append(img);
    if (i.legende) fig.append(el("figcaption", "", i.legende));
    vignettes.append(fig);
  }
  return vignettes;
}

export function contenuTache(ctx, contenu, t) {
  const e = ctx.etat;
  if (ctx.retourListe) {
    const retour = el("button", "lien-retour", "← Toutes les tâches");
    retour.type = "button";
    retour.addEventListener("click", ctx.ouvrirListe);
    contenu.append(retour);
  }
  contenu.append(el("h2", "", t.titre));
  contenu.append(ligne("Colonne", tronquer(nomColonne(e, t.colonne), 30)));
  contenu.append(ligne("Agent", prenomAgent(e, t.agent)));
  contenu.append(ligne("Étape", t.etape ? tronquer(t.etape, MAX_TITRE) : "—"));
  const necessaire = libelleModeleNecessaire(t);   // la montée y est comprise ; sans lui, la montée seule
  const montee = libelleMontee(t);
  if (necessaire) contenu.append(ligne("Modèle nécessaire", necessaire));
  else if (montee) contenu.append(ligne("Modèle", montee));
  const lot = libelleLot(t, e.taches);
  if (lot) contenu.append(ligne("Lot", lot));
  for (const n of notesValides(t)) {
    const p = el("p", "note-tache");
    p.append(el("strong", "", n.libelle + " : "), document.createTextNode(n.texte));
    contenu.append(p);
  }
  const type = (e.types || []).find((x) => x.id === t.type);
  if (t.type) contenu.append(ligne("Type", type ? type.nom : t.type));
  contenu.append(ligne("Mise à jour", ilYA(t.maj)));
  const travail = auTravail(t.travail);      // l'agent local au travail (dit par le bureau, relu à chaque état)
  if (travail) contenu.append(ligne("Au travail", "depuis " + travail.depuis + (travail.action ? " · " + travail.action : "")));
  if (t.attente) contenu.append(el("p", "carte-attente", t.attente));     // retenue par la charge du poste (dit par le moteur)
  if (t.bloquee) {
    const b = el("p", "bloquee");
    b.append(el("strong", "", "Bloquée : "), document.createTextNode(t.bloquee));
    contenu.append(b);
    if (e.agir) contenu.append(boutonRelancer(ctx, t));
  }

  contenu.append(el("div", "carte-sous-titre", "Journal"));
  const journal = el("ul", "journal");
  if (!t.journal.length) journal.append(el("li", "vide", "Aucune entrée"));
  for (const j of t.journal) {
    const li = el("li", "");
    li.append(el("span", "date", dateFr(j.t)), rendreTexte("texte-journal", j.texte));      // Markdown sûr
    journal.append(li);
  }
  contenu.append(journal);

  if (imagesVisibles(e, t)) contenu.append(el("div", "carte-sous-titre", "Images"), blocImages(t));

  const liens = t.liens.filter((l) => lienSur(l.url));
  if (liens.length) {
    contenu.append(el("div", "carte-sous-titre", "Liens"));
    const ul = el("ul", "liens");
    for (const l of liens) {
      const a = el("a", "", l.libelle);
      a.href = l.url;
      a.target = "_blank";
      a.rel = "noopener";
      const li = el("li", "");
      li.append(a);
      ul.append(li);
    }
    contenu.append(ul);
  }

  contenu.append(el("div", "carte-sous-titre", "Retours"));
  const retours = el("ul", "retours");
  if (!t.retours.length) retours.append(el("li", "vide", "Aucun retour"));
  for (const r of t.retours) {
    const li = el("li", "");
    li.append(el("div", "retour-texte", r.texte), el("div", "retour-date", dateFr(r.t) + (r.etat ? " · " + r.etat : "")));
    li.append(r.reponse && r.reponse.trim() ? el("div", "retour-reponse", r.reponse)
      : el("div", "retour-attente", "en attente de réponse"));
    retours.append(li);
  }
  contenu.append(retours);

  if (e.agir) {
    contenu.append(blocRetour(ctx, t.id));
    contenu.append(menuDeplacer(ctx, t.id, t.colonne));
  }
}

// Un élément de la file : pas encore une tâche, donc seulement son titre et le déplacement.
export function contenuFile(ctx, contenu, q) {
  contenu.append(el("h2", "", q.titre || q.id));
  contenu.append(ligne("File d'attente", "pas encore commencée"));
  if (ctx.etat.agir) contenu.append(menuDeplacer(ctx, q.id, null));
}

// Le panneau « File » : tous les éléments de la file (visibles puis suite), chacun déplaçable comme les visibles.
export function contenuAttente(ctx, contenu) {
  const file = ctx.etat.file;
  const elements = elementsDeFile(file);
  contenu.append(el("h2", "", "File"));
  contenu.append(ligne("Éléments en attente", String(elements.length + resteNonListe(file))));
  const liste = el("ul", "liste-file");
  if (!elements.length) liste.append(el("li", "vide", "La file est vide"));
  for (const q of elements) {
    const li = el("li", "element-file");
    li.append(el("span", "ligne-titre", tronquer(q.titre, MAX_TITRE)));
    if (ctx.etat.agir) li.append(menuDeplacer(ctx, q.id, null));
    liste.append(li);
  }
  contenu.append(liste);
  const manque = resteNonListe(file);
  if (manque > 0) contenu.append(el("p", "note", `… et ${manque} autre${manque > 1 ? "s" : ""} que le projet ne détaille pas.`));
}

// La vue liste : filtres, puis une ligne par tâche. Le filtre estompe aussi le Kanban.
export function contenuListe(ctx, contenu) {
  const e = ctx.etat;
  const f = ctx.filtreListe;
  contenu.append(el("h2", "", "Toutes les tâches"));
  const nFile = elementsDeFile(e.file).length + resteNonListe(e.file);
  if (nFile > 0) {
    const ouvrir = el("button", "bouton secondaire", `File d'attente (${nFile})`);
    ouvrir.type = "button";
    ouvrir.addEventListener("click", ctx.ouvrirAttente);
    contenu.append(ouvrir);
  }
  const filtres = el("div", "filtres");
  function bouton(texte, actif, action) {
    const b = el("button", "filtre" + (actif ? " actif" : ""), texte);
    b.type = "button";
    b.setAttribute("aria-pressed", String(actif));
    b.addEventListener("click", action);
    return b;
  }
  const rangeeEtat = el("div", "filtres-rangee");
  const etatEffectif = filtreEtatEffectif(e, f.etat);
  for (const x of filtresEtat(e)) {
    rangeeEtat.append(bouton(x.libelle, x.id === etatEffectif, () => ctx.changerFiltre({etat: x.id})));
  }
  filtres.append(rangeeEtat);
  if ((e.types || []).length) {
    const types = el("div", "filtres-rangee");
    types.append(bouton("Tous les types", !f.type, () => ctx.changerFiltre({type: null})));
    for (const t of e.types) types.append(bouton(t.nom, f.type === t.id, () => ctx.changerFiltre({type: t.id})));
    filtres.append(types);
  }
  contenu.append(filtres);

  const ids = filtrer(e.taches, filtreDeListe(e, f), e.colonnes);
  const liste = el("ul", "liste-taches");
  const montrees = (e.taches || []).filter((t) => ids.has(t.id));
  if (!montrees.length) liste.append(el("li", "vide", "Aucune tâche ne correspond"));
  for (const t of montrees) {
    const li = el("li", "");
    const b = el("button", "ligne-tache");
    b.type = "button";
    b.append(el("span", "ligne-titre", tronquer(t.titre, MAX_TITRE)),
             el("span", "ligne-detail", `${tronquer(nomColonne(e, t.colonne), 20)} · ${prenomAgent(e, t.agent)} · ${ilYA(t.maj)}`));
    b.addEventListener("click", () => ctx.ouvrirTacheDepuisListe(t.id));
    li.append(b);
    liste.append(li);
  }
  contenu.append(liste);
}
