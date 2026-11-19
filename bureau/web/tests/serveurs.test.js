// L'écran « Serveurs de travail » du bureau, rendu sur un faux DOM : déclaration, clé à copier, capacités, aperçu et accord
// d'installation, lieux colorés (conseil seulement), injoignable, texte hostile, suivi arrêté quand l'écran disparaît.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.attributs = {}; this.disabled = false; this.checked = false; this.value = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const {ecranServeurs, installerCapacites} = await import("../ui/serveurs.js");

const reponse = (status, corps) => ({ok: status >= 200 && status < 300, status, json: async () => corps});
const SERVEUR = {id: "s1", nom: "Mon serveur", hote: "203.0.113.5", utilisateur: "robot", fournisseur: "ovh",
  capacites: {base: "presente", "android-build": "absente", "unity-editeur": "inconnue"}, installation_en_cours: false,
  ligne_cle_publique: "ssh-ed25519 AAAAC3Nza robot@bureau"};
const ETAT = {serveurs: [SERVEUR], rejets: []};
const lieu = (niveau, extra = {}) => ({permis: true, raison: `raison ${niveau}`, niveau, fondee_sur: "regle", ...extra});
const LIEUX = {apk: {poste: lieu("possible"), github: lieu("recommande"),
  serveur: {permis: false, manque: ["android-build"], raison: "Capacités manquantes sur « Mon serveur » : android-build (absente).", niveau: "indisponible", fondee_sur: "regle", serveur_id: "s1"}}};
const LIEUX_OK = {apk: {poste: lieu("possible"), github: lieu("deconseille"), serveur: lieu("recommande", {serveur_id: "s1", manque: []})}};

const boutons = (c, texte) => c.tous((n) => n.tagName === "button" && (texte === undefined || n.textContent === texte));
const cases = (c) => c.tous((n) => n.tagName === "input" && n.type === "checkbox");
const caseAccord = (c) => c.tous((n) => n.tagName === "input" && n.type === "checkbox" && n.className.includes("serveurs-accord"))[0];
const clic = (n) => n.auteurs.click[0]();

function minuterie() {
  const m = {taches: [], annulees: 0, attendre(f, ms) { m.taches.push({f, ms}); return m.taches.length; }, annuler() { m.annulees++; },
    async tic() { const t = m.taches.shift(); await t.f(); }};
  return m;
}

// Un faux réseau : `routes` associe « METHODE chemin » à une réponse (ou une fonction). Tout appel est noté.
function reseau(routes) {
  const appels = [];
  const f = async (url, init = {}) => {
    const methode = init.method || "GET";
    const chemin = url.split("?")[0];
    appels.push({methode, url, chemin, init, corps: init.body ? JSON.parse(init.body) : null});
    const r = routes[`${methode} ${chemin}`];
    if (r === undefined) return reponse(404, {erreur: "inconnu"});
    return typeof r === "function" ? r(init) : r;
  };
  f.appels = appels;
  return f;
}

// Un aperçu ouvert sur le serveur s1 (action apk cochée par défaut).
async function ouvrirApercu(apercu, extra = {}) {
  const f = reseau({"POST /api/serveurs/s1/apercu": reponse(200, apercu), "POST /api/serveurs/s1/installer": reponse(202, {demarre: true}),
    "GET /api/serveurs": reponse(200, ETAT), "GET /api/serveurs/lieux": reponse(200, LIEUX), ...extra});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: minuterie(), lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Voir l'aperçu")[0]);
  return {c, f};
}

