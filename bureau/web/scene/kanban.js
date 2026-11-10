// Le tableau Kanban : colonnes, un post-it par tâche, la file d'attente, les débordements « +N ».
// Le tableau montre `regie.postits`, qui est en retard sur l'état tant qu'un agent n'a pas posé le post-it.

import * as THREE from "three";
import {PAS_TABLEAU, JEU_TABLEAU} from "../logique/plan.js";

const COULEURS = ["#ffe27a", "#ffb3b0", "#c8f0b4", "#a8e4f0", "#ffd3a1", "#cbbcff"];
const PALE = "#f2ede2";
const HAUT = 2.04;                 // hauteur du bord supérieur de la surface utile (modèle Tripo : tableau 2,2 m de haut)
const DEVANT = 0.05;               // la surface se pose juste devant la face blanche du modèle
const POSTIT = {l: 0.22, h: 0.19, e: 0.014};

function hachage(texte) {
  let h = 2166136261;
  for (const c of String(texte)) h = Math.imul(h ^ c.codePointAt(0), 16777619);
  return h >>> 0;
}

function texteTexture(texte, couleur = "#4a4e69") {
  const c = document.createElement("canvas");
  c.width = 128; c.height = 96;
  const x = c.getContext("2d");
  x.fillStyle = couleur;
  x.font = "bold 54px system-ui, sans-serif";
  x.textAlign = "center";
  x.textBaseline = "middle";
  x.fillText(texte, 64, 50);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Kanban {
  constructor(sc, plan, modeles) {
    this.sc = sc;
    this.plan = plan;
    const k = plan.kanban;
    this.k = k;
    this.groupe = new THREE.Group();
    this.groupe.position.set(k.x, 0, k.z);
    this.groupe.rotation.y = k.cap;
    if (modeles.aModele("tableau")) {
      // Un panneau (modèle de tableau sur pieds) tous les PAS_TABLEAU mètres.
      for (let i = 0; i < k.panneaux; i++) {
        const t = modeles.creer("tableau");
        t.position.x = -k.largeur / 2 - JEU_TABLEAU / 2 + PAS_TABLEAU * (i + 0.5);
        this.groupe.add(t);
      }
    } else {
      this.groupe.add(modeles.creer("tableau", {largeur: k.largeur}));
    }
    sc.scene.add(this.groupe);

    this.surface = new THREE.Mesh(new THREE.PlaneGeometry(k.largeur, k.hauteur), new THREE.MeshLambertMaterial({color: "#ffffff"}));
    this.surface.position.set(0, HAUT - k.hauteur / 2, DEVANT);
    this.surface.receiveShadow = true;
    this.groupe.add(this.surface);

    this.geoPostit = new THREE.BoxGeometry(POSTIT.l, POSTIT.h, POSTIT.e);
    this.materiaux = new Map();
    this.postits = new Map();      // cle -> {mesh, cible: Vector3}
    this.signatureColonnes = null;
    this.signature = null;
    this.textes = new Map();
  }

  _materiau(couleur) {
    if (!this.materiaux.has(couleur)) this.materiaux.set(couleur, new THREE.MeshLambertMaterial({color: couleur}));
    return this.materiaux.get(couleur);
  }

  _dessinerColonnes(colonnes) {
    const k = this.k;
    const L = 1024, H = Math.round(L * k.hauteur / k.largeur);
    const c = document.createElement("canvas");
    c.width = L; c.height = H;
    const x = c.getContext("2d");
    const px = L / k.largeur;
    x.fillStyle = "#fbfaf6";
    x.fillRect(0, 0, L, H);
    x.fillStyle = "#e9e4d8";
    x.fillRect(0, 0, L, k.entete * px);
    x.strokeStyle = "#d6cfbf";
    x.lineWidth = 3;
    const lc = k.largeurColonne * px;
    x.fillStyle = "#4a4e69";
    x.textAlign = "center";
    x.textBaseline = "middle";
    const taille = Math.max(14, Math.min(34, lc / 6));
    x.font = `600 ${taille}px system-ui, sans-serif`;
    colonnes.forEach((col, i) => {
      const gauche = 0.15 * px + i * lc;
      if (i > 0) { x.beginPath(); x.moveTo(gauche, 0.04 * px); x.lineTo(gauche, H - 0.04 * px); x.stroke(); }
      let nom = String(col.nom ?? col.id ?? "");
      while (nom.length > 1 && x.measureText(nom).width > lc - 12) nom = nom.slice(0, -2) + "…";
      x.fillText(nom, gauche + lc / 2, k.entete / 2 * px);
    });
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
    const ancien = this.surface.material.map;
    this.surface.material.map = t;
    this.surface.material.needsUpdate = true;
    if (ancien) ancien.dispose();
  }

  // Ce que le tableau doit montrer : une liste de cases {cle, type, couleur, colonne, rang, id, texte}.
  _disposition(colonnes, postits, taches, file) {
    const k = this.k;
    const parColonne = colonnes.map(() => []);
    const index = new Map(colonnes.map((c, i) => [c.id, i]));
    const ordre = new Map(taches.map((t, i) => [t.id, i]));
    const liste = [...postits.entries()].sort((a, b) => (ordre.get(a[0]) ?? 0) - (ordre.get(b[0]) ?? 0));
    for (const [id, p] of liste) {
      const i = index.get(p.colonne);
      if (i === undefined) continue;
      parColonne[i].push({cle: "t:" + id, type: "postit", id, couleur: COULEURS[hachage(id) % COULEURS.length]});
    }
    let reste = 0;
    if (parColonne.length && file) {
      for (const q of file.visibles || []) parColonne[0].push({cle: "q:" + q.id, type: "file", id: q.id, couleur: PALE});
      reste = Math.max(0, Number(file.reste) || 0);
    }
    const cases = [];
    parColonne.forEach((col, i) => {
      const extra = i === 0 ? reste : 0;
      const place = extra > 0 ? k.lignes - 1 : k.lignes;
      let visibles = col, cache = 0;
      if (col.length > place) { visibles = col.slice(0, k.lignes - 1); cache = col.length - visibles.length; }
      visibles.forEach((c, rang) => cases.push({...c, colonne: i, rang}));
      if (cache + extra > 0) cases.push({cle: "plus:" + i, type: "plus", texte: "+" + (cache + extra), colonne: i, rang: visibles.length});
    });
    return cases;
  }

  synchroniser(colonnes, postits, taches, file) {
    const sigCol = JSON.stringify(colonnes.map((c) => [c.id, c.nom]));
    if (sigCol !== this.signatureColonnes) { this.signatureColonnes = sigCol; this._dessinerColonnes(colonnes); }
    const cases = this._disposition(colonnes, postits, taches, file);
    const sig = JSON.stringify(cases.map((c) => [c.cle, c.colonne, c.rang, c.texte]));
    if (sig === this.signature) return;
    this.signature = sig;

    const vus = new Set();
    for (const c of cases) {
      vus.add(c.cle);
      const pos = this.plan.postit(c.colonne, c.rang);
      const cible = new THREE.Vector3(pos.u - this.k.largeur / 2, HAUT - pos.v, DEVANT + POSTIT.e / 2 + 0.004);
      let e = this.postits.get(c.cle);
      if (e && c.type === "plus" && e.texte !== c.texte) { this._retirer(c.cle, e); e = null; }
      if (!e) {
        let mesh;
        if (c.type === "plus") {
          mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.26, 0.19),
                                new THREE.MeshBasicMaterial({map: texteTexture(c.texte), transparent: true}));
        } else {
          mesh = new THREE.Mesh(this.geoPostit, this._materiau(c.couleur));
          mesh.castShadow = true;
          mesh.rotation.z = ((hachage(c.cle) % 9) - 4) * 0.012;
          if (c.type === "postit") {
            mesh.userData.choix = {type: "postit", id: c.id};
            this.sc.choisissables.push(mesh);
          }
        }
        mesh.position.copy(cible);
        mesh.scale.setScalar(0.01);
        this.groupe.add(mesh);
        e = {mesh, cible, texte: c.texte};
        this.postits.set(c.cle, e);
      }
      e.cible = cible;
    }
    for (const [cle, e] of this.postits) if (!vus.has(cle)) this._retirer(cle, e);
  }

  _retirer(cle, e) {
    this.groupe.remove(e.mesh);
    const i = this.sc.choisissables.indexOf(e.mesh);
    if (i >= 0) this.sc.choisissables.splice(i, 1);
    if (e.mesh.material.map) { e.mesh.material.map.dispose(); e.mesh.material.dispose(); e.mesh.geometry.dispose(); }
    this.postits.delete(cle);
  }

  // Les post-its glissent vers leur case et apparaissent en grandissant. Rend vrai tant que ça bouge.
  animer(dt) {
    const k = Math.min(1, dt * 8);
    let bouge = false;
    for (const e of this.postits.values()) {
      const m = e.mesh;
      if (m.position.distanceToSquared(e.cible) > 1e-7 || m.scale.x < 0.999) {
        m.position.lerp(e.cible, k);
        m.scale.setScalar(Math.min(1, m.scale.x + (1 - m.scale.x) * k + 0.002));
        bouge = true;
      }
    }
    return bouge;
  }
}
