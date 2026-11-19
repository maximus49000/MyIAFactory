// L'écran « Serveurs de travail » : déclarer un serveur (et copier sa clé publique), tester la connexion, voir ses capacités,
// installer ce qui manque (aperçu puis accord), et lire où tournent les actions (poste, GitHub, serveur) avec le conseil du bureau.
// Le bureau ne fait qu'afficher `GET /api/serveurs` et `GET /api/serveurs/lieux` et demander les actions par POST. Tout texte
// venu du serveur passe par textContent ; la couleur d'un lieu vient d'une classe CSS et s'écrit toujours en toutes lettres.

import {el} from "./dom.js";

const INTERVALLE_MS = 3000;
const RELEVES_SANS_TRAVAIL = 20;  // relevés sans travail en cours avant de cesser de guetter une sonde ou une installation lancée (environ 1 min)
export const MESSAGE_TEST_ENCORE = "Le test peut encore être en cours : actualisez dans un instant.";
const tableau = (v) => (Array.isArray(v) ? v : []);
const texte = (v) => (typeof v === "string" ? v : "");
const objet = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

export const ACTIONS = ["apk", "tests", "lint", "release", "emulateur", "charge"];
const LIBELLES_ACTIONS = {apk: "Construire l'APK", tests: "Lancer les tests", lint: "Analyser le code (lint)", release: "Version de diffusion (release)",
  emulateur: "Émulateur Android", charge: "Tâches de charge"};
const INSTALLABLES = ACTIONS.filter((a) => a !== "charge");   // « charge » ne demande aucune capacité : rien à installer
const LIEUX = ["poste", "github", "serveur"];
const LIBELLES_LIEUX = {poste: "poste", github: "GitHub", serveur: "serveur"};
const NIVEAUX = {recommande: "recommandé", possible: "possible", deconseille: "déconseillé", indisponible: "indisponible"};
const STATUTS = {presente: "présente", absente: "absente", inconnue: "inconnue", bloquee: "bloquée", non_installable: "non installable"};
const LIBELLES_CAPACITES = {base: "Base du serveur", durcissement: "Durcissement SSH", "android-build": "Construction Android",
  "android-emulateur": "Émulateur Android", "unity-cli": "Unity CLI", "unity-editeur": "Éditeur Unity",
  "session-graphique": "Session graphique distante", agent: "Agent de développement"};

export const LIBELLE_ACCORD = "J'autorise cette installation sur le serveur";
export const AVERTISSEMENT_CONSEIL = "Ce n'est qu'un conseil : le choix reste au Directeur.";

// Un appel au bureau. Ne lève jamais : {ok, status, d, injoignable}.
async function appeler(url, methode, corps, fetchFn) {
  try {
    const entetes = {"X-Bureau": "1"};
    const init = {method: methode, headers: entetes};
    if (corps !== undefined) { entetes["Content-Type"] = "application/json"; init.body = JSON.stringify(corps); }
    const r = await fetchFn(url, init);
    let d = {};
    try { d = objet(await r.json()); } catch { /* corps illisible */ }
    return {ok: r.ok === true, status: r.status, d, injoignable: false};
  } catch {
    return {ok: false, status: 0, d: {}, injoignable: true};
  }
}

const chemin = (id) => `/api/serveurs/${encodeURIComponent(id)}`;
const refus = (r) => texte(r.d.erreur) || `Le serveur a répondu ${r.status}.`;
const INJOIGNABLE = "Le bureau est injoignable.";

// Lit les serveurs déclarés. Rend {serveurs, rejets}, ou null si le bureau est injoignable ou répond mal.
export async function lireServeurs(fetchFn = globalThis.fetch) {
  const r = await appeler("/api/serveurs", "GET", undefined, fetchFn);
  return r.ok && Array.isArray(r.d.serveurs) ? {serveurs: r.d.serveurs, rejets: tableau(r.d.rejets)} : null;
}

