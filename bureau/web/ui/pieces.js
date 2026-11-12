// Les fichiers joints à un échange (discussion d'une fonctionnalité, « + Nouvelle fonctionnalité ») : la liste blanche des
// types et les plafonds, les mêmes que ceux du bureau (`bureau/fichiers_joints.py`, qui a le dernier mot : il contrôle aussi
// le début du contenu). Fonctions pures, testées avec node. Un fichier joint n'est jamais exécuté ni décompressé par la page.

export const MAX_FICHIERS = 8;                      // par envoi, tous types confondus
export const MAX_IMAGES_FIXES = 4;                  // dont 4 images PNG ou JPEG (photos comprises) au plus
export const MAX_OCTETS_IMAGE = 5 * 1024 * 1024;    // une image fixe, une fois réduite par la page
export const MAX_OCTETS_FICHIER = 25 * 1024 * 1024; // tout autre fichier
export const MAX_OCTETS_TOTAL = 40 * 1024 * 1024;   // la somme d'un envoi
export const MAX_OCTETS_PHOTO_CHOISIE = 60 * 1024 * 1024;   // avant réduction : au-delà, la page ne tiendrait pas en mémoire
export const MAX_NOM = 80;

// extension -> [type envoyé, catégorie]
export const TYPES = {
  ".png": ["image/png", "image"], ".jpg": ["image/jpeg", "image"], ".jpeg": ["image/jpeg", "image"],
  ".webp": ["image/webp", "image"], ".gif": ["image/gif", "animation"],
  ".mp4": ["video/mp4", "video"], ".webm": ["video/webm", "video"],
  ".mp3": ["audio/mpeg", "son"], ".ogg": ["audio/ogg", "son"], ".wav": ["audio/wav", "son"], ".flac": ["audio/flac", "son"],
  ".pdf": ["application/pdf", "document"], ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document"],
  ".xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document"],
  ".pptx": ["application/vnd.openxmlformats-officedocument.presentationml.presentation", "document"],
  ".md": ["text/markdown", "texte"], ".txt": ["text/plain", "texte"], ".csv": ["text/csv", "texte"], ".json": ["application/json", "texte"],
  ".zip": ["application/zip", "archive"],
};
// Une photo (au choix : HEIC, WebP, très grande définition…) est réduite et réencodée dans la page avant l'envoi.
const TYPES_PHOTO = ["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "image/avif", "image/bmp"];
const EXTENSIONS_PHOTO = /\.(png|jpe?g|webp|heic|heif|avif|bmp)$/i;
// Ce que propose le sélecteur de fichiers : toutes les images, les vidéos, les sons et les extensions de la liste blanche.
export const ACCEPT = ["image/*", ...Object.keys(TYPES)].join(",");
export const LISTE_BLANCHE = "images (png, jpg, gif, webp), vidéos (mp4, webm), sons (mp3, ogg, wav, flac), documents (pdf, md, txt, csv, json, docx, xlsx, pptx) et archives (zip)";

export function extension(nom) {
  const n = String(nom ?? "").split(/[\\/]/).pop();
  const i = n.lastIndexOf(".");
  return i > 0 ? n.slice(i).toLowerCase() : "";
}
export const categorie = (nom) => TYPES[extension(nom)]?.[1] ?? null;
export const typeEnvoye = (nom) => TYPES[extension(nom)]?.[0] ?? null;

// Un fichier choisi est une photo à réduire : une image fixe (le type, ou à défaut l'extension : certains téléphones ne
// donnent pas de type aux HEIC). Un GIF n'en est pas une : il part tel quel, animé.
export function estPhoto(f) {
  const type = String(f?.type ?? "").toLowerCase();
  const nom = String(f?.name ?? f?.nom ?? "");
  if (extension(nom) === ".gif" || type === "image/gif") return false;
  return TYPES_PHOTO.includes(type) || (type === "" && EXTENSIONS_PHOTO.test(nom));
}

export const nomValide = (nom) => typeof nom === "string" && nom.trim() !== "" && nom.length <= MAX_NOM && !nom.includes("..")
  && !/[\u0000-\u001f\u007f/\\:*?"<>|]/.test(nom);

const court = (nom) => (nom.length > 40 ? nom.slice(0, 39) + "…" : nom);
const mo = (octets) => `${Math.round(octets / 1048576)} Mo`;

// Le contrôle à la sélection. `deja` : les fichiers déjà prêts du brouillon (`{nom, taille, categorie}`), `choisis` : les
// fichiers qu'on vient de choisir (`{name, type, size}`). Rend le message d'erreur (français), ou null.
export function verifierChoix(deja, choisis) {
  const prets = Array.from(deja || []), liste = Array.from(choisis || []);
  if (prets.length + liste.length > MAX_FICHIERS) return `${MAX_FICHIERS} fichiers au plus par message.`;
  let total = prets.reduce((s, x) => s + (x.taille || 0), 0);
  let images = prets.filter((x) => x.categorie === "image" && /\.(png|jpe?g)$/i.test(x.nom)).length;
  for (const f of liste) {
    const nom = String(f?.name ?? "");
    const taille = Number(f?.size);
    if (estPhoto(f)) {
      if (!(taille <= MAX_OCTETS_PHOTO_CHOISIE)) return `« ${court(nom)} » est trop lourde pour être préparée (${mo(taille)}).`;
      images += 1;
      total += Math.min(taille, MAX_OCTETS_IMAGE);
      continue;
    }
    if (!(extension(nom) in TYPES)) return `« ${court(nom)} » : ce type de fichier n'est pas accepté. Sont acceptés : ${LISTE_BLANCHE}.`;
    if (!nomValide(nom)) return `Le nom de « ${court(nom)} » n'est pas valide (${MAX_NOM} caractères au plus, sans / \\ : * ? " < > |).`;
    if (!(taille > 0)) return `« ${court(nom)} » est vide.`;
    if (!(taille <= MAX_OCTETS_FICHIER)) return `« ${court(nom)} » dépasse ${mo(MAX_OCTETS_FICHIER)}.`;
    if (/\.(png|jpe?g)$/i.test(nom)) images += 1;
    total += taille;
  }
  if (images > MAX_IMAGES_FIXES) return `${MAX_IMAGES_FIXES} images PNG ou JPEG au plus par message.`;
  if (total > MAX_OCTETS_TOTAL) return `Les fichiers dépassent ${mo(MAX_OCTETS_TOTAL)} en tout.`;
  return null;
}

// La taille décodée d'un texte base64.
export function tailleBase64(donnees) {
  const s = String(donnees ?? "");
  return Math.floor(s.length * 3 / 4) - (s.endsWith("==") ? 2 : s.endsWith("=") ? 1 : 0);
}

// « 12,3 Mo », « 850 Ko », « 512 octets » ; « » pour une taille inconnue.
export function tailleLisible(octets) {
  if (typeof octets !== "number" || !Number.isFinite(octets) || octets < 0) return "";
  if (octets < 1024) return `${octets} octet${octets > 1 ? "s" : ""}`;
  const [n, unite] = octets < 1024 * 1024 ? [octets / 1024, "Ko"] : octets < 1024 ** 3 ? [octets / 1024 ** 2, "Mo"] : [octets / 1024 ** 3, "Go"];
  return `${(n < 10 ? n.toFixed(1) : Math.round(n).toString()).replace(".", ",")} ${unite}`;
}

// Le badge qui tient lieu d'icône : l'extension en majuscules (« ZIP », « PDF »).
export const badge = (nom) => (extension(nom).slice(1) || "fichier").toUpperCase().slice(0, 5);

// Comment un fichier joint d'un message se montre : `vignette` (image animée ou WebP, visionneuse au clic), `video`, `son`,
// `markdown` (lu en ligne), sinon `fichier` (nom, taille, « Télécharger »).
export function affichage(nom) {
  const c = categorie(nom);
  if (c === "animation" || extension(nom) === ".webp") return "vignette";
  if (c === "video") return "video";
  if (c === "son") return "son";
  if (extension(nom) === ".md") return "markdown";
  return "fichier";
}

// Les fichiers d'un message qui ne sont pas déjà montrés comme images (les PNG et JPEG vont dans `images`).
export function fichiersAMontrer(m) {
  const dejaVus = new Set((m?.images || []).map((i) => (typeof i === "string" ? i : i?.chemin)));
  return (Array.isArray(m?.fichiers) ? m.fichiers : [])
    .filter((x) => x && typeof x.chemin === "string" && x.chemin && !dejaVus.has(x.chemin))
    .map((x) => ({chemin: x.chemin, nom: String(x.nom || x.chemin.split(/[\\/]/).pop()), type: String(x.type || ""),
                  taille: typeof x.taille === "number" ? x.taille : null}));
}
