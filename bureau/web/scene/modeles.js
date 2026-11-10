// Les modèles 3D : un GLB déclaré dans le manifeste s'il s'est chargé, sinon un volume simple
// de même encombrement. Un modèle manquant ne casse rien.
// Convention : l'avant de chaque objet regarde vers +z, sa base est posée à y = 0.

import * as THREE from "three";
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js";

export const NOMS = ["bureau", "chaise", "ecran", "armoire", "etagere", "plante", "machine_cafe",
                     "canape", "table_basse", "tableau", "bureau_direction", "personnage"];

const materiaux = new Map();
export function matiere(couleur, options = {}) {
  const cle = couleur + JSON.stringify(options);
  if (!materiaux.has(cle)) {
    const m = new THREE.MeshLambertMaterial({color: couleur, ...options});
    materiaux.set(cle, m);
    partages.add(m);
  }
  return materiaux.get(cle);
}
const partages = new Set();
export const estPartage = (m) => partages.has(m);

function ombre(o) {
  o.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
  return o;
}

function boite(g, l, h, p, couleur, x, y, z) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(l, h, p), matiere(couleur));
  m.position.set(x, y + h / 2, z);
  g.add(m);
  return m;
}

function cylindre(g, r1, r2, h, couleur, x, y, z, segments = 16) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, segments), matiere(couleur));
  m.position.set(x, y + h / 2, z);
  g.add(m);
  return m;
}

function boule(g, r, couleur, x, y, z) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), matiere(couleur));
  m.position.set(x, y, z);
  g.add(m);
  return m;
}

const BOIS = "#d9b48a", BOIS_FONCE = "#8a5a3b", PIED = "#6d6a73";