// Lit les lieux conseillés pour les actions. Rend {action: {poste, github, serveur}}, ou null.
export async function lireLieux(fetchFn = globalThis.fetch) {
  const r = await appeler(`/api/serveurs/lieux?actions=${ACTIONS.join(",")}`, "GET", undefined, fetchFn);
  return r.ok ? r.d : null;
}

// Déclare un serveur. Ne lève jamais : {ok, message, serveur}.
export async function declarerServeur(champs, fetchFn = globalThis.fetch) {
  const r = await appeler("/api/serveurs", "POST", {nom: champs.nom, hote: champs.hote, utilisateur: champs.utilisateur, fournisseur: champs.fournisseur}, fetchFn);
  if (r.injoignable) return {ok: false, message: INJOIGNABLE};
  if (!r.ok) return {ok: false, message: refus(r)};
  return {ok: true, serveur: objet(r.d.serveur), message: texte(objet(r.d.serveur).avertissement) || "Serveur déclaré."};
}

// Lance la sonde (test de connexion et relevé des capacités). Ne lève jamais : {ok, occupe, message}.
export async function sonderServeur(id, fetchFn = globalThis.fetch) {
  const r = await appeler(`${chemin(id)}/sonder`, "POST", {}, fetchFn);
  if (r.injoignable) return {ok: false, message: INJOIGNABLE};
  if (r.status === 409) return {ok: false, occupe: true, message: texte(r.d.erreur) || "Une opération est déjà en cours."};
  if (!r.ok) return {ok: false, message: refus(r)};
  return {ok: true, message: "Test lancé : l'état se met à jour tout seul."};
}

// L'aperçu d'une installation (lecture seule). Ne lève jamais : {ok, apercu, message}.
export async function apercuInstallation(id, actions, fetchFn = globalThis.fetch) {
  const r = await appeler(`${chemin(id)}/apercu`, "POST", {actions: tableau(actions)}, fetchFn);
  if (r.injoignable) return {ok: false, message: "Aperçu impossible : le bureau est injoignable."};
  if (!r.ok) return {ok: false, message: refus(r)};
  return {ok: true, apercu: r.d};
}

// Demande l'installation. `accord` n'est envoyé vrai que s'il vaut exactement `true`. Ne lève jamais : {ok, occupe, message}.
export async function installerCapacites(idServeur, actions, accord, fetchFn = globalThis.fetch) {
  try {
    if (!Array.isArray(actions) || !actions.length) return {ok: false, message: "Choisissez au moins une action."};
    const r = await appeler(`${chemin(idServeur)}/installer`, "POST", {actions, accord: accord === true}, fetchFn);
    if (r.injoignable) return {ok: false, message: "Installation impossible à lancer : le bureau est injoignable."};
    if (r.status === 409) return {ok: false, occupe: true, message: texte(r.d.erreur) || "Une installation est déjà en cours."};
    if (!r.ok) return {ok: false, message: refus(r)};
    return {ok: true, message: "Installation lancée. L'état se met à jour tout seul."};
  } catch {
    return {ok: false, message: "Installation impossible à lancer."};
  }
}

const nombre = (v) => (typeof v === "number" && Number.isFinite(v) ? String(Math.round(v * 10) / 10).replace(".", ",") : "?");

function statutCapacite(valeur, bloquee) {
  if (bloquee) return {statut: "non_installable", raison: texte(bloquee.raison)};
  const brut = typeof valeur === "string" ? {statut: valeur} : objet(valeur);
  const statut = brut.statut === "fait" ? "presente" : brut.statut;     // l'installeur écrit « fait » pour une capacité installée
  return {statut: STATUTS[statut] ? statut : "inconnue", raison: texte(brut.raison)};
}

function lieuxVides(l) { return !l || typeof l !== "object" || !Object.keys(l).length; }

