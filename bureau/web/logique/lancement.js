// Le premier lancement du bureau : fonctions pures (testables sans navigateur) pour décider s'il faut proposer
// l'animation, dérouler sa ligne du temps et faire tomber les lettres de la fenêtre factice.

// Durées (s). Après les lettres, la fenêtre attend que le bureau soit prêt, jamais au-delà du plafond (compté depuis
// « Voir »).
export const DUREES = Object.freeze({reflexion: 2.2, frappe: 2.0, pause: 0.9, lettres: 2.6, fenetre: 1.2, plafond: 10});
export const PESANTEUR = 1400;   // px/s²
export const SIGNES = "abcdefghijklmnopqrstuvwxyz0123456789{}[]()<>=;:";
const RETARD_MAX = 2.1;          // s : la dernière lettre part au plus tard 2,1 s après le début de la chute

// Vrai seulement si le serveur dit clairement « pas encore vu » ; toute autre réponse (erreur, panne) vaut « vu ».
export function doitProposer(reponse) {
  return reponse !== null && typeof reponse === "object" && reponse.vu === false;
}

const borner = (v, min, max) => Math.min(max, Math.max(min, v));
const fini = (v) => (Number.isFinite(v) ? v : 0);

// La phase à l'instant `t` (s depuis « Voir ») et l'avancement dans cette phase (0 → 1). `pret` : l'instant (s) où le
// bureau est devenu prêt, ou `null` s'il ne l'est pas encore.
export function phase(t, pret) {
  const d = DUREES;
  t = Math.max(0, fini(t));
  const etapes = [["reflexion", d.reflexion], ["frappe", d.frappe], ["pause", d.pause], ["lettres", d.lettres]];
  let debut = 0;
  for (const [nom, duree] of etapes) {
    if (t < debut + duree) return {nom, avance: (t - debut) / duree};
    debut += duree;
  }
  const finLettres = debut;
  const pretA = Number.isFinite(pret) ? Math.min(pret, d.plafond) : d.plafond;
  const chute = Math.max(finLettres, pretA);
  if (t < chute) return {nom: "attente", avance: (t - finLettres) / (chute - finLettres)};
  if (t < chute + d.fenetre) return {nom: "fenetre", avance: (t - chute) / d.fenetre};
  return {nom: "fin", avance: 1};
}

// Le délai de départ (s) de chaque lettre `{x, y}` : de gauche à droite, du haut vers le bas, un peu au hasard.
export function departs(lettres, largeur, hauteur, alea = Math.random) {
  const w = largeur > 0 ? largeur : 1, h = hauteur > 0 ? hauteur : 1;
  return lettres.map((l) => borner(0.6 * fini(l.x) / w + 1.2 * alea() + 0.3 * (1 - fini(l.y) / h), 0, RETARD_MAX));
}

// Un pas de chute : une nouvelle lettre, la vitesse `v` (px/s) augmentée par la pesanteur.
export function tomber(lettre, dt) {
  const v = fini(lettre.v) + PESANTEUR * dt;
  return {...lettre, v, y: fini(lettre.y) + v * dt};
}

// Un signe de code tiré au hasard, pour les lettres qui se transforment en tombant.
export function signeDeCode(alea = Math.random) {
  return SIGNES[Math.min(SIGNES.length - 1, Math.floor(alea() * SIGNES.length))];
}

// Le début du message déjà tapé, selon l'avancement de la frappe.
export function texteTape(message, avance) {
  const m = String(message ?? "");
  return m.slice(0, Math.round(borner(fini(avance), 0, 1) * m.length));
}
