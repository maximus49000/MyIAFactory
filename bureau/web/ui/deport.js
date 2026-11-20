// « Où tournent les actions » : un lieu (poste, GitHub, serveur) pour chacune des actions que son type de projet permet.
// Une écriture des réglages par le serveur du bureau ; le serveur valide, la case redit l'état réel en cas de refus.

import {el} from "./dom.js";
import {urlProjet} from "./projets.js";

export const AIDE_DEPORT = "Par défaut, tout tourne sur le poste. On déporte une action sur GitHub (ou, bientôt, sur " +
  "un serveur) pour soulager le poste. Gardez la chaîne entière (APK, tests, charge, émulateur) au même lieu : une " +
  "action qui attend une production venue d'ailleurs patiente.";

// Les actions viennent de l'état (`deport.actions` : celles du type du projet, avec libellé, lieux permis, `bientot`).
// Sans elles (état ancien), les quatre actions génériques du moteur, dont les noms sont aussi ceux des avertissements.
const MSG_EMULATEUR = "peu fiable sur GitHub, utilisez le poste ou le serveur";
const ACTIONS_GENERIQUES = [
  {id: "apk", libelle: "apk", lieux: ["poste", "github", "serveur"], bientot: null},
  {id: "tests", libelle: "tests", lieux: ["poste", "github", "serveur"], bientot: null},
  {id: "charge", libelle: "charge", lieux: ["poste", "github", "serveur"], bientot: null},
  {id: "emulateur", libelle: "emulateur", lieux: ["poste", "serveur"], bientot: MSG_EMULATEUR},
];
export function actionsDe(deport) {
  const liste = deport?.actions;
  return Array.isArray(liste) && liste.length ? liste : ACTIONS_GENERIQUES;
}
const LIEUX = [["poste", "Poste"], ["github", "GitHub"], ["serveur", "Serveur"]];
const MSG_SERVEUR = "bientôt";
// Une action au seul serveur (la recette sur émulateur) : pas de défaut au poste, « Non réglé » (refusée) tant que le
// Directeur ne l'a pas réglée sur serveur pour ce projet ; ce réglage vaut accord permanent.
const NON_REGLE = ["", "Non réglé"];
const MSG_SANS_SERVEUR = "déclarez d'abord un serveur (Serveurs), puis réglez sur serveur";
export const NOTE_SERVEUR_SEUL = "Ne tourne que sur le serveur : la régler sur serveur vaut accord permanent pour ce " +
  "projet (l'agent la lance sans redemander). Non réglée, elle est refusée.";
const surServeurSeul = (def) => Array.isArray(def.lieux) && !def.lieux.includes("poste") && !def.lieux.includes("github");
const defautDe = (def) => (surServeurSeul(def) ? null : "poste");

// Écrit les lieux voulus (partiels : le serveur fusionne). {ok, message}, sans jamais lever.
export async function enregistrerDeport(lieux, fetchFn = fetch) {
  try {
    const r = await fetchFn(urlProjet("/api/reglages"), {
      method: "POST",
      headers: {"X-Bureau": "1", "Content-Type": "application/json"},
      body: JSON.stringify({deport: {lieux}}),
    });
    if (r.ok) return {ok: true, message: "Lieu enregistré."};
    let erreur = "";
    try { erreur = (await r.json())?.erreur || ""; } catch { /* corps illisible */ }
    return {ok: false, message: `Refusé : ${erreur || "le serveur a répondu " + r.status}`};
  } catch {
    return {ok: false, message: "Serveur du bureau injoignable."};
  }
}

// Le texte du moteur : « « tests » tourne au lieu « poste » mais attendra l'APK produit par GitHub : … ».
const FORME = /^« (.+?) » tourne au lieu « (.+?) » mais attendra l'(.+?) produit par (.+?) : /;

// Un seul texte court par situation (même lieu, même production attendue) ; un texte d'un autre format reste tel quel.
export function avertissementsGroupes(textes) {
  const groupes = new Map();
  const autres = [];
  for (const t of Array.isArray(textes) ? textes : []) {
    const m = typeof t === "string" ? FORME.exec(t) : null;
    if (!m) { if (typeof t === "string" && t) autres.push(t); continue; }
    const cle = `${m[2]}|${m[3]}|${m[4]}`;
    if (!groupes.has(cle)) groupes.set(cle, {actions: [], ici: m[2], produit: m[3], ailleurs: m[4]});
    groupes.get(cle).actions.push(m[1]);
  }
  const phrases = [...groupes.values()].map((g) => `${g.actions.join(", ")} : au lieu « ${g.ici} », ` +
    `attend l'${g.produit} produit par ${g.ailleurs}. Mettez la chaîne entière au même lieu pour éviter cette attente.`);
  return [...new Set([...phrases, ...autres])];
}

