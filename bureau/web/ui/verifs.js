// Les contrôles du formulaire de création, sans DOM : partagés par l'ancien formulaire (creation.js) et la création en
// deux fenêtres (echange.js).

const INTERDITS = /[<>:"/\\|?*\u0000-\u001f]/;
const RESERVES = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
export const LONGUEUR_NOM_MAX = 100;

const plein = (t) => typeof t === "string" && t.trim() !== "";

// Le message à dire pour un nom de projet refusé (même règle que installation/creation.py), ou null.
export function verifierNom(nom) {
  const n = typeof nom === "string" ? nom.trim() : "";
  if (!n) return "Donnez un nom au projet.";
  if (n.length > LONGUEUR_NOM_MAX) return `Le nom du projet est trop long (${LONGUEUR_NOM_MAX} caractères au plus).`;
  if (n === "." || n === ".." || n.endsWith(".")) return "Le nom du projet ne peut pas être « . », « .. » ni finir par un point.";
  if (INTERDITS.test(n)) return "Le nom du projet ne peut pas contenir les caractères < > : \" / \\ | ? *.";
  if (RESERVES.test(n.split(".")[0].trimEnd())) return `« ${n} » est un nom réservé par Windows : choisissez-en un autre.`;
  return null;
}

// Le message à dire avant d'envoyer, ou null.
export function verifierCreation(champs) {
  if (!plein(champs?.parent)) return "Indiquez le dossier où ranger le projet.";
  return verifierNom(champs.nom);
}

// Les mots interdits saisis (séparés par des virgules ou des retours à la ligne), sans vides ni doublons.
export function motsInterdits(texte) {
  const vus = new Set();
  for (const m of String(texte || "").split(/[,\n]/)) if (m.trim()) vus.add(m.trim());
  return [...vus];
}