// L'écran. `etat` : la réponse de /api/serveurs (ou null : injoignable). Options : `fetchFn`, `lieux` (réponse de
// /api/serveurs/lieux déjà lue), `planifier` {attendre(f, ms) -> poignée, annuler(poignée)}, `actif()` (faux : l'écran est
// retiré, on cesse de relire) et `copier(texte)` (presse-papiers).
export function ecranServeurs(etat, options = {}) {
  const fetchFn = options.fetchFn || globalThis.fetch;
  const planifieur = options.planifier || {attendre: (f, ms) => setTimeout(f, ms), annuler: (h) => clearTimeout(h)};
  const copier = options.copier || (async (t) => { await globalThis.navigator.clipboard.writeText(t); });
  const racine = el("section", "carte-serveurs");
  racine.append(el("h2", "", "Serveurs de travail"));
  const message = el("p", "reglage-message serveurs-message");
  message.setAttribute("aria-live", "polite");
  const resume = el("p", "serveurs-resume");
  const rejetsZone = el("div", "serveurs-rejets");
  const formulaire = el("div", "serveurs-formulaire");
  const liste = el("div", "serveurs-liste");
  const zoneLieux = el("div", "serveurs-lieux");
  racine.append(message, resume, liste, rejetsZone, formulaire, zoneLieux);

  let courant = etat;
  let lieux = options.lieux || null;
  const infos = new Map();      // id du serveur -> {ouvert, actions, apercu, message, chargement}
  const choix = {};             // action -> lieu retenu (local : le conseil ne déplace jamais rien)
  let lance = null;             // genre du travail qu'on vient de lancer (« sonder » | « installer ») : on guette sa fin
  let sansTravail = 0;
  let poignee = null;
  let fini = false;
  const cartes = new Map();     // id du serveur -> éléments mis à jour en place à chaque relevé
  let affiches = "";            // les serveurs dessinés
  let instantane = "";          // l'état des capacités quand on a lancé un test : s'il change, le test a rendu son résultat
  const empreinte = () => JSON.stringify(tableau(courant?.serveurs).map((s) => [s?.id, s?.capacites, s?.erreur]));
  const idsAffiches = () => tableau(courant?.serveurs).filter((s) => s && typeof s === "object" && typeof s.id === "string").map((s) => s.id).join("\n");

  const actif = () => !fini && (options.actif ? options.actif() : racine.isConnected !== false);
  const enCours = () => tableau(courant?.serveurs).some((s) => s?.installation_en_cours === true);
  const info = (id) => {
    if (!infos.has(id)) infos.set(id, {ouvert: false, actions: new Set(["apk"]), apercu: null, message: "", chargement: false});
    return infos.get(id);
  };

  // ---- les champs du formulaire « Déclarer un serveur » : construits une fois, jamais redessinés (la saisie reste)
  const champs = {};
  const champ = (cle, libelle, indice) => {
    const e = el("input", "serveurs-champ");
    e.type = "text";
    e.setAttribute("data-champ", cle);
    e.setAttribute("placeholder", indice);
    champs[cle] = e;
    const l = el("label", "serveurs-etiquette");
    l.append(el("span", "serveurs-etiquette-texte", libelle), e);
    return l;
  };
  const menu = el("select", "serveurs-champ");
  menu.setAttribute("data-champ", "fournisseur");
  const aucun = el("option", "", "Aucun");
  aucun.value = "";
  const ovh = el("option", "", "OVH");
  ovh.value = "ovh";
  menu.append(aucun, ovh);
  const etiquetteMenu = el("label", "serveurs-etiquette");
  etiquetteMenu.append(el("span", "serveurs-etiquette-texte", "Fournisseur"), menu);
  const boutonDeclarer = el("button", "bouton serveurs-declarer", "Déclarer le serveur");
  boutonDeclarer.type = "button";
  formulaire.append(el("h3", "", "Déclarer un serveur"), champ("nom", "Nom", "Mon serveur"), champ("hote", "Adresse", "203.0.113.5"),
    champ("utilisateur", "Utilisateur", "robot"), etiquetteMenu, boutonDeclarer);

  async function relire() {
    const [neuf, l] = await Promise.all([lireServeurs(fetchFn), lireLieux(fetchFn)]);
    if (neuf) courant = neuf;
    if (l) lieux = l;
    return neuf;
  }

  boutonDeclarer.addEventListener("click", async () => {
    if (boutonDeclarer.disabled) return;
    boutonDeclarer.disabled = true;
    message.textContent = "Déclaration…";
    const r = await declarerServeur({nom: champs.nom.value.trim(), hote: champs.hote.value.trim(), utilisateur: champs.utilisateur.value.trim(),
      fournisseur: menu.value === "ovh" ? "ovh" : null}, fetchFn);
    message.textContent = r.message;
    if (r.ok) {
      const neuf = await relire();
      const connus = tableau(courant?.serveurs);
      if (!neuf && r.serveur.id && !connus.some((s) => s?.id === r.serveur.id)) courant = {serveurs: [...connus, r.serveur], rejets: tableau(courant?.rejets)};
      for (const k of Object.keys(champs)) champs[k].value = "";
      menu.value = "";
    }
    boutonDeclarer.disabled = false;
    dessiner();
  });

  // ---- un serveur
  function ligneCle(serveur, i) {
    const ligne = texte(serveur.ligne_cle_publique);
    if (!ligne) return null;
    const zone = el("div", "serveurs-cle");
    zone.append(el("div", "carte-sous-titre", "Clé publique à ajouter au serveur (fichier authorized_keys)"), el("code", "serveurs-cle-ligne", ligne));
    const bouton = el("button", "bouton serveurs-copier", "Copier la ligne");
    bouton.type = "button";
    bouton.addEventListener("click", async () => {
      try { await copier(ligne); info(serveur.id).message = "Copiée."; } catch { info(serveur.id).message = "Copie impossible : sélectionnez la ligne à la main."; }
      dessiner();
    });
    zone.append(bouton);
    return zone;
  }

  function remplirCapacites(zone, serveur, i) {
    const bloquees = new Map(tableau(i.apercu?.bloquees).filter((b) => b && typeof b.id === "string").map((b) => [b.id, b]));
    const entrees = Object.entries(objet(serveur.capacites));
    const lignes = entrees.length ? [] : [el("p", "ligne-detail", "Aucune capacité relevée : testez la connexion.")];
    for (const [id, valeur] of entrees) {
      const {statut, raison} = statutCapacite(valeur, bloquees.get(id));
      const l = el("div", `serveurs-capacite capacite-${statut}`);
      l.append(el("strong", "serveurs-capacite-nom", LIBELLES_CAPACITES[id] || id), el("span", `serveur-badge capacite-badge-${statut}`, STATUTS[statut]));
      if (raison) l.append(el("span", "ligne-detail serveurs-capacite-raison", raison));
      lignes.push(l);
    }
    zone.replaceChildren(...lignes);
  }

  function panneauInstallation(serveur, i) {
    const zone = el("div", "serveurs-installation");
    zone.append(el("div", "carte-sous-titre", "Installer ce qu'il faut pour ces actions"));
    for (const a of INSTALLABLES) {
      const c = el("input", "serveurs-action-case");
      c.type = "checkbox";
      c.checked = i.actions.has(a);
      c.addEventListener("change", () => { if (c.checked) i.actions.add(a); else i.actions.delete(a); i.apercu = null; dessiner(); });
      const l = el("label", "serveurs-action");
      l.append(c, el("span", "", ` ${LIBELLES_ACTIONS[a]}`));
      zone.append(l);
    }
    const voir = el("button", "bouton serveurs-apercu", "Voir l'aperçu");
    voir.type = "button";
    voir.disabled = i.chargement;
    voir.addEventListener("click", async () => {
      if (!i.actions.size) { i.message = "Choisissez au moins une action."; dessiner(); return; }
      i.chargement = true; i.apercu = null; i.message = "Lecture du serveur…"; dessiner();
      const r = await apercuInstallation(serveur.id, ACTIONS.filter((a) => i.actions.has(a)), fetchFn);
      i.chargement = false;
      if (r.ok) { i.apercu = r.apercu; i.message = ""; } else i.message = r.message;
      dessiner();
    });
    zone.append(voir);
    const a = i.apercu;
    if (a) {
      if (texte(a.erreur)) zone.append(el("p", "serveurs-erreur", a.erreur));
      else zone.append(apercuInstallation_(serveur, i, a));
    }
    return zone;
  }

  function apercuInstallation_(serveur, i, a) {
    const zone = el("div", "serveurs-apercu-zone");
    const bloquees = tableau(a.bloquees).filter((b) => b && typeof b.id === "string");
    const ids = new Set(bloquees.map((b) => b.id));
    const manquantes = tableau(a.manquantes).filter((m) => typeof m === "string");
    const installables = manquantes.filter((m) => !ids.has(m));
    if (!manquantes.length) { zone.append(el("p", "serveurs-rien", "Rien à installer : tout est déjà présent.")); return zone; }
    zone.append(el("div", "carte-sous-titre", "Capacités à installer"));
    for (const m of installables) zone.append(el("div", "serveurs-manquante", LIBELLES_CAPACITES[m] || m));
    for (const b of bloquees) zone.append(el("div", "serveurs-bloquee", `${LIBELLES_CAPACITES[b.id] || b.id} : non installable (${texte(b.raison)})`));
    zone.append(el("p", "serveurs-estimation", `Estimation : ${nombre(a.taille_go)} Go sur le disque, environ ${nombre(a.duree_min)} min.`));
    if (!installables.length) return zone;
    const accord = el("input", "serveurs-accord");
    accord.type = "checkbox";
    accord.checked = false;
    const etiquette = el("label", "serveurs-accord-libelle");
    etiquette.append(accord, el("span", "", ` ${LIBELLE_ACCORD}`));
    const lancer = el("button", "bouton serveurs-lancer", "Lancer l'installation");
    lancer.type = "button";
    lancer.disabled = i.envoi === true;       // un bouton reconstruit pendant un envoi reste grisé
    lancer.addEventListener("click", async () => {
      if (lancer.disabled || i.envoi) return;
      // L'accord n'est donné que par la case cochée, et il ne sert qu'une fois : décochée tout de suite, avant l'envoi.
      const accorde = accord.checked === true;
      accord.checked = false;
      if (!accorde) { i.message = "Cochez la case d'accord pour lancer l'installation."; dessiner(); return; }
      i.envoi = true;                         // posé de façon synchrone : aucun second envoi avant la réponse
      lancer.disabled = true;
      i.message = "Envoi…";
      let r;
      try { r = await installerCapacites(serveur.id, ACTIONS.filter((x) => i.actions.has(x)), true, fetchFn); } finally { i.envoi = false; }
      i.message = r.message;
      if (r.ok || r.occupe) { lance = "installer"; sansTravail = 0; }
      if (r.ok) { i.apercu = null; i.ouvert = false; }
      dessiner();
      planifier();
    });
    zone.append(etiquette, lancer);
    return zone;
  }

  function cartePourServeur(serveur) {
    const i = info(serveur.id);
    const c = el("div", "serveurs-serveur");
    const tete = el("div", "serveurs-serveur-tete");
    tete.append(el("strong", "serveurs-nom", texte(serveur.nom) || texte(serveur.id)),
      el("span", "ligne-detail serveurs-adresse", `${texte(serveur.utilisateur)}@${texte(serveur.hote)}${texte(serveur.fournisseur) ? ` (${serveur.fournisseur})` : ""}`));
    c.append(tete);
    const encours = el("p", "serveurs-encours");
    const erreur = el("p", "reglage-message serveurs-erreur");
    erreur.setAttribute("role", "alert");
    c.append(encours, erreur);
    const cle = ligneCle(serveur, i);
    if (cle) c.append(cle);
    const tester = el("button", "bouton serveurs-tester", "Tester la connexion");
    tester.type = "button";
    const verifier = el("button", "bouton serveurs-verifier", "Vérifier");
    verifier.type = "button";
    const installer = el("button", "bouton serveurs-installer", "Installer");
    installer.type = "button";
    const capacites = el("div", "serveurs-capacites");
    const msg = el("p", "reglage-message serveurs-message-serveur");
    msg.setAttribute("aria-live", "polite");
    const refs = {encours, erreur, tester, verifier, installer, capacites, msg};
    cartes.set(serveur.id, refs);
    majServeur(serveur);
    const sonde = async (b) => {
      if (b.disabled) return;
      i.message = "Envoi…"; msg.textContent = i.message;
      const r = await sonderServeur(serveur.id, fetchFn);
      i.message = r.message;
      if (r.ok || r.occupe) { lance = "sonder"; sansTravail = 0; instantane = empreinte(); }
      majServeur(serveur);
      planifier();
    };
    tester.addEventListener("click", () => sonde(tester));
    verifier.addEventListener("click", () => sonde(verifier));
    installer.addEventListener("click", () => { if (installer.disabled) return; i.ouvert = !i.ouvert; i.apercu = null; dessiner(); });
    const barre = el("div", "serveurs-boutons");
    barre.append(tester, verifier, installer);
    c.append(capacites, barre, msg);
    if (i.ouvert) c.append(panneauInstallation(serveur, i));
    return c;
  }

  // Met à jour en place ce qui change au fil des relevés (capacités, état, erreur, boutons, message) : jamais la zone de l'aperçu
  // ni la case d'accord, qui gardent leur DOM.
  function majServeur(serveur) {
    const r = cartes.get(serveur.id);
    if (!r) return;
    const i = info(serveur.id);
    const occupe = serveur.installation_en_cours === true;
    r.encours.textContent = occupe ? "Installation en cours …" : "";
    r.erreur.textContent = texte(serveur.erreur);
    r.tester.disabled = occupe;
    r.verifier.disabled = occupe;
    r.installer.disabled = occupe || lance === "installer";
    remplirCapacites(r.capacites, serveur, i);
    r.msg.textContent = i.message;
  }

  // ---- « Où tournent les actions »
  function legende() {
    const l = el("div", "lieux-legende");
    for (const [n, libelle] of Object.entries(NIVEAUX)) {
      const e = el("span", "lieux-legende-item");
      e.append(el("span", `lieu-pastille niveau-${n}`), el("span", "", ` ${libelle}`));
      l.append(e);
    }
    return l;
  }

  function ligneLieux(action, fiches) {
    const l = el("div", "lieux-action");
    l.append(el("strong", "lieux-action-nom", LIBELLES_ACTIONS[action] || action));
    const lieuxLigne = el("div", "lieux-choix");
    for (const nom of LIEUX) {
      const f = objet(fiches[nom]);
      const niveau = NIVEAUX[f.niveau] ? f.niveau : "indisponible";
      const permis = nom === "serveur" ? f.permis === true : f.permis !== false;
      const radio = el("input", "lieu-radio");
      radio.type = "radio";
      radio.name = `lieu-${action}`;
      radio.value = nom;
      radio.disabled = !permis;
      radio.checked = choix[action] === nom && permis;
      radio.addEventListener("change", () => { if (radio.checked) choix[action] = nom; });
      const pastille = el("span", `lieu-pastille niveau-${niveau}`);
      pastille.setAttribute("data-lieu", nom);
      const etiquette = el("span", "lieu-etiquette", `${LIBELLES_LIEUX[nom]} — ${NIVEAUX[niveau]}`);
      etiquette.setAttribute("data-lieu", nom);
      if (texte(f.raison)) etiquette.setAttribute("title", f.raison);
      const choixLieu = el("label", `lieu-choix lieu-${nom}${permis ? "" : " lieu-grise"}`);
      choixLieu.append(radio, pastille, etiquette);
      lieuxLigne.append(choixLieu);
    }
    l.append(lieuxLigne);
    const serveur = objet(fiches.serveur);
    if (serveur.permis !== true) {
      const manque = tableau(serveur.manque).filter((m) => typeof m === "string");
      const m = el("div", "lieu-manque");
      if (manque.length) m.append(el("span", "lieu-manque-liste", `Manque : ${manque.join(", ")}. `));
      if (texte(serveur.raison)) m.append(el("span", "lieu-manque-raison", serveur.raison));
      if (m.textContent) l.append(m);
    }
    return l;
  }

  function dessinerLieux() {
    zoneLieux.replaceChildren();
    zoneLieux.append(el("h3", "", "Où tournent les actions"));
    if (lieuxVides(lieux)) { zoneLieux.append(el("p", "ligne-detail", "Les lieux ne sont pas lus pour l'instant.")); return; }
    zoneLieux.append(legende(), el("p", "lieux-conseil", AVERTISSEMENT_CONSEIL));
    for (const a of ACTIONS) if (lieux[a] && typeof lieux[a] === "object") zoneLieux.append(ligneLieux(a, lieux[a]));
  }

  function dessiner() {
    const serveurs = tableau(courant?.serveurs).filter((s) => s && typeof s === "object" && typeof s.id === "string");
    if (!courant) resume.textContent = "Le bureau ne répond pas : les serveurs n'ont pas pu être lus.";
    else resume.textContent = serveurs.length ? "" : "Aucun serveur déclaré : déclarez-en un ci-dessous.";
    cartes.clear();
    liste.replaceChildren(...serveurs.map(cartePourServeur));
    affiches = idsAffiches();
    const rejets = tableau(courant?.rejets).filter((r) => typeof r === "string");
    rejetsZone.replaceChildren(...(rejets.length ? [el("div", "carte-sous-titre", "Déclarations ignorées"), ...rejets.map((r) => el("p", "ligne-detail serveurs-rejet", r))] : []));
    dessinerLieux();
  }

  function planifier() {
    if (poignee !== null || !actif() || !(enCours() || lance)) return;
    poignee = planifieur.attendre(async () => {
      poignee = null;
      if (!actif()) return;
      await relire();
      if (!actif()) return;
      if (enCours()) sansTravail = 0;
      else if (lance === "sonder" && empreinte() !== instantane) { lance = null; sansTravail = 0; }     // le test a rendu son résultat
      else if (lance && ++sansTravail >= RELEVES_SANS_TRAVAIL) {
        if (lance === "sonder") message.textContent = MESSAGE_TEST_ENCORE;
        lance = null; sansTravail = 0;
      }
      if (idsAffiches() !== affiches) dessiner();       // un serveur apparu ou disparu : seul cas d'un dessin complet
      else {
        for (const s of tableau(courant?.serveurs)) if (s && typeof s.id === "string") majServeur(s);
        dessinerLieux();
      }
      planifier();
    }, INTERVALLE_MS);
  }

  racine.planifier = planifier;
  racine.rafraichir = async () => { await relire(); dessiner(); planifier(); };
  racine.arreter = () => { fini = true; if (poignee !== null) { planifieur.annuler(poignee); poignee = null; } };
  dessiner();
  planifier();
  return racine;
}

// Monte l'écran dans `conteneur` : lit les serveurs et les lieux puis dessine (injoignable : l'écran le dit). Rend l'écran.
export async function monterEcranServeurs(conteneur, options = {}) {
  const fetchFn = options.fetchFn || globalThis.fetch;
  const [etat, lieux] = await Promise.all([lireServeurs(fetchFn), lireLieux(fetchFn)]);
  const ecran = ecranServeurs(etat, {...options, fetchFn, lieux});
  conteneur.append(ecran);
  ecran.planifier();   // l'écran est maintenant dans la page : une installation en cours se suit
  return ecran;
}