function rangee(ctx, def, lieuxActuels, groupe, message, fetchFn) {
  const action = def.id;
  const nom = def.libelle || action;
  const fieldset = el("div", "deport-action");
  fieldset.setAttribute("role", "radiogroup");
  fieldset.setAttribute("aria-label", nom);
  fieldset.append(el("span", "deport-nom", nom));
  const radios = [];
  const seul = surServeurSeul(def);
  // au seul serveur : ses lieux permis et « Non réglé », jamais poste ni GitHub
  const choix = seul ? [...LIEUX.filter(([l]) => def.lieux.includes(l)), NON_REGLE] : LIEUX;
  const serveurDeclare = ctx.etat.deport?.serveur_declare === true;
  for (const [lieu, libelle] of choix) {
    const label = el("label", "lecons-auto-label deport-choix");
    const r = document.createElement("input");
    r.type = "radio";
    r.name = "deport-" + action;
    r.value = lieu;
    r.checked = (lieuxActuels[action] ?? "") === lieu;
    const permis = lieu === "" || (Array.isArray(def.lieux) ? def.lieux.includes(lieu) : true);
    // le serveur n'est réglable que pour une action que `deporter` y sert, et seulement si un serveur est déclaré
    const msgServeur = def.servie_au_serveur === true ? (serveurDeclare ? "" : MSG_SANS_SERVEUR) : MSG_SERVEUR;
    const grise = lieu === "serveur" ? msgServeur : (permis ? "" : (def.bientot || "indisponible pour ce type de projet"));
    r.disabled = grise !== "";
    label.append(r, el("span", "", " " + libelle + (grise ? " (" + grise + ")" : "")));
    r.addEventListener("change", async () => {
      const avant = lieuxActuels[action] ?? "";
      message.textContent = "";
      groupe.forEach((x) => { x.disabled = true; });
      const rep = await enregistrerDeport({[action]: lieu === "" ? null : lieu}, fetchFn);
      groupe.forEach((x) => { x.disabled = x.grise; });
      if (rep.ok) { lieuxActuels[action] = lieu === "" ? null : lieu; ctx.rouvrir?.(); }
      else radios.forEach((x) => { x.checked = x.value === avant; });   // refus : le choix redit l'état réel
      message.textContent = rep.message;
    });
    r.grise = grise !== "";
    radios.push(r);
    groupe.push(r);
    fieldset.append(label);
  }
  if (seul) fieldset.append(el("p", "note", NOTE_SERVEUR_SEUL));
  return fieldset;
}

async function erreurDe(r) {
  try { return (await r.json())?.erreur || ""; } catch { return ""; }
}

// L'aperçu du workflow que le déport écrirait (une lecture, rien n'est écrit). {ok, apercu} ou {ok: false, message}.
export async function lireApercu(fetchFn = fetch) {
  try {
    const r = await fetchFn(urlProjet("/api/deport/apercu"), {headers: {"X-Bureau": "1"}});
    if (r.ok) return {ok: true, apercu: await r.json()};
    return {ok: false, message: `Refusé : ${(await erreurDe(r)) || "le serveur a répondu " + r.status}`};
  } catch {
    return {ok: false, message: "Serveur du bureau injoignable."};
  }
}

// La validation du Directeur : envoie l'empreinte vue ; le serveur refuse si le contenu voulu a changé depuis.
export async function validerEtPousser(empreinte, fetchFn = fetch) {
  try {
    const r = await fetchFn(urlProjet("/api/deport/appliquer"), {
      method: "POST",
      headers: {"X-Bureau": "1", "Content-Type": "application/json"},
      body: JSON.stringify({empreinte}),
    });
    if (r.ok) {
      let message = "";
      try { message = (await r.json())?.message || ""; } catch { /* corps illisible */ }
      return {ok: true, message: message || "Workflow envoyé."};
    }
    return {ok: false, message: `Refusé : ${(await erreurDe(r)) || "le serveur a répondu " + r.status}`};
  } catch {
    return {ok: false, message: "Serveur du bureau injoignable."};
  }
}

const ETATS_APERCU = {
  absent: "Aucun workflow n'existe encore : il sera créé.",
  a_valider: "Un workflow MyIAFactory existe : voici ce qui change.",
  a_jour: "Le workflow est déjà à jour : rien à envoyer.",
  modifie_a_la_main: "Le fichier a été modifié à la main : MyIAFactory ne l'écrase pas.",
  aucune_action: "Aucune action n'est déportée sur GitHub.",
};

