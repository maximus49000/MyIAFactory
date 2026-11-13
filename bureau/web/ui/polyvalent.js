// Les agents polyvalents (conception 2026-11-13-agents-polyvalents-design.md) : ni service, ni plafond de modèle à eux.
// Leur service est celui de la tâche qu'ils tiennent (le relevé le dit déjà sur l'agent), leur modèle celui de cette tâche,
// et les leçons se lisent par métier. Tout est pur ; un projet à l'ancienne passe par ces fonctions sans changer d'affichage.

// La première tâche en cours de l'agent, ou null.
export function tacheEnCours(etat, agent) {
  for (const id of agent?.taches || []) {
    const t = (etat?.taches || []).find((x) => x.id === id);
    if (t) return t;
  }
  return null;
}

// Le modèle sur lequel la tâche tourne : celui de son départ, sinon celui que son étape demande ; null si inconnu.
export function modeleDeLaTache(t) {
  return t?.modele_depart || t?.modele_necessaire?.modele || null;
}

// Les lignes « libellé / valeur » de la carte d'un agent pour son modèle : le plafond de sa fiche (agent à l'ancienne,
// jamais dépassé), ou sa tâche et le modèle de cette tâche (agent polyvalent).
export function lignesModele(etat, agent) {
  if (!agent?.polyvalent) return [["Plafond", agent?.modele || "?"]];
  const t = tacheEnCours(etat, agent);
  return [["Tâche", t ? t.titre : "aucune"], ["Modèle de la tâche", t ? (modeleDeLaTache(t) || "?") : "—"]];
}

// Ce que la liste des agents d'un service dit de chacun : son modèle (le plafond, ou celui de sa tâche) et son statut.
export function modeleAffiche(etat, agent) {
  if (!agent?.polyvalent) return agent?.modele || "?";
  return modeleDeLaTache(tacheEnCours(etat, agent)) || "—";
}

// Les métiers d'un service qui ont des leçons : [{role, lecons: [{id, texte, etat}]}]. Vide pour un projet à l'ancienne
// (ses leçons sont dans les fiches de ses agents).
export function leconsParMetier(etat, service) {
  return (etat?.metiers || []).filter((m) => m.service === service && (m.lecons || []).length)
    .map((m) => ({role: m.role, lecons: m.lecons}));
}
