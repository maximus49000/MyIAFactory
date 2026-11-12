// L'abonnement Claude : les deux jauges de la barre du haut (fenêtre de 5 h, semaine) et la part estimée d'un coût.
// Les jauges sont le détail « utilisé » de chaque fenêtre avec sa remise à zéro ; le rond (conso.js) est la synthèse.
// Les deux lisent LA MÊME lecture (mesure.js, servie par /api/conso : compte, sinon dernier appel du moteur) et les mêmes
// seuils. Les % sont ceux du COMPTE, donc ils comptent aussi les autres sessions Claude de l'utilisateur. Une valeur
// absente n'est jamais remplacée par un chiffre inventé. Tout texte passe par textContent.
// La part estimée d'un coût vient de l'état `abonnement` de /api/etat (points par euro).

import {INFOBULLE_CO2, lienMethode} from "./empreinte.js";
import {tonReste, ageMesure, agePhrase, formaterPart, consoCourante} from "./mesure.js";

export {ageMesure, formaterPart};

export const INFOBULLE_PART = "estimation : les % du compte comptent aussi vos autres sessions Claude";
export const TEXTE_ETALONNAGE = "part estimée : en cours d'étalonnage";
const FENETRES = [["five_hour", "5 h"], ["seven_day", "Semaine"]];

let courant;   // l'état `abonnement` le plus récent (undefined : jamais reçu ; null : couche API)

export function definirAbonnement(ab) {
  courant = ab && typeof ab === "object" ? ab : null;
}

const nombre = (v) => typeof v === "number" && Number.isFinite(v);

// Le ton d'une jauge : celui du rond pour ce qui reste (attention sous 30 % restants, alerte sous 10 %).
export function tonJauge(pourcent) {
  return nombre(pourcent) ? tonReste(100 - pourcent) : "inconnu";
}

// L'heure de remise à zéro en heure locale : « 14:30 » ; avec le jour pour la semaine (« jeu. 14:30 »).
export function heureRemise(remise, avecJour = false, options = {}) {
  if (!nombre(remise)) return "";
  const format = {hour: "2-digit", minute: "2-digit", hour12: false, ...(avecJour ? {weekday: "short"} : {}), ...options};
  return new Date(remise * 1000).toLocaleString("fr-FR", format).replace(",", "");
}

// Ce que la jauge d'une fenêtre dit : le nombre utilisé, le ton, la remise à zéro et l'âge de la mesure (avec sa
// provenance). `c` : la lecture du rond (`fenetres: [{cle, utilise, remise: date ISO}]`, `mesure`, `source`).
export function vueJauge(fenetre, c, maintenant = Date.now() / 1000, options = {}) {
  const f = c?.disponible === true ? (c.fenetres || []).find((x) => x.cle === fenetre) : null;
  if (!f || !nombre(f.utilise)) return null;
  const remiseT = Date.parse(f.remise) / 1000;
  const passee = nombre(remiseT) && remiseT <= maintenant;   // la fenêtre a été remise à zéro depuis la mesure
  const remise = passee ? "remise à zéro" : `RAZ ${heureRemise(remiseT, fenetre === "seven_day", options)}`.trim();
  return {pourcent: f.utilise, ton: passee ? "inconnu" : tonJauge(f.utilise),
          texte: passee ? "—" : `${Math.round(f.utilise)} %`, remise, age: agePhrase(c, maintenant),
          source: c.source === "moteur" ? "moteur" : "compte"};
}

// --- La part estimée d'un coût (euros) de l'abonnement : « ≈ 1,2 % semaine ».

function ratioSemaine(ab) {
  const r = ab?.pourcent_par_euro?.seven_day;
  return nombre(r) && r > 0 ? r : null;
}

