// Petites fonctions de texte, pures (sans DOM), testées avec node.

import {urlProjet} from "./projets.js";

// Coupe un texte à n caractères et ajoute « … » s'il était plus long. Accepte null.
export function tronquer(texte, n) {
  if (texte === null || texte === undefined) return "";
  const t = String(texte);
  return t.length > n ? t.slice(0, n) + "…" : t;
}

// Même format que côté serveur : « 45 min » sous 60 min, « 2 h » sous 48 h, « 3 j » au-delà (arrondi inférieur).
export function dureeEnClair(minutes) {
  if (minutes < 60) return `${Math.floor(minutes)} min`;
  if (minutes < 48 * 60) return `${Math.floor(minutes / 60)} h`;
  return `${Math.floor(minutes / 1440)} j`;
}

function minutesDepuis(date, maintenant) {
  if (typeof date !== "string" || !date) return null;
  const t = new Date(date).getTime();     // une date sans fuseau est lue comme une heure locale
  if (Number.isNaN(t)) return null;
  return Math.max(0, (maintenant.getTime() - t) / 60000);
}

// « il y a 2 h » ; « inconnue » si la date manque ou est illisible.
export function ilYA(date, maintenant = new Date()) {
  const m = minutesDepuis(date, maintenant);
  if (m === null) return "inconnue";
  if (m < 1) return "à l'instant";
  return "il y a " + dureeEnClair(m);
}

// Le voyant de la factory : {libelle, ton} avec ton parmi ok | pause | alerte.
export function voyant(factory, erreur, maintenant = new Date()) {
  if (erreur) return {libelle: "Relevé indisponible", ton: "alerte"};
  if (!factory) return {libelle: "Relevé indisponible", ton: "alerte"};
  if (factory.etat === "en pause") return {libelle: "En pause", ton: "pause"};
  if (factory.etat === "en marche") {
    if (factory.inactive) {
      const m = minutesDepuis(factory.derniere_activite, maintenant);
      return {libelle: m === null ? "En marche, sans activité" : `En marche, sans activité depuis ${dureeEnClair(m)}`, ton: "alerte"};
    }
    return {libelle: "En marche", ton: "ok"};
  }
  return {libelle: "Relevé indisponible", ton: "alerte"};
}

// Ce qui retient le travail, dit par le moteur : la pause d'une installation d'outil (pour tous les projets du bureau),
// puis les tâches prêtes que la charge retient. Rend une liste de {ton, texte} (vide si rien ne retient rien).
export function retenues(etat) {
  const lignes = [];
  const pause = etat?.pause_installation;
  if (pause && typeof pause.texte === "string" && pause.texte.trim()) lignes.push({ton: "pause", texte: pause.texte});
  const attente = etat?.attente_charge;
  if (attente && typeof attente.texte === "string" && attente.texte.trim()) lignes.push({ton: "attente", texte: attente.texte});
  return lignes;
}

// L'infobulle de la barre de charge.
export function libelleCharge(c, agentsLocauxMax) {
  const limite = Number.isInteger(agentsLocauxMax) && agentsLocauxMax >= 1 ? ` · ${agentsLocauxMax} agents locaux au plus` : "";
  if (!c || !c.disponible) return "Mesure indisponible" + limite;
  return `Charge ${Math.round(c.charge)} % · processeur ${Math.round(c.cpu)} %, mémoire ${Math.round(c.memoire)} %` + limite;
}

// Les identifiants des colonnes terminées (`terminee: true`).
export function colonnesTerminees(colonnes) {
  return new Set((colonnes || []).filter((c) => c && c.terminee === true).map((c) => c.id));
}

// Les identifiants des tâches qui passent le filtre : en cours (= `active`), non terminées (= pas dans une colonne
// terminée, donc aussi celles en attente ou bloquées) et/ou d'un type donné.
export function filtrer(taches, {enCours = false, nonTerminees = false, type = null} = {}, colonnes = []) {
  const finies = nonTerminees ? colonnesTerminees(colonnes) : new Set();
  const ids = new Set();
  for (const t of taches || []) {
    if (enCours && !t.active) continue;
    if (finies.has(t.colonne)) continue;
    if (type && t.type !== type) continue;
    ids.add(t.id);
  }
  return ids;
}

// Les filtres d'état de la vue liste, dans l'ordre : « Non terminées » n'existe que si une colonne est terminée.
export function filtresEtat(etat) {
  const filtres = [{id: "toutes", libelle: "Toutes"}, {id: "en_cours", libelle: "En cours"}];
  if (colonnesTerminees(etat?.colonnes).size > 0) filtres.unshift({id: "non_terminees", libelle: "Non terminées"});
  return filtres;
}

// Le filtre d'état réellement appliqué : le choix de l'utilisateur s'il est encore possible,
// sinon « Non terminées » quand une colonne est terminée, sinon « Toutes ».
export function filtreEtatEffectif(etat, choix) {
  const filtres = filtresEtat(etat);
  if (choix && filtres.some((f) => f.id === choix)) return choix;
  return filtres[0].id;
}

