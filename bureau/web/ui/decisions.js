// Les décisions de la version 4 au bureau du Directeur : cahiers et méthodes à valider, genres à confirmer,
// « méthode à revoir ? », sessions cloud à créer. Chaque bouton envoie une demande au projet, jamais un changement direct.

import {el} from "./dom.js";
import {tronquer, dateFr, euros} from "./texte.js";
import {nomAgent} from "./detail.js";
import {decisionsDirecteur, demandeGenre, demandeSession, lireSession, issuesGenreFonctionnalite, demandeGenreFonctionnalite,
  demandeEnvironnement, demandeElargirGenre, demandeInstallerOutil, demandeOutilAgent, demandeAccordAgent,
  demandeRegleProjet, regleProposee, MAX_REGLE_PROJET, demandeSerieArretee, demandeFinVue, demandeFableTache} from "./actions.js";
import {blocOutil} from "./outils.js";
import {decisionChezPartenaire} from "./chez-partenaire.js";
import {rendreOrganisation} from "./organisation.js";
import {demandeMethode} from "./fonctionnalite.js";
import {aVerifier, enteteValidation, estEnvoyee, ouvrirValidation, pointsDeValidation, urlTelechargement,
  lienAcces} from "./validation.js";
import {ouvrirCahier, resumeCahier} from "./cahier.js";
import {etiquettePart, avecPart, marquerPart} from "./abonnement.js";
import {etiquetteCO2} from "./empreinte.js";
import {projetCourant, urlProjet} from "./projets.js";

const plein = (t) => typeof t === "string" && t.trim() !== "";
const MOTIF_GENRE =/^[a-z0-9][a-z0-9-]{0,39}$/;

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
  if (!d.fonctionnalite) return el("span", "lien-tache", d.nom || "Le projet");   // une décision du projet
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

