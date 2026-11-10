// La page : lit l'état toutes les 3 s, en déduit les changements, fait jouer la régie, dessine.

import {changements, etatUtilisable} from "./logique/diff.js";
import {creerPlan} from "./logique/plan.js";
import {Regie} from "./logique/regie.js";
import {creerScene} from "./scene/scene.js";
import {charger} from "./scene/modeles.js";
import {Personnages} from "./scene/personnages.js";
import {Kanban} from "./scene/kanban.js";

const INTERVALLE = 3000;      // ms entre deux lectures de l'état
const DT_MAX = 0.1;           // s : plafond d'un pas de temps
const IMAGE_MOUVEMENT = 1 / 30, IMAGE_REPOS = 1 / 12;

const conteneur = document.getElementById("scene");

function signaler(message) {
  if (message) document.body.dataset.erreur = message;
  else delete document.body.dataset.erreur;
}

async function lireEtat() {
  try {
    const r = await fetch("/api/etat", {cache: "no-store"});
    if (!r.ok) return {erreur: `Le serveur a répondu ${r.status}.`};
    return await r.json();
  } catch {
    return {erreur: "Serveur du bureau injoignable."};
  }
}

const structure = (e) => JSON.stringify([e.services, (e.colonnes || []).map((c) => c.id)]);

// Le Directeur (l'utilisateur) : un personnage fixe à son bureau. Ce n'est pas un agent du relevé.
function acteurDirecteur(plan) {
  return {x: plan.directeur.x, z: plan.directeur.z, cap: plan.directeur.cap, action: "debout",
          agent: {id: "directeur", prenom: "Directeur", couleur: "#c9a227", lieu: "local", statut: "libre", fixe: true, bulle: ""}};
}

async function demarrer() {
  let etat = await lireEtat();
  while (!etatUtilisable(etat)) {
    signaler(etat?.erreur || "Relevé indisponible.");
    await new Promise((r) => setTimeout(r, INTERVALLE));
    etat = await lireEtat();
  }
  signaler(null);
  document.title = `${etat.projet} · le bureau vivant`;

  const plan = creerPlan(etat.services || [], etat.colonnes || []);
  const modeles = await charger("./modeles/manifeste.json");
  const sc = creerScene(conteneur, plan, modeles);
  const regie = new Regie(plan);
  const personnages = new Personnages(sc, modeles);
  const kanban = new Kanban(sc, plan, modeles);
  const directeur = acteurDirecteur(plan);
  const sigStructure = structure(etat);
  let dernier = etat;
  let aRemettre = false;
  regie.appliquer(etat, []);
  sc.assombrir(etat.factory?.etat === "en pause");

  const acteursVus = () => new Map([...regie.acteurs, ["directeur", directeur]]);
  let besoin = true;          // une image est à refaire même si rien ne bouge (état changé, fenêtre redimensionnée)

  async function sonder() {
    const e = await lireEtat();
    if (!etatUtilisable(e)) { signaler(e?.erreur || "Relevé indisponible."); return; }
    signaler(null);
    if (structure(e) !== sigStructure) { location.reload(); return; }   // services ou colonnes changés : on redessine tout
    if (document.hidden) { dernier = e; aRemettre = true; return; }
    regie.appliquer(e, changements(dernier, e));
    dernier = e;
    sc.assombrir(e.factory?.etat === "en pause");
    besoin = true;
  }
  setInterval(sonder, INTERVALLE);

  let avant = performance.now(), cumul = 0, intervalle = IMAGE_REPOS;
  function image(maintenant) {
    if (document.hidden) return;
    requestAnimationFrame(image);
    cumul += (maintenant - avant) / 1000;
    avant = maintenant;
    if (cumul < intervalle && !besoin) return;
    const dt = Math.min(cumul, DT_MAX);
    cumul = 0;
    regie.avancer(dt);
    personnages.synchroniser(acteursVus());
    kanban.synchroniser(dernier.colonnes || [], regie.postits, dernier.taches || [], dernier.file);
    const marche = personnages.animer(dt);
    const bouge = marche | kanban.animer(dt) | sc.transition(dt);
    intervalle = bouge ? IMAGE_MOUVEMENT : IMAGE_REPOS;
    sc.rendu(marche || besoin);
    besoin = false;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    if (aRemettre) { regie.reinitialiser(dernier); aRemettre = false; }   // pas d'animation de rattrapage
    avant = performance.now();
    cumul = 0;
    besoin = true;
    requestAnimationFrame(image);
  });
  window.addEventListener("resize", () => { sc.redimensionner(); besoin = true; });
  requestAnimationFrame(image);

  // Pour l'inspection depuis la console du navigateur.
  window.bureau = {plan, regie, scene: sc, personnages, kanban, etat: () => dernier};
}

demarrer().catch((e) => {
  console.error(e);
  signaler("La page n'a pas pu démarrer : " + (e?.message || e));
});
