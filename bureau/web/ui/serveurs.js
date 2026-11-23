// L'écran « Serveurs de travail » : déclarer un serveur (et copier sa clé publique), tester la connexion, voir ses capacités,
// installer ce qui manque (aperçu puis accord), et lire où tournent les actions (poste, GitHub, serveur) avec le conseil du bureau.
// Le bureau ne fait qu'afficher `GET /api/serveurs`, `GET /api/serveurs/lieux` et `GET /api/serveurs/taches` et demander les actions par POST. Tout texte
// venu du serveur passe par textContent ; la couleur d'un lieu vient d'une classe CSS et s'écrit toujours en toutes lettres.

import {el} from "./dom.js";

const INTERVALLE_MS = 3000;
const INTERVALLE_REPOS_MS = 15000;   // relevé des tâches quand aucune n'est active (une nouvelle tâche apparaît quand même)
const RELEVES_SANS_TRAVAIL = 20;  // relevés sans travail en cours avant de cesser de guetter une sonde ou une installation lancée (environ 1 min)
export const MESSAGE_TEST_ENCORE = "Le test peut encore être en cours : actualisez dans un instant.";
const tableau = (v) => (Array.isArray(v) ? v : []);
const texte = (v) => (typeof v === "string" ? v : "");
const objet = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

export const ACTIONS = ["apk", "tests", "lint", "release", "emulateur", "recette-emulateur", "charge"];
const LIBELLES_ACTIONS = {apk: "Construire l'APK", tests: "Lancer les tests", lint: "Analyser le code (lint)", release: "Version de diffusion (release)",
  emulateur: "Émulateur Android", "recette-emulateur": "Recette sur émulateur (image de l'émulateur)", charge: "Tâches de charge"};
const INSTALLABLES = ACTIONS.filter((a) => a !== "charge");   // « charge » ne demande aucune capacité : rien à installer
const LIEUX = ["poste", "github", "serveur"];
const LIBELLES_LIEUX = {poste: "poste", github: "GitHub", serveur: "serveur"};
const NIVEAUX = {recommande: "recommandé", possible: "possible", deconseille: "déconseillé", indisponible: "indisponible"};
const STATUTS = {presente: "présente", absente: "absente", inconnue: "inconnue", bloquee: "bloquée", non_installable: "non installable",
  a_faire: "à faire", en_cours: "en cours"};
const LIBELLES_CAPACITES = {base: "Base du serveur", durcissement: "Durcissement SSH", "android-build": "Construction Android",
  "android-emulateur": "Émulateur Android", "emulateur-image": "Image de l'émulateur", "unity-cli": "Unity CLI", "unity-editeur": "Éditeur Unity",
  "session-graphique": "Session graphique distante", agent: "Agent de développement", "agent-abonnement": "Connexion à l'abonnement",
  "unity-licence": "Licence Unity", "unity-bac-a-sable": "Bac à sable Unity"};

// Licence et bac à sable Unity (§ 5.16, tâche 14i) : textes fixes, la raison et les étapes viennent du bureau (textContent seulement).
const VARIANTES_LICENCE = new Set(["B1", "B2", "B3"]);
export function texteLicenceUnity(u) {
  const l = objet(objet(u).licence);
  if (l.etat === "conteneur") return `Licence Unity : dans le conteneur${VARIANTES_LICENCE.has(l.variante) ? ` (${l.variante})` : ""}`;
  if (l.etat === "hote") return "Licence Unity : sur l'hôte, bac à sable";
  return `Licence Unity : absente${texte(l.raison) ? ` — ${texte(l.raison)}` : ""}`;
}
export function texteBacASable(u) {
  return `Bac à sable Unity : ${objet(u).bac_a_sable === "pret" ? "prêt" : "absent"}`;
}

// « Vérifier la licence » : rétablit l'état d'avant d'une licence refusée si ses fichiers sont là, puis sonde. {ok, occupe, message}.
export async function verifierLicence(id, fetchFn = globalThis.fetch) {
  const r = await appeler(`${chemin(id)}/verifier-licence`, "POST", {}, fetchFn);
  if (r.injoignable) return {ok: false, message: INJOIGNABLE};
  if (r.status === 409) return {ok: false, occupe: true, message: texte(r.d.erreur) || "Une opération est déjà en cours."};
  if (!r.ok) return {ok: false, message: refus(r)};
  return {ok: true, message: "Vérification lancée : l'état se met à jour tout seul."};
}

