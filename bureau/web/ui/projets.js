// Les projets du bureau : le projet choisi, l'adresse des requêtes et les liens de livrable.
// Les fonctions pures sont testées avec node ; le reste ne touche au navigateur que dans un try/catch.

import {lienSur} from "./actions.js";

const CLE = "myiafactory.projet";
let courant = null;   // null : un seul projet (ou sélecteur absent), les adresses restent telles quelles

// Ajoute ou remplace `projet` dans une adresse ; `id` nul ou vide : adresse inchangée.
export function avecProjet(url, id) {
  if (id === null || id === undefined || id === "") return url;
  const [chemin, requete = ""] = url.split("?");
  const reste = requete.split("&").filter((p) => p && p.split("=")[0] !== "projet");
  reste.push("projet=" + encodeURIComponent(id));
  return chemin + "?" + reste.join("&");
}

// Le projet mémorisé s'il existe encore dans la liste, sinon le premier ; null si la liste est vide.
export function projetInitial(liste, memorise) {
  if (!Array.isArray(liste) || !liste.length) return null;
  return liste.some((p) => p?.id === memorise) ? memorise : liste[0].id;
}

// La valeur de la dernière entrée de la liste déroulante : elle ouvre le formulaire au lieu de changer de projet.
export const ENTREE_NOUVEAU = "__nouveau_projet__";

// Les entrées de la liste déroulante : un choix par projet (avec sa pastille d'attente), puis « Nouveau projet… ».
export function optionsProjets(projets, id) {
  const options = (Array.isArray(projets) ? projets : []).map((p) => ({
    value: p.id, selected: p.id === id,
    libelle: (p.nom || p.id) + (p.attente > 0 ? ` (${p.attente})` : "") + (p.erreur ? " ⚠" : "")}));
  options.push({value: ENTREE_NOUVEAU, selected: false, libelle: "Nouveau projet…"});
  return options;
}

// Les livrables du projet et des fonctionnalités, le plus récent d'abord (sans date : à la fin).
// Un `lien` non sûr est écarté ; un `chemin` passe par /api/livrable.
export function livrables(etat, projet) {
  const sources = [];
  if (etat?.livrable) sources.push({l: etat.livrable, fonc: null});
  for (const f of etat?.fonctionnalites || []) if (f?.livrable) sources.push({l: f.livrable, fonc: f.id});
  const sortie = [];
  for (const {l, fonc} of sources) {
    if (typeof l.libelle !== "string" || !l.libelle) continue;
    let url = null;
    if (l.lien !== undefined && l.lien !== null) {
      if (!lienSur(l.lien)) continue;
      url = l.lien;
    } else if (typeof l.chemin === "string" && l.chemin) {
      url = avecProjet("/api/livrable" + (fonc ? "?fonctionnalite=" + encodeURIComponent(fonc) : ""), projet);
    } else continue;
    sortie.push({libelle: l.libelle, url, date: typeof l.date === "string" ? l.date : null});
  }
  return sortie.map((x, i) => [x, i])
    .sort(([a, i], [b, j]) => (b.date || "").localeCompare(a.date || "") || i - j).map(([x]) => x);
}

// --- Le projet courant de la page.
export function projetCourant() { return courant; }
export function definirProjet(id) { courant = id || null; }
export function urlProjet(url) { return avecProjet(url, courant); }

export function memorise() {
  try { return localStorage.getItem(CLE); } catch { return null; }
}
export function memoriser(id) {
  try { localStorage.setItem(CLE, id); } catch { /* stockage indisponible : le choix ne sera pas retenu */ }
}

// Lit la liste des projets. Rend {multi, projets, parents} ; en cas d'échec, un seul projet sans sélecteur.
export async function lireProjets(fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/projets", {cache: "no-store", signal: AbortSignal.timeout(15000)});
    if (!r.ok) return {multi: false, projets: [], parents: []};
    const j = await r.json();
    return {multi: j?.multi === true && Array.isArray(j.projets) && j.projets.length > 0,
            projets: Array.isArray(j?.projets) ? j.projets : [],
            parents: Array.isArray(j?.parents) ? j.parents.filter((x) => typeof x === "string") : []};
  } catch {
    return {multi: false, projets: [], parents: []};
  }
}
