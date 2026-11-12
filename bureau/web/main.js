// La page : lit l'état toutes les 3 s, en déduit les changements, fait jouer la régie, dessine.

import {changements, etatUtilisable} from "./logique/diff.js";
import {creerPlan} from "./logique/plan.js";
import {estMobile} from "./logique/mobile.js";
import {doitProposer} from "./logique/lancement.js";
import {Regie} from "./logique/regie.js";
import {creerScene} from "./scene/scene.js";
import {charger} from "./scene/modeles.js";
import {Personnages} from "./scene/personnages.js";
import {Kanban} from "./scene/kanban.js";
import {creerBarre} from "./ui/barre.js";
import {creerPanneaux} from "./ui/panneaux.js";
import {brancherGestes} from "./ui/gestes.js";
import {lireProjets, projetInitial, definirProjet, memorise, memoriser, urlProjet, projetCourant} from "./ui/projets.js";

const INTERVALLE = 3000;      // ms entre deux lectures de l'état
const DELAI_LECTURE = 15000;  // ms : au-delà, la lecture est abandonnée (le serveur coupe le relevé à 10 s)
const DT_MAX = 0.1;           // s : plafond d'un pas de temps
const IMAGE_MOUVEMENT = 1 / 30, IMAGE_REPOS = 1 / 12;

// Téléphone ou tablette : moins de 768 px de large, ou un doigt pour pointeur. La classe « mobile » règle la mise en page
// (barre compacte, panneaux plein écran) ; sur ordinateur rien ne change.
const requeteDoigt = window.matchMedia ? window.matchMedia("(pointer: coarse)") : null;
const mobile = () => estMobile(window.innerWidth, requeteDoigt?.matches === true);
function majMobile() { document.documentElement.classList.toggle("mobile", mobile()); }
majMobile();
window.addEventListener("resize", majMobile);

// Le bureau est « prêt » quand la première image de la scène est dessinée (le premier lancement attend ce moment).
let signalerPret, echecPret;
const pret = new Promise((ok, ko) => { signalerPret = ok; echecPret = ko; });
pret.catch(() => {});

// Premier lancement : demandé en parallèle du démarrage, sans le retarder. L'effet n'est chargé que s'il n'a jamais été
// proposé ; une panne vaut « déjà vu ».
fetch("/api/lancement", {cache: "no-store"})
  .then((r) => (r.ok ? r.json() : null))
  .then((r) => {
    if (!doitProposer(r)) return;
    const marquer = () => fetch("/api/lancement", {method: "POST", body: "{}",
      headers: {"X-Bureau": "1", "Content-Type": "application/json"}}).catch(() => {});
    return import("./ui/lancement.js").then((m) => m.lancer({pret, marquer}));
  })
  .catch(() => {});

const conteneur = document.getElementById("scene");
const barre = creerBarre(document.getElementById("barre"), document.getElementById("bandeau"));

// Relevé indisponible (message) ou de retour à la normale (null) : le bandeau et le voyant le disent.
function signaler(message) {
  if (message) barre.majErreur(message);
}

async function lireEtat() {
  try {
    const r = await fetch(urlProjet("/api/etat"), {cache: "no-store", signal: AbortSignal.timeout(DELAI_LECTURE)});
    if (!r.ok) return {erreur: `Le serveur a répondu ${r.status}.`};
    return await r.json();
  } catch {
    return {erreur: "Serveur du bureau injoignable."};
  }
}

const structure = (e) => JSON.stringify([e.services, (e.colonnes || []).map((c) => c.id), Boolean(e.partenaires)]);

// Le Directeur (l'utilisateur) : un personnage fixe à son bureau. Ce n'est pas un agent du relevé.
function acteurDirecteur(plan) {
  return {x: plan.directeur.x, z: plan.directeur.z, cap: plan.directeur.cap, action: "debout",
          agent: {id: "directeur", prenom: "Directeur", couleur: "#c9a227", lieu: "local", statut: "libre", fixe: true, bulle: ""}};
}