// La zone Unity d'une carte : deux lignes d'état et les étapes humaines guidées (lien https seulement, mode opératoire, bouton).
export function zoneUnity(u, surBouton) {
  const z = [];
  if (!u || typeof u !== "object") return z;
  z.push(el("p", "ligne-detail serveurs-unity-licence", texteLicenceUnity(u)), el("p", "ligne-detail serveurs-unity-bac", texteBacASable(u)));
  for (const e of tableau(u.etapes).slice(0, 4)) {
    if (!e || typeof e !== "object" || !texte(e.texte)) continue;
    const bloc = el("div", "serveurs-unity-etape");
    bloc.append(el("strong", "", `Étape à faire par vous : ${texte(e.texte)}`));
    if (texte(e.lien).startsWith("https://")) {
      const a = el("a", "serveurs-unity-lien", "Documentation de Unity Hub");
      a.href = e.lien; a.target = "_blank"; a.rel = "noopener noreferrer";
      bloc.append(el("span", "", " "), a);
    }
    const liste = el("ol", "serveurs-unity-mode");
    for (const pas of tableau(e.mode_operatoire).slice(0, 10)) if (texte(pas)) liste.append(el("li", "", texte(pas)));
    bloc.append(liste);
    if (texte(e.bouton)) {
      const b = el("button", "bouton serveurs-unity-verifier", texte(e.bouton));
      b.type = "button";
      b.addEventListener("click", () => surBouton(b, e));
      bloc.append(b);
    }
    z.push(bloc);
  }
  return z;
}

// La procédure de connexion à l'abonnement (faite une fois par le Directeur sur le serveur) : une adresse fixe du dépôt public.
export const LIEN_CONNEXION_ABONNEMENT = "https://github.com/maximus49000/MyIAFactory/blob/main/docs/serveur-agents.md#connexion-a-l-abonnement";
export const MESSAGE_ABONNEMENT_A_FAIRE = "Connexion à l'abonnement à faire";
const ABONNEMENT_A_FAIRE = new Set(["absente", "a_faire", "bloquee"]);

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

// La migration du serveur OVH existant. `lireMigration` ne lit que des fichiers côté bureau. Ne lève jamais : proposition ou null.
export const MESSAGE_MIGRATION_DETECTEE = "Votre serveur OVH a été détecté";
export const LIBELLE_ACCORD_MIGRATION = "J'autorise l'inscription de ce serveur (rien n'est réinstallé ni modifié sur le serveur)";

export async function lireMigration(fetchFn = globalThis.fetch) {
  const r = await appeler("/api/serveurs/migration", "GET", undefined, fetchFn);
  const p = r.ok ? objet(r.d.proposition) : {};
  return r.ok && p.serveur && typeof p.serveur === "object" ? p : null;
}

// L'aperçu de la migration (sondes en lecture seule). Ne lève jamais : {ok, apercu, message}.
export async function apercuMigration(fetchFn = globalThis.fetch) {
  const r = await appeler("/api/serveurs/migration/apercu", "POST", {}, fetchFn);
  if (r.injoignable) return {ok: false, message: "Aperçu impossible : le bureau est injoignable."};
  if (!r.ok) return {ok: false, message: refus(r)};
  return {ok: true, apercu: r.d};
}

// Confirme la migration. `accord` n'est envoyé vrai que s'il vaut exactement `true`. Ne lève jamais : {ok, message}.
export async function confirmerMigration(accord, fetchFn = globalThis.fetch) {
  const r = await appeler("/api/serveurs/migration/confirmer", "POST", {accord: accord === true}, fetchFn);
  if (r.injoignable) return {ok: false, message: "Migration impossible : le bureau est injoignable."};
  if (!r.ok) return {ok: false, status: r.status, message: refus(r)};
  return {ok: true, message: "Serveur inscrit."};
}

