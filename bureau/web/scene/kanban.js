// Le tableau Kanban : colonnes, un post-it par tâche, la file d'attente, les débordements « +N ».
// Le tableau montre `regie.postits`, qui est en retard sur l'état tant qu'un agent n'a pas posé le post-it.

import * as THREE from "three";
import {PAS_TABLEAU, JEU_TABLEAU} from "../logique/plan.js";
import {fileDepliable, resteApresVisibles} from "../ui/texte.js";
import {vignettesVoulues, Vignettes} from "../logique/vignettes.js";

const COULEURS = ["#ffe27a", "#ffb3b0", "#c8f0b4", "#a8e4f0", "#ffd3a1", "#cbbcff"];
const PALE = "#f2ede2";
const HAUT = 2.04;                 // hauteur du bord supérieur de la surface utile (modèle Tripo : tableau 2,2 m de haut)
const DEVANT = 0.05;               // la surface se pose juste devant la face blanche du modèle
const POSTIT = {l: 0.22, h: 0.19, e: 0.014};
const COTE_MAX = 256;   // côté maximal (px) d'une vignette en mémoire : une photo de 4 k ne doit pas rester telle quelle sur la carte graphique
const VIGNETTE = {l: 0.18, h: 0.11, y: -0.025};   // cadre de la vignette sur un post-it (centré, un peu bas)

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

