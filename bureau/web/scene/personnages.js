// Les personnages : un par acteur de la régie, teinté à la couleur de l'agent,
// avec son prénom au-dessus de la tête et sa bulle quand il travaille.

import * as THREE from "three";
import {CSS2DObject} from "three/addons/renderers/CSS2DRenderer.js";
import * as Squelette from "./squelette.js";
import {estPartage} from "./modeles.js";

const FOULEE = 0.75;          // m parcourus par cycle de marche
const VITESSE_ROTATION = 9;   // rad/s pour se tourner
const HAUTEUR_ASSIS = 0;      // hanches à 0,52 m une fois la figurine agrandie : juste au-dessus de l'assise
const ECHELLE_FIGURINE = 1.3; // la figurine de repli fait 1,15 m ; agrandie pour rester lisible de loin

const lisser = (a, b, k) => a + (b - a) * k;
function angleVers(a, b, max) {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return a + Math.max(-max, Math.min(max, d));
}

export class Personnages {
  constructor(sc, modeles) {
    this.sc = sc;
    this.modeles = modeles;
    this.figures = new Map();
    this.temps = 0;
  }

  // acteurs : Map<id, {x, z, cap, action, assis?, agent}>
  synchroniser(acteurs) {
    for (const [id, f] of this.figures) if (!acteurs.has(id)) this._retirer(id, f);
    for (const [id, a] of acteurs) {
      let f = this.figures.get(id);
      if (!f) f = this._creer(id, a);
      f.acteur = a;
      this._etiqueter(f, a.agent);
    }
  }

  // Avance les animations. Rend vrai si quelqu'un marche ou se tourne (rendu plus fluide nécessaire).
  animer(dt) {
    this.temps += dt;
    let bouge = false;
    for (const f of this.figures.values()) bouge = this._animer(f, dt) || bouge;
    return bouge;
  }

  // --- interne

  _creer(id, a) {
    const g = this.modeles.creer("personnage");
    // Le modèle Tripo (squelette + marche) si présent ; sinon la figurine articulée.
    const sq = this.modeles.aModele("personnage") ? Squelette.preparer(g) : null;
    if (!this.modeles.aModele("personnage")) g.scale.setScalar(ECHELLE_FIGURINE);
    const hauteurTexte = sq ? sq.hauteur + 0.06 : 1.4;
    g.userData.choix = {type: a.agent.fixe ? "direction" : "agent", id: a.agent.fixe ? "direction" : id};
    g.position.set(a.x, 0, a.z);
    g.rotation.y = a.cap;
    const art = g.userData.articulations || null;
    // Teinte : buste et bras à la couleur de l'agent, cheveux plus foncés.
    if (g.userData.tenue) {
      g.userData.cheveux.material = new THREE.MeshLambertMaterial({color: "#555555"});
    } else if (!sq) {
      g.traverse((m) => { if (m.isMesh) m.material = m.material.clone(); });
    }

    const etiquette = document.createElement("div");
    etiquette.className = "etiquette";
    const nom = document.createElement("span");
    nom.className = "prenom";
    const nuage = document.createElement("span");
    nuage.className = "nuage";
    nuage.textContent = "☁";
    nuage.title = "Agent cloud";
    etiquette.append(nuage, nom);
    const oEtiquette = new CSS2DObject(etiquette);
    oEtiquette.position.set(0, hauteurTexte, 0);
    oEtiquette.center.set(0.5, 1);
    g.add(oEtiquette);

    const porteur = document.createElement("div");
    porteur.className = "porte-bulle";
    const bulle = document.createElement("div");
    bulle.className = "bulle";
    porteur.append(bulle);
    const oBulle = new CSS2DObject(porteur);
    oBulle.position.set(0, hauteurTexte, 0);
    oBulle.center.set(0.5, 1);
    g.add(oBulle);

    this.sc.scene.add(g);
    this.sc.choisissables.push(g);
    const f = {id, g, art, sq, etiquette, nom, nuage, bulle, oBulle, acteur: a, couleur: null,
               phase: Math.random() * 10, decalage: Math.random() * 10, x: a.x, z: a.z, assise: 0};
    this.figures.set(id, f);
    return f;
  }

  _retirer(id, f) {
    f.g.traverse((o) => { if (o.isCSS2DObject) o.element.remove(); });
    this.sc.scene.remove(f.g);
    this._liberer(f);
    const i = this.sc.choisissables.indexOf(f.g);
    if (i >= 0) this.sc.choisissables.splice(i, 1);
    this.figures.delete(id);
  }

  // Libère ce qui n'appartient qu'à cette figure (le modèle Tripo partage sa géométrie et sa texture
  // entre toutes les copies ; les matériaux de matiere() sont partagés aussi).
  _liberer(f) {
    if (f.sq) {
      f.sq.mixer?.stopAllAction();
      f.sq.mixer?.uncacheRoot(f.g);
      f.sq.tasse.geometry.dispose();
      f.sq.tasse.material.dispose();
      f.g.traverse((m) => { if (m.isSkinnedMesh) m.material.dispose(); });
      return;
    }
    f.g.traverse((m) => {
      if (!m.isMesh) return;
      m.geometry.dispose();
      if (!estPartage(m.material)) m.material.dispose();
    });
  }

