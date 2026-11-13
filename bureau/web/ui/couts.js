// Le coût des tâches : celui de chaque tâche finie (relu au plus toutes les 30 s, une seule lecture à la fois) et celui
// d'une tâche en cours (`travail.cout`, servi avec l'état et recalculé à chaque relecture : il évolue).

import {urlProjet} from "./projets.js";
import {euros} from "./texte.js";

const DUREE_MS = 30000;
let memoire = {t: 0, promesse: null};

export async function coutsDesTaches(fetchFn = fetch, maintenant = Date.now()) {
  if (memoire.promesse && maintenant - memoire.t < DUREE_MS) return memoire.promesse;
  memoire = {t: maintenant, promesse: (async () => {
    try {
      const r = await fetchFn(urlProjet("/api/couts?taches=tout"), {cache: "no-store"});
      const d = await r.json();
      return d?.disponible ? d.taches || {} : null;
    } catch { return null; }
  })()};
  return memoire.promesse;
}

export function oublierCouts() { memoire = {t: 0, promesse: null}; }

// Le libellé du coût d'une tâche. `couts` : la table servie (ou null si indisponible). Pur.
export function libelleCout(t, couts) {
  const enCours = t?.travail?.cout;
  if (enCours && typeof enCours.total === "number") {
    return `${euros(enCours.total)} jusqu'ici${enCours.sans_prix ? " + prix inconnu" : ""} (tâche en cours : le coût évolue)`;
  }
  const c = couts?.[t?.id];
  if (c && typeof c.total === "number") return euros(c.total) + (c.sans_prix ? " + prix inconnu" : "");
  if (couts === null) return "indisponible";
  return t?.colonne === "fait" ? "aucune consommation notée" : "pas encore de consommation";
}

// Le temps d'une tâche, en minutes : de son départ à sa fin (`debut`, `fin` servis par le relevé) ; en cours, depuis le
// départ de son agent jusqu'à maintenant. `null` si on ne le sait pas. Pur.
export function minutesDeTache(t, maintenant = new Date()) {
  const ms = (x) => (typeof x === "string" && x ? new Date(x).getTime() : NaN);
  const debut = ms(t?.debut), fin = ms(t?.fin);
  if (Number.isFinite(debut) && Number.isFinite(fin) && fin >= debut) return (fin - debut) / 60000;
  if (t?.colonne === "fait") return null;
  const depart = Number.isFinite(ms(t?.travail?.depuis)) ? ms(t.travail.depuis) : debut;
  return Number.isFinite(depart) ? Math.max(0, (maintenant.getTime() - depart) / 60000) : null;
}

// « 12 min », « 1 h 05 », « 2 j 3 h » ; en cours : « … jusqu'ici ». `null` sans durée connue. Pur.
export function libelleDuree(t, maintenant = new Date()) {
  const m = minutesDeTache(t, maintenant);
  if (m === null) return null;
  const texte = m < 1 ? "moins d'une minute" : m < 60 ? `${Math.floor(m)} min`
    : m < 48 * 60 ? `${Math.floor(m / 60)} h ${String(Math.floor(m % 60)).padStart(2, "0")}`
    : `${Math.floor(m / 1440)} j ${Math.floor((m % 1440) / 60)} h`;
  return t?.colonne === "fait" ? texte : texte + " jusqu'ici";
}

// Le total d'une liste de tâches : `{euros, sans_prix, minutes, inconnues}` (une tâche sans durée connue est comptée
// dans `inconnues`). `couts` : la table servie, ou null. Pur.
export function totalDesTaches(taches, couts, maintenant = new Date()) {
  let euros = 0, sansPrix = 0, minutes = 0, inconnues = 0;
  for (const t of taches) {
    const c = t?.travail?.cout || couts?.[t?.id];
    if (c && typeof c.total === "number") { euros += c.total; sansPrix += c.sans_prix || 0; }
    const m = minutesDeTache(t, maintenant);
    if (m === null) inconnues += 1; else minutes += m;
  }
  return {euros, sans_prix: sansPrix, minutes, inconnues};
}

// « Total : ≈ 4,20 € · 3 h 10 » (+ « dont 2 sans durée connue »). Pur.
export function libelleTotal(x) {
  const m = x.minutes;
  const temps = m < 60 ? `${Math.floor(m)} min` : `${Math.floor(m / 60)} h ${String(Math.floor(m % 60)).padStart(2, "0")}`;
  return `Total : ${euros(x.euros)}${x.sans_prix ? " + prix inconnu" : ""} · ${temps}`
    + (x.inconnues ? ` (dont ${x.inconnues} sans durée connue)` : "");
}
