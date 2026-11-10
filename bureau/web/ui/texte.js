// Petites fonctions de texte, pures (sans DOM), testées avec node.

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

// L'infobulle de la barre de charge.
export function libelleCharge(c) {
  if (!c || !c.disponible) return "Mesure indisponible";
  return `Charge ${Math.round(c.charge)} % · processeur ${Math.round(c.cpu)} %, mémoire ${Math.round(c.memoire)} %`;
}

// Les identifiants des tâches qui passent le filtre : en cours (= `active`) et/ou d'un type donné.
export function filtrer(taches, {enCours = false, type = null} = {}) {
  const ids = new Set();
  for (const t of taches || []) {
    if (enCours && !t.active) continue;
    if (type && t.type !== type) continue;
    ids.add(t.id);
  }
  return ids;
}

// Les vignettes d'une tâche : l'adresse porte la date de mise à jour, pour que le cache suive une image refaite.
export function imagesUrl(tache) {
  const maj = encodeURIComponent(tache?.maj ?? "");
  return (tache?.images || []).map((i) => ({
    url: `/api/image?chemin=${encodeURIComponent(i.chemin)}&t=${maj}`,
    legende: i.legende || "",
  }));
}

// Une date du relevé en clair (heure locale) ; un texte illisible est rendu tel quel.
export function dateFr(date) {
  if (typeof date !== "string" || !date) return "";
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
