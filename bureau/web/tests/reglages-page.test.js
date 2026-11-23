// La page « Réglages » : trois niveaux (global, type, projet), origine de chaque valeur, retour à l'hérité.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.attrs = {};
    this.checked = false; this.disabled = false; this.value = ""; this.name = ""; this.type = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};
globalThis.window = globalThis.window || {confirm: () => true};

const {enregistrerNiveau, contenuReglages, definirNiveauEdite, niveauEditeActuel} = await import("../ui/reglages.js");

const ligne = (id, extra = {}) => ({id, section: "actions", libelle: id.replace("deport.", ""), aide: "", forme: "lieu",
  choix: ["poste", "github", "serveur"], niveaux: ["global", "type", "projet"], valeur: "poste", origine: "defaut", valeurs: {},
  applicable: true, ...extra});
const page = (lignes, extra = {}) => ({genre: "application-mobile-android", type_disponible: true, lignes, ...extra});
const rendre = (reglages_page, fetchFn, plus = {}) => {
  const ctx = {etat: {reglages_page, agir: true, version: 4, ...plus}, rouvrir() { ctx.rouvert = (ctx.rouvert || 0) + 1; }};
  return {ctx, bloc: contenuReglages(ctx, new Noeud("div"), fetchFn || (async () => ({ok: false, status: 500, json: async () => ({})})))};
};
const radios = (b, id) => b.tous((n) => n.tagName === "input" && n.type === "radio" && (!id || n.name === "reglage-" + id));
const boutons = (b) => b.tous((n) => n.tagName === "button");
const bouton = (b, texte) => boutons(b).find((x) => x.textContent === texte);
const changer = async (r) => { r.checked = true; for (const f of r.auteurs.change || []) await f(); };
const cliquer = async (x) => { for (const f of x.auteurs.click || []) await f(); };
const ok = (corps = {}) => async () => ({ok: true, status: 200, json: async () => corps});

test("enregistrerNiveau_envoie_le_bon_corps_et_les_en_tetes", async () => {
  const vus = [];
  const rep = await enregistrerNiveau("global", "deport.apk", "github", async (url, o) => { vus.push([url, o]); return {ok: true, json: async () => ({id: "deport.apk"})}; });
  assert.match(vus[0][0], /\/api\/reglages\/niveau/);
  assert.equal(vus[0][1].method, "POST");
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.equal(vus[0][1].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(vus[0][1].body), {niveau: "global", id: "deport.apk", valeur: "github"});
  assert.equal(rep.ok, true);
  assert.deepEqual(rep.ligne, {id: "deport.apk"});
  const nul = await enregistrerNiveau("projet", "deport.apk", null, async (u, o) => { vus.push(o); return {ok: true, json: async () => ({})}; });
  assert.equal(JSON.parse(vus[1].body).valeur, null);
  assert.equal(nul.ok, true);
  const refus = await enregistrerNiveau("type", "x", 1, async () => ({ok: false, status: 400, json: async () => ({erreur: "pas de genre"})}));
  assert.deepEqual([refus.ok, refus.message], [false, "Refusé : pas de genre"]);
  const coupe = await enregistrerNiveau("type", "x", 1, async () => { throw new Error("réseau"); });
  assert.deepEqual(coupe, {ok: false, message: "Serveur du bureau injoignable."});
});

test("refus_serveur_remet_l_etat_reel", async () => {
  definirNiveauEdite("projet");
  const {bloc, ctx} = rendre(page([ligne("deport.apk")]),
    async () => ({ok: false, status: 400, json: async () => ({erreur: "pas maintenant"})}));
  await changer(radios(bloc, "deport.apk").find((r) => r.value === "github"));
  assert.equal(radios(bloc, "deport.apk").find((r) => r.value === "github").checked, false);
  assert.equal(radios(bloc, "deport.apk").find((r) => r.value === "poste").checked, true);
  assert.match(bloc.textContent, /Refusé : pas maintenant/);
  assert.equal(ctx.rouvert, undefined);
  // les contrôles sont rendus (« Serveur » reste grisé : l'action n'est pas servie au serveur)
  assert.equal(radios(bloc).filter((r) => r.value !== "serveur").some((r) => r.disabled), false);
  assert.equal(radios(bloc).find((r) => r.value === "serveur").disabled, true);
});