// Volumes simples : chunky, couleurs douces.
const VOLUMES = {
  bureau(g) {
    boite(g, 1.2, 0.06, 0.7, BOIS, 0, 0.69, 0);
    boite(g, 0.06, 0.69, 0.62, BOIS, -0.55, 0, 0);
    boite(g, 0.06, 0.69, 0.62, BOIS, 0.55, 0, 0);
    boite(g, 1.04, 0.32, 0.04, "#cfa57a", 0, 0.37, -0.28);
  },
  chaise(g) {
    cylindre(g, 0.22, 0.22, 0.04, PIED, 0, 0.02, 0);
    cylindre(g, 0.03, 0.03, 0.36, PIED, 0, 0.06, 0, 8);
    boite(g, 0.46, 0.08, 0.44, "#4fa3a5", 0, 0.42, 0);
    boite(g, 0.44, 0.42, 0.07, "#4fa3a5", 0, 0.5, -0.2);
  },
  ecran(g) {
    boite(g, 0.16, 0.02, 0.12, PIED, 0, 0, -0.05);
    boite(g, 0.03, 0.12, 0.03, PIED, 0, 0.02, -0.05);
    boite(g, 0.56, 0.32, 0.04, "#2e3440", 0, 0.12, -0.05);
    const face = boite(g, 0.5, 0.26, 0.005, "#8fc1e3", 0, 0.15, -0.028);
    face.material = matiere("#8fc1e3", {emissive: "#3c6f96", emissiveIntensity: 0.35});
    boite(g, 0.42, 0.02, 0.14, "#e8e4dc", 0, 0, 0.17);
  },
  armoire(g) {
    boite(g, 0.5, 0.7, 0.45, "#8fb3d9", 0, 0, 0);
    boite(g, 0.42, 0.01, 0.01, "#6d8fb6", 0, 0.35, 0.226);
    boite(g, 0.12, 0.03, 0.02, "#e8e4dc", 0, 0.55, 0.235);
    boite(g, 0.12, 0.03, 0.02, "#e8e4dc", 0, 0.2, 0.235);
  },
  etagere(g) {
    boite(g, 0.9, 1.6, 0.05, BOIS, 0, 0, -0.15);
    for (const x of [-0.43, 0.43]) boite(g, 0.04, 1.6, 0.35, BOIS, x, 0, 0);
    const couleurs = ["#e07a5f", "#3d8eb9", "#f2cc8f", "#81b29a", "#9d7bb0"];
    for (const [k, y] of [0.02, 0.52, 1.02, 1.52].entries()) {
      boite(g, 0.82, 0.04, 0.33, BOIS, 0, y, 0);
      if (y < 1.5) for (let i = 0; i < 4 + (k % 2); i++)
        boite(g, 0.09, 0.32 + 0.04 * ((i + k) % 2), 0.24, couleurs[(i + k) % 5], -0.3 + i * 0.13, y + 0.04, 0);
    }
  },
  plante(g) {
    cylindre(g, 0.2, 0.15, 0.32, "#d0835f", 0, 0, 0);
    boule(g, 0.24, "#6fa86b", 0, 0.52, 0);
    boule(g, 0.17, "#82bb76", 0.13, 0.66, 0.06);
    boule(g, 0.15, "#5d9a5c", -0.11, 0.7, -0.05);
  },
  machine_cafe(g) {
    boite(g, 0.9, 0.9, 0.55, BOIS, 0, 0, 0);
    boite(g, 0.38, 0.4, 0.34, "#d1495b", 0.1, 0.9, -0.04);
    boite(g, 0.3, 0.06, 0.06, "#2e3440", 0.1, 1.05, 0.15);
    cylindre(g, 0.04, 0.035, 0.08, "#f7f1e6", -0.25, 0.9, 0.08, 10);
    cylindre(g, 0.04, 0.035, 0.08, "#f7f1e6", -0.33, 0.9, -0.05, 10);
  },
  canape(g) {
    const C = "#e0b04a";
    boite(g, 1.6, 0.22, 0.75, "#c99a3a", 0, 0.08, 0);
    boite(g, 1.4, 0.14, 0.62, C, 0, 0.3, 0.05);
    boite(g, 1.6, 0.42, 0.18, C, 0, 0.3, -0.29);
    for (const x of [-0.74, 0.74]) boite(g, 0.14, 0.3, 0.75, C, x, 0.3, 0);
  },
  table_basse(g) {
    cylindre(g, 0.45, 0.45, 0.06, BOIS, 0, 0.34, 0, 24);
    cylindre(g, 0.05, 0.08, 0.34, BOIS_FONCE, 0, 0, 0, 10);
    cylindre(g, 0.04, 0.035, 0.08, "#f2cc8f", 0.15, 0.4, 0.05, 10);
    cylindre(g, 0.04, 0.035, 0.08, "#81b29a", -0.12, 0.4, -0.1, 10);
  },
  tableau(g, {largeur = 3} = {}) {
    // Cadre et pieds seulement : la surface et les post-its sont dessinés par kanban.js.
    // Surface utile : 1,25 m de haut, bord supérieur à 2,04 m (voir kanban.js).
    for (const x of [-largeur / 2 + 0.1, largeur / 2 - 0.1]) {
      boite(g, 0.06, 2.05, 0.06, PIED, x, 0, -0.04);
      boite(g, 0.1, 0.05, 0.7, PIED, x, 0, -0.04);
    }
    boite(g, largeur + 0.1, 1.37, 0.06, "#8d99ae", 0, 0.73, -0.04);
  },
  bureau_direction(g) {
    boite(g, 2.0, 0.08, 0.9, "#7a4b31", 0, 0.7, 0);
    boite(g, 1.9, 0.7, 0.8, "#6a3f29", 0, 0, -0.02);
    boite(g, 0.5, 0.02, 0.35, "#3d6b4a", -0.35, 0.78, 0);
    cylindre(g, 0.08, 0.1, 0.03, "#2e5e3e", 0.65, 0.78, -0.2, 12);
    cylindre(g, 0.015, 0.015, 0.3, "#c9a94a", 0.65, 0.81, -0.2, 6);
    const abat = cylindre(g, 0.06, 0.13, 0.12, "#2f7a4d", 0.65, 1.08, -0.15, 14);
    abat.rotation.x = 0.35;
  },
  personnage(g) {
    // Figurine trapue articulée : hanches, jambes, buste, bras, tête.
    // Le buste et les bras portent la couleur de l'agent (matériau propre à chaque copie).
    const peau = matiere("#f1cfae");
    const pantalon = matiere("#4a4e69");
    const tenue = new THREE.MeshLambertMaterial({color: "#cccccc"});
    const art = {};
    const corps = new THREE.Group();
    g.add(corps);
    art.corps = corps;
    for (const [nom, x] of [["jambeG", -0.085], ["jambeD", 0.085]]) {
      const pivot = new THREE.Group();
      pivot.position.set(x, 0.4, 0);
      const m = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.24, 4, 10), pantalon);
      m.position.y = -0.2;
      pivot.add(m);
      corps.add(pivot);
      art[nom] = pivot;
    }
    const buste = new THREE.Mesh(new THREE.CapsuleGeometry(0.18, 0.22, 4, 14), tenue);
    buste.position.y = 0.6;
    buste.scale.set(1, 1, 0.82);
    corps.add(buste);
    for (const [nom, x] of [["brasG", -0.225], ["brasD", 0.225]]) {
      const pivot = new THREE.Group();
      pivot.position.set(x, 0.76, 0);
      const m = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.22, 4, 8), tenue);
      m.position.y = -0.15;
      pivot.add(m);
      const main = new THREE.Mesh(new THREE.SphereGeometry(0.055, 10, 8), peau);
      main.position.y = -0.3;
      pivot.add(main);
      corps.add(pivot);
      art[nom] = pivot;
    }
    const tete = new THREE.Group();
    tete.position.y = 0.98;
    const crane = new THREE.Mesh(new THREE.SphereGeometry(0.21, 20, 16), peau);
    tete.add(crane);
    const cheveux = new THREE.Mesh(new THREE.SphereGeometry(0.22, 20, 12, 0, Math.PI * 2, 0, Math.PI * 0.42), tenue);
    cheveux.position.y = 0.015;
    cheveux.rotation.x = -0.25;
    tete.add(cheveux);
    for (const x of [-0.07, 0.07]) {
      const oeil = new THREE.Mesh(new THREE.SphereGeometry(0.022, 8, 6), matiere("#2e3440"));
      oeil.position.set(x, 0.01, 0.195);
      tete.add(oeil);
    }
    corps.add(tete);
    art.tete = tete;
    const tasse = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.04, 0.09, 10), matiere("#f7f1e6"));
    tasse.position.set(0, -0.33, 0.05);
    tasse.visible = false;
    art.brasD.add(tasse);
    art.tasse = tasse;
    g.userData.articulations = art;
    g.userData.tenue = tenue;
    g.userData.cheveux = cheveux;
  },
};

