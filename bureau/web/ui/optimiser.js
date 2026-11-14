// « Optimiser la charge » : le bouton près de la jauge de charge ouvre « Ce qui charge l'ordinateur », les programmes
// qui prennent le plus le processeur (mesuré sur environ 1 s par le serveur) et la mémoire. Ce qui appartient à
// MyIAFactory porte son étiquette (agent, moteur, bureau, lancé par un agent). « Arrêter » demande toujours
// confirmation : rien n'est arrêté sans le clic de l'utilisateur. Un programme protégé n'a pas de bouton (et le serveur
// refuse de l'arrêter). Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";

const ENTETES = {"X-Bureau": "1", "Content-Type": "application/json"};

export function confirmationArret(p) {
  return `Arrêter ${p.nom} (pid ${p.pid}) ?`;
}

function nombre(x, chiffres = 1) {
  return typeof x === "number" && Number.isFinite(x) ? x.toLocaleString("fr-FR", {maximumFractionDigits: chiffres}) : "?";
}

// Les lignes à montrer : chacune a un pid entier et un nom ; le reste est complété.
export function lignesProcessus(donnees) {
  const liste = Array.isArray(donnees?.processus) ? donnees.processus : [];
  return liste.filter((p) => p && Number.isInteger(p.pid) && typeof p.nom === "string")
    .map((p) => ({pid: p.pid, nom: p.nom, cpu: p.cpu, memoire_mo: p.memoire_mo,
                  etiquette: typeof p.etiquette === "string" && p.etiquette ? p.etiquette : null,
                  protege: p.protege !== false}));
}

// Construit le panneau dans `conteneur`. `arreter(p, bouton)` et `actualiser(bouton)` : les gestes de l'utilisateur.
export function rendreProcessus(conteneur, donnees, {arreter, actualiser, erreur = null, enCours = false}) {
  conteneur.replaceChildren();
  conteneur.append(el("h2", "optimiser-titre", "Ce qui charge l'ordinateur"));
  const haut = el("div", "optimiser-haut");
  const boutonActualiser = el("button", "bouton-barre optimiser-actualiser", "Actualiser");
  boutonActualiser.type = "button";
  boutonActualiser.disabled = enCours;
  boutonActualiser.addEventListener("click", () => actualiser(boutonActualiser));
  haut.append(el("p", "optimiser-texte", "Les programmes qui prennent le plus le processeur (mesuré sur environ " +
    "1 seconde) et la mémoire. Arrêter un programme ferme son travail en cours."), boutonActualiser);
  conteneur.append(haut);
  if (enCours) {
    conteneur.append(el("p", "optimiser-texte", "Mesure en cours…"));
    return;
  }
  if (erreur) {
    conteneur.append(el("p", "optimiser-erreur", erreur));
    return;
  }
  const lignes = lignesProcessus(donnees);
  if (!lignes.length) {
    conteneur.append(el("p", "optimiser-texte", "Aucun programme à montrer."));
    return;
  }
  const table = el("table", "optimiser-table");
  const tete = el("tr", "");
  for (const t of ["Programme", "Processeur", "Mémoire", ""]) tete.append(el("th", "", t));
  table.append(tete);
  for (const p of lignes) {
    const tr = el("tr", "");
    const nom = el("td", "optimiser-nom");
    nom.append(el("span", "", p.nom), el("span", "optimiser-pid", ` pid ${p.pid}`));
    if (p.etiquette) nom.append(el("span", "optimiser-etiquette", p.etiquette));
    const geste = el("td", "optimiser-geste");
    if (p.protege) {
      geste.append(el("span", "optimiser-protege", "protégé"));
    } else {
      const b = el("button", "bouton-barre optimiser-arreter", "Arrêter");
      b.type = "button";
      b.addEventListener("click", () => arreter(p, b));
      geste.append(b);
    }
    tr.append(nom, el("td", "optimiser-nombre", `${nombre(p.cpu)} %`), el("td", "optimiser-nombre",
      `${nombre(p.memoire_mo, 0)} Mo`), geste);
    table.append(tr);
  }
  conteneur.append(table);
}

// La liste du serveur : `{donnees}` ou `{erreur}`. Ne lève jamais.
export async function lireProcessus(fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/processus", {cache: "no-store"});
    let corps = null;
    try { corps = await r.json(); } catch { /* corps illisible */ }
    if (r.ok) return {donnees: corps};
    return {erreur: corps?.erreur || `La liste des programmes est indisponible (le serveur a répondu ${r.status}).`};
  } catch {
    return {erreur: "La liste des programmes est indisponible : serveur injoignable."};
  }
}

// La demande d'arrêt (après confirmation). Rend `{ok, message}` ; ne lève jamais.
export async function demanderArret(pid, fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/processus/arreter", {method: "POST", headers: ENTETES, body: JSON.stringify({pid})});
    let corps = null;
    try { corps = await r.json(); } catch { /* corps illisible */ }
    if (r.ok) return {ok: true, message: corps?.message || `Programme ${pid} arrêté.`};
    return {ok: false, message: `Arrêt refusé : ${corps?.erreur || "le serveur a répondu " + r.status}`};
  } catch {
    return {ok: false, message: "Arrêt refusé : serveur injoignable"};
  }
}

// Le panneau, branché au bouton de la barre. `confirmer` : la confirmation (par défaut celle du navigateur).
export function brancherOptimiser(bouton, dire, {fetchFn = fetch, confirmer = (m) => globalThis.confirm(m)} = {}) {
  const fond = el("div", "optimiser");
  fond.hidden = true;
  const boite = el("div", "optimiser-boite");
  boite.setAttribute("role", "dialog");
  boite.setAttribute("aria-modal", "true");
  boite.setAttribute("aria-label", "Ce qui charge l'ordinateur");
  const contenu = el("div", "optimiser-contenu");
  const fermer = el("button", "bouton-barre optimiser-fermer", "Fermer");
  fermer.type = "button";
  boite.append(contenu, fermer);
  fond.append(boite);
  document.body.append(fond);
  const cacher = () => { fond.hidden = true; };
  fermer.addEventListener("click", cacher);
  fond.addEventListener("click", (ev) => { if (ev.target === fond) cacher(); });

  let dernieres = null;
  async function actualiser() {
    rendreProcessus(contenu, dernieres, {arreter, actualiser, enCours: true});
    const r = await lireProcessus(fetchFn);
    if (r.donnees) dernieres = r.donnees;
    rendreProcessus(contenu, dernieres, {arreter, actualiser, erreur: r.erreur || null});
  }

  async function arreter(p, b) {
    if (!confirmer(confirmationArret(p))) return;
    if (b) b.disabled = true;
    const r = await demanderArret(p.pid, fetchFn);
    dire(r.message, r.ok);
    await actualiser();
  }

  async function ouvrir() {
    fond.hidden = false;
    await actualiser();
  }
  bouton.addEventListener("click", ouvrir);
  return {fond, contenu, ouvrir, actualiser, arreter};
}