// Les tâches d'émulation du serveur : `GET /api/serveurs/taches` (index local, jamais de réseau) et l'arrêt par POST.
const LIBELLES_ETATS_TACHE = {en_attente: "en attente", en_cours: "en cours", terminee: "terminée", echouee: "échouée", arretee: "arrêtée", inconnu: "état inconnu"};
const LIBELLES_STATUTS_RAPPORT = {ok: "ok", plantage: "plantage", limite: "limite atteinte", erreur: "erreur"};
const LIBELLES_MODES = {scenario: "scénario", pilote: "pilote", seul: "seul"};
const ETATS_FINAUX = new Set(["terminee", "echouee", "arretee"]);
const TACHES_ACTIVES = new Set(["en_attente", "en_cours"]);
const estActive = (t) => TACHES_ACTIVES.has(t.etat);

// Lit les tâches. Rend {taches}, ou null si le bureau est injoignable ou répond mal.
export async function lireTaches(fetchFn = globalThis.fetch) {
  const r = await appeler("/api/serveurs/taches", "GET", undefined, fetchFn);
  return r.ok && Array.isArray(r.d.taches) ? {taches: r.d.taches} : null;
}

// Demande l'arrêt d'une tâche. Ne lève jamais : {ok, occupe, message}.
export async function arreterTache(id, fetchFn = globalThis.fetch) {
  const r = await appeler(`/api/serveurs/taches/${encodeURIComponent(id)}/arreter`, "POST", {}, fetchFn);
  if (r.injoignable) return {ok: false, message: "Arrêt impossible : le bureau est injoignable."};
  if (r.status === 409) return {ok: false, occupe: true, message: texte(r.d.erreur) || "Une opération est déjà en cours : réessayez dans un instant."};
  if (!r.ok) return {ok: false, message: refus(r)};
  // l'arrêt d'un agent répond avec l'état final (absent : l'arrêt tourne encore) et, pour un agent pilote, celui de son
  // émulation liée (`arretee`, `non_confirmee` ; absent : pas d'émulation liée)
  return {ok: true, etat: texte(r.d.etat), emulation: texte(r.d.emulation)};
}

// Le message de fin d'un arrêt d'agent : il ne parle d'émulation que s'il y en avait une, et dit si son arrêt a échoué.
export function messageArretAgent(r) {
  if (!ETATS_FINAUX.has(r.etat)) return `L'arrêt n'est pas confirmé (état : ${LIBELLES_ETATS_TACHE[r.etat] || "état inconnu"}).`;
  if (r.emulation === "arretee") return "Arrêt confirmé : l'agent et son émulation sont arrêtés.";
  if (r.emulation === "non_confirmee") return "Arrêt de l'agent confirmé ; l'arrêt de son émulation n'est pas confirmé.";
  return "Arrêt confirmé : l'agent est arrêté.";
}

function duree(s) {
  if (typeof s !== "number" || !Number.isFinite(s) || s < 0) return "";
  const n = Math.round(s);
  return n < 60 ? `${n} s` : `${Math.floor(n / 60)} min ${n % 60} s`;
}
const compte = (n) => (typeof n === "number" && Number.isFinite(n) && n >= 0 ? `${Math.floor(n)} capture${n >= 2 ? "s" : ""}` : "");

const nombre = (v) => (typeof v === "number" && Number.isFinite(v) ? String(Math.round(v * 10) / 10).replace(".", ",") : "?");