function volume(nom, options) {
  const g = new THREE.Group();
  g.name = nom;
  (VOLUMES[nom] || ((x) => boite(x, 0.5, 0.5, 0.5, "#cccccc", 0, 0, 0)))(g, options);
  return ombre(g);
}

// Charge le manifeste et les GLB qu'il déclare. Rien ne lève : un échec donne un volume simple.
export async function charger(manifesteUrl) {
  let manifeste = {};
  try {
    const r = await fetch(manifesteUrl, {cache: "no-cache"});
    if (r.ok) manifeste = await r.json();
  } catch { manifeste = {}; }

  const base = new URL(manifesteUrl, location.href);
  const chargeur = new GLTFLoader();
  const prets = new Map();
  await Promise.all(Object.entries(manifeste || {}).map(async ([nom, entree]) => {
    if (!entree || !entree.fichier) return;
    try {
      const gltf = await chargeur.loadAsync(new URL(entree.fichier, base).href);
      const racine = gltf.scene;
      const boiteEnglobante = new THREE.Box3().setFromObject(racine);
      const taille = boiteEnglobante.getSize(new THREE.Vector3());
      const echelle = entree.hauteur && taille.y > 0 ? entree.hauteur / taille.y : 1;
      const centre = boiteEnglobante.getCenter(new THREE.Vector3());
      racine.position.set(-centre.x * echelle, -boiteEnglobante.min.y * echelle, -centre.z * echelle);
      racine.scale.setScalar(echelle);
      const g = new THREE.Group();
      g.name = nom;
      g.add(racine);
      g.userData.animations = gltf.animations || [];
      prets.set(nom, ombre(g));
    } catch (e) {
      console.warn(`Modèle « ${nom} » indisponible, volume simple utilisé.`, e);
    }
  }));

  return {
    aModele: (nom) => prets.has(nom),
    creer(nom, options = {}) {
      const modele = prets.get(nom);
      if (!modele) return volume(nom, options);
      const copie = SkeletonUtils.clone(modele);
      copie.userData.animations = modele.userData.animations;
      return copie;
    },
  };
}