  _etiqueter(f, agent) {
    if (f.couleur !== agent.couleur) {
      f.couleur = agent.couleur;
      const c = new THREE.Color(agent.couleur || "#cccccc");
      if (f.sq) {
        f.sq.teinte.value.copy(c);
      } else if (f.g.userData.tenue) {
        f.g.userData.tenue.color.copy(c);
        f.g.userData.cheveux.material.color.copy(c).multiplyScalar(0.45);
      } else {
        f.g.traverse((m) => { if (m.isMesh && m.material.color) m.material.color.copy(c); });
      }
      f.etiquette.style.setProperty("--couleur", agent.couleur || "#888");
    }
    if (f.nom.textContent !== agent.prenom) f.nom.textContent = agent.prenom || "?";
    f.nuage.hidden = agent.lieu !== "cloud";
    f.etiquette.classList.toggle("chef", Boolean(agent.chef));
    f.etiquette.classList.toggle("directeur", Boolean(agent.fixe));
    const texte = agent.bulle || "";
    if (f.bulle.textContent !== texte) f.bulle.textContent = texte;
    f.bulle.classList.toggle("grise", agent.statut === "sans_nouvelles");
  }

  _animer(f, dt) {
    const a = f.acteur, art = f.art, ag = a.agent;
    const g = f.g;
    // Position : la régie donne déjà un mouvement continu ; on suit.
    const dx = a.x - f.x, dz = a.z - f.z;
    const parcouru = Math.hypot(dx, dz);
    f.x = a.x; f.z = a.z;
    g.position.x = a.x; g.position.z = a.z;
    const avant = g.rotation.y;
    g.rotation.y = angleVers(g.rotation.y, a.cap, VITESSE_ROTATION * dt);
    const tourne = Math.abs(g.rotation.y - avant) > 1e-4;

    const marche = a.action === "marche";
    const assis = a.action === "assis" || (a.action === "cafe" && a.assis);
    const travaille = ag.statut === "travail";
    const enPoste = (a.action === "assis" || a.action === "debout") && !ag.chef && !ag.fixe;
    f.oBulle.visible = Boolean(ag.bulle) && enPoste && (ag.statut === "travail" || ag.statut === "sans_nouvelles");
    // Bulles de voisins de bureau à deux hauteurs, pour qu'elles ne se recouvrent pas.
    if (f.oBulle.visible) f.oBulle.element.classList.toggle("haute", (Math.round(a.x / 1.4) & 1) === 1);
    if (art && art.tasse) art.tasse.visible = a.action === "cafe";

    const k = Math.min(1, dt * 10);
    const t = this.temps + f.decalage;
    f.assise = lisser(f.assise, assis ? 1 : 0, k);
    const assiseBouge = Math.abs(f.assise - (assis ? 1 : 0)) > 0.01;

    if (f.sq) {
      const fondu = Squelette.animer(f.sq, {marche, parcouru, assise: f.assise, action: a.action,
                                            travaille, enPoste, assis, t, dt});
      return marche || tourne || assiseBouge || fondu;
    }
    if (!art) return marche || tourne;

    let jambe = 0, brasG = 0, brasD = 0, brasDz = 0, tete = 0, bond = 0;

    if (marche) {
      f.phase += (parcouru / FOULEE) * Math.PI * 2;
      const s = Math.sin(f.phase);
      jambe = s * 0.55;
      brasG = s * 0.45;
      brasD = -s * 0.45;
      bond = Math.abs(Math.cos(f.phase)) * 0.035;
    } else if (a.action === "postit") {
      brasD = -2.3 + Math.sin(t * 6) * 0.08;
      brasG = 0.1;
      tete = -0.15;
    } else if (a.action === "cafe") {
      const gorgee = (Math.sin(t * 0.7) + 1) / 2 > 0.85;
      brasD = gorgee ? -2.25 : -1.25;
      brasDz = gorgee ? 0.35 : 0.15;
      brasG = assis ? -0.6 : 0.05;
      tete = gorgee ? -0.2 : Math.sin(t * 0.5) * 0.1;
    } else if (enPoste && travaille) {
      // Taper au clavier (assis) ou griffonner (debout).
      const base = assis ? -1.15 : -0.7;
      brasG = base + Math.sin(t * 13) * 0.1;
      brasD = base + Math.sin(t * 13 + Math.PI) * 0.1;
      tete = 0.12 + Math.sin(t * 1.3) * 0.04;
    } else if (enPoste) {
      // Sans nouvelles : immobile, la tête basse.
      brasG = brasD = assis ? -0.95 : 0;
      tete = 0.3;
    } else {
      brasG = Math.sin(t * 1.1) * 0.04;
      brasD = -brasG;
    }

    const r = art;
    r.jambeG.rotation.x = lisser(r.jambeG.rotation.x, marche ? jambe : -Math.PI / 2 * f.assise, marche ? 1 : k);
    r.jambeD.rotation.x = lisser(r.jambeD.rotation.x, marche ? -jambe : -Math.PI / 2 * f.assise, marche ? 1 : k);
    r.brasG.rotation.x = lisser(r.brasG.rotation.x, brasG, marche ? 1 : k);
    r.brasD.rotation.x = lisser(r.brasD.rotation.x, brasD, marche ? 1 : k);
    r.brasD.rotation.z = lisser(r.brasD.rotation.z, brasDz, k);
    r.tete.rotation.x = lisser(r.tete.rotation.x, tete, k);
    r.corps.position.y = HAUTEUR_ASSIS * f.assise + bond;
    r.corps.scale.y = 1 + Math.sin(t * 2.2) * 0.008;
    return marche || tourne || assiseBouge;
  }
}
