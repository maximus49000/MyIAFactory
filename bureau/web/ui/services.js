// La zone « Services » de l'écran des serveurs : le service permanent de chaque projet sur le serveur (docs/serveur-services.md).
// État en toutes lettres, adresse publique, jeton à copier (lu au coffre du poste sur le clic seulement, jamais affiché),
// secrets saisis par le Directeur (champ masqué, vidé après l'envoi ; l'écran ne montre que « présent » ou « absent » par nom),
// journal (200 lignes, masquées au serveur), boutons Actualiser, Journal, Redémarrer, Arrêter, Déployer.
// Le bureau ne fait qu'afficher `GET /api/services` et demander les actions par POST. Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";

const tableau = (v) => (Array.isArray(v) ? v : []);
const texte = (v) => (typeof v === "string" ? v : "");
const objet = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

export const LIBELLES_ETATS = {actif: "actif", arrete: "arrêté", echec: "en échec", absent: "jamais déployé", supprime: "supprimé",
  inconnu: "état inconnu (actualisez)"};
export const LIBELLES_DEPLOIEMENT = {ok: "réussi", retour_arriere: "refusé, ancienne version remise", echec: "échoué", interrompu: "interrompu (le moteur a été relancé), le prochain déploiement le reprendra",
  en_cours: "en cours", occupe: "déjà en cours", refus: "refusé"};
const ACTIONS = [["etat", "Actualiser l'état"], ["journal", "Lire le journal"], ["redemarrer", "Redémarrer"], ["arreter", "Arrêter"],
  ["deployer", "Déployer maintenant"]];
const CONFIRMER = {arreter: "Arrêter le service ? Il ne répondra plus jusqu'au prochain redémarrage ou déploiement.",
  deployer: "Déployer maintenant le commit courant du projet ?"};

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

const route = (projet, action) => `/api/services/${encodeURIComponent(projet)}/${action}`;
const refus = (r) => (r.injoignable ? "Le bureau est injoignable." : texte(r.d.erreur) || `Le bureau a répondu ${r.status}.`);

// Rend la liste des services, ou null si le bureau ne répond pas comme attendu.
export async function lireServices(fetchFn = globalThis.fetch) {
  const r = await appeler("/api/services", "GET", undefined, fetchFn);
  return r.ok && Array.isArray(r.d.services) ? r.d.services : null;
}

// Demande une action (etat, journal, redemarrer, arreter, deployer) : {ok, message}.
export async function actionService(projet, action, fetchFn = globalThis.fetch) {
  const r = await appeler(route(projet, action), "POST", {}, fetchFn);
  if (r.ok) return {ok: true, message: "Demandé : le résultat s'affiche à l'actualisation."};
  return {ok: false, message: refus(r)};
}

// La case « Déployer automatiquement à chaque modification » : {ok, auto, message}.
export async function reglerAuto(projet, actif, fetchFn = globalThis.fetch) {
  const r = await appeler(route(projet, "auto"), "POST", {actif}, fetchFn);
  if (!r.ok) return {ok: false, message: refus(r)};
  return {ok: true, auto: r.d.auto === true, message: r.d.auto === true
    ? "Déploiement automatique activé : chaque modification du projet sera déployée sans demander."
    : "Déploiement automatique désactivé : le déploiement se fait au bouton « Déployer maintenant »."};
}

// Envoie un secret saisi par le Directeur. La valeur n'est jamais gardée ni affichée par l'écran.
export async function poserSecret(projet, nom, valeur, fetchFn = globalThis.fetch) {
  const r = await appeler(route(projet, "secrets"), "POST", {secrets: {[nom]: valeur}}, fetchFn);
  if (r.ok) return {ok: true, message: `${nom} envoyé au serveur : il apparaîtra « présent » à l'actualisation.`};
  return {ok: false, message: refus(r)};
}

// Lit le jeton au coffre du poste et le copie ; il n'est jamais écrit dans la page.
export async function copierJeton(projet, copier, fetchFn = globalThis.fetch) {
  const r = await appeler(route(projet, "jeton"), "POST", {}, fetchFn);
  if (!r.ok || typeof r.d.jeton !== "string") return {ok: false, message: refus(r)};
  try {
    await copier(r.d.jeton);
  } catch {
    // dernier recours : le jeton est rendu pour s'afficher dans un champ à sélectionner à la main (clic du Directeur seulement)
    return {ok: false, jeton: r.d.jeton, message: "La copie a été refusée par le navigateur : touchez le champ pour sélectionner le jeton, puis copiez-le."};
  }
  return {ok: true, message: "Jeton copié : à donner seulement aux personnes qui doivent appeler le service."};
}

