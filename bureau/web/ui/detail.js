// Les panneaux de la page qui montrent des tâches : le détail d'une tâche, un élément de la file, la vue liste.
// Chaque fonction remplit `contenu` ; les gestes passent par `ctx.barre.demander` (une demande au projet).

import {el, ligne} from "./dom.js";
import {tronquer, ilYA, auTravail, avancementEnClair, suiviDuRetour, dateFr, pourquoiElleAttend, filtrer, filtresEtat, filtreEtatEffectif, filtreDeListe, imagesUrl, imagesVisibles, notesValides, elementsDeFile, resteNonListe} from "./texte.js";
import {lienSur, libelleMontee, libelleModeleNecessaire, libelleLot} from "./actions.js";
import {reessayerImage} from "./reessai.js";
import {rendreTexte} from "./markdown.js";
import {coutsDesTaches, libelleCout} from "./couts.js";
import {livraisonGroupee, titreAffiche} from "./repetitions.js";
import {libelleEtapeTache} from "./parcours-correction.js";
import {questionsEnAttente} from "./fonctionnalite.js";

export const MAX_RETOUR = 3500;
const MAX_TITRE = 90;

function nomColonne(e, id) {
  return (e.colonnes || []).find((c) => c.id === id)?.nom || "—";
}

export function prenomAgent(e, id) {
  // Un agent retiré de l'équipe garde son prénom : ses tâches réalisées le nomment toujours.
  return (e.agents || []).find((a) => a.id === id)?.prenom || (e.anciens_agents || []).find((a) => a.id === id)?.prenom || "personne";
}

