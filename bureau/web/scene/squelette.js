// Le personnage Tripo : un modèle à squelette (os nommés à la Mixamo) avec une animation de marche.
// La marche vient du modèle ; les autres poses (assis, taper, café, post-it) sont fabriquées ici
// en tournant les os. La teinte de l'agent ne colore que le pull (gris clair dans le modèle).

import * as THREE from "three";

// Vitesse des pieds au sol pendant la marche du modèle, en hauteurs de personnage par seconde
// d'animation (mesurée sur le modèle dans Blender : 0,0173 m par image à 24 images/s, pour 1,024 m).
const VITESSE_PIEDS = 0.405;
// Le pull occupe cette tranche de la hauteur du modèle au repos (bas du pull → épaules).
const BANDE_PULL = [0.36, 0.72];

const OS = {
  hanches: "Hips", buste: "Spine1", cou: "Neck", tete: "Head",
  cuisseG: "LeftUpLeg", genouG: "LeftLeg", cuisseD: "RightUpLeg", genouD: "RightLeg",
  brasG: "LeftArm", avantBrasG: "LeftForeArm", brasD: "RightArm", avantBrasD: "RightForeArm",
  mainD: "RightHand",
};

const _q = new THREE.Quaternion();
const _e = new THREE.Euler();
const _v = new THREE.Vector3();

function trouverOs(liste, nom) {
  return liste.find((b) => b.name === "mixamorig" + nom || b.name === "mixamorig:" + nom)
      || liste.find((b) => b.name.endsWith(nom)) || null;
}

// Pull teinté : le gris clair et peu saturé de la tranche du pull prend la couleur de l'agent,
// en gardant les ombres peintes. La peau, les cheveux, le pantalon et les chaussures ne changent pas.
function teinter(mesh, teinte) {
  const geo = mesh.geometry;
  if (!geo.userData.hauteurRepos) {
    mesh.updateWorldMatrix(true, false);
    const inv = new THREE.Matrix3().setFromMatrix4(mesh.matrixWorld).invert();
    const axe = new THREE.Vector3(0, 1, 0).applyMatrix3(inv).normalize();
    const pos = geo.attributes.position;
    let bas = Infinity, haut = -Infinity;
    for (let i = 0; i < pos.count; i++) {
      const h = _v.fromBufferAttribute(pos, i).dot(axe);
      if (h < bas) bas = h;
      if (h > haut) haut = h;
    }
    geo.userData.hauteurRepos = {axe, bas, haut};
  }
  const {axe, bas, haut} = geo.userData.hauteurRepos;
  const mat = mesh.material.clone();
  mat.onBeforeCompile = (s) => {
    s.uniforms.uTeinte = teinte;
    s.uniforms.uAxe = {value: axe};
    s.uniforms.uBas = {value: bas};
    s.uniforms.uHaut = {value: haut};
    s.vertexShader = "uniform vec3 uAxe;\nuniform float uBas;\nuniform float uHaut;\nvarying float vHauteur;\n"
      + s.vertexShader.replace("#include <begin_vertex>",
        "#include <begin_vertex>\nvHauteur = (dot(position, uAxe) - uBas) / (uHaut - uBas);");
    s.fragmentShader = "uniform vec3 uTeinte;\nvarying float vHauteur;\n"
      + s.fragmentShader.replace("#include <map_fragment>", `#include <map_fragment>
        {
          vec3 c = diffuseColor.rgb;
          float sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
          float lum = dot(c, vec3(0.3333));
          float masque = (1.0 - smoothstep(0.04, 0.1, sat))
                       * smoothstep(0.22, 0.35, lum)
                       * smoothstep(${BANDE_PULL[0].toFixed(3)} - 0.015, ${BANDE_PULL[0].toFixed(3)} + 0.01, vHauteur)
                       * (1.0 - smoothstep(${BANDE_PULL[1].toFixed(3)} - 0.01, ${BANDE_PULL[1].toFixed(3)} + 0.015, vHauteur));
          diffuseColor.rgb = mix(c, uTeinte * min(lum / 0.55, 1.15), masque);
        }`);
  };
  mat.customProgramCacheKey = () => "personnage-teinte";
  mesh.material = mat;
}

// Prépare une copie du modèle : os utiles, repos, animation de marche, teinte.
// g vient d'être cloné et n'est encore ni tourné ni déplacé.
export function preparer(g) {
  g.updateMatrixWorld(true);
  const racine = g.children[0];
  const liste = [];
  const peaux = [];
  g.traverse((o) => { if (o.isBone) liste.push(o); if (o.isSkinnedMesh) peaux.push(o); });
  if (!liste.length) return null;

  const tous = liste.map((o) => {
    const P = o.parent.getWorldQuaternion(new THREE.Quaternion());
    return {o, repos: o.quaternion.clone(), reposPos: o.position.clone(), P, Pinv: P.clone().invert(),
            courant: o.quaternion.clone(), cible: o.quaternion.clone()};
  });
  const os = {};
  for (const [cle, nom] of Object.entries(OS)) {
    const b = trouverOs(liste, nom);
    os[cle] = b ? tous.find((t) => t.o === b) : null;
  }

  const teinte = {value: new THREE.Color("#cccccc")};
  for (const m of peaux) teinter(m, teinte);

  const hauteur = new THREE.Box3().setFromObject(racine).getSize(_v).y || 1;
  const clips = g.userData.animations || [];
  const clip = clips.find((c) => /marche|walk/i.test(c.name)) || clips[0] || null;
  const mixer = clip ? new THREE.AnimationMixer(g) : null;
  if (mixer) mixer.clipAction(clip).play();

  const tasse = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.04, 0.09, 10),
                               new THREE.MeshLambertMaterial({color: "#f7f1e6"}));
  tasse.visible = false;
  tasse.castShadow = true;
  g.add(tasse);

  return {racine, baseY: racine.position.y, tous, os, teinte, hauteur, mixer, clip, tasse,
          tMarche: 0, poidsMarche: 0, vitesseAnim: VITESSE_PIEDS * hauteur};
}

