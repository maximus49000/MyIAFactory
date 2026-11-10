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