// Le prénom de l'agent, sinon sa clé (un agent pas encore venu au bureau, par exemple une fiche cloud qui attend sa
// session) ; « personne » s'il n'y a pas d'agent.
export function nomAgent(e, id) {
  return (e?.agents || []).find((a) => a.id === id)?.prenom || (e?.anciens_agents || []).find((a) => a.id === id)?.prenom
    || (typeof id === "string" && id ? id : "personne");
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

// L'encadré « Pourquoi elle attend » : la raison, ce qui la retient, ce qu'il lui faudra ensuite, quand elle partira.
function blocPourquoi(p) {
  const bloc = el("section", "pourquoi-attente");
  bloc.setAttribute("aria-label", p.titre);
  bloc.append(el("div", "carte-sous-titre", p.titre));
  const raison = el("p", "pourquoi-raison");
  raison.append(el("strong", "", p.famille + " : "), document.createTextNode(p.raison));
  bloc.append(raison);
  const liste = (titre, lignes) => {
    if (!lignes.length) return;
    bloc.append(el("p", "pourquoi-titre", titre));
    const ul = el("ul", "pourquoi-lignes");
    for (const l of lignes) ul.append(el("li", "", l));
    bloc.append(ul);
  };
  liste("Ce qui la retient", p.retient);
  liste("Ce qu'il lui faudra ensuite", p.ensuite);
  if (p.quand) bloc.append(el("p", "pourquoi-quand", p.quand));
  return bloc;
}

// Les questions à choix qui attendent l'utilisateur dans la discussion de la fonctionnalité de cette tâche, ou null.
export function questionsAAttendre(e, t) {
  if (!t?.fonctionnalite || t.colonne === "fait") return null;
  return questionsEnAttente((e?.fonctionnalites || []).find((f) => f.id === t.fonctionnalite));
}

// La ligne « Story » : le nom de la fonctionnalité de la tâche, un lien qui ouvre sa carte. Null sans fonctionnalité
// connue ; texte simple si la page ne sait pas ouvrir une fonctionnalité.
const PHASES = {lecture: "il lit le code", modification: "il modifie des fichiers", compilation: "il compile",
                tests: "il lance des tests", autre: "il travaille"};

const HISTORIQUE_VISIBLE = 20;

// L'historique des appels de l'agent (du plus récent au plus ancien) : 20 visibles, « Voir tout » pour le reste. Null s'il est vide.
export function blocHistorique(historique) {
  const liste = Array.isArray(historique) ? historique : [];
  if (!liste.length) return null;
  const bloc = el("div", "historique-appels");
  const ul = el("ul", "historique-liste");
  const montrer = (tout) => ul.replaceChildren(...(tout ? liste : liste.slice(0, HISTORIQUE_VISIBLE)).map((h) => {
    const li = el("li", "historique-appel", h.texte);
    if (h.t) li.setAttribute("title", h.t);
    return li;
  }));
  montrer(false);
  bloc.append(ligne("Historique des appels", ""), ul);
  if (liste.length > HISTORIQUE_VISIBLE) {
    const b = el("button", "lien-retour", `Voir tout (${liste.length})`);
    b.type = "button";
    b.addEventListener("click", () => { montrer(true); b.hidden = true; });
    bloc.append(b);
  }
  return bloc;
}

// Où en est la tâche (liste de l'agent, sinon sa phase), le temps passé et restant, et si ça avance (voir avancementEnClair).
function blocAvancement(av, travail) {
  const bloc = el("div", "avancement");
  const etat = el("p", "avancement-etat avancement-" + av.ton);
  etat.append(el("strong", "", "État : "), document.createTextNode(av.etatTexte));
  bloc.append(etat);
  if (!travail && av.sansListe) return bloc;      // l'agent a fini (ou le moteur est arrêté) : pas de « il n'a rien fait »
  if (av.dansLeLot) {      // finie ou à venir dans le lot : sa liste seule, le temps est sur la tâche que fait la session
    if (!av.sansListe) {
      const liste = el("ul", "avancement-points");
      for (const p of av.points) liste.append(el("li", p.fait ? "fait" : "", (p.fait ? "✔ " : "○ ") + p.texte));
      bloc.append(ligne("Où il en est", ""), liste);
    }
    return bloc;
  }
  if (av.sansListe) {
    const phase = av.phase ? PHASES[av.phase] || PHASES.autre : null;
    bloc.append(ligne("Où il en est", (phase || "pas encore d'action") + " · liste de l'agent absente"));
  } else {
    const liste = el("ul", "avancement-points");
    for (const p of av.points) liste.append(el("li", p.fait ? "fait" : "", (p.fait ? "✔ " : "○ ") + p.texte));
    bloc.append(ligne("Où il en est", ""), liste);
    if (av.enCours) bloc.append(ligne("En cours", av.enCours));
  }
  const temps = [];
  if (av.passe) temps.push("passé " + av.passe);
  if (av.cumul && av.cumul !== av.passe) temps.push("depuis le début de la tâche " + av.cumul);
  temps.push("reste " + av.reste);
  bloc.append(ligne("Temps", temps.join(" · ")));
  if (travail?.action) bloc.append(ligne("Au travail", travail.action));
  const historique = blocHistorique(av.historique);
  if (historique) bloc.append(historique);
  return bloc;
}

// Où en est un retour transmis (voir suiviDuRetour) : l'étape, où en est l'agent, puis sa réponse quand elle est là.
function blocSuiviRetour(s, quand) {
  const bloc = el("div", "retour-suivi retour-suivi-" + s.ton);
  const tete = el("div", "retour-suivi-etat");
  tete.append(el("strong", "", "Suivi : " + s.libelle), document.createTextNode(quand ? " · " + dateFr(quand) : ""));
  bloc.append(tete);
  if (s.ouAgent) bloc.append(el("div", "retour-suivi-agent", "Où en est l'agent : " + s.ouAgent));
  if (s.texte) bloc.append(s.etat === "repondu" ? rendreTexte("retour-suivi-texte", s.texte)
    : el("div", "retour-suivi-texte", s.texte));
  return bloc;
}

export function ligneStory(ctx, e, t) {
  if (!t?.fonctionnalite) return null;
  const f = (e?.fonctionnalites || []).find((x) => x?.id === t.fonctionnalite);
  if (!f) return null;
  const nom = tronquer(f.nom || f.id, MAX_TITRE);
  const l = ligne("Story", ctx.ouvrirFonctionnalite ? "" : nom);
  if (ctx.ouvrirFonctionnalite) {
    const b = el("button", "lien-retour lien-story", nom + " →");
    b.type = "button";
    b.title = "Ouvrir la carte de la story";
    b.addEventListener("click", () => ctx.ouvrirFonctionnalite(f.id));
    l.lastChild.append(b);
  }
  return l;
}

export function contenuTache(ctx, contenu, t) {
  const e = ctx.etat;
  if (ctx.retourListe) {
    const retour = el("button", "lien-retour", "← Toutes les tâches");
    retour.type = "button";
    retour.addEventListener("click", ctx.ouvrirListe);
    contenu.append(retour);
  }
  contenu.append(el("h2", "", titreAffiche(e, t)));      // « Retour 2 – … » pour une étape refaite
  const groupe = livraisonGroupee(t);
  if (groupe) {            // un seul livrable pour plusieurs éléments : leur liste, pas l'objectif de l'élément meneur
    const r = el("p", "resume-tache");
    r.append(el("strong", "", "Objectif : "), document.createTextNode(
      "un seul livrable pour " + (groupe.noms.length ? groupe.noms.join(", ") : `${groupe.n} éléments`) + "."));
    contenu.append(r);
  } else if (t.resume) {   // l'objectif de la tâche : élément, étape, dernière consigne (servi par le relevé)
    const r = el("p", "resume-tache");
    r.append(el("strong", "", "Objectif : "), document.createTextNode(t.resume));
    contenu.append(r);
  }
  // L'agent attend des réponses à ses questions à choix : elles se répondent dans la discussion de la fonctionnalité.
  const attente = questionsAAttendre(e, t);
  if (attente && ctx.ouvrirFonctionnalite) {
    const n = attente.questions.length;
    const b = el("button", "bouton", n > 1 ? `Répondre aux ${n} questions de l'agent` : "Répondre à la question de l'agent");
    b.type = "button";
    b.addEventListener("click", () => ctx.ouvrirFonctionnalite(t.fonctionnalite));
    contenu.append(b);
  }
  const story = ligneStory(ctx, e, t);         // la fonctionnalité (ou correction) dont la tâche fait partie
  if (story) contenu.append(story);
  contenu.append(ligne("Colonne", tronquer(nomColonne(e, t.colonne), 30)));
  contenu.append(ligne("Agent", prenomAgent(e, t.agent)));
  const etape = libelleEtapeTache(e, t);       // « diagnostic », « correctif »… pour une correction
  contenu.append(ligne("Étape", etape ? tronquer(etape, MAX_TITRE) : "—"));
  const necessaire = libelleModeleNecessaire(t);   // la montée y est comprise ; sans lui, la montée seule
  const montee = libelleMontee(t);
  if (necessaire) contenu.append(ligne("Modèle nécessaire", necessaire));
  else if (montee) contenu.append(ligne("Modèle", montee));
  const lot = libelleLot(t, e.taches);
  if (lot) contenu.append(ligne("Lot", lot));
  if (t.lieu === "local") contenu.append(ligne("Lieu", "Sur le poste local"));
  else if (t.lieu === "serveur") contenu.append(ligne("Lieu", "Sur le serveur"));
  else if (t.lieu === "cloud") contenu.append(ligne("Lieu", "Dans le cloud"));
  for (const n of notesValides(t)) {
    const p = el("p", "note-tache");
    p.append(el("strong", "", n.libelle + " : "), document.createTextNode(n.texte));
    contenu.append(p);
  }
  const type = (e.types || []).find((x) => x.id === t.type);
  if (t.type) contenu.append(ligne("Type", type ? type.nom : t.type));
  contenu.append(ligne("Mise à jour", ilYA(t.maj)));
  // Son coût : en cours, il évolue à chaque relecture ; fini, celui noté dans l'historique d'usage.
  const cout = ligne("Coût", t.travail?.cout ? libelleCout(t, {}) : "…");
  contenu.append(cout);
  if (!t.travail?.cout) {
    coutsDesTaches().then((c) => { const v = cout.lastChild; if (v) v.textContent = libelleCout(t, c); });
  }
  const travail = auTravail(t.travail);      // l'agent local au travail (dit par le bureau, relu à chaque état)
  const av = avancementEnClair(t.avancement);
  if (av) contenu.append(blocAvancement(av, travail));
  else if (travail) contenu.append(ligne("Au travail", "depuis " + travail.depuis + (travail.action ? " · " + travail.action : "")));
  const pourquoi = pourquoiElleAttend(t);     // pourquoi elle ne part pas (dit par le moteur)
  if (pourquoi) contenu.append(blocPourquoi(pourquoi));
  else if (t.attente) contenu.append(el("p", "carte-attente", t.attente));     // retenue par la charge (moteur d'avant)
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
    const suivi = suiviDuRetour(r, t.avancement);
    if (suivi) li.append(blocSuiviRetour(suivi, r.suivi?.t));
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
