// L'abonnement Claude : les deux jauges de la barre du haut (fenêtre de 5 h, semaine) et la part estimée d'un coût.
// Les % viennent des appels `claude -p` (état servi : `abonnement`) ; ils sont ceux du COMPTE, donc ils comptent aussi
// les autres sessions Claude de l'utilisateur. Une valeur absente n'est jamais remplacée par un chiffre inventé.
// Tout texte passe par textContent.

export const INFOBULLE_PART = "estimation : les % du compte comptent aussi vos autres sessions Claude";
export const TEXTE_ETALONNAGE = "part estimée : en cours d'étalonnage";
export const SEUIL_ORANGE = 80;
export const SEUIL_ROUGE = 95;
const FENETRES = [["five_hour", "5 h"], ["seven_day", "Semaine"]];

let courant;   // l'état `abonnement` le plus récent (undefined : jamais reçu ; null : couche API)

export function definirAbonnement(ab) {
  courant = ab && typeof ab === "object" ? ab : null;
}

const nombre = (v) => typeof v === "number" && Number.isFinite(v);

// Le ton d'une jauge : rouge à partir de 95 %, orange à partir de 80 %.
export function tonJauge(pourcent) {
  if (!nombre(pourcent)) return "inconnu";
  return pourcent >= SEUIL_ROUGE ? "alerte" : pourcent >= SEUIL_ORANGE ? "attention" : "ok";
}

// « il y a 3 min », « il y a 2 h », « il y a 1 j » ; vide si l'instant de la mesure est inconnu.
export function ageMesure(t, maintenant = Date.now() / 1000) {
  if (!nombre(t)) return "";
  const minutes = Math.max(0, Math.floor((maintenant - t) / 60));
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const heures = Math.floor(minutes / 60);
  return heures < 24 ? `il y a ${heures} h` : `il y a ${Math.floor(heures / 24)} j`;
}

// L'heure de remise à zéro en heure locale : « 14:30 » ; avec le jour pour la semaine (« jeu. 14:30 »).
export function heureRemise(remise, avecJour = false, options = {}) {
  if (!nombre(remise)) return "";
  const format = {hour: "2-digit", minute: "2-digit", hour12: false, ...(avecJour ? {weekday: "short"} : {}), ...options};
  return new Date(remise * 1000).toLocaleString("fr-FR", format).replace(",", "");
}

// Ce que la jauge d'une fenêtre dit : le nombre, le ton, la remise à zéro et l'âge de la mesure.
export function vueJauge(fenetre, ab, maintenant = Date.now() / 1000, options = {}) {
  const f = ab?.instantane?.[fenetre];
  if (!f || !nombre(f.pourcent)) return null;
  const passee = nombre(f.remise) && f.remise <= maintenant;   // la fenêtre a été remise à zéro depuis la mesure
  const remise = passee ? "remise à zéro" : `RAZ ${heureRemise(f.remise, fenetre === "seven_day", options)}`;
  return {pourcent: f.pourcent, ton: passee ? "inconnu" : tonJauge(f.pourcent),
          texte: passee ? "—" : `${Math.round(f.pourcent)} %`, remise, age: ageMesure(ab.instantane.t, maintenant)};
}

// --- La part estimée d'un coût (euros) de l'abonnement : « ≈ 1,2 % semaine ».

export function formaterPart(p) {
  if (!nombre(p)) return "";
  if (p < 0.1) return "< 0,1";
  return p < 10 ? p.toFixed(1).replace(".", ",") : String(Math.round(p));
}

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

// Pose l'infobulle d'avertissement sur un élément dont le texte porte une part estimée.
export function marquerPart(element) {
  if (/% semaine|étalonnage/.test(element.textContent || "")) element.title = INFOBULLE_PART;
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
  const vide = el("span", "jauges-vide", "abonnement : pas encore mesuré");
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

  function maj(ab = courant, maintenant = Date.now() / 1000) {
    racine.hidden = !ab;   // rien d'affiché quand la couche est l'API
    if (!ab) return;
    const mesure = ab.instantane && lignes.some((l) => vueJauge(l.cle, ab, maintenant));
    vide.hidden = !!mesure;
    racine.title = mesure ? "Part de l'abonnement Claude utilisée (tout le compte, vos autres sessions comprises)"
      : "Aucun appel de `claude -p` n'a encore mesuré l'abonnement";
    for (const l of lignes) {
      const v = vueJauge(l.cle, ab, maintenant);
      l.jauge.hidden = !mesure || !v;
      if (!v) continue;
      l.jauge.dataset.ton = v.ton;
      l.plein.style.width = (v.ton === "inconnu" ? 0 : Math.max(0, Math.min(100, v.pourcent))) + "%";
      l.valeur.textContent = v.texte;
      l.detail.textContent = `${v.remise} · ${v.age}`;
      l.jauge.title = `${l.nom} : ${v.texte} · ${v.remise} (heure locale) · mesuré ${v.age}`;
    }
  }
  racine.maj = maj;
  return racine;
}
