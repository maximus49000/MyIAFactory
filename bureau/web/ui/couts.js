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
