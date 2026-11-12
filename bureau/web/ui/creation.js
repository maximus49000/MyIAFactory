// Le formulaire « Nouveau projet » : depuis la liste des projets, ou depuis une décision « cette demande n'est pas du
// genre du projet ». Le bureau crée le projet vide (le serveur fait tout) puis bascule dessus. Les fonctions pures
// (contrôle, corps de la requête, suite d'une création) sont testées avec node ; tout texte passe par textContent.

import {el} from "./dom.js";
import {memoriser} from "./projets.js";

const INTERDITS = /[<>:"/\\|?*\u0000-\u001f]/;
const RESERVES = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
export const LONGUEUR_NOM_MAX = 100;

const plein = (t) => typeof t === "string" && t.trim() !== "";

// Le message à dire pour un nom de projet refusé (même règle que installation/creation.py), ou null.
export function verifierNom(nom) {
  const n = typeof nom === "string" ? nom.trim() : "";
  if (!n) return "Donnez un nom au projet.";
  if (n.length > LONGUEUR_NOM_MAX) return `Le nom du projet est trop long (${LONGUEUR_NOM_MAX} caractères au plus).`;
  if (n === "." || n === ".." || n.endsWith(".")) return "Le nom du projet ne peut pas être « . », « .. » ni finir par un point.";
  if (INTERDITS.test(n)) return "Le nom du projet ne peut pas contenir les caractères < > : \" / \\ | ? *.";
  if (RESERVES.test(n.split(".")[0].trimEnd())) return `« ${n} » est un nom réservé par Windows : choisissez-en un autre.`;
  return null;
}

// Le message à dire avant d'envoyer, ou null.
export function verifierCreation(champs) {
  if (!plein(champs?.parent)) return "Indiquez le dossier où ranger le projet.";
  return verifierNom(champs.nom);
}

// Les mots interdits saisis (séparés par des virgules ou des retours à la ligne), sans vides ni doublons.
export function motsInterdits(texte) {
  const vus = new Set();
  for (const m of String(texte || "").split(/[,\n]/)) if (m.trim()) vus.add(m.trim());
  return [...vus];
}

// Le corps de `POST /api/projets/creer`. `contexte` : {origine (id du projet affiché), decision?: {id, fonctionnalite},
// genre?, genreDescription? (genre nouveau)}. La description n'est demandée que sans demande d'origine.
export function corpsCreation(champs, contexte = {}) {
  const corps = {parent: champs.parent.trim(), nom: champs.nom.trim(), mots_interdits: motsInterdits(champs.mots),
                 facturation: champs.facturation === true, github: champs.github === true};
  if (plein(contexte.origine)) corps.origine = contexte.origine;
  if (contexte.decision) {
    corps.decision = contexte.decision.id;
    corps.fonctionnalite = contexte.decision.fonctionnalite;
    if (plein(contexte.genre)) corps.genre = contexte.genre;
    if (plein(contexte.genreDescription)) corps.genre_description = contexte.genreDescription.trim();
  } else if (plein(champs.description)) {
    corps.description = champs.description.trim();
  }
  return corps;
}

// Envoie la création. Rend {ok, projet, message, github?, demande_deposee?} ; ne lève jamais.
export async function envoyerCreation(corps, fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/projets/creer", {
      method: "POST", headers: {"X-Bureau": "1", "Content-Type": "application/json"}, body: JSON.stringify(corps)});
    let j = null;
    try { j = await r.json(); } catch { /* corps illisible */ }
    if (r.ok && j?.ok) return j;
    return {ok: false, message: j?.erreur || `Le serveur a répondu ${r.status}.`};
  } catch {
    return {ok: false, message: "Le serveur du bureau est injoignable."};
  }
}

// Le message de la réponse doit-il être lu avant de changer de projet ? (GitHub non fait, demande non déplacée)
export function aLire(reponse) {
  return reponse?.demande_deposee === false || (reponse?.github && reponse.github !== "fait" && reponse.github !== "non demandé");
}

// Après une création réussie, la page bascule sur le nouveau projet : son choix est gardé, puis la page se recharge.
export function apresCreation(reponse, {garder = memoriser, recharger = () => location.reload()} = {}) {
  if (!reponse?.ok || !plein(reponse.projet)) return false;
  garder(reponse.projet);
  recharger();
  return true;
}

function champ(libelle, controle, aide) {
  const l = el("label", "creation-champ");
  l.append(el("span", "creation-libelle", libelle), controle);
  if (aide) l.append(el("span", "lecon-meta", aide));
  return l;
}