function decisionFonctionnalite(ctx, d, boutons, corps = null) {
  const li = el("li", "");
  li.append(lienFonctionnalite(ctx, d), el("div", "decision-texte", d.texte));
  if (corps) li.append(corps);
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
  if (plein(d.description)) li.append(el("div", "lecon-meta", "Description proposée : " + d.description));
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
    // la phrase du genre nouveau est déjà rédigée : il n'y a qu'à valider (ou à corriger)
    if (nouveau() && !description.value && plein(d.description) && genre() === d.propose) description.value = d.description;
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
  if (plein(d.nouveau?.description)) li.append(el("div", "lecon-meta", "Description proposée : " + d.nouveau.description));
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

// « Élargir la description de ce genre ? » : l'ancienne et la nouvelle description (pré-remplie, modifiable). Valider
// l'écrit dans la mémoire du genre ; refuser la laisse telle quelle. La fonctionnalité n'attend pas cette réponse.
function decisionElargirGenre(ctx, d) {
  const li = el("li", "decision-genre");
  li.append(el("div", "decision-texte", d.texte), el("div", "lecon-meta", "Description actuelle : " + d.ancienne));
  if (!ctx.etat.agir) return li;
  const description = document.createElement("textarea");
  description.rows = 2;
  description.maxLength = 3500;
  description.value = d.propose || "";
  description.setAttribute("aria-label", "Nouvelle description du genre");
  const erreur = el("p", "saisie-erreur", "");
  const rangee = el("div", "lecon-boutons");
  rangee.append(
    boutonDemande(ctx, "Valider la nouvelle description", "bouton", () => demandeElargirGenre(d, "valider", description.value),
      () => { if (!description.value.trim()) { erreur.textContent = "La description ne peut pas être vide."; return false; } erreur.textContent = ""; return true; }),
    boutonDemande(ctx, "Garder l'ancienne", "bouton secondaire", () => demandeElargirGenre(d, "refuser")));
  li.append(description, erreur, rangee);
  return li;
}

// « Environnement du poste à compléter » : pour chaque outil qui manque, son objectif dans le projet, le lien officiel
// (nouvel onglet), le mode opératoire numéroté et, si un agent peut l'installer seul, « Installer en autonomie » ;
// puis « C'est fait » (revérifie en code, versions comparées) ou « Continuer sans ».
function decisionEnvironnement(ctx, d) {
  const manque = (Array.isArray(d.environnement) ? d.environnement : []).map((x) => (typeof x === "string" ? {outil: x} : x))
    .filter((x) => x && plein(x.outil));
  const outils = el("div", "outils-a-installer");
  if (plein(d.verifie_le)) outils.append(el("div", "lecon-meta", "Dernière vérification : " + heureDeVerification(d.verifie_le)));
  const sur = (message) => () => (typeof globalThis.confirm === "function" ? globalThis.confirm(message) : true);
  for (const x of manque) {
    const trouve = x.etat === "en_place";
    const action = ctx.etat.agir && !trouve && x.autonome === true && x.en_cours !== true
      ? boutonDemande(ctx, "Installer en autonomie", "bouton secondaire", () => demandeInstallerOutil(d, x.outil)) : null;
    const forcer = ctx.etat.agir && x.verification?.trouve === false && !trouve
      ? boutonDemande(ctx, "Forcer : c'est installé", "bouton secondaire", () => demandeEnvironnement(d, "forcer", x.outil),
        sur(`Confirmer que « ${x.outil} » est bien installé ? Il ne sera pas vérifié : les étapes qui en ont besoin se fieront à vous.`))
      : null;
    outils.append(blocOutil({...x, etat: trouve ? "en_place" : "a_installer"}, {action, forcer, libelleEnPlace: "trouvé"}));
  }
  const boutons = [
    boutonDemande(ctx, "C'est fait", "bouton", () => demandeEnvironnement(d, "fait")),
    boutonDemande(ctx, "Continuer sans", "bouton secondaire", () => demandeEnvironnement(d, "continuer"))];
  if (manque.some((x) => x.etat !== "en_place" && x.verification?.trouve === false)) {
    boutons.push(boutonDemande(ctx, "Forcer : tout est installé", "bouton secondaire", () => demandeEnvironnement(d, "forcer"),
      sur("Confirmer que tous les outils non trouvés sont bien installés ? Ils ne seront pas vérifiés.")));
  }
  return decisionFonctionnalite(ctx, d, boutons, outils);
}

// « 12/11/2026 14:05 » (heure locale) pour la date ISO de la dernière vérification ; le texte brut si elle est illisible.
function heureDeVerification(iso) {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  const p = (n) => String(n).padStart(2, "0");
  return `${p(t.getDate())}/${p(t.getMonth() + 1)}/${t.getFullYear()} ${p(t.getHours())}:${p(t.getMinutes())}`;
}

// La demande « valider » ou « renvoyer » sans réponses par point (la forme d'avant la fenêtre de validation, que le
// moteur accepte toujours). « Renvoyer » exige une remarque : sans texte, rien ne part (`null`). La page n'envoie plus
// que `corpsValidation` (ui/validation.js).
export function corpsValiderEtape(decision, verdict, texte) {
  const remarque = String(texte ?? "").trim();
  if (verdict === "renvoyer") return remarque ? {type: "valider_etape", decision: decision.id, verdict, texte: remarque} : null;
  return {type: "valider_etape", decision: decision.id, verdict: "valider"};
}

export {enteteValidation};

// Ce que la fenêtre de validation montrera, en une ligne : « 1 livrable · un lien d'accès · 2 images · 3 points ».
export function resumeAVerifier(d) {
  const v = aVerifier(d, {hotePage: "127.0.0.1", projet: null});
  const n = (k, un, plusieurs) => (k ? `${k} ${k > 1 ? plusieurs : un}` : null);
  return [n(v.livrables.length, "livrable", "livrables"), v.acces ? "un lien d'accès" : null,
    n(v.images.length, "image", "images"), n(pointsDeValidation(d).length, "point à vérifier", "points à vérifier")]
    .filter(Boolean).join(" · ");
}

// Un élément attend votre validation : au bureau, seulement son résumé (élément, objectif, « À valider », ce qu'il y a
// à vérifier) et « Ouvrir la validation ». On ne valide plus hors de la fenêtre de validation.
function decisionValidation(ctx, d) {
  const li = el("li", "decision-validation");
  li.append(lienFonctionnalite(ctx, d), el("div", "lecon-meta", `Élément : ${d.element?.nom || d.element?.id || "?"}`));
  for (const x of enteteValidation(d)) {
    const ligne = el("div", "decision-texte decision-entete");
    ligne.append(el("strong", "", `${x.libelle} : `), el("span", "", tronquer(x.texte, 220)));
    li.append(ligne);
  }
  if (!enteteValidation(d).length) li.append(el("div", "decision-texte", d.texte));
  li.append(el("div", "lecon-meta", resumeAVerifier(d)));
  const b = el("button", "bouton", "Ouvrir la validation");
  b.type = "button";
  b.addEventListener("click", () => (ctx.ouvrirValidation || ouvrirValidation)(ctx, d, b));
  li.append(b);
  return li;
}

// Un cahier des charges ou une méthode attend votre validation : au bureau, seulement son résumé et « Ouvrir … » ; la
// validation (ou la correction) se fait dans la fenêtre (ui/cahier.js), contenu sous les yeux.
function decisionAOuvrir(ctx, d, libelle) {
  const li = el("li", "decision-cahier");
  li.append(lienFonctionnalite(ctx, d), el("div", "decision-texte", d.texte));
  const resume = resumeCahier(ctx.etat, d);
  if (resume) li.append(el("div", "lecon-meta", resume));
  const b = el("button", "bouton", libelle);
  b.type = "button";
  b.addEventListener("click", () => (ctx.ouvrirCahier || ouvrirCahier)(ctx, d, b));
  li.append(b);
  return li;
}

// Un lien qui s'ouvre dans un nouvel onglet ; seulement une adresse https (sinon le texte seul).
function lienExterne(adresse, texte) {
  if (!(typeof adresse === "string" && adresse.startsWith("https://"))) return el("span", "", texte || String(adresse ?? ""));
  const a = document.createElement("a");
  a.href = adresse;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = texte || adresse;
  return a;
}

// Copie dans le presse-papiers ; repli quand l'API n'est pas permise (bureau ouvert en http depuis un téléphone).
async function copierTexte(texte, bouton, libelle) {
  try {
    await globalThis.navigator.clipboard.writeText(texte);
  } catch {
    const zone = document.createElement("textarea");
    zone.value = texte;
    zone.style = "position: fixed; opacity: 0";
    document.body?.append(zone);
    zone.select?.();
    try { document.execCommand?.("copy"); } finally { zone.remove?.(); }
  }
  bouton.textContent = "Copié";
  setTimeout(() => { bouton.textContent = libelle; }, 1500);
}

// « Sessions cloud à créer ». La démarche simplifiée (la décision porte `depart`) : le lien claude.ai/code, le dépôt,
// le modèle, le message de départ complet (« Copier le message »), puis l'adresse ou l'identifiant de la session créée
// et « C'est fait ». Une décision d'avant (sans `depart`) garde son champ de nom.
function decisionSession(ctx, d) {
  const e = ctx.etat;
  const li = el("li", "decision-session");
  const agent = (e.agents || []).find((a) => a.id === d.agent);
  const service = agent?.service ? (e.services || []).find((s) => s.id === agent.service)?.nom : null;
  li.append(el("div", "decision-texte", d.texte));
  li.append(el("div", "lecon-meta", [nomAgent(e, d.agent), agent?.modele, service].filter(Boolean).join(" · ")));
  const manuelle = plein(d.depart);
  if (manuelle) {
    const etapes = el("ol", "session-etapes");
    const ouvrir = el("li", "");
    ouvrir.append(el("span", "", "Ouvrir : "), lienExterne(d.lien, d.lien === "https://claude.ai/code" ? "claude.ai/code" : d.lien));
    const depot = el("li", "");
    depot.append(el("span", "", "Dépôt à choisir : "), lienExterne(d.depot, d.depot || "le dépôt GitHub du projet"));
    etapes.append(ouvrir, depot);
    if (plein(d.modele)) etapes.append(el("li", "", "Modèle : " + d.modele));
    li.append(etapes);
    const message = document.createElement("textarea");
    message.className = "session-depart";
    message.readOnly = true;
    message.rows = 6;
    message.value = d.depart;
    message.setAttribute("aria-label", "Message de départ à coller dans la session");
    const copier = el("button", "bouton secondaire", "Copier le message");
    copier.type = "button";
    copier.addEventListener("click", () => copierTexte(d.depart, copier, "Copier le message"));
    li.append(el("div", "lecon-meta", "Message de départ à coller dans la session :"), message, copier);
  }
  if (!e.agir) return li;
  const nom = document.createElement("input");
  nom.type = manuelle ? "url" : "text";
  nom.maxLength = 200;
  nom.placeholder = manuelle ? "Adresse de la session (https://claude.ai/code/…) ou son identifiant" : "Nom de la session créée";
  nom.setAttribute("aria-label", manuelle ? "Adresse ou identifiant de la session créée" : "Nom de la session créée");
  const erreur = el("p", "saisie-erreur", "");
  const valide = () => {
    if (!nom.value.trim()) {      // jamais un clic sans effet : on dit ce qui manque
      erreur.textContent = manuelle ? "Collez d'abord l'adresse de la session créée (https://claude.ai/code/…)."
        : "Donnez d'abord le nom de la session créée.";
      return false;
    }
    if (manuelle && !lireSession(nom.value)) {
      erreur.textContent = "Collez l'adresse de la session (https://claude.ai/code/…) ou son identifiant (session_…).";
      return false;
    }
    erreur.textContent = "";
    return true;
  };
  li.append(nom, erreur, boutonDemande(ctx, "C'est fait", "bouton", () => demandeSession(d.id, nom.value.trim()), valide));
  return li;
}

// « Outils à ouvrir à un agent » : l'agent arrêté, la commande refusée (une ligne, déjà coupée par le moteur), puis
// « Autoriser ce programme pour cet agent » (seulement si le moteur a pu nommer le programme) et « Refuser » ; sans
// programme à nommer, « C'est fait, relancer » une fois la fiche complétée à la main.
function decisionOutilAgent(ctx, d) {
  const li = el("li", "decision-outil");
  li.append(el("div", "decision-texte", d.texte));
  if (plein(d.commande)) li.append(el("div", "lecon-meta", "Commande refusée : " + d.commande));
  if (!ctx.etat.agir) return li;
  const rangee = el("div", "lecon-boutons");
  if (plein(d.programme)) {
    rangee.append(boutonDemande(ctx, "Autoriser ce programme pour cet agent", "bouton", () => demandeOutilAgent(d, "autoriser")));
  } else {
    rangee.append(boutonDemande(ctx, "C'est fait, relancer", "bouton", () => demandeOutilAgent(d, "relancer")));
  }
  rangee.append(boutonDemande(ctx, "Refuser", "bouton secondaire", () => demandeOutilAgent(d, "refuser")));
  li.append(rangee);
  return li;
}

// « Tâches qui demandent Fable » : la tâche et la raison (la justification de l'étape, ou la montée depuis Opus), puis
// « Autoriser Fable » (pour cette tâche seulement) ou « Refuser : Opus ». Rien ne part sur Fable sans ce clic.
function decisionFableTache(ctx, d) {
  const li = el("li", "decision-fable");
  li.append(el("div", "decision-texte", d.texte));
  if (plein(d.raison)) li.append(el("div", "lecon-meta", "Raison : " + d.raison));
  if (!ctx.etat.agir) return li;
  const rangee = el("div", "lecon-boutons");
  rangee.append(boutonDemande(ctx, "Autoriser Fable", "bouton", () => demandeFableTache(d, "autoriser")),
    boutonDemande(ctx, "Refuser : Opus", "bouton secondaire", () => demandeFableTache(d, "refuser")));
  li.append(rangee);
  return li;
}

// « Demandes d'accord des agents » : l'agent, ce qu'il veut faire et pourquoi, ce que ça implique (fenêtres, branchement,
// coût), le rappel de la règle quand il vise un appareil physique ; « J'accepte », « Je refuse » et une consigne facultative.
function decisionAccordAgent(ctx, d) {
  const li = el("li", "decision-accord");
  li.append(el("div", "decision-texte", d.texte));
  li.append(el("div", "lecon-meta", [nomAgent(ctx.etat, d.agent), d.partenaire && "chez " + d.partenaire, d.cout && "coût : " + d.cout]
    .filter(plein).join(" · ")));
  if (plein(d.pourquoi)) li.append(el("div", "decision-texte", "Pourquoi : " + d.pourquoi));
  if (plein(d.implique)) li.append(el("div", "lecon-meta", "Ce que cela implique : " + d.implique));
  if (plein(d.regle)) li.append(el("div", "decision-regle", d.regle));
  for (const r of Array.isArray(d.regles_touchees) ? d.regles_touchees : []) {     // un rappel : le Directeur statue
    if (plein(r?.texte)) li.append(el("div", "decision-regle", "Cette demande contredit la règle du projet : " + r.texte));
  }
  if (!ctx.etat.agir) return li;
  const consigne = document.createElement("input");
  consigne.type = "text";
  consigne.maxLength = 500;
  consigne.placeholder = "Consigne pour l'agent (facultative)";
  consigne.setAttribute("aria-label", "Consigne pour l'agent");
  li.append(consigne);
  // « Retenir comme règle du projet » : le texte proposé est modifiable ; coché, la réponse le note au projet (les agents
  // le reçoivent ensuite à chaque départ). Cochée d'emblée quand le moteur propose une règle (l'appareil physique).
  let retenir = null, regle = null;
  if (Array.isArray(ctx.etat.regles_projet)) {
    retenir = document.createElement("input");
    retenir.type = "checkbox";
    retenir.checked = plein(d.regle_proposee);
    retenir.setAttribute("aria-label", "Retenir comme règle du projet");
    const etiquette = el("label", "decision-retenir");
    etiquette.append(retenir, el("span", "", " Retenir comme règle du projet"));
    regle = document.createElement("textarea");
    regle.value = regleProposee(d);
    regle.maxLength = MAX_REGLE_PROJET;
    regle.rows = 2;
    regle.setAttribute("aria-label", "Texte de la règle du projet");
    regle.hidden = !retenir.checked;
    retenir.addEventListener("change", () => { regle.hidden = !retenir.checked; });
    li.append(etiquette, regle);
  }
  const retenue = () => (retenir && retenir.checked ? regle.value : undefined);
  const avant = () => (retenir && retenir.checked ? regleValide(ctx, regle.value) : true);   // coché mais vide : rien ne part
  const rangee = el("div", "lecon-boutons");
  const choix = (Array.isArray(d.choix) ? d.choix : []).filter(plein);
  if (choix.length) {     // l'agent a proposé des choix : ses boutons, la demande n'est pas écartée
    for (const c of choix) {
      rangee.append(boutonDemande(ctx, c, "bouton secondaire", () => demandeAccordAgent(d, "choisir", consigne.value, retenue(), c), avant));
    }
  } else {
    rangee.append(boutonDemande(ctx, "J'accepte", "bouton", () => demandeAccordAgent(d, "accepter", consigne.value, retenue()), avant),
                  boutonDemande(ctx, "Je refuse", "bouton secondaire", () => demandeAccordAgent(d, "refuser", consigne.value, retenue()), avant));
  }
  li.append(rangee);
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

// « Règles du projet » : celles que le Directeur a retenues, que chaque agent reçoit en tête de son départ. Chaque geste
// (ajouter, modifier, supprimer après confirmation) est une demande au projet.
function regleDuProjet(ctx, r) {
  const li = el("li", "regle-projet");
  const texte = el("span", "regle-projet-texte", r.texte);
  li.append(texte);
  if (r.origine && plein(r.origine.agent)) li.append(el("span", "lecon-meta", " · demandée par " + nomAgent(ctx.etat, r.origine.agent)));
  if (!ctx.etat.agir) return li;
  const rangee = el("div", "lecon-boutons");
  const modifier = el("button", "bouton secondaire", "Modifier");
  modifier.type = "button";
  modifier.addEventListener("click", () => {
    modifier.hidden = true;
    texte.hidden = true;
    const zone = saisieRegle(r.texte);
    const edition = el("div", "lecon-boutons");
    const annuler = el("button", "bouton secondaire", "Annuler");
    annuler.type = "button";
    annuler.addEventListener("click", () => { zone.hidden = edition.hidden = true; modifier.hidden = texte.hidden = false; });
    edition.append(boutonDemande(ctx, "Enregistrer", "bouton", () => demandeRegleProjet("modifier", r.id, zone.value),
      () => regleValide(ctx, zone.value)), annuler);
    li.append(zone, edition);
  });
  const supprimer = boutonDemande(ctx, "Supprimer", "bouton secondaire", () => demandeRegleProjet("supprimer", r.id),
    () => (typeof globalThis.confirm === "function"
      ? globalThis.confirm("Supprimer cette règle du projet ? Les agents ne la recevront plus.") : true));
  rangee.append(modifier, supprimer);
  li.append(rangee);
  return li;
}

function saisieRegle(depart) {
  const zone = document.createElement("textarea");
  zone.value = depart;
  zone.maxLength = MAX_REGLE_PROJET;
  zone.rows = 2;
  zone.placeholder = "Une règle que chaque agent respecte dans ce projet";
  zone.setAttribute("aria-label", "Texte de la règle du projet");
  return zone;
}

function regleValide(ctx, texte) {
  const t = String(texte || "").trim();
  const probleme = t === "" ? "La règle est vide." : t.length > MAX_REGLE_PROJET ? `La règle dépasse ${MAX_REGLE_PROJET} caractères.` : "";
  if (probleme && typeof ctx.barre.dire === "function") ctx.barre.dire(probleme);
  return probleme === "";
}

function reglesDuProjet(ctx) {
  const liste = ctx.etat.regles_projet.filter((r) => plein(r?.id) && plein(r?.texte)).map((r) => regleDuProjet(ctx, r));
  const s = partie("Règles du projet", "Aucune règle pour l'instant", liste);
  if (ctx.etat.agir) {
    const zone = saisieRegle("");
    const ajouter = boutonDemande(ctx, "Ajouter la règle", "bouton", () => demandeRegleProjet("ajouter", null, zone.value),
      () => regleValide(ctx, zone.value));
    const rangee = el("div", "regle-projet-ajout");
    rangee.append(zone, ajouter);
    s.append(rangee);
  }
  return s;
}

// « La série de … ne progresse plus » : la raison, et « Relancer la série » (le moteur la relit depuis le suivi).
function decisionSerieArretee(ctx, d) {
  const li = el("li", "decision-serie");
  li.append(lienFonctionnalite(ctx, d), el("div", "decision-texte", d.texte));
  if (ctx.etat.agir) {
    const rangee = el("div", "lecon-boutons");
    rangee.append(boutonDemande(ctx, "Relancer la série", "bouton", () => demandeSerieArretee(d)));
    li.append(rangee);
  }
  return li;
}

// L'avis de fin d'une fonctionnalité, en données : ses livrables à télécharger, le lien d'accès de son site (relayé par
// le bureau au téléphone : `/apercu/<projet>/fin-<fonctionnalité>/`) et les éléments laissés de côté.
export function avisDeFin(x, {hotePage = globalThis.location?.hostname || "127.0.0.1", projet = projetCourant(),
                              origine = null} = {}) {
  const livrables = (Array.isArray(x?.livrables) ? x.livrables : []).filter((l) => plein(l?.chemin)).map((l) => ({
    chemin: l.chemin, titre: plein(l.titre) ? l.titre : l.chemin.split(/[\\/]/).pop(),
    url: urlTelechargement(x.fonctionnalite, l.chemin, projet, origine)}));
  const acces = x?.acces ? lienAcces({id: "fin-" + x.fonctionnalite, acces: x.acces}, {hotePage, projet, origine}) : null;
  const laisses = (Array.isArray(x?.laisses) ? x.laisses : []).filter(plein);
  return {livrables, acces, laisses};
}

// La ligne de coût de l'avis de fin : « Coût : ≈ 1,20 € · ≈ 3 % semaine · CO₂ … » (ce que dit déjà le panneau).
export function texteCoutDeFin(c) {
  if (!c?.disponible) return "";
  return avecPart(avecPart(`Coût : ${euros(c.total)}${c.sans_prix ? " + prix inconnu" : ""}`, etiquettePart(c.total)),
                  etiquetteCO2(c.co2));
}

// « Fonctionnalités terminées » : nom, date, coût, livrables, site, catalogue ; « Vu » ferme l'avis (non bloquant).
function decisionFin(ctx, x) {
  const li = el("li", "decision-fin");
  const a = avisDeFin(x);
  li.append(lienFonctionnalite(ctx, x), el("div", "lecon-meta", "Terminée" + (plein(x.date) ? " le " + dateFr(x.date) : "")));
  const cout = el("div", "lecon-meta", "");
  li.append(cout);
  if (typeof globalThis.fetch === "function") {
    (async () => {
      try {
        const r = await globalThis.fetch(urlProjet(`/api/couts?fonctionnalite=${encodeURIComponent(x.fonctionnalite)}`),
                                         {cache: "no-store"});
        cout.textContent = texteCoutDeFin(await r.json());
        if (cout.textContent) marquerPart(cout);
      } catch { cout.textContent = ""; }
    })();
  }
  const liens = el("div", "fin-liens");
  for (const l of a.livrables) {
    const lien = el("a", "bouton secondaire val-telecharger", "Télécharger : " + l.titre);
    lien.href = l.url;
    liens.append(lien);
  }
  if (a.acces) {
    const lien = el("a", "bouton secondaire", "Ouvrir le site" + (a.acces.description ? " : " + a.acces.description : ""));
    lien.href = a.acces.url;
    lien.target = "_blank";
    lien.rel = "noopener noreferrer";
    liens.append(lien);
  }
  if (x.catalogue && typeof ctx.ouvrirCatalogue === "function") {
    const b = el("button", "bouton secondaire", "Ouvrir le catalogue");
    b.type = "button";
    b.addEventListener("click", () => ctx.ouvrirCatalogue(x.fonctionnalite));
    liens.append(b);
  }
  if (!a.livrables.length && !a.acces && !(x.catalogue && typeof ctx.ouvrirCatalogue === "function")) {
    liens.append(el("span", "note", "Aucun livrable ni lien d'accès noté : ouvrez la fonctionnalité pour ses documents."));
  }
  li.append(liens);
  if (a.laisses.length) li.append(el("div", "lecon-meta", "Laissés de côté : " + a.laisses.join(", ")));
  if (ctx.etat.agir) {
    const rangee = el("div", "lecon-boutons");
    rangee.append(boutonDemande(ctx, "Vu", "bouton", () => demandeFinVue(x.fonctionnalite)));
    li.append(rangee);
  }
  return li;
}

export function contenuDecisionsV4(ctx, contenu) {
  const d = decisionsDirecteur(ctx.etat);
  if (d.terminees.length) {     // non bloquant : en tête, seulement quand il y en a
    contenu.append(partie("Fonctionnalités terminées", "", d.terminees.map((x) => decisionFin(ctx, x))));
  }
  if (d.series.length) {
    contenu.append(partie("Séries qui ne progressent plus", "", d.series.map((x) => decisionSerieArretee(ctx, x))));
  }
  contenu.append(partie("Réponses attendues", "Aucune discussion n'attend votre réponse",
    d.reponses.map((x) => reponseAttendue(ctx, x))));
  if (d.chezPartenaires.length) {     // seulement quand il y en a : l'utilisateur fait la génération chez le partenaire
    contenu.append(partie("À faire chez un partenaire", "", d.chezPartenaires.map((x) =>
      decisionChezPartenaire(ctx, x, (libelle, classe, fabrique, avant) => boutonDemande(ctx, libelle, classe, fabrique, avant)))));
  }
  const validations = [
    ...d.cahiers.filter((x) => !estEnvoyee(x.id)).map((x) => decisionAOuvrir(ctx, x, "Ouvrir le cahier des charges")),
    ...d.methodes.filter((x) => !estEnvoyee(x.id)).map((x) => decisionAOuvrir(ctx, x, "Ouvrir la méthode")),
  ];
  contenu.append(partie("Cahiers et méthodes à valider", "Aucun cahier ni méthode à valider", validations));
  contenu.append(partie("Éléments à valider", "Aucun élément n'attend votre validation",
    d.validations.filter((x) => !estEnvoyee(x.id)).map((x) => decisionValidation(ctx, x))));   // déjà répondue : retirée
  contenu.append(partie("Demandes d'un autre genre", "Aucune demande ne sort du genre du projet",
    d.genresDemandes.map((x) => decisionGenreFonctionnalite(ctx, x))));
  contenu.append(partie("Genres à confirmer", "Aucun genre à confirmer", d.genres.map((x) => decisionGenre(ctx, x))));
  contenu.append(partie("Descriptions de genre à élargir", "Aucune description de genre à élargir",
    d.elargissements.map((x) => decisionElargirGenre(ctx, x))));
  contenu.append(partie("Méthode à revoir ?", "Aucune méthode à revoir", d.revoir.map((x) => decisionFonctionnalite(ctx, x, [
    boutonDemande(ctx, "Oui, revoir", "bouton", () => demandeMethode(x.fonctionnalite, "revoir")),
    boutonDemande(ctx, "Non, garder", "bouton secondaire", () => demandeMethode(x.fonctionnalite, "garder"))]))));
  contenu.append(partie("Organisation à valider", "Aucune organisation à valider",
    d.organisations.map((x) => rendreOrganisation(ctx, x, (libelle, classe, fabrique, avant) =>
      boutonDemande(ctx, libelle, classe, fabrique, avant)))));
  contenu.append(partie("Environnement du poste à compléter", "Aucun outil ne manque",
    d.environnements.map((x) => decisionEnvironnement(ctx, x))));
  if (d.fables.length) {     // seulement quand il y en a : une tâche attend l'accord pour Fable
    contenu.append(partie("Tâches qui demandent Fable", "", d.fables.map((x) => decisionFableTache(ctx, x))));
  }
  contenu.append(partie("Demandes d'accord des agents", "Aucun agent n'attend votre accord",
    d.accords.map((x) => decisionAccordAgent(ctx, x))));
  contenu.append(partie("Outils à ouvrir à un agent", "Aucun agent n'attend un outil",
    d.outils.map((x) => decisionOutilAgent(ctx, x))));
  contenu.append(partie("Sessions cloud à créer", "Aucune session à créer", d.sessions.map((x) => decisionSession(ctx, x))));
  if (Array.isArray(ctx.etat.regles_projet)) contenu.append(reglesDuProjet(ctx));   // absent : le projet ne les gère pas
}