// Pose d'un os : rotation exprimée dans les axes du personnage au repos (x vers sa gauche,
// y vers le haut, z vers l'avant), appliquée par-dessus la pose de repos et portée par le parent.
function viser(b, x, y, z) {
  if (!b) return;
  _e.set(x, y, z, "XYZ");
  _q.setFromEuler(_e);
  b.cible.copy(b.Pinv).multiply(_q).multiply(b.P).multiply(b.repos);
}

const BAS = 1.32; // bras le long du corps, un peu écartés

// p : {marche, parcouru, assise (0..1), action, travaille, enPoste, assis, t, dt}
export function animer(sq, p) {
  const {os} = sq;
  const k = Math.min(1, p.dt * 10);
  for (const b of sq.tous) b.cible.copy(b.repos);

  // Bras : épaule (avant = levé vers l'avant depuis le bas), coude (pliure vers l'avant).
  let avantG = 0.05, avantD = 0.05, coudeG = 0.15, coudeD = 0.15, tete = 0, buste = 0;
  const t = p.t;
  if (p.action === "postit") {
    avantD = 2.35 + Math.sin(t * 6) * 0.06; coudeD = 0.25; tete = -0.2;
  } else if (p.action === "cafe") {
    const gorgee = (Math.sin(t * 0.7) + 1) / 2 > 0.85;
    avantD = gorgee ? 0.95 : 0.45; coudeD = gorgee ? 2.1 : 1.6;
    if (p.assis) { avantG = 0.5; coudeG = 0.5; }
    tete = gorgee ? -0.25 : Math.sin(t * 0.5) * 0.08;
  } else if (p.enPoste && p.travaille) {
    // Taper au clavier (assis) ou griffonner (debout) : les avant-bras battent en alternance.
    avantG = avantD = p.assis ? 0.55 : 0.35;
    coudeG = 1.05 + Math.sin(t * 13) * 0.12;
    coudeD = 1.05 + Math.sin(t * 13 + Math.PI) * 0.12;
    tete = 0.15 + Math.sin(t * 1.3) * 0.04;
    buste = 0.08;
  } else if (p.enPoste) {
    // Sans nouvelles : immobile, la tête basse.
    avantG = avantD = p.assis ? 0.5 : 0.05; coudeG = coudeD = p.assis ? 0.9 : 0.15;
    tete = 0.35;
  } else {
    const s = Math.sin(t * 1.1) * 0.04;
    avantG += s; avantD -= s;
  }
  viser(os.brasG, -avantG, 0, -BAS);
  viser(os.brasD, -avantD, 0, BAS);
  viser(os.avantBrasG, 0, -coudeG, 0);
  viser(os.avantBrasD, 0, coudeD, 0);
  viser(os.tete, tete, 0, 0);
  viser(os.buste, buste, 0, 0);
  if (p.assise > 0.001) {
    viser(os.cuisseG, -Math.PI / 2 * p.assise, 0, 0);
    viser(os.cuisseD, -Math.PI / 2 * p.assise, 0, 0);
    viser(os.genouG, Math.PI / 2 * p.assise, 0, 0);
    viser(os.genouD, Math.PI / 2 * p.assise, 0, 0);
  }

  for (const b of sq.tous) b.courant.slerp(b.cible, k);

  // Marche du modèle, fondue avec la pose fabriquée. Le temps d'animation avance avec la distance
  // parcourue : les pieds restent posés quelle que soit la vitesse.
  const vise = p.marche && sq.mixer ? 1 : 0;
  sq.poidsMarche += (vise - sq.poidsMarche) * Math.min(1, p.dt * 8);
  if (!vise && sq.poidsMarche < 0.01) sq.poidsMarche = 0;
  const w = sq.poidsMarche;
  if (w > 0) {
    sq.tMarche = (sq.tMarche + p.parcouru / sq.vitesseAnim) % sq.clip.duration;
    sq.mixer.setTime(sq.tMarche);
    for (const b of sq.tous) {
      b.o.quaternion.slerpQuaternions(b.courant, b.o.quaternion, w);
      b.o.position.lerpVectors(b.reposPos, b.o.position, w);
    }
  } else {
    for (const b of sq.tous) { b.o.quaternion.copy(b.courant); b.o.position.copy(b.reposPos); }
  }

  // Assis : le corps descend sur l'assise.
  sq.racine.position.y = sq.baseY - 0.06 * p.assise;

  // La tasse suit la main droite, toujours droite.
  sq.tasse.visible = p.action === "cafe" && Boolean(os.mainD);
  if (sq.tasse.visible) {
    const g = sq.racine.parent;
    g.updateMatrixWorld(true);
    os.mainD.o.getWorldPosition(_v);
    g.worldToLocal(_v);
    sq.tasse.position.copy(_v);
    sq.tasse.position.y += 0.02;
    sq.tasse.position.z += 0.04;
  }
  return w > 0;
}