// L'aperçu et la validation : le diff s'affiche, « Valider et pousser » envoie l'empreinte affichée (branche de travail).
function blocApercu(fetchFn) {
  const bloc = el("div", "deport-apercu");
  const zone = el("div", "deport-apercu-zone");
  const message = el("p", "note", "");
  message.setAttribute("aria-live", "polite");
  const voir = el("button", "", "Aperçu du workflow");
  voir.type = "button";
  async function ouvrir() {
    zone.textContent = "";
    message.textContent = "";
    const rep = await lireApercu(fetchFn);
    if (!rep.ok) { message.textContent = rep.message; return; }
    const a = rep.apercu;
    zone.append(el("p", "note", ETATS_APERCU[a.etat] || a.etat), el("p", "note", a.chemin || ""));
    // la base distante : les commits locaux non poussés ne partent pas, une branche non poussée est refusée
    if (a.note) zone.append(el("p", "note", a.note));
    if (a.diff) zone.append(el("pre", "deport-diff", a.diff));
    const pousser = el("button", "", "Valider et pousser");
    pousser.type = "button";
    pousser.disabled = !(a.etat === "absent" || a.etat === "a_valider") || !a.empreinte;
    pousser.addEventListener("click", async () => {
      pousser.disabled = true;
      message.textContent = "";
      const r = await validerEtPousser(a.empreinte, fetchFn);
      message.textContent = r.message;
      pousser.disabled = r.ok;   // envoyé : plus rien à valider ; refusé : on peut réessayer (après un nouvel aperçu)
    });
    zone.append(pousser);
  }
  voir.addEventListener("click", ouvrir);
  bloc.append(voir, zone, message);
  return bloc;
}

const espaces = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

// « 640 / 2 000 min » (quota connu), « 640 min (illimité) » (dépôt public), « 640 min » (quota inconnu : estimation).
export function libelleMinutes(c) {
  const m = espaces(c?.minutes_total || 0);
  if (c?.public) return `${m} min (illimité)`;
  return typeof c?.quota === "number" ? `${m} / ${espaces(c.quota)} min` : `${m} min`;
}

const CONCLUSIONS = {success: "réussi", failure: "échoué", cancelled: "annulé", timed_out: "délai dépassé",
  skipped: "ignoré", startup_failure: "n'a pas démarré"};

function dureeCourte(s) {
  const n = Math.max(0, Math.round(Number(s) || 0));
  return n < 60 ? `${n} s` : `${Math.floor(n / 60)} min ${n % 60} s`;
}

// Les minutes GitHub du mois, le niveau (ok / alerte / dépassé), le détail par action et les derniers résultats
// (réussi ou échoué, durée, lien vers l'exécution). Pur : `c` est `deport.conso` de l'état.
export function blocConso(c) {
  const niveau = ["alerte", "depasse"].includes(c?.niveau) ? c.niveau : "ok";
  const bloc = el("div", `deport-conso deport-conso-${niveau}`);
  bloc.setAttribute("role", niveau === "ok" ? "status" : "alert");
  bloc.append(el("h5", "", `Consommation GitHub ${c?.mois || ""} : ${libelleMinutes(c)}`.replace("  ", " ")));
  if (c?.texte) bloc.append(el("p", "note", c.texte));
  for (const a of Array.isArray(c?.par_action) ? c.par_action : []) {
    bloc.append(el("p", "note", `${a.libelle || a.action} : ${espaces(a.minutes)} min (${a.executions} exécution${a.executions > 1 ? "s" : ""})`));
  }
  const derniers = Array.isArray(c?.derniers) ? c.derniers : [];
  if (derniers.length) {
    bloc.append(el("h5", "", "Derniers résultats"));
    for (const d of derniers) {
      const ligne = el("p", "note deport-resultat", `${d.libelle || d.action} : ${CONCLUSIONS[d.conclusion] || d.conclusion || "en cours"} (${dureeCourte(d.duree_s)}) `);
      if (typeof d.url === "string" && d.url.startsWith("https://")) {
        const a = el("a", "", "voir l'exécution");
        a.href = d.url;
        a.rel = "noopener";
        a.target = "_blank";
        ligne.append(a);
      }
      bloc.append(ligne);
    }
  }
  return bloc;
}

// Le bloc « Où tournent les actions » ; `fetchFn` seulement pour les tests.
export function blocDeport(ctx, fetchFn = fetch) {
  const bloc = el("div", "lecons-auto deport");
  const d = ctx.etat.deport || {};
  const actions = actionsDe(d);
  const lieux = {...Object.fromEntries(actions.map((a) => [a.id, defautDe(a)])), ...(d.lieux || {})};
  if (ctx.etat.deport) ctx.etat.deport.lieux = lieux;
  const message = el("p", "note", "");
  message.setAttribute("aria-live", "polite");
  const groupe = [];
  bloc.append(el("h4", "", "Où tournent les actions"), el("p", "note", AIDE_DEPORT));
  for (const def of actions) bloc.append(rangee(ctx, def, lieux, groupe, message, fetchFn));
  for (const phrase of avertissementsGroupes(d.avertissements)) bloc.append(el("p", "note deport-avertissement", phrase));
  bloc.append(message);
  if (actions.some((a) => lieux[a.id] === "github")) bloc.append(blocApercu(fetchFn));
  if (d.conso) bloc.append(blocConso(d.conso));
  return bloc;
}
