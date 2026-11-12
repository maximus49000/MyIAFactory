// Les décisions de la version 4 au bureau du Directeur : cahiers et méthodes à valider, genres à confirmer,
// « méthode à revoir ? », sessions cloud à créer. Chaque bouton envoie une demande au projet, jamais un changement direct.

import {el} from "./dom.js";
import {tronquer} from "./texte.js";
import {nomAgent} from "./detail.js";
import {decisionsDirecteur, demandeGenre, demandeSession, issuesGenreFonctionnalite, demandeGenreFonctionnalite,
  demandeEnvironnement} from "./actions.js";
import {rendreOrganisation} from "./organisation.js";
import {demandeCahier, demandeMethode} from "./fonctionnalite.js";

const MOTIF_GENRE = /^[a-z0-9][a-z0-9-]{0,39}$/;

function partie(titre, vide, elements) {
  const s = el("section", "partie");
  s.append(el("h3", "", titre));
  const ul = el("ul", "liste-partie");
  if (!elements.length) ul.append(el("li", "vide", vide));
  for (const x of elements) ul.append(x);
  s.append(ul);
  return s;
}

function lienFonctionnalite(ctx, d) {
  const b = el("button", "lien-tache", d.nom || d.fonctionnalite);
  b.type = "button";
  b.addEventListener("click", () => ctx.ouvrirFonctionnalite(d.fonctionnalite));
  return b;
}

// Un bouton qui envoie une demande ; grisé jusqu'à la réponse, et de nouveau actif si elle est refusée.
// `avant` (facultatif) peut empêcher l'envoi (saisie incomplète).
export function boutonDemande(ctx, libelle, classe, fabrique, avant = () => true) {
  const b = el("button", classe, libelle);
  b.type = "button";
  b.addEventListener("click", async () => {
    if (!avant()) return;
    b.disabled = true;
    const r = await ctx.barre.demander(fabrique(), b);
    if (!r.ok) b.disabled = false;
  });
  return b;
}

function decisionFonctionnalite(ctx, d, boutons) {
  const li = el("li", "");
  li.append(lienFonctionnalite(ctx, d), el("div", "decision-texte", d.texte));
  if (ctx.etat.agir) {
    const rangee = el("div", "lecon-boutons");
    rangee.append(...boutons);
    li.append(rangee);
  }
  return li;
}

function decisionGenre(ctx, d) {
  const li = el("li", "decision-genre");
  li.append(el("div", "decision-texte", d.texte), el("div", "lecon-meta", "Genre proposé : " + d.propose));
  if (!ctx.etat.agir) return li;
  const connus = Array.isArray(d.genres_connus) ? d.genres_connus : [];
  const menu = el("select", "genre-choix");
  menu.setAttribute("aria-label", "Genre du projet");
  for (const g of new Set([d.propose, ...connus])) menu.append(new Option(g, g));
  menu.append(new Option("Nouveau genre…", ""));
  const identifiant = document.createElement("input");
  identifiant.type = "text";
  identifiant.placeholder = "Identifiant du genre (minuscules, chiffres, tirets)";
  identifiant.maxLength = 40;
  const description = document.createElement("textarea");
  description.rows = 2;
  description.maxLength = 3500;
  description.placeholder = "Décrire ce genre de projet en une phrase";
  const erreur = el("p", "saisie-erreur", "");
  const genre = () => (menu.value === "" ? identifiant.value.trim() : menu.value);
  const nouveau = () => !connus.includes(genre());   // un genre inconnu demande une description
  const maj = () => {
    identifiant.hidden = menu.value !== "";
    description.hidden = !nouveau();
  };
  menu.addEventListener("change", maj);
  identifiant.addEventListener("input", maj);
  maj();
  const confirmer = boutonDemande(ctx, "Confirmer le genre", "bouton",
    () => demandeGenre(d.id, genre(), nouveau() ? description.value : undefined),
    () => {
      if (!MOTIF_GENRE.test(genre())) { erreur.textContent = "Identifiant de genre invalide (minuscules, chiffres, tirets ; 40 caractères au plus)."; return false; }
      if (nouveau() && !description.value.trim()) { erreur.textContent = "Un nouveau genre demande une description."; return false; }
      erreur.textContent = "";
      return true;
    });
  li.append(menu, identifiant, description, erreur, confirmer);
  return li;
}