// Le filtre de la vue liste ({etat: choix ou null, type}) prêt pour `filtrer`.
export function filtreDeListe(etat, filtreListe) {
  const choix = filtreEtatEffectif(etat, filtreListe?.etat);
  return {enCours: choix === "en_cours", nonTerminees: choix === "non_terminees", type: filtreListe?.type ?? null};
}

// Les vignettes d'une tâche : l'adresse porte la date de mise à jour, pour que le cache suive une image refaite.
export function imagesUrl(tache) {
  const maj = encodeURIComponent(tache?.maj ?? "");
  return (tache?.images || []).map((i) => ({
    url: urlProjet(`/api/image?chemin=${encodeURIComponent(i.chemin)}&t=${maj}`),
    legende: i.legende || "",
  }));
}

// Une date du relevé en clair (heure locale) ; un texte illisible est rendu tel quel.
export function dateFr(date) {
  if (typeof date !== "string" || !date) return "";
  const jour = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);  // une date sans heure : le jour dit, sans fuseau
  if (jour) return new Date(+jour[1], +jour[2] - 1, +jour[3]).toLocaleDateString("fr-FR", {day: "numeric", month: "short"});
  const t = new Date(date);
  if (Number.isNaN(t.getTime())) return date;
  return t.toLocaleString("fr-FR", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"});
}

// Les vignettes ne se montrent que si le projet déclare des racines d'images (sinon les adresses seraient cassées).
export function imagesVisibles(etat, tache) {
  return etat?.images_ok === true && (tache?.images || []).length > 0;
}

// Les notes libres d'une tâche : seules celles qui ont un libellé et un texte (le texte garde ses retours à la ligne).
export function notesValides(tache) {
  const l = Array.isArray(tache?.notes) ? tache.notes : [];
  return l.filter((n) => n && typeof n.libelle === "string" && n.libelle
    && typeof n.texte === "string" && n.texte).map((n) => ({libelle: n.libelle, texte: n.texte}));
}

// La vue liste est un ajout de la version 2 : un relevé en version 1 garde le bureau d'avant, sans bouton.
export function listeDisponible(etat) {
  return (etat?.version ?? 1) >= 2;
}

// Le panneau Direction d'un relevé en version 1 : la phrase d'avant (compteur de décisions) et sa note.
export function phrasesDirectionV1(etat) {
  const n = etat?.decisions || 0;
  return [
    {classe: "decisions", texte: n === 0 ? "Aucune décision n'attend le Directeur."
      : n === 1 ? "1 décision attend le Directeur." : `${n} décisions attendent le Directeur.`},
    {classe: "note", texte: "La liste détaillée des décisions arrivera avec le projet 2."},
  ];
}

// Les éléments de la file, dans l'ordre : les visibles puis la suite. Un identifiant n'apparaît qu'une fois ;
// sans titre, l'identifiant en tient lieu.
export function elementsDeFile(file) {
  const sortie = [];
  const vus = new Set();
  for (const [liste, visible] of [[file?.visibles, true], [file?.suite, false]]) {
    if (!Array.isArray(liste)) continue;
    for (const q of liste) {
      if (!q || typeof q.id !== "string" || !q.id || vus.has(q.id)) continue;
      vus.add(q.id);
      sortie.push({id: q.id, titre: typeof q.titre === "string" && q.titre ? q.titre : q.id, visible});
    }
  }
  return sortie;
}

// Le nombre d'éléments au-delà des visibles : le plus grand de `reste` et de la longueur de la suite.
export function resteApresVisibles(file) {
  const reste = Number(file?.reste);
  const suite = Array.isArray(file?.suite) ? file.suite.length : 0;
  return Math.max(Number.isFinite(reste) ? reste : 0, suite);
}

// Le « + n » de la file ouvre le panneau « File » seulement s'il y a des éléments au-delà des visibles.
export function fileDepliable(file) {
  return resteApresVisibles(file) > 0;
}

// Le nombre d'éléments de la file que le panneau ne peut pas lister (la suite fournie est plus courte que le reste).
export function resteNonListe(file) {
  const suite = Array.isArray(file?.suite) ? file.suite.length : 0;
  return Math.max(0, resteApresVisibles(file) - suite);
}

// Un montant en euros, toujours précédé de « ≈ » (jamais une facture) ; « — » quand il manque.
export function euros(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return "≈ " + v.toFixed(2).replace(".", ",") + " €";
}

// Un nombre de tokens en clair : « 850 », « 12,4 k », « 1,3 M ».
export function tokens(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".", ",") + " M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(".", ",") + " k";
  return String(Math.round(n));
}

export const PERIODES = ["aujourdhui", "7j", "30j"];
export const PERIODE_DEFAUT = "7j";

export function libellePeriode(p) {
  return {aujourdhui: "Aujourd'hui", "7j": "7 jours", "30j": "30 jours"}[p] || "7 jours";
}
