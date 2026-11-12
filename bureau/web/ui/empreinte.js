// L'empreinte carbone estimée, affichée à côté des coûts en euros. Elle est calculée côté serveur (bureau/empreinte.py,
// méthode EcoLogits : https://ecologits.ai/latest/methodology/llm_inference/) ; la page ne fait que la mettre en forme.
// Une fourchette `{min, max}` en grammes de CO2e ; absente (rien à montrer) quand aucun modèle n'a pu être estimé.
// Tout texte passe par textContent.

export const URL_METHODE = "https://ecologits.ai/latest/methodology/llm_inference/";
export const INFOBULLE_CO2 = "estimation EcoLogits : tailles de modèles estimées, tokens de sortie seulement, électricité des États-Unis";

const nombre = (v) => typeof v === "number" && Number.isFinite(v);

function formater(g, kg) {
  const v = kg ? g / 1000 : g;
  if (!kg && v < 0.01) return "< 0,01";
  const texte = v < 1 && !kg ? v.toFixed(2) : v < 10 ? v.toFixed(1) : String(Math.round(v));
  return texte.replace(".", ",");
}

// « ≈ 0,46 à 0,72 g CO₂e » ; en kg à partir de 1000 g ; vide sans valeur. « (partiel) » : un usage n'a pas pu être estimé.
export function etiquetteCO2(co2) {
  if (!co2 || !nombre(co2.min) || !nombre(co2.max) || co2.max <= 0) return "";
  const kg = co2.max >= 1000;
  const a = formater(co2.min, kg), b = formater(co2.max, kg);
  const unite = kg ? "kg" : "g";
  const texte = a === b ? `${a.startsWith("<") ? "" : "≈ "}${a} ${unite} CO₂e` : `≈ ${a} à ${b} ${unite} CO₂e`;
  return co2.incomplet === true ? `${texte} (partiel)` : texte;
}

// L'énergie en Wh de la même estimation : « 1,1 à 1,8 Wh » (pour une infobulle) ; vide sans valeur.
export function energie(co2) {
  if (!co2 || !nombre(co2.wh_min) || !nombre(co2.wh_max)) return "";
  const f = (v) => (v < 10 ? v.toFixed(2) : v < 1000 ? v.toFixed(1) : String(Math.round(v))).replace(".", ",");
  const a = f(co2.wh_min), b = f(co2.wh_max);
  return a === b ? `${a} Wh` : `${a} à ${b} Wh`;
}

// L'infobulle : l'avertissement, et l'énergie quand on la connaît.
export function infobulleCO2(co2) {
  const e = energie(co2);
  return e ? `${INFOBULLE_CO2} · énergie ≈ ${e}` : INFOBULLE_CO2;
}

// Pose seulement l'infobulle (sur une ligne de la facturation, par exemple) quand le texte porte une empreinte.
export function marquerTitreCO2(element, co2) {
  if (/CO₂e/.test(element.textContent || "")) element.title = infobulleCO2(co2);
  return element;
}

// Le lien vers la méthode, à ajouter après un texte qui porte une empreinte.
export function lienMethode() {
  const a = document.createElement("a");
  a.className = "lien-methode";
  a.href = URL_METHODE;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = " méthode";
  a.title = "La méthode EcoLogits";
  return a;
}