// Le serveur envoie, par capacité, {statut, detail, geste} (statuts du moteur : presente, absente, inconnue, a_faire, en_cours,
// fait, bloque). Une simple chaîne reste lue comme un statut. La raison (détail puis geste proposé) se montre quand elle aide :
// capacité bloquée, à faire (en attente) ou inconnue.
const STATUTS_MOTEUR = {fait: "presente", bloque: "bloquee"};
const AVEC_RAISON = new Set(["bloquee", "a_faire", "inconnue"]);
function statutCapacite(valeur, bloquee) {
  if (bloquee) return {statut: "non_installable", raison: texte(bloquee.raison)};
  const brut = typeof valeur === "string" ? {statut: valeur} : objet(valeur);
  const lu = STATUTS_MOTEUR[brut.statut] || brut.statut;
  const statut = STATUTS[lu] ? lu : "inconnue";
  const raison = AVEC_RAISON.has(statut) ? [texte(brut.raison) || texte(brut.detail), texte(brut.geste)].filter(Boolean).join(" ") : "";
  return {statut, raison};
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
  const zoneMigration = el("div", "serveurs-migration");
  const zoneTaches = el("div", "serveurs-taches");
  racine.append(message, zoneMigration, resume, liste, zoneTaches, rejetsZone, formulaire, zoneLieux);

  let courant = etat;
  let lieux = options.lieux || null;
  const infos = new Map();      // id du serveur -> {ouvert, actions, apercu, message, chargement}
  let lance = null;             // genre du travail qu'on vient de lancer (« sonder » | « installer ») : on guette sa fin
  let sansTravail = 0;
  let poignee = null;
  let fini = false;
  let taches = options.taches;    // undefined : l'écran ne montre pas les tâches ; null : lecture impossible ; sinon la liste
  let echecLecture = taches === null;
  let poigneeTaches = null;
  const lignesTaches = new Map(); // id de la tâche -> éléments mis à jour en place à chaque relevé
  const envois = new Set();       // tâches dont un POST d'arrêt est parti et n'a pas encore reçu sa réponse
  const refusArret = new Map();   // id de la tâche -> message du dernier arrêt refusé ou impossible
  const noteArret = new Map();    // id de la tâche -> ce que la réponse de l'arrêt a dit de l'état final
  let idsTaches = "";             // les tâches dessinées, dans l'ordre
  const cartes = new Map();     // id du serveur -> éléments mis à jour en place à chaque relevé
  let affiches = "";            // les serveurs dessinés
  let lectures = 0;             // relevés faits depuis le lancement d'un test
  const idsAffiches = () => tableau(courant?.serveurs).filter((s) => s && typeof s === "object" && typeof s.id === "string").map((s) => s.id).join("\n");

  const actif = () => !fini && (options.actif ? options.actif() : racine.isConnected !== false);
  const sondeTourne = () => tableau(courant?.serveurs).some((s) => s?.sonde_en_cours === true);
  const enCours = () => tableau(courant?.serveurs).some((s) => s?.installation_en_cours === true) || sondeTourne();
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
      const avant = i.vues;                    // l'état des capacités au départ de la demande
      const r = await apercuInstallation(serveur.id, ACTIONS.filter((a) => i.actions.has(a)), fetchFn);
      i.chargement = false;
      if (r.ok && i.vues !== avant) i.message = "L'état du serveur a changé : refaites l'aperçu avant d'installer.";   // aperçu déjà périmé
      else if (r.ok) { i.apercu = r.apercu; i.message = ""; } else i.message = r.message;
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
    lancer.disabled = i.envoi === true || serveur.installation_en_cours === true;   // un bouton reconstruit pendant un envoi reste grisé
    i.lancer = lancer;
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
    const abonnement = el("p", "ligne-detail serveurs-abonnement");
    const erreur = el("p", "reglage-message serveurs-erreur");
    erreur.setAttribute("role", "alert");
    c.append(encours, erreur, abonnement);
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
    const zone = el("div", "serveurs-installation-zone");
    const unity = el("div", "serveurs-unity");
    const refs = {encours, erreur, abonnement, tester, verifier, installer, capacites, msg, zone, unity};
    cartes.set(serveur.id, refs);
    majServeur(serveur);
    const sonde = async (b) => {
      if (b.disabled) return;
      i.message = "Envoi…"; msg.textContent = i.message;
      const r = await sonderServeur(serveur.id, fetchFn);
      i.message = r.message;
      if (r.ok || r.occupe) { lance = "sonder"; sansTravail = 0; lectures = 0; }
      majServeur(entreeCourante(serveur));     // l'entrée du dernier relevé, pas celle de la création de la carte
      planifier();
    };
    refs.surUnity = async (b, etape) => {
      if (b.disabled) return;
      if (texte(etape.bouton) !== "Vérifier la licence") return sonde(b);     // « Vérifier l'éditeur » : la sonde seule
      i.message = "Envoi…"; msg.textContent = i.message;
      const r = await verifierLicence(serveur.id, fetchFn);
      i.message = r.message;
      if (r.ok || r.occupe) { lance = "sonder"; sansTravail = 0; lectures = 0; }
      majServeur(entreeCourante(serveur));
      planifier();
    };
    tester.addEventListener("click", () => sonde(tester));
    verifier.addEventListener("click", () => sonde(verifier));
    installer.addEventListener("click", () => { if (installer.disabled) return; i.ouvert = !i.ouvert; i.apercu = null; dessiner(); });
    const barre = el("div", "serveurs-boutons");
    barre.append(tester, verifier, installer);
    c.append(capacites, unity, barre, msg, zone);
    reconstruireInstallation(serveur);
    return c;
  }

  const entreeCourante = (serveur) => tableau(courant?.serveurs).find((s) => s && s.id === serveur.id) || serveur;

  // La zone d'installation d'une carte (cases d'actions, aperçu, accord) : seule celle-ci est refaite.
  function reconstruireInstallation(serveur) {
    const r = cartes.get(serveur.id);
    const i = info(serveur.id);
    i.lancer = null;
    if (r) r.zone.replaceChildren(...(i.ouvert ? [panneauInstallation(serveur, i)] : []));
  }

  // Les capacités ont changé depuis le dernier relevé vu : l'aperçu (et l'accord donné pour lui) ne vaut plus.
  // Rend vrai si un aperçu a été écarté.
  function perimer(serveur) {
    const i = info(serveur.id);
    const vu = JSON.stringify(serveur.capacites ?? null);
    const change = i.vues !== undefined && i.vues !== vu;
    i.vues = vu;
    if (change && i.apercu) { i.apercu = null; return true; }
    return false;
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
    const aFaire = ABONNEMENT_A_FAIRE.has(statutCapacite(objet(serveur.capacites)["agent-abonnement"]).statut);
    if (!aFaire) r.abonnement.replaceChildren();
    else if (!r.abonnement.textContent) {       // le texte et le lien sont fixes : jamais ce que le serveur en dit
      const lien = el("a", "serveurs-abonnement-lien", "Voir la procédure");
      lien.href = LIEN_CONNEXION_ABONNEMENT;
      lien.target = "_blank";
      lien.rel = "noopener noreferrer";
      r.abonnement.append(el("strong", "", `${MESSAGE_ABONNEMENT_A_FAIRE}. `), lien);
    }
    r.tester.disabled = occupe;
    r.verifier.disabled = occupe;
    r.installer.disabled = occupe || lance === "installer";
    const ecarte = perimer(serveur);
    remplirCapacites(r.capacites, serveur, i);
    r.unity.replaceChildren(...zoneUnity(serveur.unity, (b, e) => r.surUnity && r.surUnity(b, e)));
    if (ecarte) { i.message = "L'état du serveur a changé : refaites l'aperçu avant d'installer."; reconstruireInstallation(serveur); }
    if (i.lancer) i.lancer.disabled = occupe || i.envoi === true;
    r.msg.textContent = i.message;
  }

  // ---- « Tâches du serveur » : la liste est refaite quand l'ordre ou l'ensemble des tâches change, sinon mise à jour en place
  // (jamais d'autre zone de la carte). Tout texte venu du serveur passe par textContent ; l'état s'écrit toujours en toutes lettres.
  const tachesZone = {
    echec: el("p", "reglage-message serveurs-taches-echec"),
    vide: el("p", "ligne-detail serveurs-taches-vide"),
    liste: el("div", "serveurs-taches-liste"),
  };
  tachesZone.echec.setAttribute("role", "alert");
  if (taches !== undefined) zoneTaches.append(el("h3", "", "Tâches du serveur"), tachesZone.echec, tachesZone.vide, tachesZone.liste);

  const tachesValides = () => tableau(taches).filter((t) => t && typeof t === "object" && typeof t.id === "string").map((t) => ({...t, etat: LIBELLES_ETATS_TACHE[t.etat] ? t.etat : "inconnu"}));

  function ligneTache(t) {
    const racineLigne = el("div", "serveurs-tache");
    const tete = el("div", "serveurs-tache-tete");
    const refs = {ligne: racineLigne, etat: el("span", "serveur-badge tache-etat"), statut: el("span", "serveur-badge tache-statut"),
      detail: el("span", "ligne-detail serveurs-tache-detail"), actions: el("div", "serveurs-tache-actions"), msg: el("p", "reglage-message serveurs-tache-message"), bouton: null};
    refs.msg.setAttribute("role", "alert");
    tete.append(el("strong", "serveurs-tache-id", t.id), ...(t.type === "agent" ? [el("span", "serveur-badge tache-type", "agent serveur")] : []),
      refs.etat, refs.statut, refs.detail);
    racineLigne.append(tete, refs.actions, refs.msg);
    return refs;
  }

  function boutonArret(refs, id) {
    const b = el("button", "bouton serveurs-tache-arreter", "Arrêter");
    b.type = "button";
    b.addEventListener("click", async () => {
      if (b.disabled || envois.has(id)) return;
      envois.add(id);                                   // posé de façon synchrone : aucun second envoi avant la réponse
      b.disabled = true;
      refusArret.delete(id);
      refs.msg.textContent = "Arrêt demandé…";
      let r;
      try { r = await arreterTache(id, fetchFn); } finally { envois.delete(id); }
      if (!r.ok) refusArret.set(id, r.message);
      else if (r.etat) noteArret.set(id, messageArretAgent(r));
      await relireTaches();
      majTaches();
      planifierTaches();
    });
    return b;
  }

  function majLigneTache(refs, t) {
    const id = t.id;
    const arretEnCours = t.arret_en_cours === true || envois.has(id);
    refs.etat.className = `serveur-badge tache-etat tache-etat-${t.etat}`;
    refs.etat.textContent = LIBELLES_ETATS_TACHE[t.etat];
    refs.statut.textContent = LIBELLES_STATUTS_RAPPORT[t.statut] ? `rapport : ${LIBELLES_STATUTS_RAPPORT[t.statut]}` : "";
    refs.statut.className = `serveur-badge tache-statut tache-statut-${LIBELLES_STATUTS_RAPPORT[t.statut] ? t.statut : "aucun"}`;
    const agent = t.type === "agent";
    refs.detail.textContent = [LIBELLES_MODES[t.mode], texte(t.projet), agent && texte(t.tache) && `tâche ${t.tache}`, agent && texte(t.branche) && `branche ${t.branche}`,
      texte(t.serveur_id) && `serveur ${t.serveur_id}`, duree(t.duree_s), agent ? "" : compte(t.captures)].filter(Boolean).join(" · ");
    if (estActive(t)) {
      if (!refs.bouton) { refs.bouton = boutonArret(refs, id); refs.actions.append(refs.bouton); }
      refs.bouton.disabled = arretEnCours;
      refs.bouton.textContent = arretEnCours ? "Arrêt en cours…" : "Arrêter";
    } else if (refs.bouton) { refs.actions.replaceChildren(); refs.bouton = null; refusArret.delete(id); }
    refs.msg.textContent = envois.has(id) ? "Arrêt demandé…" : arretEnCours ? "Arrêt en cours : un instant." : texte(refusArret.get(id)) || texte(t.erreur) || texte(noteArret.get(id));
  }

  function majTaches() {
    if (taches === undefined) return;
    const valides = tachesValides();
    tachesZone.echec.textContent = echecLecture ? (valides.length ? "Mise à jour impossible : dernière liste connue." : "Les tâches n'ont pas pu être lues : nouvel essai dans un instant.") : "";
    tachesZone.vide.textContent = !echecLecture && !valides.length ? "Aucune tâche pour l'instant : les tâches d'émulation lancées sur le serveur apparaîtront ici." : "";
    const ids = valides.map((t) => t.id).join("\n");
    if (ids !== idsTaches) {                            // un ensemble ou un ordre différent : seule la liste des tâches est refaite
      lignesTaches.clear();
      tachesZone.liste.replaceChildren(...valides.map((t) => { const refs = ligneTache(t); lignesTaches.set(t.id, refs); return refs.ligne; }));
      idsTaches = ids;
    }
    for (const t of valides) majLigneTache(lignesTaches.get(t.id), t);
  }

  async function relireTaches() {
    const r = await lireTaches(fetchFn);
    echecLecture = r === null;
    if (r) taches = r.taches;
    return r;
  }

  function planifierTaches() {
    if (poigneeTaches !== null || !actif() || taches === undefined) return;
    const vives = tachesValides().some(estActive) || envois.size > 0;
    poigneeTaches = planifieur.attendre(async () => {
      poigneeTaches = null;
      if (!actif()) return;
      await relireTaches();
      if (!actif()) return;
      majTaches();
      planifierTaches();
    }, vives ? INTERVALLE_MS : INTERVALLE_REPOS_MS);
  }

  // ---- « Aptitude des lieux » : lecture seule ; le choix se fait dans la page Réglages
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
      const pastille = el("span", `lieu-pastille niveau-${niveau}`);
      pastille.setAttribute("data-lieu", nom);
      const etiquette = el("span", "lieu-etiquette", `${LIBELLES_LIEUX[nom]} — ${NIVEAUX[niveau]}`);
      etiquette.setAttribute("data-lieu", nom);
      if (texte(f.raison)) etiquette.setAttribute("title", f.raison);
      const choixLieu = el("span", `lieu-choix lieu-${nom}${permis ? "" : " lieu-grise"}`);
      choixLieu.append(pastille, etiquette);
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
    zoneLieux.append(el("h3", "", "Aptitude des lieux"));
    if (lieuxVides(lieux)) { zoneLieux.append(el("p", "ligne-detail", "Les lieux ne sont pas lus pour l'instant.")); return; }
    zoneLieux.append(legende(), el("p", "lieux-conseil", AVERTISSEMENT_CONSEIL));
    if (typeof options.ouvrirReglages === "function") {
      const regler = el("button", "bouton lieux-regler", "Régler dans Réglages");
      regler.type = "button";
      regler.addEventListener("click", () => options.ouvrirReglages());
      zoneLieux.append(regler);
    }
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
      const serveurs = tableau(courant?.serveurs);
      const sondeConnue = serveurs.some((s) => typeof s?.sonde_en_cours === "boolean");
      if (!sondeTourne() && message.textContent === MESSAGE_TEST_ENCORE) message.textContent = "";   // le test a fini : l'avis tombe
      if (lance === "sonder") {
        lectures++;
        if (sondeConnue && !sondeTourne()) { lance = null; lectures = 0; }                 // front descendant : fin, sans message
        else if (lectures >= RELEVES_SANS_TRAVAIL) { message.textContent = MESSAGE_TEST_ENCORE; lance = null; lectures = 0; }
      } else if (enCours()) sansTravail = 0;
      else if (lance && ++sansTravail >= RELEVES_SANS_TRAVAIL) { lance = null; sansTravail = 0; }
      if (idsAffiches() !== affiches) dessiner();       // un serveur apparu ou disparu : seul cas d'un dessin complet
      else {
        for (const s of tableau(courant?.serveurs)) if (s && typeof s.id === "string") majServeur(s);
        dessinerLieux();
      }
      planifier();
    }, INTERVALLE_MS);
  }

  // ---- la migration du serveur OVH existant : jamais d'écriture sans la case cochée et le bouton de confirmation
  function cartesMigration(proposition) {
    const p = objet(proposition);
    const s = objet(p.serveur);
    const carte = el("div", "serveurs-migration-carte");
    const note = el("p", "reglage-message serveurs-migration-message");
    note.setAttribute("aria-live", "polite");
    const detail = el("div", "serveurs-migration-detail");
    carte.append(el("h3", "", MESSAGE_MIGRATION_DETECTEE),
      el("p", "serveurs-migration-resume", `${texte(s.nom) || "Serveur OVH"} : ${texte(s.utilisateur)}@${texte(s.hote)} (fournisseur ${texte(s.fournisseur) || "aucun"}).`),
      el("p", "serveurs-migration-source", `Lu dans : ${tableau(p.source).filter((f) => typeof f === "string").join(", ")}. Rien n'est réinstallé : seul le bureau l'inscrit.`),
      detail, note);
    const bApercu = el("button", "bouton serveurs-migration-apercu", "Voir l'aperçu (lecture seule)");
    bApercu.type = "button";
    const accord = el("input", "serveurs-accord");
    accord.type = "checkbox";
    accord.checked = false;
    const etiquette = el("label", "serveurs-accord-libelle");
    etiquette.append(accord, el("span", "", ` ${LIBELLE_ACCORD_MIGRATION}`));
    const bConfirmer = el("button", "bouton serveurs-migration-confirmer", "Confirmer l'inscription du serveur");
    bConfirmer.type = "button";
    let envoi = false;
    let aRelire = false;                    // après un délai dépassé (504), la liste doit être relue avant tout nouvel envoi
    const declare = () => tableau(courant?.serveurs).length > 0;
    bApercu.addEventListener("click", async () => {
      if (bApercu.disabled) return;
      bApercu.disabled = true;
      note.textContent = "Lecture du serveur…";
      const r = await apercuMigration(fetchFn);
      bApercu.disabled = false;
      note.textContent = r.ok ? "" : r.message;
      if (!r.ok) return;
      const caps = objet(r.apercu.capacites);
      detail.replaceChildren(el("div", "carte-sous-titre", r.apercu.joignable === false ? "Serveur injoignable : état inconnu" : "État constaté sur le serveur"),
        ...Object.keys(LIBELLES_CAPACITES).filter((i) => i in caps).map((i) => {
          const statut = STATUTS[caps[i]] ? caps[i] : "inconnue";
          return el("div", "serveurs-capacite", `${LIBELLES_CAPACITES[i]} : ${STATUTS[statut]}`);
        }));
    });
    bConfirmer.addEventListener("click", async () => {
      if (envoi || bConfirmer.disabled) return;
      // L'accord n'est donné que par la case cochée, et il ne sert qu'une fois : décochée tout de suite, avant l'envoi.
      const accorde = accord.checked === true;
      accord.checked = false;
      if (aRelire) {                         // aucun envoi : on relit d'abord la liste (la confirmation a pu aboutir)
        envoi = true;
        const neuf = await relire();
        envoi = false;
        if (neuf && declare()) { zoneMigration.replaceChildren(); dessiner(); return; }
        if (neuf) { aRelire = false; note.textContent = "Liste relue : le serveur n'est pas inscrit. Cochez la case puis confirmez de nouveau."; }
        else note.textContent = "Relisez d'abord la liste des serveurs : la confirmation précédente a peut-être abouti.";
        return;
      }
      if (!accorde) { note.textContent = "Cochez la case d'accord pour inscrire le serveur."; return; }
      envoi = true;                         // posé de façon synchrone : aucun second envoi avant la réponse
      bConfirmer.disabled = true;
      note.textContent = "Inscription…";
      let r;
      try { r = await confirmerMigration(true, fetchFn); } finally { envoi = false; bConfirmer.disabled = false; }
      if (r.ok) {
        zoneMigration.replaceChildren();
        message.textContent = "Serveur OVH inscrit : ses capacités sont celles constatées.";
        await relire();
        dessiner();
        planifier();
        return;
      }
      note.textContent = r.message;
      if (r.status === 409 || r.status === 504) {      // déjà déclaré, ou issue inconnue : on relit la liste avant toute autre chose
        if (r.status === 504) aRelire = true;
        const neuf = await relire();
        if (neuf) {
          if (r.status === 504) aRelire = false;
          if (declare()) { zoneMigration.replaceChildren(); dessiner(); return; }
        } else if (r.status === 504) note.textContent = `${r.message} Relisez la liste des serveurs avant de réessayer.`;
        dessiner();
      }
    });
    carte.append(bApercu, etiquette, bConfirmer);
    return carte;
  }
  if (options.migration) zoneMigration.append(cartesMigration(options.migration));

  racine.planifier = () => { planifier(); planifierTaches(); };
  racine.rafraichir = async () => { await relire(); if (taches !== undefined) { await relireTaches(); majTaches(); } dessiner(); planifier(); planifierTaches(); };
  racine.arreter = () => {
    fini = true;
    if (poignee !== null) { planifieur.annuler(poignee); poignee = null; }
    if (poigneeTaches !== null) { planifieur.annuler(poigneeTaches); poigneeTaches = null; }
  };
  dessiner();
  majTaches();
  planifier();
  planifierTaches();
  return racine;
}

// Monte l'écran dans `conteneur` : lit les serveurs et les lieux puis dessine (injoignable : l'écran le dit). Rend l'écran.
export async function monterEcranServeurs(conteneur, options = {}) {
  const fetchFn = options.fetchFn || globalThis.fetch;
  const [etat, lieux, migration, lues] = await Promise.all([lireServeurs(fetchFn), lireLieux(fetchFn), lireMigration(fetchFn), lireTaches(fetchFn)]);
  const ecran = ecranServeurs(etat, {...options, fetchFn, lieux, migration, taches: lues ? lues.taches : null});
  conteneur.append(ecran);
  ecran.planifier();   // l'écran est maintenant dans la page : une installation en cours se suit
  return ecran;
}
