// La semaine du forfait Claude en courbe : la logique pure (échelles, paliers, filtres en cascade, marques d'usage) et le
// dessin SVG à la main (aucune bibliothèque). Les données viennent de /api/semaines, /api/semaine et /api/sujets
// (bureau/semaines.py, bureau/sujets.py) : la courbe est le compteur de TOUT le compte, elle ne se filtre pas ; les
// bandes montrent quand la sélection (projet, fonctionnalité, tâche, étape) a utilisé Claude.
// Une seule couleur de série (le bleu des agents), contraste vérifié sur le fond ; tout texte passe par textContent.

export const SEP = "\x1f";                 // sépare les identifiants d'un chemin dans l'`id` d'un nœud (bureau/sujets.py)
export const NIVEAUX = ["Projet", "Fonctionnalité", "Tâche", "Sous-tâche"];
export const COULEUR = "#2f6fd0";
const PALIERS = [5, 10, 20, 30, 40, 50, 60, 80, 100];
const NS = "http://www.w3.org/2000/svg";

const nombre = (v) => typeof v === "number" && Number.isFinite(v);

// --- Échelles.

// Le haut de l'axe vertical : le plus petit palier qui contient la valeur avec un peu d'air (5 à 100 %).
export function plafond(max) {
  const m = nombre(max) && max > 0 ? max : 0;
  return PALIERS.find((p) => p >= m * 1.1) ?? 100;
}

// Les points de la courbe en paliers `[t, % utilisé]` : la valeur tient jusqu'au point suivant (un compteur lu par
// instants), puis jusqu'à `jusqua` (maintenant, ou la dernière lecture d'une semaine passée). Rien avant le premier point.
export function paliers(points, jusqua) {
  const pts = (Array.isArray(points) ? points : []).filter((p) => nombre(p?.t) && nombre(p?.pourcent))
    .sort((a, b) => a.t - b.t);
  if (!pts.length) return [];
  const sortie = [[pts[0].t, pts[0].pourcent]];
  for (let i = 1; i < pts.length; i++) {
    sortie.push([pts[i].t, pts[i - 1].pourcent], [pts[i].t, pts[i].pourcent]);
  }
  const dernier = pts[pts.length - 1];
  if (nombre(jusqua) && jusqua > dernier.t) sortie.push([jusqua, dernier.pourcent]);
  return sortie;
}

// La valeur de la courbe à l'instant t (le dernier point connu), ou null avant le premier.
export function valeurA(points, t) {
  let v = null;
  for (const p of points || []) {
    if (p.t <= t) v = p.pourcent;
    else break;
  }
  return v;
}

// --- Le rythme idéal : la droite de la consommation parfaite, 0 % utilisé au début de la fenêtre (remise − 7 jours) et
// 100 % à la seconde de la remise. Au-dessus de la droite, on consomme plus vite que ce rythme.

export const RYTHME_COULEUR = "#d03b3b";
export const SEMAINE_S = 7 * 86400;

const debutDe = (semaine) => (nombre(semaine?.debut) ? semaine.debut : semaine.remise - SEMAINE_S);

// Le pourcentage utilisé qu'il faudrait avoir à l'instant t (0 à 100, borné à la fenêtre).
export function rythmeA(semaine, t) {
  const d = debutDe(semaine);
  return Math.min(100, Math.max(0, ((t - d) / (semaine.remise - d)) * 100));
}

// L'écart de la courbe à la droite à l'instant t, en points de pourcentage (> 0 : en avance sur le rythme), ou null sans mesure.
export function ecartRythme(semaine, points, t) {
  const v = valeurA(points, t);
  return v === null ? null : v - rythmeA(semaine, t);
}

const dec = (v) => (Math.round(v * 10) / 10).toString().replace(".", ",");
const libPoints = (v) => `${dec(v)} point${Math.abs(v) >= 2 ? "s" : ""}`;
const nul = (e) => Math.round(Math.abs(e) * 10) === 0;

// « Au-dessus de X points » / « En dessous de X points » (vide sans écart connu).
export function phraseEcart(ecart) {
  if (!nombre(ecart)) return "";
  if (nul(ecart)) return "Sur le rythme idéal";
  return ecart > 0 ? `Au-dessus du rythme de ${libPoints(ecart)}` : `En dessous de ${libPoints(-ecart)}`;
}

