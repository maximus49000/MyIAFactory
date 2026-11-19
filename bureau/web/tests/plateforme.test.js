// La carte « Serveur » du bureau, rendue sur un faux DOM : les sept étapes, l'accord d'effacement, les gestes, l'injoignable, le suivi.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.attributs = {}; this.disabled = false; this.checked = false; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const {carteServeur, demanderInstallation, lirePlateforme, texteAvecLiens} = await import("../ui/plateforme.js");

const IDS = ["lecture", "os", "ssh", "durcissement", "docker", "images", "licence"];
const etape = (id, statut = "a_faire", extra = {}) => ({id, libelle: `Étape ${id}`, statut, detail: `détail ${id}`, geste: "", ...extra});
const ETAT = {etapes: IDS.map((i) => etape(i)), pret: false, pret_sans_unity: false, derniere_lecture: ""};
const reponse = (status, corps) => ({ok: status >= 200 && status < 300, status, json: async () => corps});
const bouton = (c) => c.tous((n) => n.tagName === "button")[0];
const case_ = (c) => c.tous((n) => n.tagName === "input" && n.type === "checkbox")[0];
const clic = (c) => bouton(c).auteurs.click[0]();

// Une minuterie à la main : rien n'attend pour de vrai.
function minuterie() {
  const m = {taches: [], annulees: 0, attendre(f, ms) { m.taches.push({f, ms}); return m.taches.length; }, annuler() { m.annulees++; },
    async tic() { const t = m.taches.shift(); await t.f(); }};
  return m;
}

test("la carte liste les sept étapes dans l ordre", () => {
  const c = carteServeur(ETAT, {installer: async () => ({ok: true})});
  const libelles = c.tous((n) => n.className.startsWith("serveur-libelle")).map((n) => n.textContent);
  assert.deepEqual(libelles, IDS.map((i) => `Étape ${i}`));
  assert.match(c.textContent, /détail docker/);
  assert.match(c.textContent, /à faire/);
});

test("fait, bloqué et en cours ont leur badge", () => {
  const e = {...ETAT, etapes: [etape("lecture", "fait"), etape("os", "bloque"), etape("ssh", "en_cours")]};
  const t = carteServeur(e, {minuterie: minuterie()}).textContent;
  assert.match(t, /fait ✓/);
  assert.match(t, /bloqué/);
  assert.match(t, /en cours/);
});

test("l avertissement d effacement et la case décochée sont là avant tout accord", () => {
  const c = carteServeur(ETAT);
  assert.match(c.textContent, /Réinstaller efface le disque du serveur/);
  assert.match(c.textContent, /J'autorise l'effacement du serveur/);
  assert.equal(case_(c).checked, false);
  assert.equal(bouton(c).textContent, "Mettre en place / reprendre");
});

test("le bouton n envoie jamais accord_reinstallation vrai sans la case cochée", async () => {
  const accords = [];
  const c = carteServeur(ETAT, {installer: async (a) => { accords.push(a); return {ok: false, message: "non"}; }});
  await clic(c);
  case_(c).checked = true;
  await clic(c);
  case_(c).checked = false;
  await clic(c);
  assert.deepEqual(accords, [false, true, false]);
});

test("demanderInstallation : le corps ne porte true que pour true, l en-tête X-Bureau est mis", async () => {
  const appels = [];
  const f = async (url, init) => { appels.push([url, init]); return reponse(202, {demarre: true}); };
  for (const a of [undefined, null, "oui", 1, false, true]) await demanderInstallation(a, f);
  assert.deepEqual(appels.map((x) => JSON.parse(x[1].body).accord_reinstallation), [false, false, false, false, false, true]);
  assert.equal(appels[0][0], "/api/plateforme/installer");
  assert.equal(appels[0][1].method, "POST");
  assert.equal(appels[0][1].headers["X-Bureau"], "1");
  assert.equal(appels[0][1].headers["Content-Type"], "application/json");
});

test("demanderInstallation ne lève jamais : 409, 403 et réseau coupé donnent un message", async () => {
  assert.deepEqual(await demanderInstallation(false, async () => reponse(202, {demarre: true})), {ok: true, message: "Installation lancée. L'état se met à jour tout seul."});
  const occupe = await demanderInstallation(false, async () => reponse(409, {erreur: "Une installation est déjà en cours."}));
  assert.equal(occupe.ok, false);
  assert.equal(occupe.occupe, true);
  assert.match(occupe.message, /déjà en cours/);
  const refus = await demanderInstallation(false, async () => reponse(403, {erreur: "En-têtes requis manquants."}));
  assert.deepEqual([refus.ok, refus.message], [false, "En-têtes requis manquants."]);
  const illisible = await demanderInstallation(false, async () => ({ok: false, status: 500, json: async () => { throw new Error("x"); }}));
  assert.match(illisible.message, /500/);
  const coupe = await demanderInstallation(true, async () => { throw new TypeError("fetch failed"); });
  assert.equal(coupe.ok, false);
  assert.match(coupe.message, /injoignable/);
});

test("un geste humain affiche son lien et son mode opératoire", () => {
  const geste = "Ouvrez https://www.ovhcloud.com/fr/manager (menu Serveurs), puis cliquez sur Réinstaller.";
  const e = {...ETAT, etapes: [etape("lecture"), etape("os", "bloque", {geste})]};
  const c = carteServeur(e);
  assert.match(c.textContent, /À faire de votre côté/);
  assert.match(c.textContent, /menu Serveurs/);
  const liens = c.tous((n) => n.tagName === "a");
  assert.equal(liens.length, 1);
  assert.equal(liens[0].href, "https://www.ovhcloud.com/fr/manager");
  assert.equal(liens[0].textContent, "https://www.ovhcloud.com/fr/manager");
  assert.equal(liens[0].rel, "noopener noreferrer");
  assert.equal(liens[0].target, "_blank");
  assert.equal(carteServeur(ETAT).textContent.includes("À faire de votre côté"), false);
});