// « Cette demande n'est pas du genre du projet » : le genre se corrige (liste des genres connus, ou un nouveau avec sa
// description), puis trois issues : un nouveau projet (formulaire), rester ici, ou « c'est le même genre ».
function decisionGenreFonctionnalite(ctx, d) {
  const li = el("li", "decision-genre");
  li.append(lienFonctionnalite(ctx, d), el("div", "decision-texte", d.texte),
            el("div", "lecon-meta", "Genre proposé : " + d.propose + (d.incertain ? " (le moteur hésite)" : "")));
  const issues = issuesGenreFonctionnalite(d, ctx.etat.agir);
  if (!issues.length) return li;
  const connus = Array.isArray(d.genres_connus) ? d.genres_connus : [];
  const menu = el("select", "genre-choix");
  menu.setAttribute("aria-label", "Genre de la demande");
  for (const g of new Set([d.propose, ...connus].filter(Boolean))) menu.append(new Option(g, g));
  menu.append(new Option("Nouveau genre…", ""));
  const identifiant = document.createElement("input");
  identifiant.type = "text";
  identifiant.placeholder = "Identifiant du genre (minuscules, chiffres, tirets)";
  identifiant.maxLength = 40;
  const description = document.createElement("textarea");
  description.rows = 2;
  description.maxLength = 3500;
  description.placeholder = "Décrire ce genre de projet en une phrase";
  if (d.nouveau?.id && d.nouveau.id === d.propose) description.value = d.nouveau.description || "";
  const erreur = el("p", "saisie-erreur", "");
  const genre = () => (menu.value === "" ? identifiant.value.trim() : menu.value);
  const nouveau = () => !connus.includes(genre());   // un genre inconnu demande sa description
  const maj = () => {
    identifiant.hidden = menu.value !== "";
    description.hidden = !nouveau();
    if (nouveau() && !description.value && d.nouveau?.id === genre()) description.value = d.nouveau.description || "";
  };
  menu.addEventListener("change", maj);
  identifiant.addEventListener("input", maj);
  maj();
  const valide = () => {
    if (!MOTIF_GENRE.test(genre())) { erreur.textContent = "Identifiant de genre invalide (minuscules, chiffres, tirets ; 40 caractères au plus)."; return false; }
    if (nouveau() && !description.value.trim()) { erreur.textContent = "Un nouveau genre demande une description."; return false; }
    erreur.textContent = "";
    return true;
  };
  const choisi = () => ({genre: genre(), description: nouveau() ? description.value : undefined});
  li.append(menu, identifiant, description, erreur);
  const rangee = el("div", "lecon-boutons");
  for (const issue of issues) {
    if (issue.choix === "nouveau_projet") {
      const b = el("button", "bouton", issue.libelle);
      b.type = "button";
      b.addEventListener("click", () => {
        if (!valide()) return;
        const c = choisi();
        const ouvert = ctx.barre.nouveauProjet({decision: {id: d.id, fonctionnalite: d.fonctionnalite, nom: d.nom},
                                                genre: c.genre, genreDescription: c.description, nomPropose: d.nom});
        if (!ouvert) erreur.textContent = "La création d'un projet n'est pas disponible dans ce bureau : choisissez « Dans ce projet ».";
      });
      rangee.append(b);
    } else if (issue.choix === "meme") {
      rangee.append(boutonDemande(ctx, issue.libelle, "bouton secondaire", () => demandeGenreFonctionnalite(d, "meme")));
    } else {
      rangee.append(boutonDemande(ctx, issue.libelle, "bouton secondaire", () => demandeGenreFonctionnalite(d, "ici", choisi()), valide));
    }
  }
  li.append(rangee);
  return li;
}