function saisie(type, valeur, extra = {}) {
  const i = document.createElement("input");
  i.type = type;
  if (type === "checkbox") i.checked = valeur === true; else i.value = valeur || "";
  for (const [k, v] of Object.entries(extra)) i[k] = v;
  return i;
}

// Ouvre le formulaire. `options` : {projets, parents, id (projet affiché), decision?, genre?, genreDescription?,
// nomPropose?}. Rend une fonction qui le ferme.
export function ouvrirCreation(options = {}) {
  const {projets = [], parents = [], id = null, decision = null} = options;
  const origine = projets.find((p) => p?.id === id) || {};
  const fond = el("div", "creation-fond");
  const fenetre = el("form", "creation");
  fenetre.setAttribute("role", "dialog");
  fenetre.setAttribute("aria-label", "Nouveau projet");
  fond.append(fenetre);
  const fermer = () => fond.remove();

  const parent = saisie("text", parents[0] || "", {placeholder: "Dossier où ranger le projet", maxLength: 500});
  parent.setAttribute("list", "creation-parents");
  parent.setAttribute("autocomplete", "off");
  const suggestions = document.createElement("datalist");
  suggestions.id = "creation-parents";
  for (const p of parents) suggestions.append(new Option(p, p));
  const nom = saisie("text", options.nomPropose || "", {placeholder: "Nom du projet (devient le nom du dossier)", maxLength: LONGUEUR_NOM_MAX});
  const mots = saisie("text", (origine.mots_interdits || []).join(", "), {placeholder: "Séparés par des virgules"});
  const facturation = saisie("checkbox", origine.facturation === true);
  const github = saisie("checkbox", false);
  const description = document.createElement("textarea");
  description.rows = 3;
  description.maxLength = 3500;
  description.placeholder = "Ce que fera ce projet, en une ou deux phrases";
  const erreur = el("p", "saisie-erreur", "");
  erreur.setAttribute("role", "alert");
  const envoi = el("button", "bouton", "Créer le projet");
  envoi.type = "submit";
  const annuler = el("button", "bouton secondaire", "Annuler");
  annuler.type = "button";
  annuler.addEventListener("click", fermer);

  fenetre.append(el("h2", "", "Nouveau projet"), champ("Dossier parent", parent), suggestions, champ("Nom du projet", nom),
                 champ("Mots interdits (le nom du projet est ajouté)", mots));
  const cocheFacturation = el("label", "creation-case");
  cocheFacturation.append(facturation, el("span", "", " Suivre les coûts de ce projet (un objectif de facturation)"));
  const cocheGithub = el("label", "creation-case");
  cocheGithub.append(github, el("span", "", " Créer aussi un dépôt GitHub privé"));
  fenetre.append(cocheFacturation, cocheGithub);
  if (!decision) {
    fenetre.append(champ("Description du projet", description, "Le genre vous sera proposé dans un instant."));
  } else {
    fenetre.append(el("p", "lecon-meta", "La demande « " + (decision.nom || decision.fonctionnalite) + " » ira dans ce nouveau projet."));
  }
  const rangee = el("div", "lecon-boutons");
  rangee.append(envoi, annuler);
  fenetre.append(erreur, rangee);

  fenetre.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const champs = {parent: parent.value, nom: nom.value, mots: mots.value, facturation: facturation.checked,
                    github: github.checked, description: description.value};
    const message = verifierCreation(champs);
    if (message) { erreur.textContent = message; return; }
    erreur.textContent = "";
    envoi.disabled = true;
    const reponse = await envoyerCreation(corpsCreation(champs, {origine: id, decision, genre: options.genre,
                                                                 genreDescription: options.genreDescription}));
    if (!reponse.ok) { erreur.textContent = reponse.message; envoi.disabled = false; return; }
    if (!aLire(reponse)) { apresCreation(reponse); return; }
    // Une chose à lire avant de changer de projet : GitHub non fait, ou la demande restée dans ce projet.
    fenetre.replaceChildren(el("h2", "", "Projet créé"), el("p", "", reponse.message));
    const suite = el("button", "bouton", "Ouvrir le nouveau projet");
    suite.type = "button";
    suite.addEventListener("click", () => apresCreation(reponse));
    fenetre.append(suite);
  });
  fond.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fermer(); });
  document.body.append(fond);
  nom.focus();
  return fermer;
}