function carte(s, options) {
  const {fetchFn, copier, confirmer, relire} = options;
  const projet = texte(s.projet);
  const c = el("div", "service-carte");
  const msg = el("p", "reglage-message service-message");
  msg.setAttribute("role", "status");
  const etat = LIBELLES_ETATS[s.etat] || LIBELLES_ETATS.inconnu;
  c.append(el("h4", "", `${texte(s.nom) || projet} (${projet})`));
  c.append(el("p", `serveur-badge service-etat service-etat-${LIBELLES_ETATS[s.etat] ? s.etat : "inconnu"}`, `État : ${etat}`
    + (s.sante_ok === true ? ", santé ok" : s.sante_ok === false ? ", santé en échec" : "")));
  if (texte(s.declaration_erreur)) c.append(el("p", "reglage-message", `Déclaration refusée : ${texte(s.declaration_erreur)}`));
  const dep = objet(s.deploiement);
  if (texte(dep.statut)) {
    c.append(el("p", "ligne-detail service-deploiement", `Dernier déploiement : ${LIBELLES_DEPLOIEMENT[dep.statut] || texte(dep.statut)}`
      + (texte(dep.commit) ? ` (commit ${texte(dep.commit).slice(0, 12)})` : "") + (texte(dep.detail) ? ` — ${texte(dep.detail)}` : "")));
  }
  const encours = objet(s.deploiement);      // un déploiement qui tourne : le service répond encore avec l'ancienne version
  if (encours.statut === "en_cours" || s.occupe === true) {
    const depuis = Date.parse(texte(encours.debut));
    const heure = Number.isNaN(depuis) ? "" : ` depuis ${new Date(depuis).toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"})}`;
    c.append(el("p", "reglage-message service-en-cours", `Déploiement en cours${heure}`
      + (texte(encours.commit) ? ` (commit ${texte(encours.commit).slice(0, 12)})` : "")
      + " : l'ancienne version répond encore, patientez quelques minutes puis actualisez l'état."));
  }
  const adresse = texte(s.adresse);
  c.append(el("p", "ligne-detail service-adresse", adresse ? `Adresse publique : ${adresse}` : "Adresse publique : pas encore déployé"));

  const zoneJeton = el("div", "service-jeton");
  if (s.jeton_present) {
    const b = el("button", "", "Copier le jeton");
    b.addEventListener("click", async () => {
      const res = await copierJeton(projet, copier, fetchFn);
      msg.textContent = res.message;
      zoneJeton.querySelectorAll?.(".service-jeton-champ").forEach((x) => x.remove());
      if (res.jeton) {
        const champ = el("input", "service-jeton-champ");
        champ.readOnly = true;
        champ.value = res.jeton;
        champ.addEventListener("focus", () => champ.select?.());
        zoneJeton.append(champ);
      }
    });
    zoneJeton.append(el("span", "ligne-detail", "Jeton d'accès (Authorization: Bearer) : au coffre du poste "), b);
  } else {
    zoneJeton.append(el("span", "ligne-detail", "Jeton d'accès : créé au premier déploiement"));
  }
  c.append(zoneJeton);

  const secrets = objet(s.secrets);
  const zoneSecrets = el("div", "service-secrets");
  zoneSecrets.append(el("h5", "", "Secrets (saisis par vous seul ; jamais lus par un agent)"));
  const noms = Object.keys(secrets);
  if (!noms.length) zoneSecrets.append(el("p", "ligne-detail", "Ce service ne déclare aucun secret."));
  for (const nom of noms) {
    const l = el("div", "service-secret");
    const present = secrets[nom] === true;
    const champ = el("input", "service-secret-valeur");
    champ.type = "password";
    champ.setAttribute("autocomplete", "off");
    champ.setAttribute("aria-label", `Valeur de ${nom}`);
    const b = el("button", "", present ? "Remplacer" : "Enregistrer");
    b.addEventListener("click", async () => {
      const valeur = typeof champ.value === "string" ? champ.value.trim() : "";
      if (!valeur) { msg.textContent = `Collez d'abord la valeur de ${nom}.`; return; }
      champ.value = "";                       // la valeur ne reste jamais dans la page
      b.disabled = true;
      const r = await poserSecret(projet, nom, valeur, fetchFn);
      b.disabled = false;
      msg.textContent = r.message;
    });
    l.append(el("span", `serveur-badge service-secret-${present ? "present" : "absent"}`, `${nom} : ${present ? "présent" : "absent"}`), champ, b);
    zoneSecrets.append(l);
  }
  c.append(zoneSecrets);

  const auto = document.createElement("input");     // la case : cochée, tout nouveau commit du projet est déployé sans demander
  auto.type = "checkbox";
  auto.checked = s.auto === true;
  auto.setAttribute("aria-label", "Déployer automatiquement à chaque modification");
  auto.addEventListener("change", async () => {
    const voulu = auto.checked;
    const r = await reglerAuto(projet, voulu, fetchFn);
    if (!r.ok) auto.checked = !voulu;                // refusé : la case revient comme avant
    msg.textContent = r.message;
  });
  const etiquetteAuto = el("label", "service-auto");
  etiquetteAuto.append(auto, el("span", "", " Déployer automatiquement à chaque modification (sans confirmation)"));
  c.append(etiquetteAuto);

  const actions = el("div", "service-actions");
  for (const [action, libelle] of ACTIONS) {
    const b = el("button", "", libelle);
    b.disabled = s.occupe === true;
    b.addEventListener("click", async () => {
      if (CONFIRMER[action] && !confirmer(CONFIRMER[action])) return;
      const r = await actionService(projet, action, fetchFn);
      msg.textContent = r.message;
      if (r.ok && relire) relire();
    });
    actions.append(b);
  }
  c.append(actions, msg);

  const journal = tableau(s.journal).filter((l) => typeof l === "string");
  if (journal.length) {
    const pre = el("pre", "service-journal");
    pre.textContent = journal.slice(-200).join("\n");
    c.append(el("h5", "", "Journal (200 dernières lignes, secrets masqués)"), pre);
  }
  return c;
}

