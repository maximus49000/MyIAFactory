// Les cases du déport : un lieu (poste / GitHub / serveur) par action, les avertissements de l'état sous les choix.
import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {};
    this.checked = false; this.disabled = false; this.value = ""; this.name = ""; this.type = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t), createTextNode: (t) => { const n = new Noeud("#texte"); n._texte = t; return n; }};

const {blocDeport, enregistrerDeport, AIDE_DEPORT, avertissementsGroupes} = await import("../ui/deport.js");

const POSTE = {apk: "poste", tests: "poste", charge: "poste", emulateur: "poste"};
const radios = (b) => b.tous((n) => n.tagName === "input" && n.type === "radio");
const radio = (b, action, lieu) => radios(b).find((r) => r.name === "deport-" + action && r.value === lieu);
const changer = async (r) => { r.checked = true; for (const f of r.auteurs.change || []) await f(); };

function rendre(deport, fetchFn) {
  const ctx = {etat: {deport}, rouvrir() { ctx.rouvert = true; }};
  return {ctx, bloc: blocDeport(ctx, fetchFn || (async () => ({ok: true})))};
}

test("l'aide dit que le poste est le défaut et qu'on déporte pour le soulager", () => {
  assert.match(AIDE_DEPORT, /poste/);
  assert.match(AIDE_DEPORT, /défaut/);
  assert.match(AIDE_DEPORT, /soulager/);
});

test("chaque action a un choix poste, GitHub, serveur ; le lieu de l'état est coché", () => {
  const {bloc} = rendre({lieux: {...POSTE, tests: "github"}, avertissements: []});
  for (const action of ["apk", "tests", "charge", "emulateur"]) {
    assert.deepEqual(radios(bloc).filter((r) => r.name === "deport-" + action).map((r) => r.value), ["poste", "github", "serveur"]);
    assert.match(bloc.textContent, new RegExp(action));
  }
  assert.equal(radio(bloc, "tests", "github").checked, true);
  assert.equal(radio(bloc, "tests", "poste").checked, false);
  assert.equal(radio(bloc, "apk", "poste").checked, true);
});

test("serveur est grisé et dit « bientôt » ; l'émulateur n'offre pas GitHub", () => {
  const {bloc} = rendre({lieux: POSTE, avertissements: [], serveur_disponible: false});
  for (const action of ["apk", "tests", "charge", "emulateur"]) assert.equal(radio(bloc, action, "serveur").disabled, true);
  assert.match(bloc.textContent, /bientôt/);
  assert.equal(radio(bloc, "emulateur", "github").disabled, true);
  assert.equal(radio(bloc, "apk", "github").disabled, false);
  assert.match(bloc.textContent, /peu fiable sur GitHub, utilisez le poste ou le serveur/);
});

test("changer un choix écrit {lieux: {action: lieu}} dans deport et rouvre le bureau", async () => {
  const vus = [];
  const {bloc, ctx} = rendre({lieux: POSTE, avertissements: []}, async (url, options) => { vus.push([url, options]); return {ok: true}; });
  await changer(radio(bloc, "apk", "github"));
  assert.match(vus[0][0], /\/api\/reglages/);
  assert.equal(vus[0][1].method, "POST");
  assert.equal(vus[0][1].headers["X-Bureau"], "1");
  assert.deepEqual(JSON.parse(vus[0][1].body), {deport: {lieux: {apk: "github"}}});
  assert.equal(ctx.etat.deport.lieux.apk, "github");
  assert.equal(ctx.rouvert, true);
});

test("enregistrerDeport : refus du serveur, injoignable", async () => {
  const refus = await enregistrerDeport({apk: "github"}, async () => ({ok: false, status: 400, json: async () => ({erreur: "lieu inconnu"})}));
  assert.deepEqual(refus, {ok: false, message: "Refusé : lieu inconnu"});
  const coupe = await enregistrerDeport({apk: "github"}, async () => { throw new Error("réseau"); });
  assert.deepEqual(coupe, {ok: false, message: "Serveur du bureau injoignable."});
  const ok = await enregistrerDeport({apk: "github"}, async () => ({ok: true}));
  assert.equal(ok.ok, true);
});

test("un refus remet le choix réel et affiche le message", async () => {
  const {bloc, ctx} = rendre({lieux: POSTE, avertissements: []},
    async () => ({ok: false, status: 400, json: async () => ({erreur: "pas maintenant"})}));
  await changer(radio(bloc, "tests", "github"));
  assert.equal(radio(bloc, "tests", "github").checked, false);
  assert.equal(radio(bloc, "tests", "poste").checked, true);
  assert.match(bloc.textContent, /Refusé : pas maintenant/);
  assert.equal(ctx.rouvert, undefined);
  assert.equal(radios(bloc).some((r) => r.disabled && r.value !== "serveur" && !(r.name.endsWith("emulateur") && r.value === "github")), false);
});

const texte = (action, ici, produit, ailleurs) => `« ${action} » tourne au lieu « ${ici} » mais attendra l'${produit} produit par ${ailleurs} : ` +
  "mettez la chaîne entière au même lieu pour éviter cette attente.";

test("les avertissements d'une même situation sont groupés, chaque action reste nommée", () => {
  const avertissements = [texte("tests", "poste", "APK", "GitHub"), texte("emulateur", "poste", "APK", "GitHub"),
    texte("charge", "poste", "APK", "GitHub")];
  const {bloc} = rendre({lieux: {...POSTE, apk: "github"}, avertissements});
  const notes = bloc.tous((n) => n.className.includes("deport-avertissement"));
  assert.equal(notes.length, 1);
  assert.match(notes[0].textContent, /tests/);
  assert.match(notes[0].textContent, /emulateur/);
  assert.match(notes[0].textContent, /charge/);
  assert.match(notes[0].textContent, /GitHub/);
  assert.match(notes[0].textContent, /même lieu/);
});

test("un avertissement d'un autre format s'affiche tel quel ; sans avertissement, rien", () => {
  const {bloc} = rendre({lieux: POSTE, avertissements: ["Autre chose."]});
  assert.match(bloc.textContent, /Autre chose\./);
  const {bloc: vide} = rendre({lieux: POSTE, avertissements: []});
  assert.equal(vide.tous((n) => n.className.includes("deport-avertissement")).length, 0);
});

test("un état sans déport donne les lieux par défaut (poste)", () => {
  const ctx = {etat: {}};
  const bloc = blocDeport(ctx, async () => ({ok: true}));
  assert.equal(radio(bloc, "apk", "poste").checked, true);
});

// Lien avec le moteur : la vraie sortie de bureau.deport.avertissements() doit passer par le regroupement.
// Si l'un des deux textes change, ce test casse (le texte copié à la main ci-dessus ne suffirait pas).
test("la vraie sortie de bureau/deport.py est reconnue et regroupée", () => {
  const racine = fileURLToPath(new URL("../../..", import.meta.url));
  const sortie = execFileSync("py", ["-3.12", "-c", "import json; from bureau import deport; " +
    "print(json.dumps(deport.avertissements({'apk': 'github', 'tests': 'poste', 'emulateur': 'poste', 'charge': 'poste'})))"],
  {cwd: racine, encoding: "utf8"});
  const reels = JSON.parse(sortie);
  assert.equal(reels.length, 3);
  const groupes = avertissementsGroupes(reels);
  assert.equal(groupes.length, 1);
  assert.match(groupes[0], /tests, charge, emulateur|tests, emulateur, charge/);
  assert.doesNotMatch(groupes[0], /tourne au lieu/);   // reconnu par la regex, pas affiché tel quel
});
