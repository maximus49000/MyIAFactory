// La scène : caméra isométrique, lumière, sol, murs, meubles, noms des pièces.

import * as THREE from "three";
import {CSS2DRenderer, CSS2DObject} from "three/addons/renderers/CSS2DRenderer.js";
import {matiere} from "./modeles.js";
import {tronquer} from "../ui/texte.js";
import {decalageBorne, ZOOM_MIN, ZOOM_MAX} from "../logique/mobile.js";

const SOLS_SERVICES = ["#cfe3d2", "#d5dcf0", "#f3dccb", "#ece3b5", "#d3ebee", "#eed5e2"];
const SOL_CAFE = "#f0c7a2", SOL_DIRECTION = "#b8cdb0", SOL_PARTENAIRES = "#c3d0e6", SOL_OPEN = "#ead9bf";
const MUR = "#f7f1e6", CHAPEAU = "#d9c7ad", SOCLE = "#c9b79d";
const HAUT_MUR = 2.4, MI_MUR = 0.75, BAS_MUR = 0.22, EPAIS = 0.12;
const MARGE = 1.6;

const LUMIERE = {
  jour: {ciel: new THREE.Color("#fff6e8"), sol: new THREE.Color("#b49a7c"), hemi: 1.55, soleil: 1.9, teinte: new THREE.Color("#fff1dc")},
  pause: {ciel: new THREE.Color("#b3bde0"), sol: new THREE.Color("#7a7088"), hemi: 1.05, soleil: 0.75, teinte: new THREE.Color("#c4cdf0")},
};