test("la ligne de cle publique est affichee et copiable", async () => {
  const copies = [];
  const c = ecranServeurs(ETAT, {fetchFn: reseau({}), planifier: minuterie(), copier: async (t) => { copies.push(t); }, lieux: LIEUX});
  const ligne = c.tous((n) => n.className.includes("serveurs-cle-ligne"))[0];
  assert.equal(ligne.textContent, "ssh-ed25519 AAAAC3Nza robot@bureau");
  await clic(boutons(c, "Copier la ligne")[0]);
  assert.deepEqual(copies, ["ssh-ed25519 AAAAC3Nza robot@bureau"]);
  assert.match(c.textContent, /Copiée/);
  const sans = ecranServeurs({serveurs: [{...SERVEUR, ligne_cle_publique: null}], rejets: []}, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  assert.equal(sans.tous((n) => n.className.includes("serveurs-cle-ligne")).length, 0);
  assert.equal(boutons(sans, "Copier la ligne").length, 0);
});

test("le choix serveur est grise avec ce qui manque", () => {
  const c = ecranServeurs(ETAT, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  const choix = c.tous((n) => n.tagName === "input" && n.type === "radio");
  const serveur = choix.find((n) => n.value === "serveur");
  assert.equal(serveur.disabled, true);
  assert.equal(choix.find((n) => n.value === "poste").disabled, false);
  assert.equal(choix.find((n) => n.value === "github").disabled, false);
  assert.match(c.textContent, /Manque : android-build/);
  assert.match(c.textContent, /Capacités manquantes sur « Mon serveur »/);
});

test("le choix serveur est actif quand les capacites sont presentes", () => {
  const c = ecranServeurs(ETAT, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX_OK});
  const serveur = c.tous((n) => n.tagName === "input" && n.type === "radio").find((n) => n.value === "serveur");
  assert.equal(serveur.disabled, false);
  assert.doesNotMatch(c.textContent, /Manque :/);
});

test("chaque lieu porte sa couleur par classe, son libelle en toutes lettres, sa raison au survol et la legende", () => {
  const c = ecranServeurs(ETAT, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  const pastille = (lieuNom) => c.tous((n) => n.className.includes("lieu-pastille") && n.attributs["data-lieu"] === lieuNom)[0];
  assert.match(pastille("github").className, /niveau-recommande/);
  assert.match(pastille("poste").className, /niveau-possible/);
  assert.match(pastille("serveur").className, /niveau-indisponible/);
  const etiquette = (lieuNom) => c.tous((n) => n.className.includes("lieu-etiquette") && n.attributs["data-lieu"] === lieuNom)[0];
  assert.match(etiquette("github").textContent, /GitHub.*recommandé/);
  assert.match(etiquette("poste").textContent, /poste.*possible/);
  assert.match(etiquette("serveur").textContent, /serveur.*indisponible/);
  assert.equal(etiquette("github").attributs.title, "raison recommande");
  for (const mot of ["recommandé", "possible", "déconseillé", "indisponible"]) assert.match(c.tous((n) => n.className.includes("lieux-legende"))[0].textContent, new RegExp(mot));
  assert.match(c.textContent, /ce n'est qu'un conseil/i);
  const rouge = ecranServeurs(ETAT, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX_OK});
  assert.match(rouge.tous((n) => n.className.includes("lieu-pastille") && n.attributs["data-lieu"] === "github")[0].className, /niveau-deconseille/);
});

test("capacite non installable affiche sa raison", async () => {
  const apercu = {manquantes: ["android-build", "unity-editeur"], taille_go: 5.4, duree_min: 10,
    bloquees: [{id: "unity-editeur", raison: "installer l'éditeur par la session graphique (Unity Hub)"}], etat: {}};
  const {c} = await ouvrirApercu(apercu);
  assert.match(c.textContent, /non installable/);
  assert.match(c.textContent, /installer l'éditeur par la session graphique \(Unity Hub\)/);
  assert.match(c.textContent, /5,4 Go/);
  assert.match(c.textContent, /10 min/);
});

const cap = (statut, detail = "", geste = "") => ({statut, detail, geste});    // la forme réelle envoyée par le serveur

test("les capacites se lisent : presente, absente, inconnue, bloque (forme reelle du serveur)", () => {
  const e = {serveurs: [{...SERVEUR, capacites: {base: cap("presente", "Constatée par la sonde."), "android-build": cap("absente"),
    "unity-cli": cap("inconnue"), "unity-editeur": cap("bloque", "pas d'éditeur", "Installez-le par Unity Hub.")}}], rejets: []};
  const c = ecranServeurs(e, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  for (const mot of [/présente/, /absente/, /inconnue/, /bloquée/, /pas d'éditeur/, /Installez-le par Unity Hub/]) assert.match(c.textContent, mot);
  assert.equal(c.tous((n) => n.className.includes("capacite-badge-bloquee")).length, 1);
  assert.doesNotMatch(c.textContent, /Constatée par la sonde/);       // le détail d'une capacité présente n'encombre pas la carte
});

test("les statuts du moteur a_faire et en_cours se lisent en francais, bloque garde sa raison", () => {
  const e = {serveurs: [{...SERVEUR, capacites: {base: cap("en_cours", "Installation de « Base » en cours."),
    "android-build": cap("a_faire", "En attente de base.", "Relancez l'installation."), agent: cap("bloque", "Disque plein", "Libérez de la place.")}}], rejets: []};
  const c = ecranServeurs(e, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  assert.equal(c.tous((n) => n.className.includes("capacite-badge-en_cours")).length, 1);
  assert.equal(c.tous((n) => n.className.includes("capacite-badge-a_faire")).length, 1);
  assert.equal(c.tous((n) => n.className.includes("capacite-badge-bloquee")).length, 1);
  for (const mot of [/à faire/, /en cours/, /bloquée/, /En attente de base/, /Disque plein/, /Libérez de la place/]) assert.match(c.textContent, mot);
  assert.doesNotMatch(c.textContent, /a_faire|en_cours|bloque\b/);
});

test("le detail d'une capacite bloquee passe par textContent, jamais par du HTML", () => {
  const e = {serveurs: [{...SERVEUR, capacites: {agent: cap("bloque", "<img src=x onerror=alert(1)>", "<b>geste</b>")}}], rejets: []};
  const c = ecranServeurs(e, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  assert.match(c.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(c.tous((n) => n.tagName === "img" || n.tagName === "b").length, 0);
});

test("une capacite installee (statut fait) se lit presente", () => {
  const e = {serveurs: [{...SERVEUR, capacites: {base: "fait", "android-build": {statut: "fait"}}}], rejets: []};
  const c = ecranServeurs(e, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX_OK});
  assert.equal(c.tous((n) => n.className.includes("capacite-badge-presente")).length, 2);
  assert.doesNotMatch(c.textContent, /inconnue|fait/);
});

test("un relevé pendant un aperçu ouvert garde la case cochee et l aperçu", async () => {
  const m = minuterie();
  const apercu = {manquantes: ["android-build"], taille_go: 5.4, duree_min: 10, bloquees: [], etat: {}};
  const f = reseau({"POST /api/serveurs/s1/apercu": reponse(200, apercu), "POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "GET /api/serveurs": reponse(200, {serveurs: [{...SERVEUR, erreur: "Autre"}], rejets: []}), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Voir l'aperçu")[0]);
  await clic(boutons(c, "Vérifier")[0]);
  const case1 = caseAccord(c);
  case1.checked = true;
  const lancer = boutons(c, "Lancer l'installation")[0];
  await m.tic();
  assert.equal(caseAccord(c), case1);
  assert.equal(case1.checked, true);
  assert.equal(boutons(c, "Lancer l'installation")[0], lancer);
  assert.match(c.textContent, /Capacités à installer/);
});

test("pendant un envoi en cours, aucun second accord vrai ne peut partir", async () => {
  const m = minuterie();
  const apercu = {manquantes: ["android-build"], taille_go: 5.4, duree_min: 10, bloquees: [], etat: {}};
  let liberer;
  const attente = new Promise((r) => { liberer = r; });
  const f = reseau({"POST /api/serveurs/s1/apercu": reponse(200, apercu), "POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "POST /api/serveurs/s1/installer": async () => { await attente; return reponse(202, {demarre: true}); },
    "GET /api/serveurs": reponse(200, ETAT), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Voir l'aperçu")[0]);
  await clic(boutons(c, "Vérifier")[0]);
  caseAccord(c).checked = true;
  const envoi = clic(boutons(c, "Lancer l'installation")[0]);      // en vol
  await m.tic();                                                   // un relevé arrive pendant l'envoi
  const neuf = boutons(c, "Lancer l'installation")[0];
  if (neuf) { caseAccord(c).checked = true; assert.equal(neuf.disabled, true); await clic(neuf); }
  liberer();
  await envoi;
  assert.equal(f.appels.filter((a) => a.chemin.endsWith("/installer") && a.corps.accord === true).length, 1);
});

const avecSonde = (v, extra = {}) => ({serveurs: [{...SERVEUR, sonde_en_cours: v, ...extra}], rejets: []});

test("sonde en cours : on guette tant que le drapeau est vrai, le message n arrive qu au vingtieme relevé", async () => {
  const m = minuterie();
  let etat = avecSonde(true);
  const f = reseau({"POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}), "GET /api/serveurs": () => reponse(200, etat), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(avecSonde(false), {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Tester la connexion")[0]);
  for (let i = 0; i < 19; i++) await m.tic();
  assert.doesNotMatch(c.textContent, /peut encore être en cours/);
  await m.tic();
  assert.match(c.textContent, /Le test peut encore être en cours : actualisez dans un instant\./);
  etat = avecSonde(false);
  await m.tic();
  assert.doesNotMatch(c.textContent, /peut encore être en cours/);
});

test("un test qui finit avec les memes capacites et la meme erreur ne produit aucun message", async () => {
  const m = minuterie();
  const lectures = [avecSonde(true, {erreur: "Serveur injoignable."}), avecSonde(false, {erreur: "Serveur injoignable."})];
  const f = reseau({"POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}), "GET /api/serveurs": () => reponse(200, lectures.shift()), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(avecSonde(false, {erreur: "Serveur injoignable."}), {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Tester la connexion")[0]);
  await m.tic();
  await m.tic();
  assert.equal(m.taches.length, 0);
  assert.doesNotMatch(c.textContent, /peut encore être en cours/);
});

test("champ sonde_en_cours absent : la veille dure 20 relevés puis le message apparait", async () => {
  const m = minuterie();
  const f = reseau({"POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}), "GET /api/serveurs": reponse(200, ETAT), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Tester la connexion")[0]);
  let lectures = 0;
  while (m.taches.length && lectures < 100) { await m.tic(); lectures++; }
  assert.equal(lectures, 20);
  assert.match(c.textContent, /Le test peut encore être en cours/);
});

test("un relevé qui change les capacites ecarte l apercu : case decochee, plus de confirmation, aucun accord vrai", async () => {
  const m = minuterie();
  const apercu = {manquantes: ["android-build"], taille_go: 5.4, duree_min: 10, bloquees: [], etat: {}};
  const f = reseau({"POST /api/serveurs/s1/apercu": reponse(200, apercu), "POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "GET /api/serveurs": reponse(200, {serveurs: [{...SERVEUR, capacites: {base: "presente", "android-build": "presente"}}], rejets: []}),
    "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Voir l'aperçu")[0]);
  await clic(boutons(c, "Vérifier")[0]);
  caseAccord(c).checked = true;
  await m.tic();
  assert.equal(caseAccord(c), undefined);
  assert.equal(boutons(c, "Lancer l'installation").length, 0);
  assert.match(c.textContent, /refaites l'aperçu/);
  assert.equal(f.appels.filter((a) => a.chemin.endsWith("/installer")).length, 0);
});

const APERCU_A = {manquantes: ["android-build"], taille_go: 5.4, duree_min: 10, bloquees: [], etat: {}};
const CAPS_B = {base: "presente", "android-build": "presente"};

test("capacites changees pendant un envoi : la zone refaite n a ni case d accord ni second accord vrai", async () => {
  const m = minuterie();
  let liberer;
  const attente = new Promise((r) => { liberer = r; });
  const f = reseau({"POST /api/serveurs/s1/apercu": reponse(200, APERCU_A), "POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "POST /api/serveurs/s1/installer": async () => { await attente; return reponse(202, {demarre: true}); },
    "GET /api/serveurs": reponse(200, {serveurs: [{...SERVEUR, capacites: CAPS_B}], rejets: []}), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Voir l'aperçu")[0]);
  await clic(boutons(c, "Vérifier")[0]);
  caseAccord(c).checked = true;
  const envoi = clic(boutons(c, "Lancer l'installation")[0]);
  await m.tic();                                              // le relevé change les capacités pendant l'envoi
  assert.equal(caseAccord(c), undefined);
  assert.equal(boutons(c, "Lancer l'installation").length, 0);
  assert.match(c.textContent, /refaites l'aperçu/);
  liberer();
  await envoi;
  assert.equal(f.appels.filter((a) => a.chemin.endsWith("/installer") && a.corps.accord === true).length, 1);
});

test("une zone reconstruite depuis une entree en installation a sa confirmation grisee", async () => {
  const m = minuterie();
  const f = reseau({"POST /api/serveurs/s1/apercu": reponse(200, APERCU_A), "POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "GET /api/serveurs": reponse(200, {serveurs: [{...SERVEUR, installation_en_cours: true}, {...SERVEUR, id: "s2", nom: "Deux"}], rejets: []}),
    "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Voir l'aperçu")[0]);
  await clic(boutons(c, "Vérifier")[0]);
  await m.tic();                                              // la liste change : dessin complet, zone refaite
  assert.match(c.textContent, /Deux/);
  const lancer = boutons(c, "Lancer l'installation")[0];
  assert.ok(lancer);
  assert.equal(lancer.disabled, true);
});

test("la sonde lit l entree courante : Vérifier apres un relevé ne remet pas les capacites de la creation de la carte", async () => {
  const m = minuterie();
  const f = reseau({"POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "GET /api/serveurs": reponse(200, {serveurs: [{...SERVEUR, capacites: CAPS_B}], rejets: []}), "GET /api/serveurs/lieux": reponse(200, LIEUX_OK)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX_OK});
  assert.match(c.textContent, /absente/);
  await clic(boutons(c, "Vérifier")[0]);
  await m.tic();                                              // les capacités passent à CAPS_B : plus rien d'absent
  assert.doesNotMatch(c.textContent, /absente/);
  await clic(boutons(c, "Vérifier")[0]);                      // même carte, non reconstruite : elle doit lire l'entrée courante
  assert.doesNotMatch(c.textContent, /absente/);
});

test("un aperçu recu apres un changement de capacites pendant la requete est ecarte", async () => {
  const m = minuterie();
  let liberer;
  const attente = new Promise((r) => { liberer = r; });
  const f = reseau({"POST /api/serveurs/s1/apercu": async () => { await attente; return reponse(200, APERCU_A); }, "POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}),
    "GET /api/serveurs": reponse(200, {serveurs: [{...SERVEUR, capacites: CAPS_B}], rejets: []}), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Installer")[0]);
  await clic(boutons(c, "Vérifier")[0]);
  const demande = clic(boutons(c, "Voir l'aperçu")[0]);       // en vol
  await m.tic();                                              // les capacités changent pendant la requête
  liberer();
  await demande;
  assert.equal(caseAccord(c), undefined);
  assert.equal(boutons(c, "Lancer l'installation").length, 0);
  assert.match(c.textContent, /refaites l'aperçu/);
});

test("l accord n est jamais envoye vrai sans la case cochee", async () => {
  const apercu = {manquantes: ["android-build"], taille_go: 5.4, duree_min: 10, bloquees: [], etat: {}};
  const {c, f} = await ouvrirApercu(apercu);
  assert.equal(caseAccord(c).checked, false);
  await clic(boutons(c, "Lancer l'installation")[0]);
  assert.equal(f.appels.filter((a) => a.chemin === "/api/serveurs/s1/installer" && a.corps.accord === true).length, 0);
  assert.match(c.textContent, /Cochez la case/);
  caseAccord(c).checked = true;
  await clic(boutons(c, "Lancer l'installation")[0]);
  const envois = f.appels.filter((a) => a.chemin === "/api/serveurs/s1/installer");
  assert.deepEqual(envois.map((a) => a.corps.accord), [true]);
  assert.deepEqual(envois[0].corps.actions, ["apk"]);
  assert.equal(envois[0].init.headers["X-Bureau"], "1");
  assert.equal(envois[0].init.headers["Content-Type"], "application/json");
});

test("installerCapacites : accord true seulement pour true, ne leve jamais", async () => {
  const f = reseau({"POST /api/serveurs/s1/installer": reponse(202, {demarre: true})});
  for (const a of [undefined, null, "oui", 1, false, true]) await installerCapacites("s1", ["apk"], a, f);
  assert.deepEqual(f.appels.map((x) => x.corps.accord), [false, false, false, false, false, true]);
  assert.equal(f.appels[0].chemin, "/api/serveurs/s1/installer");
  assert.equal((await installerCapacites("s1", ["apk"], true, f)).ok, true);
  const occupe = await installerCapacites("s1", ["apk"], true, async () => reponse(409, {erreur: "Une installation est déjà en cours."}));
  assert.deepEqual([occupe.ok, occupe.occupe], [false, true]);
  assert.match(occupe.message, /déjà en cours/);
  const refus = await installerCapacites("s1", ["apk"], true, async () => reponse(400, {erreur: "Installation refusée."}));
  assert.deepEqual([refus.ok, refus.message], [false, "Installation refusée."]);
  const illisible = await installerCapacites("s1", ["apk"], true, async () => ({ok: false, status: 500, json: async () => { throw new Error("x"); }}));
  assert.match(illisible.message, /500/);
  const coupe = await installerCapacites("s1", ["apk"], true, async () => { throw new TypeError("fetch failed"); });
  assert.equal(coupe.ok, false);
  assert.match(coupe.message, /injoignable/);
  assert.equal((await installerCapacites("s1", "pas une liste", true, f)).ok, false);
});

test("la case d accord se decoche apres l envoi", async () => {
  for (const rep of [reponse(202, {demarre: true}), reponse(409, {erreur: "Déjà en cours."}), reponse(500, {})]) {
    const apercu = {manquantes: ["android-build"], taille_go: 5.4, duree_min: 10, bloquees: [], etat: {}};
    const {c, f} = await ouvrirApercu(apercu, {"POST /api/serveurs/s1/installer": rep});
    const avant = caseAccord(c);
    avant.checked = true;
    await clic(boutons(c, "Lancer l'installation")[0]);
    assert.equal(avant.checked, false);
    assert.ok(!caseAccord(c) || caseAccord(c).checked === false);
    assert.equal(f.appels.filter((a) => a.chemin.endsWith("/installer") && a.corps.accord === true).length, 1);
    // un second envoi sans recocher n'envoie jamais vrai
    const bouton = boutons(c, "Lancer l'installation")[0];
    if (bouton) { bouton.disabled = false; await clic(bouton); }
    assert.equal(f.appels.filter((a) => a.chemin.endsWith("/installer") && a.corps.accord === true).length, 1);
  }
});

test("un texte du serveur avec du HTML n est pas interprete", () => {
  const hostile = "<img src=x onerror=alert(1)>";
  const e = {serveurs: [{...SERVEUR, nom: "<b>gras</b>", hote: "<script>x</script>", utilisateur: hostile, erreur: hostile,
    ligne_cle_publique: `ssh-ed25519 ${hostile}`}], rejets: [`<i>rejet</i> ${hostile}`]};
  const lieux = {apk: {...LIEUX.apk, serveur: {...LIEUX.apk.serveur, raison: hostile, manque: [hostile]}}};
  const c = ecranServeurs(e, {fetchFn: reseau({}), planifier: minuterie(), lieux});
  assert.match(c.textContent, /<b>gras<\/b>/);
  assert.match(c.textContent, /<script>x<\/script>/);
  assert.match(c.textContent, /<i>rejet<\/i>/);
  assert.equal(c.tous((n) => ["img", "b", "i", "script"].includes(n.tagName)).length, 0);
  assert.equal(c.tous((n) => n.tagName === "a").length, 0);
});

test("serveur injoignable affiche un message sans exception", async () => {
  const c = ecranServeurs(null, {fetchFn: async () => { throw new Error("coupé"); }, planifier: minuterie()});
  assert.match(c.textContent, /ne répond pas/);
  assert.equal(boutons(c, "Déclarer le serveur").length, 1);
  const vide = ecranServeurs({serveurs: [], rejets: []}, {fetchFn: reseau({}), planifier: minuterie(), lieux: {}});
  assert.match(vide.textContent, /Aucun serveur déclaré/);
  const {c: c2} = await ouvrirApercu({}, {"POST /api/serveurs/s1/apercu": async () => { throw new TypeError("coupé"); }});
  assert.match(c2.textContent, /injoignable/);
  const {c: c3} = await ouvrirApercu({}, {"POST /api/serveurs/s1/apercu": reponse(504, {erreur: "L'aperçu prend trop de temps : réessayez."})});
  assert.match(c3.textContent, /trop de temps/);
});

test("declarer un serveur envoie les quatre champs et affiche la cle a copier", async () => {
  const f = reseau({"POST /api/serveurs": reponse(201, {serveur: {...SERVEUR, id: "s2"}}), "GET /api/serveurs": reponse(200, {serveurs: [SERVEUR, {...SERVEUR, id: "s2", nom: "Deux"}], rejets: []}),
    "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs({serveurs: [], rejets: []}, {fetchFn: f, planifier: minuterie(), lieux: {}});
  const champ = (nom) => c.tous((n) => n.tagName === "input" && n.attributs["data-champ"] === nom)[0];
  champ("nom").value = "Deux"; champ("hote").value = "203.0.113.9"; champ("utilisateur").value = "robot";
  const menu = c.tous((n) => n.tagName === "select")[0];
  menu.value = "ovh";
  await clic(boutons(c, "Déclarer le serveur")[0]);
  const post = f.appels.find((a) => a.methode === "POST");
  assert.deepEqual(post.corps, {nom: "Deux", hote: "203.0.113.9", utilisateur: "robot", fournisseur: "ovh"});
  assert.equal(post.init.headers["X-Bureau"], "1");
  menu.value = "";
  await clic(boutons(c, "Déclarer le serveur")[0]);
  assert.equal(f.appels.filter((a) => a.methode === "POST")[1].corps.fournisseur, null);
  assert.match(c.textContent, /ssh-ed25519 AAAAC3Nza/);
});

test("declarer : un refus du serveur est montre en francais", async () => {
  const f = reseau({"POST /api/serveurs": reponse(400, {erreur: "Adresse du serveur invalide."})});
  const c = ecranServeurs({serveurs: [], rejets: []}, {fetchFn: f, planifier: minuterie(), lieux: {}});
  await clic(boutons(c, "Déclarer le serveur")[0]);
  assert.match(c.textContent, /Adresse du serveur invalide\./);
});

test("tester la connexion lance la sonde puis suit l etat par la minuterie injectee", async () => {
  const m = minuterie();
  const lectures = [{serveurs: [{...SERVEUR, sonde_en_cours: false, capacites: {base: "presente", "android-build": "presente"}}], rejets: []}];
  const f = reseau({"POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}), "GET /api/serveurs": () => reponse(200, lectures[0]), "GET /api/serveurs/lieux": reponse(200, LIEUX_OK)});
  const c = ecranServeurs(ETAT, {fetchFn: f, planifier: m, lieux: LIEUX});
  await clic(boutons(c, "Tester la connexion")[0]);
  assert.equal(f.appels.filter((a) => a.chemin === "/api/serveurs/s1/sonder").length, 1);
  assert.equal(m.taches.length, 1);
  assert.ok(m.taches[0].ms >= 1000);
  await m.tic();
  assert.match(c.textContent, /présente/);
  const serveur = c.tous((n) => n.tagName === "input" && n.type === "radio").find((n) => n.value === "serveur");
  assert.equal(serveur.disabled, false);
  for (let i = 0; i < 12 && m.taches.length; i++) await m.tic();
  assert.equal(m.taches.length, 0);
});

test("ecran retire de la page : le suivi s arrete et arreter() annule la lecture prevue", async () => {
  const m = minuterie();
  let monte = true;
  const f = reseau({"POST /api/serveurs/s1/sonder": reponse(202, {demarre: true}), "GET /api/serveurs": reponse(200, ETAT), "GET /api/serveurs/lieux": reponse(200, LIEUX)});
  const c = ecranServeurs({serveurs: [{...SERVEUR, installation_en_cours: true}], rejets: []}, {fetchFn: f, planifier: m, actif: () => monte, lieux: LIEUX});
  monte = false;
  await m.tic();
  assert.equal(f.appels.length, 0);
  assert.equal(m.taches.length, 0);
  const m2 = minuterie();
  const c2 = ecranServeurs({serveurs: [{...SERVEUR, installation_en_cours: true}], rejets: []}, {fetchFn: f, planifier: m2, lieux: LIEUX});
  c2.arreter();
  assert.equal(m2.annulees, 1);
  assert.ok(c);
});

test("une installation en cours grise Installer et affiche l erreur masquee en texte simple", () => {
  const e = {serveurs: [{...SERVEUR, installation_en_cours: true, erreur: "Échec <b>x</b>"}], rejets: []};
  const c = ecranServeurs(e, {fetchFn: reseau({}), planifier: minuterie(), lieux: LIEUX});
  assert.equal(boutons(c, "Installer")[0].disabled, true);
  assert.match(c.textContent, /Échec <b>x<\/b>/);
  assert.equal(c.tous((n) => n.tagName === "b").length, 0);
});

test("l aperçu ne coche aucune action cachee : il envoie les actions cochees", async () => {
  const apercu = {manquantes: [], taille_go: 0, duree_min: 0, bloquees: [], etat: {}};
  const {c, f} = await ouvrirApercu(apercu);
  assert.deepEqual(f.appels.find((a) => a.chemin === "/api/serveurs/s1/apercu").corps, {actions: ["apk"]});
  assert.match(c.textContent, /Rien à installer/);
  assert.equal(boutons(c, "Lancer l'installation").length, 0);
  assert.ok(cases(c).length >= 2);
});