// Un outil du poste ne s'est pas installé : ce qui manque, puis « C'est fait » (revérifie) ou « Continuer sans ».
function decisionEnvironnement(ctx, d) {
  const manque = Array.isArray(d.environnement) ? d.environnement : [];
  const noms = manque.map((x) => (typeof x === "string" ? x : x?.outil)).filter(Boolean);
  return decisionFonctionnalite(ctx, {...d, texte: d.texte + (noms.length ? " Il manque : " + noms.join(", ") + "." : "")}, [
    boutonDemande(ctx, "C'est fait", "bouton", () => demandeEnvironnement(d, "fait")),
    boutonDemande(ctx, "Continuer sans", "bouton secondaire", () => demandeEnvironnement(d, "continuer"))]);
}

function decisionSession(ctx, d) {
  const e = ctx.etat;
  const li = el("li", "decision-session");
  const agent = (e.agents || []).find((a) => a.id === d.agent);
  const service = agent?.service ? (e.services || []).find((s) => s.id === agent.service)?.nom : null;
  li.append(el("div", "decision-texte", d.texte));
  li.append(el("div", "lecon-meta", [nomAgent(e, d.agent), agent?.modele, service].filter(Boolean).join(" · ")));
  if (!e.agir) return li;
  const nom = document.createElement("input");
  nom.type = "text";
  nom.maxLength = 200;
  nom.placeholder = "Nom de la session créée";
  nom.setAttribute("aria-label", "Nom de la session créée");
  li.append(nom, boutonDemande(ctx, "C'est fait", "bouton", () => demandeSession(d.id, nom.value.trim()), () => nom.value.trim() !== ""));
  return li;
}

// Une discussion qui attend votre réponse : qui parle, ce qu'il a dit en dernier, et de quoi y aller.
function reponseAttendue(ctx, x) {
  const li = el("li", "");
  const qui = nomAgent(ctx.etat, x.dernier.auteur);
  li.append(lienFonctionnalite(ctx, x), el("div", "lecon-meta", qui + " attend votre réponse"),
            el("div", "decision-texte", tronquer(x.dernier.texte || "", 280)));
  const b = el("button", "bouton", "Répondre");
  b.type = "button";
  b.addEventListener("click", () => ctx.ouvrirFonctionnalite(x.fonctionnalite));
  li.append(b);
  return li;
}

export function contenuDecisionsV4(ctx, contenu) {
  const d = decisionsDirecteur(ctx.etat);
  contenu.append(partie("Réponses attendues", "Aucune discussion n'attend votre réponse",
    d.reponses.map((x) => reponseAttendue(ctx, x))));
  const validations = [
    ...d.cahiers.map((x) => decisionFonctionnalite(ctx, x, [
      boutonDemande(ctx, "Valider le cahier", "bouton", () => demandeCahier(x.fonctionnalite, "valider"))])),
    ...d.methodes.map((x) => decisionFonctionnalite(ctx, x, [
      boutonDemande(ctx, "Valider la méthode", "bouton", () => demandeMethode(x.fonctionnalite, "valider"))])),
  ];
  contenu.append(partie("Cahiers et méthodes à valider", "Aucun cahier ni méthode à valider", validations));
  contenu.append(partie("Demandes d'un autre genre", "Aucune demande ne sort du genre du projet",
    d.genresDemandes.map((x) => decisionGenreFonctionnalite(ctx, x))));
  contenu.append(partie("Genres à confirmer", "Aucun genre à confirmer", d.genres.map((x) => decisionGenre(ctx, x))));
  contenu.append(partie("Méthode à revoir ?", "Aucune méthode à revoir", d.revoir.map((x) => decisionFonctionnalite(ctx, x, [
    boutonDemande(ctx, "Oui, revoir", "bouton", () => demandeMethode(x.fonctionnalite, "revoir")),
    boutonDemande(ctx, "Non, garder", "bouton secondaire", () => demandeMethode(x.fonctionnalite, "garder"))]))));
  contenu.append(partie("Organisation à valider", "Aucune organisation à valider",
    d.organisations.map((x) => rendreOrganisation(ctx, x, (libelle, classe, fabrique, avant) =>
      boutonDemande(ctx, libelle, classe, fabrique, avant)))));
  contenu.append(partie("Environnement du poste à compléter", "Aucun outil ne manque",
    d.environnements.map((x) => decisionEnvironnement(ctx, x))));
  contenu.append(partie("Sessions cloud à créer", "Aucune session à créer", d.sessions.map((x) => decisionSession(ctx, x))));
}