test("un texte hostile du serveur reste du texte : pas d élément, pas de lien javascript", () => {
  const hostile = "<img src=x onerror=alert(1)> javascript:alert(1) <a href=\"http://x\">y</a>";
  const e = {...ETAT, etapes: [etape("os", "bloque", {libelle: "<b>gras</b>", detail: "<script>x</script>", geste: hostile})]};
  const c = carteServeur(e);
  assert.match(c.textContent, /<b>gras<\/b>/);
  assert.match(c.textContent, /<script>x<\/script>/);
  assert.equal(c.tous((n) => ["img", "b", "script"].includes(n.tagName)).length, 0);
  assert.equal(c.tous((n) => n.tagName === "a").every((a) => /^https?:/.test(a.href)), true);
  const r = texteAvecLiens("ftp://x.fr et javascript:alert(1)");
  assert.equal(r.tous((n) => n.tagName === "a").length, 0);
});

test("serveur injoignable : un message, pas d exception", async () => {
  assert.equal(await lirePlateforme(async () => { throw new Error("coupé"); }), null);
  assert.equal(await lirePlateforme(async () => reponse(500, {})), null);
  const c = carteServeur(null);
  assert.match(c.textContent, /ne répond pas/);
  assert.equal(bouton(c).disabled, false);
});

test("pas encore de lecture : lisible, tout à faire", () => {
  const c = carteServeur({etapes: [], pret: false, pret_sans_unity: false, derniere_lecture: ""});
  assert.match(c.textContent, /à mettre en place/);
});

test("prêt, et prêt sans Unity quand la licence n est pas faite", () => {
  const fait = IDS.map((i) => etape(i, "fait"));
  assert.match(carteServeur({etapes: fait, pret: true, pret_sans_unity: true}).textContent, /Prêt(?!,)/);
  const sans = IDS.map((i) => etape(i, i === "licence" ? "a_faire" : "fait"));
  assert.match(carteServeur({etapes: sans, pret: false, pret_sans_unity: true}).textContent, /Prêt, sans Unity/);
  assert.doesNotMatch(carteServeur(ETAT).textContent, /Prêt/);
});

test("pendant une installation : bouton grisé, relevé toutes les quelques secondes, fin quand plus rien ne tourne", async () => {
  const m = minuterie();
  const lectures = [
    {...ETAT, etapes: [etape("lecture", "fait"), etape("os", "en_cours")]},
    {...ETAT, etapes: IDS.map((i) => etape(i, "fait")), pret: true},
  ];
  const urls = [];
  const f = async (url) => { urls.push(url); return reponse(200, lectures.shift()); };
  const c = carteServeur({...ETAT, etapes: [etape("os", "en_cours")]}, {minuterie: m, fetchFn: f, installer: async () => ({ok: true})});
  assert.equal(bouton(c).disabled, true);
  assert.equal(m.taches.length, 1);
  assert.ok(m.taches[0].ms >= 1000);
  await m.tic();
  assert.deepEqual(urls, ["/api/plateforme"]);
  assert.equal(bouton(c).disabled, true);
  assert.equal(m.taches.length, 1);
  await m.tic();
  assert.equal(bouton(c).disabled, false);
  assert.match(c.textContent, /Prêt/);
  assert.equal(m.taches.length, 0);
});

test("un 409 (déjà en cours) grise le bouton et lance le suivi", async () => {
  const m = minuterie();
  const c = carteServeur(ETAT, {minuterie: m, fetchFn: async () => reponse(200, ETAT), installer: async () => ({ok: false, occupe: true, message: "Une installation est déjà en cours."})});
  await clic(c);
  assert.match(c.textContent, /déjà en cours/);
  assert.equal(bouton(c).disabled, true);
  assert.equal(m.taches.length, 1);
});

test("une installation lancée qui ne démarre pas rend le bouton après quelques relevés", async () => {
  const m = minuterie();
  const c = carteServeur(ETAT, {minuterie: m, fetchFn: async () => reponse(200, ETAT), installer: async () => ({ok: true, message: "Lancée."})});
  await clic(c);
  assert.equal(bouton(c).disabled, true);
  for (let i = 0; i < 10 && m.taches.length; i++) await m.tic();
  assert.equal(bouton(c).disabled, false);
  assert.equal(m.taches.length, 0);
});

test("carte retirée de la page : le suivi s arrête, arreter() annule le relevé prévu", async () => {
  const m = minuterie();
  let monte = true;
  const urls = [];
  const c = carteServeur({...ETAT, etapes: [etape("os", "en_cours")]}, {minuterie: m, actif: () => monte, fetchFn: async (u) => { urls.push(u); return reponse(200, ETAT); }});
  monte = false;
  await m.tic();
  assert.deepEqual(urls, []);
  assert.equal(m.taches.length, 0);
  const m2 = minuterie();
  const c2 = carteServeur({...ETAT, etapes: [etape("os", "en_cours")]}, {minuterie: m2});
  c2.arreter();
  assert.equal(m2.annulees, 1);
  assert.ok(c);
});
