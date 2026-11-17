// « Où tournent les actions » : un lieu (poste, GitHub, serveur) pour chacune des quatre actions du projet.
// Une écriture des réglages par le serveur du bureau ; le serveur valide, la case redit l'état réel en cas de refus.

import {el} from "./dom.js";
import {urlProjet} from "./projets.js";

export const AIDE_DEPORT = "Par défaut, tout tourne sur le poste. On déporte une action sur GitHub (ou, bientôt, sur " +
  "un serveur) pour soulager le poste. Gardez la chaîne entière (APK, tests, charge, émulateur) au même lieu : une " +
  "action qui attend une production venue d'ailleurs patiente.";

// Les noms des actions sont ceux du moteur (ceux que citent aussi les avertissements).
const ACTIONS = ["apk", "tests", "charge", "emulateur"];
const LIEUX = [["poste", "Poste"], ["github", "GitHub"], ["serveur", "Serveur"]];
const MSG_SERVEUR = "bientôt";
const MSG_EMULATEUR = "peu fiable sur GitHub, utilisez le poste ou le serveur";

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

function rangee(ctx, action, nom, lieuxActuels, groupe, message, fetchFn) {
  const fieldset = el("div", "deport-action");
  fieldset.setAttribute("role", "radiogroup");
  fieldset.setAttribute("aria-label", nom);
  fieldset.append(el("span", "deport-nom", nom));
  const radios = [];
  for (const [lieu, libelle] of LIEUX) {
    const label = el("label", "lecons-auto-label deport-choix");
    const r = document.createElement("input");
    r.type = "radio";
    r.name = "deport-" + action;
    r.value = lieu;
    r.checked = lieuxActuels[action] === lieu;
    const grise = lieu === "serveur" ? MSG_SERVEUR : (action === "emulateur" && lieu === "github" ? MSG_EMULATEUR : "");
    r.disabled = grise !== "";
    label.append(r, el("span", "", " " + libelle + (grise ? " (" + grise + ")" : "")));
    r.addEventListener("change", async () => {
      const avant = lieuxActuels[action];
      message.textContent = "";
      groupe.forEach((x) => { x.disabled = true; });
      const rep = await enregistrerDeport({[action]: lieu}, fetchFn);
      groupe.forEach((x) => { x.disabled = x.grise; });
      if (rep.ok) { lieuxActuels[action] = lieu; ctx.rouvrir?.(); }
      else radios.forEach((x) => { x.checked = x.value === avant; });   // refus : le choix redit l'état réel
      message.textContent = rep.message;
    });
    r.grise = grise !== "";
    radios.push(r);
    groupe.push(r);
    fieldset.append(label);
  }
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

// Le bloc « Où tournent les actions » ; `fetchFn` seulement pour les tests.
export function blocDeport(ctx, fetchFn = fetch) {
  const bloc = el("div", "lecons-auto deport");
  const d = ctx.etat.deport || {};
  const lieux = {apk: "poste", tests: "poste", charge: "poste", emulateur: "poste", ...(d.lieux || {})};
  if (ctx.etat.deport) ctx.etat.deport.lieux = lieux;
  const message = el("p", "note", "");
  message.setAttribute("aria-live", "polite");
  const groupe = [];
  bloc.append(el("h4", "", "Où tournent les actions"), el("p", "note", AIDE_DEPORT));
  for (const action of ACTIONS) bloc.append(rangee(ctx, action, action, lieux, groupe, message, fetchFn));
  for (const phrase of avertissementsGroupes(d.avertissements)) bloc.append(el("p", "note deport-avertissement", phrase));
  bloc.append(message);
  if (ACTIONS.some((a) => lieux[a] === "github")) bloc.append(blocApercu(fetchFn));
  return bloc;
}