// Charge une image et la réduit à COTE_MAX px de côté au plus (ratio gardé) ; l'image d'origine n'est pas gardée.
// Rend un ImageBitmap (à fermer avec .close()), retourné à l'envers (flipY) comme three.js l'attend d'un ImageBitmap.
function chargerReduit(url, surSucces, surEchec) {
  const img = new Image();
  img.onload = async () => {
    try {
      const k = Math.min(1, COTE_MAX / Math.max(img.naturalWidth || 1, img.naturalHeight || 1));
      surSucces(await createImageBitmap(img, {
        resizeWidth: Math.max(1, Math.round(img.naturalWidth * k)),
        resizeHeight: Math.max(1, Math.round(img.naturalHeight * k)),
        resizeQuality: "medium", imageOrientation: "flipY",
      }));
    } catch { surEchec(); }
  };
  img.onerror = surEchec;
  img.src = url;
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
    this.pales = new Map();        // matériaux estompés (tâches exclues par le filtre de la vue liste)
    this.filtre = null;            // Set d'identifiants de tâches à montrer, ou null (tout montrer)
    this.postits = new Map();      // cle -> {mesh, cible: Vector3}
    this.signatureColonnes = null;
    this.signature = null;
    this.textes = new Map();
    this.vignettes = new Vignettes({
      charger: chargerReduit, creer: (id, image) => this._creerVignette(id, image),
      retirer: (id, objet) => this._retirerVignette(id, objet),
    });
  }

  _materiau(couleur) {
    if (!this.materiaux.has(couleur)) this.materiaux.set(couleur, new THREE.MeshLambertMaterial({color: couleur}));
    return this.materiaux.get(couleur);
  }

  _materiauEstompe(couleur) {
    if (!this.pales.has(couleur)) {
      this.pales.set(couleur, new THREE.MeshLambertMaterial({color: couleur, transparent: true, opacity: 0.25}));
    }
    return this.pales.get(couleur);
  }

  // La vue liste filtre : les post-its exclus s'estompent (opacité 0,25). `ids` null : tout est montré.
  estomper(ids) {
    this.filtre = ids || null;
    for (const e of this.postits.values()) this._appliquerFiltre(e);
  }

  _appliquerFiltre(e) {
    if (e.type !== "postit") return;
    const estompe = Boolean(this.filtre) && !this.filtre.has(e.id);
    if (e.estompe === estompe) return;
    e.estompe = estompe;
    e.mesh.material = estompe ? this._materiauEstompe(e.couleur) : this._materiau(e.couleur);
    e.mesh.castShadow = !estompe;
    if (e.vignetteMesh) e.vignetteMesh.material.opacity = estompe ? 0.25 : 1;
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
      reste = resteApresVisibles(file);
    }
    const cases = [];
    parColonne.forEach((col, i) => {
      const extra = i === 0 ? reste : 0;
      const place = extra > 0 ? k.lignes - 1 : k.lignes;
      let visibles = col, cache = 0;
      if (col.length > place) { visibles = col.slice(0, k.lignes - 1); cache = col.length - visibles.length; }
      visibles.forEach((c, rang) => cases.push({...c, colonne: i, rang}));
      if (cache + extra > 0) {
        // Dans la première colonne, le « + n » ouvre le panneau « File » quand la file a des éléments au-delà des visibles.
        const depliable = i === 0 && fileDepliable(file);
        cases.push({cle: "plus:" + i, type: "plus", texte: "+" + (cache + extra), depliable, colonne: i, rang: visibles.length});
      }
    });
    return cases;
  }

  synchroniser(colonnes, postits, taches, file, imagesOk = false) {
    const sigCol = JSON.stringify(colonnes.map((c) => [c.id, c.nom]));
    if (sigCol !== this.signatureColonnes) { this.signatureColonnes = sigCol; this._dessinerColonnes(colonnes); }
    const cases = this._disposition(colonnes, postits, taches, file);
    const sig = JSON.stringify(cases.map((c) => [c.cle, c.colonne, c.rang, c.texte, c.depliable]));
    if (sig !== this.signature) {
      this.signature = sig;
      this._placer(cases);
    }
    this._synchroniserVignettes(taches, imagesOk);
  }

  _placer(cases) {
    const vus = new Set();
    for (const c of cases) {
      vus.add(c.cle);
      const pos = this.plan.postit(c.colonne, c.rang);
      const cible = new THREE.Vector3(pos.u - this.k.largeur / 2, HAUT - pos.v, DEVANT + POSTIT.e / 2 + 0.004);
      let e = this.postits.get(c.cle);
      if (e && c.type === "plus" && (e.texte !== c.texte || e.depliable !== c.depliable)) { this._retirer(c.cle, e); e = null; }
      if (!e) {
        let mesh;
        if (c.type === "plus") {
          mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.26, 0.19),
                                new THREE.MeshBasicMaterial({map: texteTexture(c.texte), transparent: true}));
          if (c.depliable) {
            mesh.userData.choix = {type: "attente", id: null};
            this.sc.choisissables.push(mesh);
          }
        } else {
          mesh = new THREE.Mesh(this.geoPostit, this._materiau(c.couleur));
          mesh.castShadow = true;
          mesh.rotation.z = ((hachage(c.cle) % 9) - 4) * 0.012;
          if (c.type === "postit" || c.type === "file") {
            mesh.userData.choix = {type: c.type, id: c.id};
            this.sc.choisissables.push(mesh);
          }
        }
        mesh.position.copy(cible);
        mesh.scale.setScalar(0.01);
        this.groupe.add(mesh);
        e = {mesh, cible, texte: c.texte, depliable: c.depliable, type: c.type, id: c.id, couleur: c.couleur, estompe: false};
        this.postits.set(c.cle, e);
      }
      e.cible = cible;
      this._appliquerFiltre(e);
    }
    for (const [cle, e] of this.postits) if (!vus.has(cle)) this._retirer(cle, e);
  }

  // Une vignette (première image de la tâche) sur chaque post-it visible, seulement si les images sont servies.
  // Une texture par post-it, réduite ; remplacée à l'arrivée de la nouvelle, libérée quand le post-it disparaît.
  _synchroniserVignettes(taches, imagesOk) {
    const ids = [];
    for (const e of this.postits.values()) if (e.type === "postit") ids.push(e.id);
    this.vignettes.synchroniser(vignettesVoulues(imagesOk, taches, ids));
  }

  _creerVignette(id, bitmap) {
    const e = this.postits.get("t:" + id);
    if (!e) return null;
    const texture = new THREE.Texture(bitmap);
    texture.flipY = false;
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    const k = Math.min(VIGNETTE.l / bitmap.width, VIGNETTE.h / bitmap.height);
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(bitmap.width * k, bitmap.height * k),
                                new THREE.MeshBasicMaterial({map: texture, transparent: true}));
    mesh.position.set(0, VIGNETTE.y, POSTIT.e / 2 + 0.001);
    mesh.material.opacity = e.estompe ? 0.25 : 1;
    e.mesh.add(mesh);
    e.vignetteMesh = mesh;
    return {mesh, bitmap};
  }

  _retirerVignette(id, objet) {
    const e = this.postits.get("t:" + id);
    if (e && e.vignetteMesh === objet.mesh) e.vignetteMesh = null;
    objet.mesh.removeFromParent();
    objet.mesh.material.map.dispose();
    objet.mesh.material.dispose();
    objet.mesh.geometry.dispose();
    objet.bitmap.close();
  }

  _retirer(cle, e) {
    if (e.type === "postit") this.vignettes.oublier(e.id);
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
