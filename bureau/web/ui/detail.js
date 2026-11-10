// Les panneaux de la page qui montrent des tâches : le détail d'une tâche, un élément de la file, la vue liste.
// Chaque fonction remplit `contenu` ; les gestes passent par `ctx.barre.demander` (une demande au projet).

import {el, ligne} from "./dom.js";
import {tronquer, ilYA, dateFr, filtrer, imagesUrl} from "./texte.js";
import {lienSur} from "./actions.js";

export const MAX_RETOUR = 3500;
const MAX_TITRE = 90;

function nomColonne(e, id) {
  return (e.colonnes || []).find((c) => c.id === id)?.nom || "—";
}

export function prenomAgent(e, id) {
  return (e.agents || []).find((a) => a.id === id)?.prenom || "personne";
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

// La zone « Faire un retour » ; le brouillon survit aux rafraîchissements du panneau.
function blocRetour(ctx, tacheId) {
  const bloc = el("section", "retour-saisie");
  bloc.append(el("h3", "", "Faire un retour"));
  const zone = document.createElement("textarea");
  zone.rows = 4;
  zone.maxLength = MAX_RETOUR;
  zone.placeholder = "Écrire un retour pour l'orchestrateur…";
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
  const type = (e.types || []).find((x) => x.id === t.type);
  if (t.type) contenu.append(ligne("Type", type ? type.nom : t.type));
  contenu.append(ligne("Mise à jour", ilYA(t.maj)));
  if (t.bloquee) {
    const b = el("p", "bloquee");
    b.append(el("strong", "", "Bloquée : "), document.createTextNode(t.bloquee));
    contenu.append(b);
  }

  contenu.append(el("div", "carte-sous-titre", "Journal"));
  const journal = el("ul", "journal");
  if (!t.journal.length) journal.append(el("li", "vide", "Aucune entrée"));
  for (const j of t.journal) {
    const li = el("li", "");
    li.append(el("span", "date", dateFr(j.t)), el("span", "texte-journal", j.texte));
    journal.append(li);
  }
  contenu.append(journal);

  if (t.images.length) contenu.append(el("div", "carte-sous-titre", "Images"), blocImages(t));

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
    li.append(el("div", "retour-texte", r.texte), el("div", "retour-date", dateFr(r.t)));
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

// La vue liste : filtres, puis une ligne par tâche. Le filtre estompe aussi le Kanban.
export function contenuListe(ctx, contenu) {
  const e = ctx.etat;
  const f = ctx.filtreListe;
  contenu.append(el("h2", "", "Toutes les tâches"));
  const filtres = el("div", "filtres");
  function bouton(texte, actif, action) {
    const b = el("button", "filtre" + (actif ? " actif" : ""), texte);
    b.type = "button";
    b.setAttribute("aria-pressed", String(actif));
    b.addEventListener("click", action);
    return b;
  }
  const rangeeEtat = el("div", "filtres-rangee");
  rangeeEtat.append(bouton("Toutes", !f.enCours, () => ctx.changerFiltre({enCours: false})),
                    bouton("En cours", f.enCours, () => ctx.changerFiltre({enCours: true})));
  filtres.append(rangeeEtat);
  if ((e.types || []).length) {
    const types = el("div", "filtres-rangee");
    types.append(bouton("Tous les types", !f.type, () => ctx.changerFiltre({type: null})));
    for (const t of e.types) types.append(bouton(t.nom, f.type === t.id, () => ctx.changerFiltre({type: t.id})));
    filtres.append(types);
  }
  contenu.append(filtres);

  const ids = filtrer(e.taches, f);
  const liste = el("ul", "liste-taches");
  const montrees = (e.taches || []).filter((t) => ids.has(t.id));
  if (!montrees.length) liste.append(el("li", "vide", "Aucune tâche ne correspond"));
  for (const t of montrees) {
    const li = el("li", "");
    const b = el("button", "ligne-tache");
    b.type = "button";
    b.append(el("span", "ligne-titre", tronquer(t.titre, MAX_TITRE)),
             el("span", "ligne-detail", `${tronquer(nomColonne(e, t.colonne), 20)} · ${prenomAgent(e, t.agent)} · ${ilYA(t.maj)}`));
    b.addEventListener("click", () => ctx.ouvrirTache(t.id));
    li.append(b);
    liste.append(li);
  }
  contenu.append(liste);
}