// Copie : l'API du navigateur, sinon (bureau ouvert en http depuis un téléphone : API refusée) une zone de texte copiée par
// `execCommand`. Lève si aucune des deux ne copie.
export async function copierDansLePressePapiers(texte) {
  try {
    await globalThis.navigator.clipboard.writeText(texte);
    return;
  } catch { /* repli ci-dessous */ }
  const zone = document.createElement("textarea");
  zone.value = texte;
  zone.setAttribute("readonly", "");
  zone.style = "position: fixed; opacity: 0";
  document.body.append(zone);
  try {
    zone.select();
    zone.setSelectionRange?.(0, texte.length);
    if (!document.execCommand("copy")) throw new Error("copie refusée");
  } finally {
    zone.remove();
  }
}

// La zone entière. `services` : la liste (null : lecture impossible). Options : fetchFn, copier(texte), confirmer(question), relire().
export function zoneServices(services, options = {}) {
  const opts = {fetchFn: options.fetchFn || globalThis.fetch,
    copier: options.copier || copierDansLePressePapiers,
    confirmer: options.confirmer || ((q) => globalThis.confirm(q)), relire: options.relire};
  const z = el("section", "services-zone");
  z.append(el("h3", "", "Services"));
  if (services === null) {
    const e = el("p", "reglage-message", "Les services n'ont pas pu être lus.");
    e.setAttribute("role", "alert");
    z.append(e);
    return z;
  }
  const liste = tableau(services).filter((s) => s && typeof s === "object" && typeof s.projet === "string");
  if (!liste.length) {
    z.append(el("p", "ligne-detail", "Aucun projet ne déclare de service permanent (.factory/service.json)."));
    return z;
  }
  for (const s of liste) z.append(carte(s, opts));
  return z;
}

// Monte la zone dans `conteneur` et la redessine à chaque `relire` (après une action). Rend la zone.
export async function monterZoneServices(conteneur, options = {}) {
  const fetchFn = options.fetchFn || globalThis.fetch;
  let zone = null;
  async function relire() {
    const services = await lireServices(fetchFn);
    const nouvelle = zoneServices(services, {...options, fetchFn, relire});
    if (zone && zone.replaceWith) zone.replaceWith(nouvelle); else conteneur.append(nouvelle);
    zone = nouvelle;
    return zone;
  }
  return relire();
}
