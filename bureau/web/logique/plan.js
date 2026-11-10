// Le plan de l'open space : pièces, places, meubles, chemins.
// Fonction pure : ni DOM, ni three.js. Repère : x vers la droite, z vers le bas du plan, en mètres.
// Le bâtiment est centré sur l'origine. Pour chaque pièce, (x, z) est son centre.
//
// Disposition : une rangée de services en haut, l'open space au milieu avec le Kanban,
// une rangée en bas (café, services en surplus, direction). Chaque pièce a une porte
// au milieu du mur qui donne sur l'open space.
//
// cap : angle de la direction regardée, vecteur (sin cap, cos cap). cap = 0 regarde vers +z.

const LP = 6;          // largeur d'une pièce
const PP = 5;          // profondeur d'une pièce
const PO = 8;          // profondeur de l'open space
const DEMI_PORTE = 0.6;
const MARGE_TABLEAU = 0.35;
// Le tableau est fait de panneaux blancs côte à côte (un modèle de tableau sur pieds chacun) :
// un panneau tous les PAS_TABLEAU mètres, JEU_TABLEAU de cadre entre la dernière surface blanche et le bout.
export const PAS_TABLEAU = 1.75, JEU_TABLEAU = 0.16;

const capVers = (de, vers) => Math.atan2(vers.x - de.x, vers.z - de.z);
const pt = (p) => ({x: p.x, z: p.z});

