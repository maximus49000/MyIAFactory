// Ce que le rond et les jauges partagent : la même lecture (servie par /api/conso), les mêmes seuils, le même âge.
// Une seule source : jamais deux valeurs différentes à l'écran. Les pourcentages sont en « utilisé » (jauges) ou en
// « reste » (rond) ; les deux se déduisent l'un de l'autre (reste = 100 − utilisé).

const nombre = (v) => typeof v === "number" && Number.isFinite(v);

let courante = null;          // la dernière lecture reçue (null : aucune)
const ecouteurs = new Set();

export function definirConsoCourante(c) {
  courante = c && typeof c === "object" ? c : null;
  for (const f of ecouteurs) f(courante);
}

export function consoCourante() {
  return courante;
}

export function surConso(fonction) {
  ecouteurs.add(fonction);
}

// Le ton selon ce qui reste : ok au-dessus de 30 %, attention entre 10 et 30 %, alerte en dessous.
// Le rond, ses lignes et les jauges (par `100 − utilisé`) suivent ces seuils : une jauge rouge quand le rond est en alerte.
export function tonReste(reste) {
  if (!nombre(reste)) return "inconnu";
  return reste > 30 ? "ok" : reste > 10 ? "attention" : "alerte";
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

// L'âge de la lecture, avec sa provenance quand ce n'est pas une lecture directe du compte :
// « il y a 2 min » ou « d'après le dernier appel, il y a 12 min ».
export function agePhrase(c, maintenant = Date.now() / 1000) {
  const age = ageMesure(c?.mesure, maintenant);
  if (c?.source === "moteur") return age ? `d'après le dernier appel, ${age}` : "d'après le dernier appel";
  return age;
}

// La part estimée des coûts affichée avec ses chiffres : « 1,3 », « 12 », « < 0,1 ».
export function formaterPart(p) {
  if (!nombre(p)) return "";
  if (p < 0.1) return "< 0,1";
  return p < 10 ? p.toFixed(1).replace(".", ",") : String(Math.round(p));
}

// La ligne du panneau du rond : « Part estimée de vos coûts : ≈ 2,0 % de la semaine par euro » ou « étalonnage en cours
// (1/3 mesures) » ; vide quand la couche est l'API (aucune part).
export function lignePart(part) {
  if (!part || typeof part !== "object") return "";
  const r = part.pourcent_par_euro;
  if (nombre(r) && r > 0) return `Part estimée de vos coûts : ≈ ${formaterPart(r)} % de la semaine par euro`;
  return `Part estimée de vos coûts : étalonnage en cours (${nombre(part.mesures) ? part.mesures : 0}/${nombre(part.minimum) ? part.minimum : 3} mesures)`;
}