// Sous le petit graphique, pour la semaine en cours seulement.
export function ligneRythme(semaine, pts, maintenant) {
  if (!semaine?.courante) return "";
  const t = Math.min(maintenant, semaine.remise);
  const e = ecartRythme(semaine, pts, t);
  if (e === null) return "";
  if (nul(e)) return "Rythme : sur le rythme idéal";
  return `Rythme : en ${e > 0 ? "avance" : "retard"} de ${libPoints(Math.abs(e))}`;
}

// Jusqu'où la courbe est tracée : maintenant pour la semaine en cours, la dernière lecture sinon (au plus la remise).
export function finDeCourbe(semaine, maintenant) {
  if (!semaine) return null;
  if (semaine.courante) return Math.min(maintenant, semaine.remise);
  return Math.min(nombre(semaine.vu) ? semaine.vu : semaine.remise, semaine.remise);
}

// Les minuits locaux de la fenêtre : `[{t, libelle}]` (le libellé est le jour, placé au milieu de la journée par le dessin).
export function graduationsJours(debut, fin) {
  const d = new Date(debut * 1000);
  d.setHours(0, 0, 0, 0);
  const sortie = [];
  while (d.getTime() / 1000 < fin) {
    const t = d.getTime() / 1000;
    sortie.push({t, libelle: d.toLocaleDateString("fr-FR", {weekday: "short"})});
    d.setDate(d.getDate() + 1);
  }
  return sortie;
}

// --- Les sujets : arbre, filtres en cascade, marques.

export function trouver(sujets, id) {
  for (const n of sujets || []) {
    if (n.id === id) return n;
    const dedans = trouver(n.enfants, id);
    if (dedans) return dedans;
  }
  return null;
}

// Les nœuds depuis la racine jusqu'à `id` (vide si inconnu ou vide).
export function chemin(sujets, id) {
  if (!id) return [];
  const morceaux = id.split(SEP);
  const sortie = [];
  let niveau = sujets;
  for (let i = 1; i <= morceaux.length; i++) {
    const n = (niveau || []).find((x) => x.id === morceaux.slice(0, i).join(SEP));
    if (!n) return [];
    sortie.push(n);
    niveau = n.enfants;
  }
  return sortie;
}

// Les listes déroulantes : une par niveau, ses options (les enfants du niveau choisi au-dessus) et la valeur choisie.
// Un niveau n'a d'options que si son parent est choisi et a des enfants.
export function niveaux(sujets, selection) {
  const suite = chemin(sujets, selection);
  const sortie = [];
  let options = sujets || [];
  for (let k = 0; k < NIVEAUX.length; k++) {
    const choisi = suite[k] || null;
    sortie.push({libelle: NIVEAUX[k], options: options.map((n) => ({id: n.id, nom: n.nom})), valeur: choisi ? choisi.id : "",
                 actif: options.length > 0});
    options = choisi ? choisi.enfants || [] : [];
  }
  return sortie;
}

// La sélection après le choix de `id` dans la liste du niveau k : vide = « Tous » = le parent (niveau k − 1) ou rien.
export function apresChoix(sujets, selection, k, id) {
  if (id) return id;
  const suite = chemin(sujets, selection);
  return k > 0 && suite[k - 1] ? suite[k - 1].id : "";
}

// Toutes les marques d'usage d'un nœud et de ses descendants, rangées par date.
export function marquesDe(noeud) {
  if (!noeud) return [];
  const sortie = [...(noeud.marques || [])];
  for (const e of noeud.enfants || []) sortie.push(...marquesDe(e));
  return sortie.sort((a, b) => a.t - b.t);
}

// Les marques de la sélection (tout si rien n'est choisi).
export function marquesSelection(arbre, selection) {
  const n = selection ? trouver(arbre?.sujets, selection) : null;
  return n ? marquesDe(n) : (arbre?.sujets || []).flatMap(marquesDe).sort((a, b) => a.t - b.t);
}

