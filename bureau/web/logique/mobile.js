// Le bureau sur un téléphone ou une tablette : fonctions pures (testables sans navigateur) pour détecter le
// mobile, pincer pour zoomer, déplacer la vue sans sortir du bâtiment, et préparer les photos avant l'envoi.

export const SEUIL_MOBILE = 768;        // px : sous cette largeur, c'est un mobile
export const COTE_MAX_IMAGE = 2048;     // px : le plus grand côté d'une photo envoyée
export const OCTETS_MAX_IMAGE = 5 * 1024 * 1024;   // la limite du serveur
export const ZOOM_MIN = 1, ZOOM_MAX = 4;

// Vrai sous 768 px de large, ou si le pointeur principal est grossier (un doigt).
export function estMobile(largeur, pointeurGrossier) {
  return pointeurGrossier === true || (Number.isFinite(largeur) && largeur < SEUIL_MOBILE);
}

const borner = (v, min, max) => Math.min(max, Math.max(min, v));

// Le zoom après un pincement : l'écart entre les deux doigts passe de `ecartDebut` à `ecartFin`. Borné ; un écart
// de départ nul ou illisible ne change rien.
export function zoomPincement(ecartDebut, ecartFin, zoom, min = ZOOM_MIN, max = ZOOM_MAX) {
  const courant = borner(Number.isFinite(zoom) ? zoom : min, min, max);
  if (!(ecartDebut > 0) || !(ecartFin > 0) || !Number.isFinite(ecartDebut) || !Number.isFinite(ecartFin)) return courant;
  return borner(courant * (ecartFin / ecartDebut), min, max);
}

// Le décalage de la vue (en unités de la scène) ramené dans le bâtiment : à zoom 1 rien ne bouge, plus on zoome plus
// la vue peut s'éloigner du centre, sans jamais montrer au-delà du cadrage d'ensemble. `demi` = [demi-largeur,
// demi-hauteur] du cadrage d'ensemble.
export function decalageBorne(decalage, zoom, demi) {
  const z = Math.max(1, Number.isFinite(zoom) ? zoom : 1);
  const marge = (d) => (Number.isFinite(d) ? d : 0) * (1 - 1 / z);
  const [mx, my] = [marge(demi?.[0]), marge(demi?.[1])];
  return [borner(Number(decalage?.[0]) || 0, -mx, mx) || 0, borner(Number(decalage?.[1]) || 0, -my, my) || 0];   // `|| 0` : jamais -0
}

// Les dimensions d'une photo réduite pour que son plus grand côté ne dépasse pas `coteMax` (jamais agrandie).
export function dimensionsReduites(largeur, hauteur, coteMax = COTE_MAX_IMAGE) {
  if (!(largeur > 0) || !(hauteur > 0)) return [1, 1];
  const echelle = Math.min(1, coteMax / Math.max(largeur, hauteur));
  return [Math.max(1, Math.round(largeur * echelle)), Math.max(1, Math.round(hauteur * echelle))];
}

// Le format envoyé : le PNG est gardé, tout le reste (HEIC, WebP, JPEG…) devient du JPEG.
export function formatEnvoye(type) {
  return String(type || "").toLowerCase() === "image/png" ? "image/png" : "image/jpeg";
}

// La qualité JPEG à demander selon le poids d'origine, pour rester sous 5 Mo une fois réduite à 2 048 px.
export function qualitePour(octets) {
  const o = Number(octets);
  if (!(o > 0) || o <= 2 * 1024 * 1024) return 0.92;
  if (o <= 5 * 1024 * 1024) return 0.85;
  if (o <= 12 * 1024 * 1024) return 0.8;
  if (o <= 30 * 1024 * 1024) return 0.72;
  return 0.65;
}

// Le nom du fichier envoyé : celui de la photo, sans son extension d'origine, avec celle du format envoyé (le serveur
// vérifie que l'extension et le type s'accordent), et sans rien qui ressemble à un chemin.
export function nomEnvoye(nom, type, maxi = 80) {
  const brut = String(nom ?? "");
  const point = brut.lastIndexOf(".");
  const base = (point >= 0 ? brut.slice(0, point) : brut)
    .replace(/[/\\:\u0000-\u001f]/g, "_").replace(/\.{2,}/g, "_").trim();
  const ext = formatEnvoye(type) === "image/png" ? ".png" : ".jpg";
  return (base || "photo").slice(0, Math.max(1, maxi - ext.length)) + ext;
}
