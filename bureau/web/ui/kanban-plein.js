// Le Kanban en plein écran : un clic sur le tableau de la scène l'ouvre, lisible, une colonne par colonne du relevé.
// `colonnesKanban` est pure et testée avec node. Tout texte venu du relevé passe par textContent.

import {el} from "./dom.js";
import {auTravail, ilYA, tronquer} from "./texte.js";

// Ce que la colonne dit de son genre (sous son nom) : le genre du workflow dont elle est une étape, ou rien.
export function etiquetteColonne(col) {
  if (col?.validation === true) return "Validation du Directeur";   // l'élément s'y arrête jusqu'à sa réponse
  return typeof col?.genre === "string" ? col.genre : "";
}

// Les colonnes du relevé avec leurs tâches (les plus récentes en tête), et la file d'attente à part.
export function colonnesKanban(etat) {
  const prenoms = new Map((etat?.agents || []).map((a) => [a.id, a.prenom]));
  const colonnes = (etat?.colonnes || []).map((c) => ({id: c.id, nom: c.nom, terminee: c.terminee === true,
    genre: c.genre || null, workflow: c.workflow || null, validation: c.validation === true, taches: []}));
  const parId = new Map(colonnes.map((c) => [c.id, c]));
  for (const t of etat?.taches || []) {
    const c = parId.get(t.colonne);
    if (!c || t.postit === false) continue;   // sans post-it (le chef qui orchestre) : pas sur le Kanban, comme dans la scène
    c.taches.push({id: t.id, titre: t.titre, prenom: t.agent ? prenoms.get(t.agent) || t.agent : null,
                   etape: t.etape || "", maj: t.maj || null, active: t.active === true, bloquee: t.bloquee || null,
                   attente: t.attente || null, travail: t.travail || null});
  }
  for (const c of colonnes) c.taches.sort((a, b) => String(b.maj || "").localeCompare(String(a.maj || "")));
  colonnes.file = {elements: [...(etat?.file?.visibles || []), ...(etat?.file?.suite || [])]
    .map((q) => ({id: q.id, titre: q.titre})), reste: etat?.file?.reste || 0};
  return colonnes;
}

// Ouvre le Kanban en plein écran. `ouvrirTache(id)` : le panneau d'une tâche (la vue se ferme). Échap ferme.
export function ouvrirKanban(etat, ouvrirTache) {
  const colonnes = colonnesKanban(etat);
  const fond = el("div", "kanban-plein");
  fond.setAttribute("role", "dialog");
  fond.setAttribute("aria-modal", "true");
  fond.setAttribute("aria-label", "Le Kanban");
  const tete = el("div", "kanban-plein-tete");
  tete.append(el("h2", "", "Le Kanban"));
  const fermer = el("button", "kanban-plein-fermer", "×");
  fermer.type = "button";
  fermer.setAttribute("aria-label", "Fermer");
  tete.append(fermer);
  const grille = el("div", "kanban-plein-colonnes");
  const clore = () => { document.removeEventListener("keydown", clavier, true); fond.remove(); };
  const clavier = (ev) => { if (ev.key === "Escape") { ev.stopPropagation(); ev.preventDefault(); clore(); } };
  if (colonnes.file.elements.length) {
    const c = el("section", "kanban-plein-colonne file");
    c.append(el("h3", "", `File d'attente (${colonnes.file.elements.length + colonnes.file.reste})`));
    for (const q of colonnes.file.elements.slice(0, 50)) c.append(el("div", "kanban-carte pale", tronquer(q.titre, 90)));
    grille.append(c);
  }
  for (const col of colonnes) {
    const c = el("section", "kanban-plein-colonne" + (col.terminee ? " terminee" : ""));
    c.append(el("h3", "", `${col.nom} (${col.taches.length})`));
    if (etiquetteColonne(col)) c.append(el("p", "kanban-plein-genre", etiquetteColonne(col)));
    for (const t of col.taches.slice(0, 200)) {
      const carte = el("button", "kanban-carte" + (t.bloquee ? " bloquee" : "") + (t.active ? "" : " inactive"));
      carte.type = "button";
      carte.append(el("strong", "", tronquer(t.titre, 120)));
      const meta = [t.prenom, t.etape, t.maj ? ilYA(t.maj) : null].filter(Boolean).join(" · ");
      if (meta) carte.append(el("span", "kanban-carte-meta", meta));
      if (t.attente) carte.append(el("span", "kanban-carte-attente", t.attente));
      const travail = auTravail(t.travail);
      if (travail) {
        carte.append(el("span", "kanban-carte-travail", "Au travail depuis " + travail.depuis
          + (travail.action ? " · " + travail.action : "")));
      }
      if (t.bloquee) carte.append(el("span", "kanban-carte-bloquee", "Bloquée : " + tronquer(t.bloquee, 90)));
      carte.addEventListener("click", () => { clore(); ouvrirTache(t.id); });
      c.append(carte);
    }
    if (!col.taches.length) c.append(el("p", "vide", "Aucune tâche"));
    grille.append(c);
  }
  fermer.addEventListener("click", clore);
  fond.addEventListener("click", (ev) => { if (ev.target === fond) clore(); });
  document.addEventListener("keydown", clavier, true);
  fond.append(tete, grille);
  document.body.append(fond);
  fermer.focus();
}