// Le total de la sélection (ou de tout) : `{nom, euros, sans_prix, n, co2}`.
export function totalSelection(arbre, selection) {
  const n = selection ? trouver(arbre?.sujets, selection) : null;
  if (n) return {nom: chemin(arbre.sujets, selection).map((x) => x.nom).join(" › "), euros: n.euros, sans_prix: n.sans_prix, n: n.n, co2: n.co2};
  return {nom: "Tous les projets", euros: arbre?.euros ?? 0, sans_prix: arbre?.sans_prix ?? 0, n: arbre?.n ?? 0, co2: arbre?.co2};
}

// La liste affichée : la sélection elle-même (surlignée par la page) puis ses descendants, ou tous les nœuds sans
// sélection, en profondeur d'abord, chacun avec la profondeur et le chemin de ses parents ; triés par coût à chaque
// niveau (déjà fait par le serveur).
export function lignesListe(arbre, selection) {
  const racine = selection ? trouver(arbre?.sujets, selection) : null;
  const depart = racine ? [racine] : arbre?.sujets || [];
  const base = racine ? chemin(arbre.sujets, selection).slice(0, -1).map((x) => x.nom) : [];
  const sortie = [];
  (function marcher(noeuds, parents) {
    for (const n of noeuds) {
      sortie.push({noeud: n, profondeur: parents.length - base.length, parents});
      marcher(n.enfants || [], [...parents, n.nom]);
    }
  })(depart, base);
  return sortie;
}

// Les bandes d'usage en pixels : `[{x, l, t, duree, euros, modele}]`. Une durée inconnue (ou courte) donne un trait fin.
export function bandes(marques, debut, fin, largeur, minimum = 3) {
  const echelle = largeur / (fin - debut);
  return marques.filter((m) => m.t >= debut && m.t <= fin).map((m) => {
    const l = Math.max(minimum, (nombre(m.duree) ? m.duree : 0) * echelle);
    const x = Math.min(largeur - l, Math.max(0, (m.t - debut) * echelle));
    return {x, l, t: m.t, duree: nombre(m.duree) ? m.duree : null, euros: m.euros ?? null, modele: m.modele};
  });
}

// --- Le dessin.

function noeud(tag, attrs = {}, texte) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (texte !== undefined) e.textContent = texte;
  return e;
}

const pct = (v) => (Math.round(v * 10) / 10).toString().replace(".", ",") + " %";

export function heureLocale(t, avecJour = true) {
  return new Date(t * 1000).toLocaleString("fr-FR", {...(avecJour ? {weekday: "short"} : {}), hour: "2-digit", minute: "2-digit", hour12: false})
    .replace(",", "");
}

// Le texte alternatif de la courbe.
export function resume(semaine, points, maintenant) {
  if (!points?.length) return "Quota de la semaine : aucune mesure.";
  const dernier = points[points.length - 1].pourcent;
  const fin = semaine.courante ? `à ${heureLocale(Math.min(maintenant, semaine.remise))}` : "en fin de semaine";
  return `Quota de la semaine : ${pct(dernier)} utilisé ${fin}, remise à zéro ${heureLocale(semaine.remise)}. ` +
    "Une droite rouge en tirets montre le rythme idéal, de 0 % au début à 100 % à la remise.";
}

