// Une image servie par /api/image qui échoue (par exemple l'instant où l'agent la copie vers sa racine : 404) reste
// cassée tant que le navigateur ne la redemande pas. Elle se redemande donc d'elle-même : 3 essais espacés, avec un
// paramètre anti-cache, puis elle reste cassée avec son texte alternatif.
export const DELAIS_REESSAI_MS = [2000, 5000, 10000];

const MARQUE = "/api/image";
const ESSAI = /([?&])r=\d+(?=&|$)/;

// L'adresse sans son paramètre d'essai.
export function adresseDeBase(src) {
  return String(src).replace(/\?r=\d+&/, "?").replace(ESSAI, "").replace(/[?&]$/, "");
}

// L'adresse du n-ième essai (n >= 1) : la base plus `r=n`.
export function adresseDEssai(base, n) {
  return `${base}${base.includes("?") ? "&" : "?"}r=${n}`;
}

// Branche le réessai sur `img`. `apresEchec` est appelée quand les essais sont épuisés. `planifier` sert aux tests.
export function reessayerImage(img, {delais = DELAIS_REESSAI_MS, planifier = setTimeout, apresEchec = null} = {}) {
  let base = null;
  let fait = 0;
  img.addEventListener("error", () => {
    const src = String(img.src || "");
    if (!src.includes(MARQUE)) return;
    const courante = adresseDeBase(src);
    if (courante !== base) { base = courante; fait = 0; }   // une autre image (visionneuse) : on repart de zéro
    if (fait >= delais.length) {
      if (apresEchec) apresEchec();
      return;
    }
    const n = ++fait;
    planifier(() => {
      if (adresseDeBase(String(img.src || "")) === base) img.src = adresseDEssai(base, n);
    }, delais[n - 1]);
  });
  return img;
}