async function demarrer() {
  // Plusieurs projets : le choix mémorisé (sinon le premier) ; un seul projet : rien ne change.
  let liste = await lireProjets();
  if (liste.multi) {
    const id = projetInitial(liste.projets, memorise());
    definirProjet(id);
    barre.majProjets(true, liste.projets, id, liste.parents);
    barre.surCreation((options) => import("./ui/creation.js").then((m) => m.ouvrirCreation(options)));
  }
  let etat = await lireEtat();
  while (!etatUtilisable(etat)) {
    signaler(etat?.erreur || "Relevé indisponible.");
    await new Promise((r) => setTimeout(r, INTERVALLE));
    etat = await lireEtat();
  }
  barre.majEtat(etat);
  document.title = `${etat.projet} · le bureau vivant`;

  const plan = creerPlan(etat.services || [], etat.colonnes || [], {partenaires: Boolean(etat.partenaires)});
  const modeles = await charger("./modeles/manifeste.json");
  const sc = creerScene(conteneur, plan, modeles, {mobile: mobile()});
  const regie = new Regie(plan);
  const personnages = new Personnages(sc, modeles);
  const kanban = new Kanban(sc, plan, modeles);
  const directeur = acteurDirecteur(plan);
  const sigStructure = structure(etat);
  let dernier = etat;
  let aRemettre = false;
  regie.appliquer(etat, []);
  sc.assombrir(etat.factory?.etat === "en pause");

  const panneaux = creerPanneaux({
    conteneur, carte: document.getElementById("carte"), panneau: document.getElementById("panneau"),
    sc, plan, etat: () => dernier, barre,
    surFiltre: () => { besoin = true; },
  });
  brancherGestes(conteneur, sc, () => { besoin = true; });
  barre.boutonListe.addEventListener("click", () => panneaux.basculerListe());
  panneaux.maj(etat);

  const acteursVus = () => new Map([...regie.acteurs, ["directeur", directeur]]);
  let besoin = true;          // une image est à refaire même si rien ne bouge (état changé, fenêtre redimensionnée)

  let enLecture = false;      // une lecture à la fois : pas de requêtes qui s'empilent
  async function sonder() {
    if (enLecture) return;
    enLecture = true;
    let e;
    try { e = await lireEtat(); } finally { enLecture = false; }
    if (!etatUtilisable(e)) { signaler(e?.erreur || "Relevé indisponible."); return; }
    barre.majEtat(e);
    if (liste.multi) {   // les pastilles des autres projets suivent (lecture du dernier état connu côté serveur)
      const l = await lireProjets();
      if (l.multi) { liste = l; barre.majProjets(true, l.projets, projetCourant(), l.parents); }
    }
    if (structure(e) !== sigStructure) { location.reload(); return; }   // services ou colonnes changés : on redessine tout
    if (document.hidden) { dernier = e; aRemettre = true; return; }
    regie.appliquer(e, changements(dernier, e));
    dernier = e;
    panneaux.maj(e);
    sc.assombrir(e.factory?.etat === "en pause");
    besoin = true;
  }
  setInterval(sonder, INTERVALLE);

  let avant = performance.now(), cumul = 0, intervalle = IMAGE_REPOS;
  let prochaine = 0;          // image demandée et pas encore jouée (une seule boucle à la fois)
  function relancer() { if (!prochaine) prochaine = requestAnimationFrame(image); }
  function image(maintenant) {
    prochaine = 0;
    if (document.hidden) return;
    relancer();
    cumul += (maintenant - avant) / 1000;
    avant = maintenant;
    if (cumul < intervalle && !besoin) return;
    const dt = Math.min(cumul, DT_MAX);
    cumul = 0;
    regie.avancer(dt);
    personnages.synchroniser(acteursVus());
    kanban.synchroniser(dernier.colonnes || [], regie.postits, dernier.taches || [], dernier.file, dernier.images_ok === true);
    kanban.estomper(panneaux.filtre());
    const marche = personnages.animer(dt);
    const bouge = marche | kanban.animer(dt) | sc.transition(dt);
    intervalle = bouge ? IMAGE_MOUVEMENT : IMAGE_REPOS;
    sc.rendu(marche || besoin);
    besoin = false;
    signalerPret();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    if (aRemettre) { regie.reinitialiser(dernier); panneaux.maj(dernier); aRemettre = false; }   // pas d'animation de rattrapage
    avant = performance.now();
    cumul = 0;
    besoin = true;
    relancer();
  });
  // La scène se recadre dès que son espace change (fenêtre, ouverture du panneau de droite).
  new ResizeObserver(() => { sc.redimensionner(); besoin = true; }).observe(conteneur);
  relancer();

  // Pour l'inspection depuis la console du navigateur.
  window.bureau = {plan, barre, panneaux, regie, scene: sc, personnages, kanban, etat: () => dernier};
}

demarrer().catch((e) => {
  echecPret(e);
  console.error(e);
  signaler("La page n'a pas pu démarrer : " + (e?.message || e));
});