// Rien quand la couche est l'API (ou sans état) ; « en cours d'étalonnage » tant que le ratio manque, sauf `court`.
export function etiquettePart(euros, {court = false, ab = courant} = {}) {
  if (!ab || !nombre(euros) || euros <= 0) return "";
  const r = ratioSemaine(ab);
  if (r === null) return court ? "" : TEXTE_ETALONNAGE;
  const part = formaterPart(euros * r);
  return `${part.startsWith("<") ? "" : "≈ "}${part} % semaine`;
}

// Pour une fourchette d'euros [min, max] : « ≈ 1,2 à 3,5 % semaine ».
export function etiquettePlage(min, max, {court = false, ab = courant} = {}) {
  if (!ab || !nombre(min) || !nombre(max) || max <= 0) return "";
  const r = ratioSemaine(ab);
  if (r === null) return court ? "" : TEXTE_ETALONNAGE;
  const a = formaterPart(min * r), b = formaterPart(max * r);
  return a === b ? etiquettePart(max, {ab}) : `≈ ${a} à ${b} % semaine`;
}

// « texte · part » ; le texte seul quand il n'y a pas de part à dire.
export function avecPart(texte, part) {
  return part ? `${texte} · ${part}` : texte;
}

// Pose l'infobulle d'avertissement sur un élément dont le texte porte une part estimée, une empreinte carbone estimée
// (avec le lien vers sa méthode), ou les deux.
export function marquerPart(element) {
  const texte = element.textContent || "";
  const infos = [];
  if (/% semaine|étalonnage/.test(texte)) infos.push(INFOBULLE_PART);
  if (/CO₂e/.test(texte)) {
    infos.push(INFOBULLE_CO2);
    if (!element.querySelector?.(".lien-methode")) element.append(lienMethode());
  }
  if (infos.length) element.title = infos.join(" — ");
  return element;
}

// --- Les jauges de la barre.

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

export function creerJauges() {
  const racine = el("div", "jauges");
  racine.setAttribute("aria-label", "Abonnement Claude");
  racine.hidden = true;
  const vide = el("span", "jauges-vide", "abonnement : pas de mesure");
  const lignes = FENETRES.map(([cle, nom]) => {
    const jauge = el("div", "jauge");
    const tete = el("span", "jauge-tete");
    const etiquette = el("span", "jauge-nom", nom);
    const piste = el("span", "jauge-piste");
    const plein = el("span", "jauge-plein");
    piste.append(plein);
    const valeur = el("span", "jauge-valeur", "—");
    tete.append(etiquette, piste, valeur);
    const detail = el("span", "jauge-detail", "");
    jauge.append(tete, detail);
    return {cle, nom, jauge, plein, valeur, detail};
  });
  racine.append(vide, ...lignes.map((l) => l.jauge));

  // Les jauges et le rond lisent la même lecture (`consoCourante`) ; cachées quand la couche est l'API (`ab` null).
  function maj(ab = courant, maintenant = Date.now() / 1000, c = consoCourante()) {
    racine.hidden = !ab || !c;   // rien d'affiché quand la couche est l'API, ni avant la première lecture du rond
    if (racine.hidden) return;
    const mesure = lignes.some((l) => vueJauge(l.cle, c, maintenant));
    vide.hidden = !!mesure;
    racine.title = mesure ? "Part de l'abonnement Claude utilisée (tout le compte, vos autres sessions comprises)"
      : "Aucune mesure de l'abonnement pour l'instant";
    for (const l of lignes) {
      const v = vueJauge(l.cle, c, maintenant);
      l.jauge.hidden = !mesure || !v;
      if (!v) continue;
      l.jauge.dataset.ton = v.ton;
      l.plein.style.width = (v.ton === "inconnu" ? 0 : Math.max(0, Math.min(100, v.pourcent))) + "%";
      l.valeur.textContent = v.texte;
      l.detail.textContent = v.age ? `${v.remise} · ${v.age}` : v.remise;
      l.jauge.title = `${l.nom} : ${v.texte} · ${v.remise} (heure locale)` + (v.age ? ` · ${v.age}` : "");
    }
  }
  racine.maj = maj;
  return racine;
}