export function creerPlan(services, colonnes) {
  const n = services.length;
  const C = Math.max(3, Math.ceil((n + 2) / 2));
  const W = C * LP;
  const H = 2 * PP + PO;
  const z0 = -H / 2;

  const pieces = [];
  const parService = new Map();
  const meubles = [];

  function rangee(liste, zc, dir) {
    const x0 = -W / 2 + (C - liste.length) * LP / 2;
    liste.forEach((p, i) => {
      const x = x0 + LP * (i + 0.5);
      const mur = zc + dir * PP / 2;
      const piece = {
        id: p.id, nom: p.nom, type: p.type, x, z: zc, largeur: LP, profondeur: PP, dir,
        porte: {x, z: mur, largeur: 2 * DEMI_PORTE},
        interieur: {x, z: mur - dir * 0.6},
        exterieur: {x, z: mur + dir * 0.6},
        fond: zc - dir * PP / 2,
      };
      pieces.push(piece);
      if (p.type === "service") parService.set(p.id, piece);
    });
  }

  const haut = services.slice(0, C).map((s) => ({id: s.id, nom: s.nom, type: "service"}));
  const bas = [
    {id: "cafe", nom: "Café", type: "cafe"},
    ...services.slice(C).map((s) => ({id: s.id, nom: s.nom, type: "service"})),
    {id: "direction", nom: "Direction", type: "direction"},
  ];
  rangee(haut, z0 + PP / 2, +1);
  rangee(bas, z0 + PP + PO + PP / 2, -1);

  const openspace = {id: "openspace", nom: "Open space", type: "openspace",
                     x: 0, z: z0 + PP + PO / 2, largeur: W, profondeur: PO};

  // Point d'une pièce en coordonnées locales : lx le long du mur, d depuis le mur du fond.
  const local = (piece, lx, d) => ({x: piece.x + lx, z: piece.fond + piece.dir * d});
  const capFond = (piece) => Math.atan2(0, -piece.dir);
  const capPorte = (piece) => Math.atan2(0, piece.dir);
  const meuble = (piece, nom, lx, d, cap) => meubles.push({nom, piece: piece.id, ...local(piece, lx, d), cap});

  // --- Services : 4 bureaux contre le mur du fond, puis des places debout.
  const BUREAUX = [-2.1, -0.7, 0.7, 2.1];
  const DEBOUT_X = [-1.2, 1.2, -2.0, 2.0, -0.4, 0.4];
  const DEBOUT_D = [2.6, 3.3, 4.0];
  for (const piece of parService.values()) {
    for (const lx of BUREAUX) {
      meuble(piece, "bureau", lx, 0.75, capPorte(piece));
      meuble(piece, "ecran", lx, 0.55, capPorte(piece));
      meuble(piece, "chaise", lx, 1.45, capFond(piece));
    }
    meuble(piece, "armoire", -2.65, 2.2, Math.PI / 2);
    meuble(piece, "etagere", 2.75, 2.4, -Math.PI / 2);
    meuble(piece, "plante", 2.6, 4.55, capPorte(piece));
  }

  function poste(serviceId, i) {
    const piece = parService.get(serviceId);
    if (!piece) return null;
    if (i < BUREAUX.length) return {...local(piece, BUREAUX[i], 1.45), cap: capFond(piece), assis: true};
    const k = i - BUREAUX.length;
    const parTour = DEBOUT_X.length * DEBOUT_D.length;
    const j = k % parTour;
    const tour = Math.floor(k / parTour);
    let lx = DEBOUT_X[j % DEBOUT_X.length];
    let d = DEBOUT_D[Math.floor(j / DEBOUT_X.length)];
    if (tour > 0) {          // au-delà de 22 personnes : on se serre (places décalées, toujours distinctes)
      lx += 0.35 * Math.sin(tour * 2.3);
      d += 0.3 * Math.cos(tour * 2.3);
    }
    return {...local(piece, lx, d), cap: capFond(piece), assis: false};
  }

  // --- Café : canapé, machine, table basse ; places choisies, puis une grille, puis l'open space.
  const cafePiece = pieces.find((p) => p.type === "cafe");
  meuble(cafePiece, "machine_cafe", 2.1, 0.4, capPorte(cafePiece));
  meuble(cafePiece, "canape", -1.5, 0.55, capPorte(cafePiece));
  meuble(cafePiece, "table_basse", -1.5, 1.55, 0);
  meuble(cafePiece, "plante", -2.65, 0.35, capPorte(cafePiece));
  meuble(cafePiece, "plante", 2.65, 4.55, capPorte(cafePiece));
  const machine = local(cafePiece, 2.1, 0.4);
  const table = local(cafePiece, -1.5, 1.55);
  const placesCafe = [];
  const ajouterCafe = (lx, d, regard, assis = false) => {
    const p = local(cafePiece, lx, d);
    if (placesCafe.some((q) => Math.hypot(q.x - p.x, q.z - p.z) < 0.6)) return;
    placesCafe.push({...p, cap: regard ? capVers(p, regard) : capPorte(cafePiece), assis});
  };
  ajouterCafe(-1.9, 0.6, null, true);   // sur le canapé
  ajouterCafe(-1.1, 0.6, null, true);
  ajouterCafe(2.1, 1.25, machine);
  ajouterCafe(1.3, 1.6, machine);
  ajouterCafe(-2.45, 1.6, table);
  ajouterCafe(-0.55, 1.6, table);
  for (const d of [2.5, 3.2, 3.9])
    for (const lx of [-2.0, -1.2, -0.4, 0.4, 1.2, 2.0]) ajouterCafe(lx, d, local(cafePiece, 0, 1.2));

  function cafe(i) {
    if (i < placesCafe.length) return {...placesCafe[i]};
    // Au-delà : devant la porte du café, dans l'open space, par rangées de 6.
    const k = i - placesCafe.length;
    const tour = Math.floor(k / 18);
    const j = k % 18;
    const lx = -2.0 + 0.8 * (j % 6) + (tour > 0 ? 0.35 * Math.sin(tour * 2.3) : 0);
    const recul = 1.0 + 0.7 * Math.floor(j / 6) + (tour > 0 ? 0.3 * Math.cos(tour * 2.3) : 0);
    const p = {x: cafePiece.x + lx, z: cafePiece.porte.z + cafePiece.dir * recul};
    return {...p, cap: capVers(p, cafePiece.porte)};
  }

  // --- Direction : le grand bureau ; le Directeur derrière, tourné vers le mur du fond
  // (qui, pour la rangée du bas, est le mur rasé face à la caméra : on voit son visage).
  const dir = pieces.find((p) => p.type === "direction");
  meuble(dir, "bureau_direction", 0, 1.3, capPorte(dir));
  meuble(dir, "chaise", 0, 2.15, capFond(dir));
  meuble(dir, "etagere", -2.0, 3.0, capFond(dir));
  meuble(dir, "armoire", 2.65, 2.4, -Math.PI / 2);
  meuble(dir, "plante", 2.65, 0.4, capPorte(dir));
  meuble(dir, "plante", -2.65, 0.4, capPorte(dir));
  const directeur = {...local(dir, 0, 2.05), cap: capFond(dir)};

  // --- Le Kanban, au centre de l'open space, tourné vers +z.
  const nc = Math.max(1, colonnes.length);
  const panneaux = Math.max(1, Math.min(Math.floor((W - 4 + JEU_TABLEAU) / PAS_TABLEAU),
                                         Math.max(2, Math.round((0.95 * nc + 0.3) / PAS_TABLEAU))));
  const largeur = panneaux * PAS_TABLEAU - JEU_TABLEAU;
  const kx = 0, kz = openspace.z - 0.6;
  const LIGNES = 4;
  const largeurColonne = (largeur - 0.3) / nc;
  // (u, v) : position du centre d'un post-it sur la surface, depuis le coin haut gauche, en mètres.
  const postit = (colonneIndex, rang) => ({
    u: 0.15 + largeurColonne * (Math.max(0, Math.min(nc - 1, colonneIndex)) + 0.5),
    v: 0.38 + 0.235 * Math.max(0, Math.min(LIGNES - 1, rang)),
  });
  const kanban = {
    x: kx, z: kz, cap: 0, largeur, panneaux, hauteur: 1.25, entete: 0.26, lignes: LIGNES, colonnes: nc, largeurColonne,
    devant: {x: kx, z: kz + 1.0, cap: Math.PI},
    devantColonne: (i) => ({x: kx - largeur / 2 + postit(i, 0).u, z: kz + 1.0, cap: Math.PI}),
    attente: (i) => {
      const tour = Math.floor(i / 18);
      const j = i % 18;
      return {x: kx - 1.75 + 0.7 * (j % 6) + 0.35 * tour, z: kz + 1.9 + 0.7 * Math.floor(j / 6), cap: Math.PI};
    },
  };
  const chef = {x: kx - largeur / 2 - 0.8, z: kz + 0.9, cap: Math.PI / 4};

  // --- Chemins.
  const obstacle = {x: kx, z: kz, hx: largeur / 2 + MARGE_TABLEAU, hz: 0.7};

  function pieceDe(p) {
    for (const r of pieces)
      if (Math.abs(p.x - r.x) <= r.largeur / 2 + 1e-9 && Math.abs(p.z - r.z) <= r.profondeur / 2 + 1e-9) return r;
    return null;
  }

  const dansPorte = (p, r) => Math.abs(p.x - r.porte.x) < DEMI_PORTE - 0.1 && Math.abs(p.z - r.porte.z) < 0.65;

  function chemin(a, b) {
    const ra = pieceDe(a), rb = pieceDe(b);
    const pts = [pt(a)];
    if (ra && ra === rb) {
      pts.push(pt(b));
      return pts;
    }
    if (ra) {
      if (!dansPorte(a, ra)) pts.push(pt(ra.interieur));
      pts.push(pt(ra.exterieur));
    }
    const arrivee = rb ? rb.exterieur : b;
    pts.push(...contourner(pts.at(-1), arrivee));
    if (rb) {
      pts.push(pt(rb.exterieur));
      if (!dansPorte(b, rb)) pts.push(pt(rb.interieur));
    }
    pts.push(pt(b));
    return pts.filter((p, i) => i === 0 || Math.hypot(p.x - pts[i - 1].x, p.z - pts[i - 1].z) > 1e-9);
  }

  function coupe(a, b) {
    // Le segment [a, b] traverse-t-il l'intérieur du rectangle obstacle ? (Liang-Barsky)
    const e = 1e-6;
    const xmin = obstacle.x - obstacle.hx + e, xmax = obstacle.x + obstacle.hx - e;
    const zmin = obstacle.z - obstacle.hz + e, zmax = obstacle.z + obstacle.hz - e;
    const dx = b.x - a.x, dz = b.z - a.z;
    let t0 = 0, t1 = 1;
    for (const [p, q] of [[-dx, a.x - xmin], [dx, xmax - a.x], [-dz, a.z - zmin], [dz, zmax - a.z]]) {
      if (p === 0) { if (q < 0) return false; continue; }
      const r = q / p;
      if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; }
      else { if (r < t0) return false; if (r < t1) t1 = r; }
    }
    return t1 - t0 > 1e-9;
  }

  function contourner(p, q) {
    if (!coupe(p, q)) return [];
    const m = 0.05;
    const c = [
      {x: obstacle.x - obstacle.hx - m, z: obstacle.z - obstacle.hz - m},
      {x: obstacle.x + obstacle.hx + m, z: obstacle.z - obstacle.hz - m},
      {x: obstacle.x + obstacle.hx + m, z: obstacle.z + obstacle.hz + m},
      {x: obstacle.x - obstacle.hx - m, z: obstacle.z + obstacle.hz + m},
    ];
    const long = (l) => l.reduce((s, v, i) => s + Math.hypot(v.x - l[i - 1 < 0 ? 0 : i - 1].x, v.z - l[i - 1 < 0 ? 0 : i - 1].z), 0);
    let meilleur = null;
    const essayer = (milieu) => {
      const l = [p, ...milieu, q];
      for (let i = 1; i < l.length; i++) if (coupe(l[i - 1], l[i])) return;
      if (!meilleur || long(l) < long([p, ...meilleur, q])) meilleur = milieu;
    };
    for (let i = 0; i < 4; i++) {
      essayer([c[i]]);
      essayer([c[i], c[(i + 1) % 4]]);
      essayer([c[i], c[(i + 3) % 4]]);
    }
    return meilleur || [];
  }

  return {
    pieces, openspace, meubles, kanban, chef, directeur,
    batiment: {largeur: W, profondeur: H},
    poste, cafe, chemin, pieceDe, postit,
    aService: (id) => parService.has(id),
  };
}