// Le graphique. `opts` : {semaine: {debut, remise, courante, vu}, points, maintenant, largeur, hauteur, compact,
// marques (bandes fortes), autres (traits discrets), titre}. Rend un <svg> et ses repères (`svg.geometrie`) pour le survol.
export function dessiner(opts) {
  const {semaine, points = [], maintenant = Date.now() / 1000, largeur = 320, hauteur = 120, compact = false} = opts;
  const marges = compact ? {g: 28, d: 8, h: 8, b: 20} : {g: 40, d: 12, h: 12, b: 26};
  const w = largeur - marges.g - marges.d, h = hauteur - marges.h - marges.b;
  const t0 = semaine.debut, t1 = semaine.remise;
  const fin = finDeCourbe(semaine, maintenant);
  const serie = paliers(points, fin);
  const haut = 100;   // la droite du rythme idéal monte jusqu'à 100 % à la remise
  const X = (t) => marges.g + ((Math.min(t1, Math.max(t0, t)) - t0) / (t1 - t0)) * w;
  const Y = (p) => marges.h + h - (Math.min(haut, Math.max(0, p)) / haut) * h;

  const svg = noeud("svg", {viewBox: `0 0 ${largeur} ${hauteur}`, width: largeur, height: hauteur, class: "sem-svg", role: "img",
                            "aria-label": opts.titre || resume(semaine, points, maintenant)});
  // grille horizontale (0, 50, 100 ; tous les quarts sur le grand graphique) : discrète
  for (const v of compact ? [0, 50, 100] : [0, 25, 50, 75, 100]) {
    svg.append(noeud("line", {x1: marges.g, x2: marges.g + w, y1: Y(v), y2: Y(v), class: v === 0 ? "sem-axe" : "sem-grille"}),
      noeud("text", {x: marges.g - 4, y: Y(v) + 4, class: "sem-etiquette", "text-anchor": "end"}, `${Math.round(v * 10) / 10}`.replace(".", ",") + " %"));
  }
  // jours : traits de minuit et nom du jour au milieu
  for (const j of graduationsJours(t0, t1)) {
    if (j.t > t0) svg.append(noeud("line", {x1: X(j.t), x2: X(j.t), y1: marges.h + h, y2: marges.h + h + 4, class: "sem-axe"}));
    const milieu = Math.min(t1, j.t + 43200);
    if (milieu > t0) svg.append(noeud("text", {x: X(Math.max(milieu, t0 + 21600)), y: hauteur - 6, class: "sem-etiquette", "text-anchor": "middle"}, j.libelle));
  }
  // bandes d'usage : d'abord les discrètes, puis celles de la sélection
  const groupe = (marques, classe) => {
    for (const b of bandes(marques || [], t0, t1, w)) {
      const r = noeud("rect", {x: marges.g + b.x, y: marges.h, width: b.l, height: h, class: classe});
      r.dataset.t = b.t;
      svg.append(r);
    }
  };
  groupe(opts.autres, "sem-bande-discrete");
  groupe(opts.marques, "sem-bande");
  // l'aire et la ligne
  if (serie.length) {
    const d = serie.map(([t, p], i) => `${i ? "L" : "M"}${X(t).toFixed(1)} ${Y(p).toFixed(1)}`).join(" ");
    const dernier = serie[serie.length - 1], premier = serie[0];
    svg.append(noeud("path", {d: `${d} L${X(dernier[0]).toFixed(1)} ${Y(0)} L${X(premier[0]).toFixed(1)} ${Y(0)} Z`, class: "sem-aire"}),
      noeud("path", {d, class: "sem-ligne"}));
  }
  // le rythme idéal : de (début, 0 %) à (remise, 100 %), en tirets rouges, sans remplissage
  svg.append(noeud("line", {x1: X(t0), y1: Y(0), x2: X(t1), y2: Y(100), class: "sem-rythme", stroke: RYTHME_COULEUR}));
  // maintenant (pointillé) et remise à zéro (bord droit)
  if (semaine.courante && maintenant >= t0 && maintenant <= t1) {
    svg.append(noeud("line", {x1: X(maintenant), x2: X(maintenant), y1: marges.h, y2: marges.h + h, class: "sem-maintenant"}),
      noeud("text", {x: Math.min(X(maintenant), marges.g + w - 2), y: marges.h + 9, class: "sem-etiquette", "text-anchor": X(maintenant) > marges.g + w - 40 ? "end" : "middle"}, "maintenant"));
  }
  svg.append(noeud("line", {x1: marges.g + w, x2: marges.g + w, y1: marges.h, y2: marges.h + h, class: "sem-raz"}));
  svg.geometrie = {marges, w, h, t0, t1, haut, X, Y, largeur, hauteur};
  return svg;
}

// L'instant sous l'abscisse x (en unités du viewBox), borné à la fenêtre.
export function instantA(svg, x) {
  const g = svg.geometrie;
  const t = g.t0 + ((x - g.marges.g) / g.w) * (g.t1 - g.t0);
  return Math.min(g.t1, Math.max(g.t0, t));
}