// Petite texture de bruit doux, pour que les sols ne soient pas des aplats (effet gouache).
function textureSol(lames) {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const x = c.getContext("2d");
  x.fillStyle = "#ffffff";
  x.fillRect(0, 0, 256, 256);
  let graine = 7;
  const alea = () => ((graine = (graine * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 1800; i++) {
    const g = 225 + Math.floor(alea() * 30);
    x.fillStyle = `rgba(${g},${g},${g},0.35)`;
    x.fillRect(alea() * 256, alea() * 256, 2 + alea() * 6, 1 + alea() * 3);
  }
  if (lames) {
    x.strokeStyle = "rgba(150,120,90,0.22)";
    x.lineWidth = 2;
    for (let y = 0; y <= 256; y += 32) { x.beginPath(); x.moveTo(0, y); x.lineTo(256, y); x.stroke(); }
    for (let r = 0; r < 8; r++) {
      const dx = (r * 97) % 256;
      x.beginPath(); x.moveTo(dx, r * 32); x.lineTo(dx, r * 32 + 32); x.stroke();
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 4;
  return t;
}

// `options.mobile` : sur un téléphone ou une tablette, la définition reste plafonnée à 1,5 × et les ombres sont
// coupées (la scène reste la même ; sur ordinateur rien ne change).
export function creerScene(conteneur, plan, modeles, options = {}) {
  const mobile = options.mobile === true;
  const scene = new THREE.Scene();

  const rendu3d = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: "low-power"});
  rendu3d.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  rendu3d.shadowMap.enabled = !mobile;
  rendu3d.shadowMap.type = THREE.PCFSoftShadowMap;
  rendu3d.shadowMap.autoUpdate = false;   // recalculées seulement quand quelqu'un se déplace (légèreté)
  rendu3d.outputColorSpace = THREE.SRGBColorSpace;
  rendu3d.toneMapping = THREE.ACESFilmicToneMapping;
  rendu3d.toneMappingExposure = 1.05;
  conteneur.appendChild(rendu3d.domElement);

  const rendu2d = new CSS2DRenderer();
  rendu2d.domElement.className = "calque-etiquettes";
  conteneur.appendChild(rendu2d.domElement);

  // --- Caméra orthographique isométrique : 45° autour de la verticale, 35,264° d'inclinaison.
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 200);
  const D = 60;
  camera.position.set(D, D, D);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();

  // --- Lumière : ciel chaud, soleil rasant qui donne des ombres douces.
  const hemi = new THREE.HemisphereLight(LUMIERE.jour.ciel, LUMIERE.jour.sol, LUMIERE.jour.hemi);
  scene.add(hemi);
  const soleil = new THREE.DirectionalLight(LUMIERE.jour.teinte, LUMIERE.jour.soleil);
  soleil.position.set(-9, 22, 7);
  soleil.castShadow = !mobile;
  const W = plan.batiment.largeur, H = plan.batiment.profondeur;
  const demi = Math.max(W, H) * 0.75;
  Object.assign(soleil.shadow.camera, {left: -demi, right: demi, top: demi, bottom: -demi, near: 1, far: 70});
  soleil.shadow.mapSize.set(2048, 2048);
  soleil.shadow.bias = -0.0004;
  soleil.shadow.normalBias = 0.02;
  soleil.shadow.radius = 4;
  scene.add(soleil);
  scene.add(soleil.target);

  const choisissables = [];
  let derniereOmbre = -Infinity;

  // --- Socle et sols.
  const socle = new THREE.Mesh(new THREE.BoxGeometry(W + 0.8, 0.5, H + 0.8), matiere(SOCLE));
  socle.position.y = -0.27;
  socle.receiveShadow = true;
  scene.add(socle);

  const texBruit = textureSol(false), texLames = textureSol(true);
  function sol(r, couleur, tex, repet, type, id) {
    const t = tex.clone();
    t.needsUpdate = true;
    t.repeat.set(r.largeur / repet, r.profondeur / repet);
    const m = new THREE.Mesh(new THREE.BoxGeometry(r.largeur, 0.04, r.profondeur),
                             new THREE.MeshLambertMaterial({color: couleur, map: t}));
    m.position.set(r.x, -0.02, r.z);
    m.receiveShadow = true;
    m.userData.choix = {type, id};
    scene.add(m);
    choisissables.push(m);
  }
  sol(plan.openspace, SOL_OPEN, texLames, 2.5, null, null);
  let iService = 0;
  for (const r of plan.pieces) {
    if (r.type === "service") sol(r, SOLS_SERVICES[iService++ % SOLS_SERVICES.length], texBruit, 3, "service", r.id);
    else if (r.type === "cafe") sol(r, SOL_CAFE, texBruit, 3, "cafe", r.id);
    else if (r.type === "partenaires") sol(r, SOL_PARTENAIRES, texBruit, 3, "partenaires", r.id);
    else sol(r, SOL_DIRECTION, texBruit, 3, "direction", r.id);
  }

  // --- Murs : grille de cellules de 0,5 m, un mur entre deux zones différentes, sauf aux portes.
  // Murs extérieurs du fond (nord, ouest) hauts ; ceux qui font face à la caméra (sud, est) rasés ;
  // cloisons intérieures à mi-hauteur, pour voir dans toutes les pièces.
  const zones = [...plan.pieces, plan.openspace];
  const C = 0.5;
  const nx = Math.round(W / C), nz = Math.round(H / C);
  const x0 = -W / 2, z0 = -H / 2;
  const zone = (i, j) => {
    if (i < 0 || j < 0 || i >= nx || j >= nz) return null;
    const x = x0 + (i + 0.5) * C, z = z0 + (j + 0.5) * C;
    return zones.find((r) => Math.abs(x - r.x) < r.largeur / 2 && Math.abs(z - r.z) < r.profondeur / 2) || null;
  };
  const grille = [];
  for (let i = 0; i < nx; i++) { grille.push([]); for (let j = 0; j < nz; j++) grille[i].push(zone(i, j)); }
  const z_ = (i, j) => (i < 0 || j < 0 || i >= nx || j >= nz ? null : grille[i][j]);
  const estPorte = (x, z) => plan.pieces.some((r) => Math.abs(z - r.porte.z) < 0.01 && Math.abs(x - r.porte.x) < r.porte.largeur / 2);

  const segments = []; // {axe: "x"|"z", fixe, debut, fin, hauteur}
  // Murs horizontaux (le long de x), entre la cellule (i, j-1) et (i, j).
  for (let j = 0; j <= nz; j++) for (let i = 0; i < nx; i++) {
    const a = z_(i, j - 1), b = z_(i, j);
    if (a === b) continue;
    const x = x0 + (i + 0.5) * C, z = z0 + j * C;
    if (a && b && estPorte(x, z)) continue;
    const h = !a ? HAUT_MUR : !b ? BAS_MUR : MI_MUR;
    segments.push({axe: "x", fixe: z, debut: x0 + i * C, fin: x0 + (i + 1) * C, hauteur: h});
  }
  // Murs verticaux (le long de z), entre la cellule (i-1, j) et (i, j).
  for (let i = 0; i <= nx; i++) for (let j = 0; j < nz; j++) {
    const a = z_(i - 1, j), b = z_(i, j);
    if (a === b) continue;
    const h = !a ? HAUT_MUR : !b ? BAS_MUR : MI_MUR;
    segments.push({axe: "z", fixe: x0 + i * C, debut: z0 + j * C, fin: z0 + (j + 1) * C, hauteur: h});
  }
  // Fusion des segments alignés et jointifs de même hauteur.
  segments.sort((p, q) => (p.axe + p.fixe + p.hauteur).localeCompare(q.axe + q.fixe + q.hauteur) || p.debut - q.debut);
  const murs = [];
  for (const s of segments) {
    const d = murs.at(-1);
    if (d && d.axe === s.axe && Math.abs(d.fixe - s.fixe) < 1e-6 && d.hauteur === s.hauteur && Math.abs(d.fin - s.debut) < 1e-6) d.fin = s.fin;
    else murs.push({...s});
  }
  const groupeMurs = new THREE.Group();
  for (const m of murs) {
    const long = m.fin - m.debut + EPAIS;
    const milieu = (m.debut + m.fin) / 2;
    const [l, p] = m.axe === "x" ? [long, EPAIS] : [EPAIS, long];
    const [x, z] = m.axe === "x" ? [milieu, m.fixe] : [m.fixe, milieu];
    const mur = new THREE.Mesh(new THREE.BoxGeometry(l, m.hauteur, p), matiere(MUR));
    mur.position.set(x, m.hauteur / 2, z);
    mur.castShadow = m.hauteur > BAS_MUR;
    mur.receiveShadow = true;
    groupeMurs.add(mur);
    const chapeau = new THREE.Mesh(new THREE.BoxGeometry(l + 0.02, 0.05, p + 0.04), matiere(CHAPEAU));
    chapeau.position.set(x, m.hauteur + 0.025, z);
    groupeMurs.add(chapeau);
  }
  scene.add(groupeMurs);

  // Fenêtres sur les grands murs du fond : des rectangles clairs, pour la lumière du jour.
  const vitre = matiere("#cfe6f2", {emissive: "#9fc7e0", emissiveIntensity: 0.25});
  for (const m of murs) {
    if (m.hauteur !== HAUT_MUR) continue;
    const long = m.fin - m.debut;
    const n = Math.floor(long / 3);
    for (let k = 0; k < n; k++) {
      const t = m.debut + (k + 0.5) * (long / n);
      const f = new THREE.Mesh(new THREE.BoxGeometry(m.axe === "x" ? 1.3 : 0.02, 0.9, m.axe === "x" ? 0.02 : 1.3), vitre);
      // la vitre est sur la face intérieure du mur (côté +z pour un mur nord, +x pour un mur ouest)
      if (m.axe === "x") f.position.set(t, 1.45, m.fixe + EPAIS / 2 + 0.005);
      else f.position.set(m.fixe + EPAIS / 2 + 0.005, 1.45, t);
      groupeMurs.add(f);
    }
  }

  // --- Meubles du plan.
  const groupeMeubles = new THREE.Group();
  for (const m of plan.meubles) {
    const o = modeles.creer(m.nom);
    o.position.set(m.x, m.nom === "ecran" ? 0.75 : 0, m.z);
    o.rotation.y = m.cap;
    groupeMeubles.add(o);
  }
  scene.add(groupeMeubles);

  // Le Directeur (l'utilisateur) est un personnage fixe à son bureau, posé par main.js via personnages.

  // --- Noms des pièces : au sol, dans le coin côté porte (loin des bulles des agents assis au fond).
  for (const r of plan.pieces) {
    const div = document.createElement("div");
    div.className = "nom-piece nom-" + r.type;
    div.textContent = tronquer(r.nom, 24);
    div.title = r.nom ?? "";
    const o = new CSS2DObject(div);
    // rangée du haut : coin gauche ; rangée du bas : coin droit (le Directeur se tient au milieu)
    const gauche = r.dir > 0;
    o.position.set(r.x + (gauche ? -1 : 1) * (r.largeur / 2 - 0.5), 0.05, r.porte.z - r.dir * 0.45);
    o.center.set(gauche ? 0 : 1, 0.5);
    scene.add(o);
  }

  // --- Cadrage : tout le bâtiment, avec une marge, quel que soit le format de la fenêtre.
  const coins = [];
  for (const x of [-W / 2 - 0.4, W / 2 + 0.4]) for (const z of [-H / 2 - 0.4, H / 2 + 0.4]) for (const y of [-0.5, HAUT_MUR + 0.8]) coins.push(new THREE.Vector3(x, y, z));
  // La vue : le cadrage d'ensemble (`base`), puis le zoom et le décalage du doigt, bornés au bâtiment.
  const vue = {zoom: 1, dx: 0, dy: 0};
  let base = null;
  function appliquerVue() {
    if (!base) return;
    [vue.dx, vue.dy] = decalageBorne([vue.dx, vue.dy], vue.zoom, [base.lv / 2, base.hv / 2]);
    const lv = base.lv / vue.zoom, hv = base.hv / vue.zoom;
    const cx = base.cx + vue.dx, cy = base.cy + vue.dy;
    Object.assign(camera, {left: cx - lv / 2, right: cx + lv / 2, top: cy + hv / 2, bottom: cy - hv / 2});
    camera.updateProjectionMatrix();
  }
  function zoomer(zoom) {
    vue.zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number.isFinite(zoom) ? zoom : vue.zoom));
    appliquerVue();
    return vue.zoom;
  }
  // Un glissement du doigt de (dxPx, dyPx) pixels : la scène suit le doigt.
  function deplacer(dxPx, dyPx) {
    if (!base) return;
    const unite = (base.lv / vue.zoom) / (conteneur.clientWidth || 1);
    vue.dx -= dxPx * unite;
    vue.dy += dyPx * unite;
    appliquerVue();
  }
  function redimensionner() {
    const l = conteneur.clientWidth || 1, h = conteneur.clientHeight || 1;
    rendu3d.setSize(l, h);
    rendu2d.setSize(l, h);
    let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
    for (const c of coins) {
      const v = c.clone().applyMatrix4(camera.matrixWorldInverse);
      xmin = Math.min(xmin, v.x); xmax = Math.max(xmax, v.x); ymin = Math.min(ymin, v.y); ymax = Math.max(ymax, v.y);
    }
    xmin -= MARGE; xmax += MARGE; ymin -= MARGE; ymax += MARGE;
    const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
    let lv = xmax - xmin, hv = ymax - ymin;
    if (lv / hv > l / h) hv = lv * h / l; else lv = hv * l / h;
    base = {cx, cy, lv, hv};
    appliquerVue();
  }
  redimensionner();

  // --- Pause : la lumière baisse doucement.
  let sombre = false, melange = 0;
  function assombrir(oui) { sombre = Boolean(oui); }
  function transition(dt) {
    const cible = sombre ? 1 : 0;
    if (Math.abs(melange - cible) < 1e-3) return false;
    melange += Math.sign(cible - melange) * Math.min(Math.abs(cible - melange), dt / 1.2);
    const j = LUMIERE.jour, p = LUMIERE.pause, t = melange;
    hemi.color.copy(j.ciel).lerp(p.ciel, t);
    hemi.groundColor.copy(j.sol).lerp(p.sol, t);
    hemi.intensity = j.hemi + (p.hemi - j.hemi) * t;
    soleil.color.copy(j.teinte).lerp(p.teinte, t);
    soleil.intensity = j.soleil + (p.soleil - j.soleil) * t;
    document.documentElement.style.setProperty("--pause", t.toFixed(3));
    return true;
  }

  // --- Ce qu'il y a sous le pointeur.
  const rayon = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  function pointer(evenement) {
    const r = rendu3d.domElement.getBoundingClientRect();
    ndc.set(((evenement.clientX - r.left) / r.width) * 2 - 1, -((evenement.clientY - r.top) / r.height) * 2 + 1);
    rayon.setFromCamera(ndc, camera);
    for (const hit of rayon.intersectObjects(choisissables, true)) {
      for (let o = hit.object; o; o = o.parent) if (o.userData.choix) {
        if (o.userData.choix.type) return {...o.userData.choix};
        break;
      }
    }
    return {type: null, id: null};
  }

  return {
    scene, camera, choisissables,
    // majOmbres : vrai quand un personnage s'est déplacé ; sinon les ombres ne sont refaites qu'une fois par seconde
    // (les petits gestes sur place ne changent pas visiblement les ombres).
    rendu(majOmbres = true) {
      const t = performance.now();
      if (majOmbres || t - derniereOmbre > 1000) { rendu3d.shadowMap.needsUpdate = true; derniereOmbre = t; }
      rendu3d.render(scene, camera);
      rendu2d.render(scene, camera);
    },
    redimensionner, assombrir, transition, pointer,
    zoom: () => vue.zoom, zoomer, deplacer,
  };
}