test("serveur_grise_bientot_pour_une_action_non_servie", () => {
  definirNiveauEdite("projet");
  for (const niveau of ["projet", "global"]) {
    definirNiveauEdite(niveau);
    const {bloc} = rendre(page([ligne("deport.apk", {servie_au_serveur: false})]), undefined, {deport: {serveur_declare: true}});
    const r = radios(bloc, "deport.apk");
    assert.equal(r.find((x) => x.value === "serveur").disabled, true, niveau);
    assert.equal(r.find((x) => x.value === "poste").disabled, false);
    assert.equal(r.find((x) => x.value === "github").disabled, false);
    assert.match(bloc.textContent, /Serveur \(bientôt\)/);
  }
  definirNiveauEdite("projet");
});

test("recette_serveur_grise_tant_qu_aucun_serveur_n_est_declare", () => {
  definirNiveauEdite("projet");
  const recette = () => ligne("deport.recette-emulateur", {niveaux: ["projet"], choix: ["serveur"], valeur: null, defaut: null, servie_au_serveur: true});
  const sans = rendre(page([recette()]), undefined, {deport: {serveur_declare: false}}).bloc;
  assert.equal(radios(sans, "deport.recette-emulateur")[0].disabled, true);
  assert.match(sans.textContent, /déclarez d'abord un serveur \(Serveurs\), puis réglez sur serveur/);
  const avec = rendre(page([recette()]), undefined, {deport: {serveur_declare: true}}).bloc;
  assert.equal(radios(avec, "deport.recette-emulateur")[0].disabled, false);
  assert.doesNotMatch(avec.textContent, /déclarez d'abord/);
});

test("les_attentes_en_chaine_sont_dites_sous_les_actions", () => {
  definirNiveauEdite("projet");
  const textes = ["« tests » tourne au lieu « poste » mais attendra l'APK produit par GitHub : mettez la chaîne entière au même lieu pour éviter cette attente.",
    "« charge » tourne au lieu « poste » mais attendra l'APK produit par GitHub : mettez la chaîne entière au même lieu pour éviter cette attente."];
  const {bloc} = rendre(page([ligne("deport.apk")]), undefined, {deport: {avertissements: textes}});
  const notes = bloc.tous((n) => /\bdeport-avertissement\b/.test(n.className));
  assert.equal(notes.length, 1, "un seul texte par situation");
  assert.match(notes[0].textContent, /tests, charge : au lieu « poste », attend l'APK produit par GitHub/);
  assert.equal(rendre(page([ligne("deport.apk")])).bloc.tous((n) => /\bdeport-avertissement\b/.test(n.className)).length, 0);
});

test("global_grise_sans_fichier_du_bureau_et_retombe_sur_projet", () => {
  definirNiveauEdite("global");
  const {bloc} = rendre(page([ligne("deport.apk")], {global_disponible: false, type_disponible: false}));
  assert.equal(bouton(bloc, "Global").disabled, true);
  assert.equal(niveauEditeActuel(), "projet");
  const actif = boutons(bloc).filter((b) => /\bactif\b/.test(b.className));
  assert.match(actif[0].textContent, /^Projet/);
  definirNiveauEdite("projet");
  assert.equal(bouton(rendre(page([ligne("deport.apk")], {global_disponible: true})).bloc, "Global").disabled, false);
});

test("les_cles_ignorees_du_fichier_du_bureau_sont_dites", () => {
  definirNiveauEdite("projet");
  const {bloc} = rendre(page([ligne("deport.apk")], {ignores: ["Fichier du bureau : « reglages » : le réglage inconnu « x » est ignoré."]}));
  assert.match(bloc.textContent, /le réglage inconnu « x » est ignoré/);
});

test("un succès enregistre au niveau édité, remplace la ligne et rouvre", async () => {
  definirNiveauEdite("global");
  const vus = [];
  const {bloc, ctx} = rendre(page([ligne("deport.apk")]), async (u, o) => { vus.push(JSON.parse(o.body)); return {ok: true, json: async () => ligne("deport.apk", {valeurs: {global: "github"}, valeur: "github", origine: "global"})}; });
  await changer(radios(bloc, "deport.apk").find((r) => r.value === "github"));
  assert.deepEqual(vus[0], {niveau: "global", id: "deport.apk", valeur: "github"});
  assert.deepEqual(ctx.etat.reglages_page.lignes[0].valeurs, {global: "github"});
  assert.equal(ctx.rouvert, 1);
  definirNiveauEdite("projet");
});

test("niveau_type_grise_sans_genre", () => {
  definirNiveauEdite("projet");
  const {bloc} = rendre(page([ligne("deport.apk")], {genre: null, type_disponible: false}));
  const type = boutons(bloc).find((b) => b.textContent.startsWith("Type"));
  assert.equal(type.disabled, true);
  assert.equal(boutons(bloc).find((b) => b.textContent === "Global").disabled, false);
  const {bloc: avec} = rendre(page([ligne("deport.apk")]));
  assert.ok(bouton(avec, "Type : application-mobile-android"));
  assert.equal(bouton(avec, "Type : application-mobile-android").disabled, false);
  assert.ok(boutons(avec).find((b) => b.textContent.startsWith("Projet : ")));
});

test("un clic sur un onglet change le niveau édité et rouvre", async () => {
  definirNiveauEdite("projet");
  const {bloc, ctx} = rendre(page([ligne("deport.apk")]));
  await cliquer(bouton(bloc, "Global"));
  assert.equal(ctx.rouvert, 1);
  const {bloc: apres} = rendre(page([ligne("deport.apk")]));
  assert.match(apres.textContent, /pas défini ici/);
  definirNiveauEdite("projet");
});

test("ligne_projet_seul_desactivee_au_niveau_global", () => {
  definirNiveauEdite("global");
  const {bloc} = rendre(page([ligne("deport.recette-emulateur", {niveaux: ["projet"], choix: ["serveur"], valeur: null}), ligne("deport.apk")]));
  assert.equal(radios(bloc, "deport.recette-emulateur").every((r) => r.disabled), true);
  assert.equal(radios(bloc, "deport.apk").filter((r) => r.value !== "serveur").some((r) => r.disabled), false);
  assert.match(bloc.textContent, /Projet seulement : jamais hérité/);
  definirNiveauEdite("projet");
  const {bloc: p} = rendre(page([ligne("deport.recette-emulateur", {niveaux: ["projet"], choix: ["serveur"], valeur: null, servie_au_serveur: true})]),
    undefined, {deport: {serveur_declare: true}});
  assert.equal(radios(p, "deport.recette-emulateur").some((r) => r.disabled), false);
  assert.match(p.textContent, /Projet seulement : accord permanent/);
});

test("pastille_origine_au_niveau_projet", () => {
  definirNiveauEdite("projet");
  const {bloc} = rendre(page([
    ligne("deport.apk", {origine: "projet", valeur: "github", valeurs: {projet: "github"}}),
    ligne("deport.tests", {origine: "type:application-mobile-android", valeur: "github", valeurs: {type: "github"}}),
    ligne("deport.charge", {origine: "global", valeur: "github", valeurs: {global: "github"}}),
    ligne("deport.emulateur"),
  ]));
  const t = bloc.textContent;
  assert.match(t, /propre au projet/);
  assert.match(t, /hérité du type application-mobile-android/);
  assert.match(t, /hérité du global/);
  assert.match(t, /défaut/);
  // la valeur héritée est estompée, la valeur propre ne l'est pas
  const lignes = bloc.tous((n) => /\bligne-reglage\b/.test(n.className));
  assert.equal(lignes.length, 4);
  assert.equal(/\bherite\b/.test(lignes[0].className), false);
  assert.equal(/\bherite\b/.test(lignes[1].className), true);
});

test("bouton_herite_envoie_null_et_n_existe_que_si_defini_ici", async () => {
  definirNiveauEdite("projet");
  const vus = [];
  const {bloc, ctx} = rendre(page([
    ligne("deport.apk", {origine: "projet", valeur: "github", valeurs: {projet: "github"}}),
    ligne("deport.tests", {origine: "global", valeur: "github", valeurs: {global: "github"}}),
  ]), async (u, o) => { vus.push(JSON.parse(o.body)); return {ok: true, json: async () => ligne("deport.apk")}; });
  const herites = boutons(bloc).filter((b) => b.textContent === "hérité");
  assert.equal(herites.length, 1);
  await cliquer(herites[0]);
  assert.deepEqual(vus[0], {niveau: "projet", id: "deport.apk", valeur: null});
  assert.equal(ctx.rouvert, 1);
  // au niveau global : seulement la ligne définie au global
  definirNiveauEdite("global");
  const {bloc: g} = rendre(page([
    ligne("deport.apk", {origine: "projet", valeur: "github", valeurs: {projet: "github"}}),
    ligne("deport.tests", {origine: "global", valeur: "github", valeurs: {global: "github"}}),
  ]));
  assert.equal(boutons(g).filter((b) => b.textContent === "hérité").length, 1);
  assert.match(g.textContent, /défini ici/);
  assert.match(g.textContent, /pas défini ici/);
  definirNiveauEdite("projet");
});

test("partage_seulement_au_niveau_global", () => {
  definirNiveauEdite("projet");
  const l = [ligne("deport.apk")];
  assert.doesNotMatch(rendre(page(l)).bloc.textContent, /Partage des connaissances/);
  definirNiveauEdite("type");
  assert.doesNotMatch(rendre(page(l)).bloc.textContent, /Partage des connaissances/);
  definirNiveauEdite("global");
  assert.match(rendre(page(l)).bloc.textContent, /Partage des connaissances/);
  assert.doesNotMatch(rendre(page(l), undefined, {agir: false}).bloc.textContent, /Partage des connaissances/);
  definirNiveauEdite("projet");
});

test("sections_et_blocs_selon_les_lieux", () => {
  definirNiveauEdite("projet");
  const t = rendre(page([ligne("deport.apk")])).bloc.textContent;
  assert.match(t, /Où tournent les actions/);
  assert.doesNotMatch(t, /Aperçu du workflow/);
  const g = rendre(page([ligne("deport.apk", {origine: "projet", valeur: "github", valeurs: {projet: "github"}})]),
    undefined, {deport: {conso: {niveau: "ok", mois: "2026-11", minutes_total: 3}}}).bloc;
  assert.ok(bouton(g, "Aperçu du workflow"));
  assert.match(g.textContent, /Consommation GitHub/);
});

test("action_inapplicable_grisee", () => {
  definirNiveauEdite("projet");
  const {bloc} = rendre(page([ligne("deport.charge", {applicable: false})]));
  assert.match(bloc.textContent, /non applicable à ce projet/);
  assert.equal(radios(bloc, "deport.charge").every((r) => r.disabled), true);
  const lg = bloc.tous((n) => /\bligne-reglage\b/.test(n.className))[0];
  assert.match(lg.className, /inapplicable/);
});

test("une ligne booléenne est une case à cocher", async () => {
  definirNiveauEdite("projet");
  const vus = [];
  const {bloc} = rendre(page([{id: "lecons_auto", section: "automatisations", libelle: "Leçons auto", aide: "", forme: "booleen",
    niveaux: ["global", "type", "projet"], valeur: true, origine: "defaut", valeurs: {}, applicable: true}]),
  async (u, o) => { vus.push(JSON.parse(o.body)); return {ok: true, json: async () => ({})}; });
  const c = bloc.tous((n) => n.tagName === "input" && n.type === "checkbox")[0];
  assert.equal(c.checked, true);
  c.checked = false;
  for (const f of c.auteurs.change) await f();
  assert.deepEqual(vus[0], {niveau: "projet", id: "lecons_auto", valeur: false});
});

test("valeur affichée quand rien n'est posé : défaut du serveur, global au niveau type", () => {
  definirNiveauEdite("type");
  const sansGlobal = rendre(page([ligne("deport.apk", {origine: "projet", valeur: "github", valeurs: {projet: "github"}, defaut: "poste"})])).bloc;
  assert.equal(radios(sansGlobal, "deport.apk").find((r) => r.value === "poste").checked, true);
  const avecGlobal = rendre(page([ligne("deport.apk", {origine: "global", valeur: "github", valeurs: {global: "github"}, defaut: "poste"})])).bloc;
  assert.equal(radios(avecGlobal, "deport.apk").find((r) => r.value === "github").checked, true);
  const sansDefaut = rendre(page([ligne("deport.recette-emulateur", {niveaux: ["global", "type", "projet"], choix: ["serveur"], valeur: null, defaut: null})])).bloc;
  assert.equal(radios(sansDefaut).some((r) => r.checked), false);
  definirNiveauEdite("projet");
});

test("booléen de défaut vrai : coché au global quand le projet le met à faux", () => {
  const l = {id: "lecons_auto", section: "automatisations", libelle: "Leçons", aide: "", forme: "booleen", niveaux: ["global", "type", "projet"],
    valeur: false, origine: "projet", valeurs: {projet: false}, applicable: true, defaut: true};
  definirNiveauEdite("global");
  const c = rendre(page([l])).bloc.tous((n) => n.type === "checkbox")[0];
  assert.equal(c.checked, true);
  definirNiveauEdite("projet");
  assert.equal(rendre(page([l])).bloc.tous((n) => n.type === "checkbox")[0].checked, false);
});

test("texte_du_serveur_via_textContent", () => {
  definirNiveauEdite("projet");
  const {bloc} = rendre(page([ligne("deport.apk", {libelle: "<b>APK</b>", aide: "<i>vite</i>"})], {genre: "<u>x</u>"}));
  assert.match(bloc.textContent, /<b>APK<\/b>/);
  assert.match(bloc.textContent, /<i>vite<\/i>/);
  assert.equal(bloc.tous((n) => ["b", "i", "u"].includes(n.tagName)).length, 0);
});

test("sans état ou en erreur : le message seul", () => {
  const sans = contenuReglages({etat: {}}, new Noeud("div"));
  assert.equal(sans.textContent.length > 0, true);
  const {bloc} = rendre(page([ligne("deport.apk")]), undefined, {reglages_page_erreur: "Page Réglages indisponible : boum"});
  assert.equal(bloc.textContent, "Page Réglages indisponible : boum");
  assert.equal(radios(bloc).length, 0);
});

test("la confirmation survit au redessin de la page, puis s'efface à l'action suivante", async () => {
  definirNiveauEdite("projet");
  const racine = {bloc: null};
  const fetchFn = ok(ligne("deport.apk", {valeur: "github", origine: "projet", valeurs: {projet: "github"}}));
  const ctx = {etat: {reglages_page: page([ligne("deport.apk")]), agir: true, version: 4}};
  // le vrai `rouvrir` redessine dans un contenu neuf
  ctx.rouvrir = () => { racine.bloc = contenuReglages(ctx, new Noeud("div"), fetchFn); };
  const premier = contenuReglages(ctx, new Noeud("div"), fetchFn);
  await changer(radios(premier, "deport.apk").find((r) => r.value === "github"));
  assert.match(racine.bloc.textContent, /Réglage enregistré\./);
  // l'action suivante efface d'abord l'ancien message : un refus le remplace
  const refus = async () => ({ok: false, status: 400, json: async () => ({erreur: "non"})});
  const second = contenuReglages(ctx, new Noeud("div"), refus);
  await changer(radios(second, "deport.apk").find((r) => r.value === "serveur"));
  assert.doesNotMatch(second.textContent, /Réglage enregistré\./);
  assert.match(second.textContent, /Refusé : non/);
});

test("le niveau « type » retombe sur « projet » quand le projet n'a pas de genre", () => {
  definirNiveauEdite("type");
  const {bloc} = rendre(page([ligne("deport.apk")], {type_disponible: false, genre: null}));
  assert.equal(niveauEditeActuel(), "projet");
  const actif = boutons(bloc).filter((b) => /\bactif\b/.test(b.className));
  assert.equal(actif.length, 1);
  assert.match(actif[0].textContent, /^Projet/);
  definirNiveauEdite("projet");
});
