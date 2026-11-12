// La fenêtre de validation : ce qu'il y a à vérifier, les liens (téléchargement, accès direct ou relayé), les réponses
// point par point et la demande envoyée ; son contenu rendu sur un faux DOM.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.attributs = {}; this.value = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const memoireLocale = new Map();    // le « stockage local » du navigateur, partagé entre « rechargements »
globalThis.localStorage = {getItem: (k) => (memoireLocale.has(k) ? memoireLocale.get(k) : null), setItem: (k, v) => memoireLocale.set(k, String(v))};
const V = await import("../ui/validation.js");

const D = {id: "v7", genre: "valider_etape", texte: "L'élément « Jeu » attend votre validation.", fonctionnalite: "f1",
  element: {id: "e1", nom: "Jeu"}, objectif: "Le jeu complet, jouable sur Android.", a_valider: "Validation avant livraison",
  compte_rendu: "Apk signé, testé sur l'émulateur.",
  fichiers: [{chemin: "build/jeu.apk", titre: "L'apk d'essai", taille: 12_900_000, date: "2026-11-12T10:05:00+01:00"},
             {chemin: "pieces/f1/menu.png", titre: "Le menu"}, {chemin: "pieces/f1/brut.png", titre: "brut.png"},
             {chemin: "src/main.gd", titre: "Le code"}],
  acces: {url: "http://127.0.0.1:5173/jeu/?mode=essai", description: "Le jeu dans le navigateur"},
  points: ["Le jeu se lance sur le téléphone", "Le bouton Jouer ouvre la partie"]};

test("points : ceux de la décision, sinon le point par défaut (décision d'avant)", () => {
  assert.deepEqual(V.pointsDeValidation(D), ["Le jeu se lance sur le téléphone", "Le bouton Jouer ouvre la partie"]);
  for (const mauvais of [undefined, [], ["x".repeat(161)], ["a", "a"], Array.from({length: 9}, (_, i) => `p${i}`), [3]]) {
    assert.deepEqual(V.pointsDeValidation({...D, points: mauvais}), [V.POINT_PAR_DEFAUT]);
  }
  assert.equal(V.POINT_PAR_DEFAUT, "L'élément correspond à l'objectif");
});

test("tailles lisibles", () => {
  assert.equal(V.tailleLisible(512), "512 octets");
  assert.equal(V.tailleLisible(850 * 1024), "850 Ko");
  assert.equal(V.tailleLisible(12_900_000), "12 Mo");
  assert.equal(V.tailleLisible(3.4 * 1024 * 1024), "3,4 Mo");
  assert.equal(V.tailleLisible(undefined), "");
});

test("à vérifier : livrables téléchargeables, images légendées, autres fichiers", () => {
  const v = V.aVerifier(D, {hotePage: "127.0.0.1", projet: "demo"});
  assert.deepEqual(v.livrables.map((l) => [l.nom, l.titre, l.taille, l.url]), [["jeu.apk", "L'apk d'essai", "12 Mo",
    "/api/telecharger?fonctionnalite=f1&chemin=build%2Fjeu.apk&projet=demo"]]);
  assert.deepEqual(v.images, [{chemin: "pieces/f1/menu.png", legende: "Le menu"}, {chemin: "pieces/f1/brut.png", legende: ""}]);
  assert.deepEqual(v.autres, [{chemin: "src/main.gd", titre: "Le code"}]);
  // au téléphone : l'adresse complète du bureau, celle que le téléphone a ouverte
  const tel = V.aVerifier(D, {hotePage: "100.64.1.2", projet: "demo", origine: "http://100.64.1.2:8765"});
  assert.equal(tel.livrables[0].url, "http://100.64.1.2:8765/api/telecharger?fonctionnalite=f1&chemin=build%2Fjeu.apk&projet=demo");
});

test("lien d'accès : direct sur l'ordinateur, relayé au téléphone, direct pour un site d'ailleurs", () => {
  assert.deepEqual(V.lienAcces(D, {hotePage: "127.0.0.1", projet: "demo"}),
    {url: "http://127.0.0.1:5173/jeu/?mode=essai", description: "Le jeu dans le navigateur", relaye: false,
     cible: "http://127.0.0.1:5173/jeu/?mode=essai"});
  const tel = V.lienAcces(D, {hotePage: "100.64.1.2", projet: "demo", origine: "http://100.64.1.2:8765"});
  assert.equal(tel.url, "http://100.64.1.2:8765/apercu/demo/v7/jeu/?mode=essai");
  assert.equal(tel.relaye, true);
  assert.equal(V.lienAcces(D, {hotePage: "100.64.1.2", projet: null}).url, "/apercu/-/v7/jeu/?mode=essai");
  const ailleurs = {...D, acces: {url: "https://essai.exemple.fr/"}};
  assert.equal(V.lienAcces(ailleurs, {hotePage: "100.64.1.2"}).url, "https://essai.exemple.fr/");
  assert.equal(V.lienAcces({...D, acces: {url: "javascript:alert(1)"}}), null);
  assert.equal(V.lienAcces({...D, acces: undefined}), null);
});

test("la demande : une réponse par point, le verdict en découle, le texte libre s'il y en a", () => {
  const [p1, p2] = V.pointsDeValidation(D);
  assert.equal(V.corpsValidation(D, {[p1]: true}, ""), null);                   // tous les points sont à choisir
  assert.equal(V.libelleEnvoi(D, {[p1]: true}), "Répondez aux 1 point restant");
  assert.deepEqual(V.corpsValidation(D, {[p1]: true, [p2]: true}, "  "),
    {type: "valider_etape", decision: "v7", verdict: "valider", reponses: [{point: p1, ok: true}, {point: p2, ok: true}]});
  assert.equal(V.libelleEnvoi(D, {[p1]: true, [p2]: true}), "Valider l'élément");
  assert.deepEqual(V.corpsValidation(D, {[p1]: true, [p2]: false}, " Le son est trop fort. "),
    {type: "valider_etape", decision: "v7", verdict: "renvoyer", texte: "Le son est trop fort.",
     reponses: [{point: p1, ok: true}, {point: p2, ok: false}]});
  assert.equal(V.libelleEnvoi(D, {[p1]: false, [p2]: false}), "Renvoyer : 2 points à revoir");
  const ancienne = {...D, points: undefined};
  assert.deepEqual(V.corpsValidation(ancienne, {[V.POINT_PAR_DEFAUT]: true}).reponses,
    [{point: V.POINT_PAR_DEFAUT, ok: true}]);
});

function rendre(d, agir = true) {
  const demandes = [];
  let fermee = 0;
  const ctx = {etat: {agir}, barre: {demander: async (x) => { demandes.push(x); return {ok: true}; }}};
  const r = V.contenuValidation(ctx, d, {fermer: () => { fermee++; }, hotePage: "100.64.1.2", origine: "http://100.64.1.2:8765"});
  return {...r, demandes, fermees: () => fermee};
}

test("la fenêtre : dans l'ordre, ce qu'on valide, de quoi vérifier, le compte rendu, les points, le champ libre", () => {
  const {boite} = rendre(D);
  const texte = boite.textContent;
  const ordre = ["Objectif : Le jeu complet", "À valider : Validation avant livraison", "L'apk d'essai", "Le jeu dans le navigateur",
    "Le menu", "Compte rendu", "Le jeu se lance sur le téléphone", "Le bouton Jouer", "Autre chose à signaler"].map((x) => texte.indexOf(x));
  assert.ok(ordre.every((x, i) => x >= 0 && (i === 0 || x > ordre[i - 1])), JSON.stringify(ordre));
  const telecharger = boite.tous((n) => n.tagName === "a" && n.textContent === "Télécharger");
  assert.equal(telecharger.length, 1);
  assert.equal(telecharger[0].attributs.download, "jeu.apk");
  assert.match(telecharger[0].href, /^http:\/\/100\.64\.1\.2:8765\/api\/telecharger\?/);
  const ouvrir = boite.tous((n) => n.tagName === "a" && n.textContent === "Ouvrir")[0];
  assert.equal(ouvrir.href, "http://100.64.1.2:8765/apercu/-/v7/jeu/?mode=essai");
  assert.deepEqual([ouvrir.target, ouvrir.rel], ["_blank", "noopener"]);
  assert.equal(boite.tous((n) => n.tagName === "img").length, 2);
  assert.equal(boite.attributs.role, "dialog");
  assert.equal(boite.attributs["aria-modal"], "true");
  assert.equal(boite.tous((n) => n.tagName === "button" && /^(Valider|Renvoyer avec)/.test(n.textContent)).length, 0);
});

test("la fenêtre : l'envoi attend une réponse par point, puis part une seule fois et ferme", async () => {
  const {boite, demandes, fermees} = rendre(D);
  const envoi = boite.tous((n) => n.className.startsWith("bouton val-envoyer"))[0];
  assert.equal(envoi.disabled, true);
  await envoi.auteurs.click[0]();
  assert.deepEqual(demandes, []);
  const radios = boite.tous((n) => n.tagName === "input" && n.type === "radio");
  assert.equal(radios.length, 4);
  radios[0].auteurs.change[0]();            // point 1 : OK
  assert.equal(envoi.disabled, true);
  radios[3].auteurs.change[0]();            // point 2 : À revoir
  assert.equal(envoi.disabled, false);
  assert.equal(envoi.textContent, "Renvoyer : 1 point à revoir");
  boite.tous((n) => n.tagName === "textarea")[0].value = "Ajoutez un bouton retour.";
  await envoi.auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "valider_etape", decision: "v7", verdict: "renvoyer", texte: "Ajoutez un bouton retour.",
    reponses: [{point: "Le jeu se lance sur le téléphone", ok: true}, {point: "Le bouton Jouer ouvre la partie", ok: false}]}]);
  assert.equal(fermees(), 1);
});

test("une décision d'avant (sans points ni fichiers) s'ouvre aussi, avec un seul point", () => {
  const ancienne = {id: "v1", genre: "valider_etape", texte: "L'élément « Accueil » attend votre validation.",
    fonctionnalite: "f1", element: {id: "e1", nom: "Accueil"}, etape: "a", tache: "t1", compte_rendu: "Fait.", fichiers: []};
  const {boite} = rendre(ancienne);
  assert.match(boite.textContent, /L'élément correspond à l'objectif/);
  assert.match(boite.textContent, /Rien à télécharger ni à ouvrir/);
  assert.equal(boite.tous((n) => n.tagName === "input").length, 2);
});

test("trois blocs en tête, après l'objectif et avant de quoi vérifier ; points ensuite", () => {
  const dit = {doit_marcher: "L'apk s'installe et affiche le menu.", pas_encore: "Le jeu ne répond pas encore.",
    conclusion: "Validez si l'application s'ouvre."};
  const {boite} = rendre({...D, ...dit});
  const texte = boite.textContent;
  const ordre = ["Objectif : Le jeu complet", "Ce qui doit marcher", "L'apk s'installe et affiche le menu.",
    "Pas encore attendu à ce stade", "Le jeu ne répond pas encore.", "À conclure", "Validez si l'application s'ouvre.",
    "L'apk d'essai", "Le jeu se lance sur le téléphone"].map((x) => texte.indexOf(x));
  assert.ok(ordre.every((x, i) => x >= 0 && (i === 0 || x > ordre[i - 1])), JSON.stringify(ordre));
  assert.deepEqual(V.consignesDeValidation({...dit, pas_encore: ""}).map((b) => b.texte),
    [dit.doit_marcher, "Tout est attendu à ce stade.", dit.conclusion]);
});

test("décision posée sans ces champs : « Ce qui doit marcher » par défaut et rien d'autre", () => {
  for (const d of [D, {...D, doit_marcher: "  "}, {...D, pas_encore: "x", conclusion: "y"}]) {
    assert.deepEqual(V.consignesDeValidation(d), [{cle: "doit_marcher", libelle: "Ce qui doit marcher",
      texte: "L'élément correspond à son objectif"}]);
  }
  const {boite} = rendre(D);
  assert.match(boite.textContent, /Ce qui doit marcher/);
  assert.doesNotMatch(boite.textContent, /Pas encore attendu|À conclure/);
});

test("nature : libellé en tête, mode opératoire numéroté juste après « Télécharger » (en jeu seulement)", () => {
  const mode = ["Installez l'apk.", "Ouvrez le jeu en portrait.", "Touchez Jouer.", "Observez le menu."];
  const {boite} = rendre({...D, nature: "en_jeu", mode_operatoire: mode});
  const texte = boite.textContent;
  const ordre = ["Objectif : Le jeu complet", "À essayer en jeu", "L'apk d'essai", "Télécharger", "Mode opératoire",
    "Installez l'apk.", "Observez le menu.", "Le jeu dans le navigateur", "Compte rendu"].map((x) => texte.indexOf(x));
  assert.ok(ordre.every((x, i) => x >= 0 && (i === 0 || x > ordre[i - 1])), JSON.stringify(ordre));
  const liste = boite.tous((n) => n.tagName === "ol")[0];
  assert.deepEqual(liste.enfants.map((e) => e.textContent), mode);
  assert.equal(V.natureDeValidation({nature: "visuel"}).libelle, "Visuel à juger");
  assert.equal(V.natureDeValidation({nature: "mecanique"}).libelle, "Mécanique à lire");
  assert.equal(V.natureDeValidation({nature: "constructor"}), null);
  assert.equal(V.natureDeValidation(D), null);
  // pas de mode opératoire hors « en jeu », ni mal formé
  assert.deepEqual(V.modeOperatoire({nature: "visuel", mode_operatoire: mode}), []);
  assert.deepEqual(V.modeOperatoire({nature: "en_jeu", mode_operatoire: ["une seule"]}), []);
  assert.deepEqual(V.modeOperatoire({nature: "en_jeu", mode_operatoire: ["a", "b", " "]}), []);
  assert.equal(rendre({...D, nature: "visuel", mode_operatoire: mode}).boite.tous((n) => n.tagName === "ol").length, 0);
  assert.doesNotMatch(rendre(D).boite.textContent, /À essayer en jeu|Visuel à juger|Mode opératoire/);
});

test("son à écouter : libellé, lecteur audio par fichier audio (adresse de lecture), téléchargement en plus", () => {
  const d = {...D, nature: "son", fichiers: [{chemin: "sons/coup épique.mp3", titre: "Le coup"}, {chemin: "sons/fond.flac", titre: "fond.flac"},
    {chemin: "pieces/f1/menu.png", titre: "Le menu"}, {chemin: "build/jeu.apk", titre: "Apk"}]};
  assert.equal(V.natureDeValidation({nature: "son"}).libelle, "Son à écouter");
  const v = V.aVerifier(d, {projet: "demo", origine: "http://100.64.1.2:8765"});
  assert.deepEqual(v.sons.map((s) => [s.nom, s.titre]), [["coup épique.mp3", "Le coup"], ["fond.flac", "fond.flac"]]);
  assert.equal(v.sons[0].url, "http://100.64.1.2:8765/api/telecharger?fonctionnalite=f1&chemin=sons%2Fcoup%20%C3%A9pique.mp3"
    + "&lecture=1&projet=demo");
  assert.deepEqual(v.livrables.map((l) => l.nom), ["jeu.apk"]);          // un son n'est pas un livrable à télécharger seul
  const {boite} = rendre(d);
  const lecteurs = boite.tous((n) => n.tagName === "audio");
  assert.equal(lecteurs.length, 2);
  assert.ok(lecteurs.every((a) => a.controls === true && a.preload === "none"));
  assert.match(lecteurs[0].src, /\/api\/telecharger\?.*&lecture=1/);
  assert.match(boite.textContent, /Son à écouter/);
  assert.match(boite.textContent, /Le coup/);
  assert.equal(boite.tous((n) => n.tagName === "a" && n.textContent === "Télécharger" && /\.(mp3|flac)$/.test(n.attributs.download)).length, 2);
  assert.doesNotMatch(boite.textContent, /Rien à télécharger/);
  assert.equal(V.estSon("a/B.FLAC") && V.estSon("x.wav") && V.estSon("x.ogg") && V.estSon("x.mp3"), true);
  assert.equal(V.estSon("x.mp4"), false);
});

test("envoi : marquée envoyée dès le départ, oubliée si l'envoi échoue, gardée si elle était déjà répondue", async () => {
  const reponses = [{ok: false, message: "La commande a échoué."}, {ok: false, message: "Cette décision a déjà reçu une réponse : x"},
    {ok: true}];
  const vus = [];
  const d = {...D, id: "v-essai"};
  const ctx = {etat: {agir: true}, barre: {demander: async () => { vus.push(V.estEnvoyee("v-essai")); return reponses.shift(); }}};
  const lancer = async () => {
    const {boite} = V.contenuValidation(ctx, d, {fermer() {}, hotePage: "127.0.0.1", origine: null});
    const radios = boite.tous((n) => n.tagName === "input" && n.type === "radio");
    radios.filter((_, i) => i % 2 === 0).forEach((r) => r.auteurs.change[0]());
    await boite.tous((n) => n.className.startsWith("bouton val-envoyer"))[0].auteurs.click[0]();
    return boite;
  };
  await lancer();
  assert.deepEqual([vus[0], V.estEnvoyee("v-essai")], [true, false]);        // échec : elle revient
  await lancer();
  assert.equal(V.estEnvoyee("v-essai"), true);                                // déjà répondue : elle reste envoyée
  const rouverte = V.contenuValidation(ctx, d, {fermer() {}, hotePage: "127.0.0.1", origine: null}).boite;
  assert.equal(rouverte.tous((n) => n.className.startsWith("bouton val-envoyer")).length, 0);
  assert.match(rouverte.textContent, /Réponse envoyée/);
  V.oublierEnvoyee("v-essai");
  await lancer();
  assert.equal(V.estEnvoyee("v-essai"), true);                                // succès : envoyée jusqu'à la disparition
  // sécurité : oubliée au bout de 30 minutes
  V.marquerEnvoyee("v-vieux", 1000);
  assert.equal(V.estEnvoyee("v-vieux", 1000 + V.SECURITE_ENVOYEE_MS - 1), true);
  assert.equal(V.estEnvoyee("v-vieux", 1000 + V.SECURITE_ENVOYEE_MS), false);
  V.oublierEnvoyee("v-essai");
});

test("sans droit d'agir : la fenêtre se lit, rien ne s'envoie", () => {
  const {boite} = rendre(D, false);
  assert.equal(boite.tous((n) => n.className.startsWith("bouton val-envoyer")).length, 0);
  assert.ok(boite.tous((n) => n.tagName === "input").every((x) => x.disabled));
});

test("les extensions téléchargeables sont celles du bureau", () => {
  const source = readFileSync(new URL("../../releve.py", import.meta.url), "utf-8");
  const bloc = source.slice(source.indexOf("TELECHARGEABLES = {"), source.indexOf("}", source.indexOf("TELECHARGEABLES = {")));
  const python = [...bloc.matchAll(/"(\.[a-z0-9]+)":/g)].map((m) => m[1]).sort();
  assert.deepEqual([...V.EXTENSIONS_TELECHARGEABLES].sort(), python);
  assert.ok(V.estTelechargeable("build/Jeu.APK") && !V.estTelechargeable("a.png") && !V.estTelechargeable("main.gd"));
});

const ETAT_SERVI = (...ids) => ({decisions_projet: [...ids.map((id) => ({id, genre: "valider_etape"})), {id: "s1", genre: "session_cloud"}],
  directeur: {total: 3, projet: 2}});

test("appliquerEnvoyees : retrait immédiat, état servi qui la contient encore, compteur ajusté", () => {
  V.marquerEnvoyee("va");
  const e = ETAT_SERVI("va", "vb");
  const vu = V.appliquerEnvoyees(e);
  assert.deepEqual(vu.decisions_projet.map((d) => d.id), ["vb", "s1"]);
  assert.deepEqual([vu.directeur.total, vu.directeur.projet], [2, 1]);
  assert.equal(e.decisions_projet.length, 3);                                  // l'état servi n'est pas modifié
  assert.deepEqual(V.appliquerEnvoyees(e).decisions_projet.map((d) => d.id), ["vb", "s1"]);   // à chaque rendu
  assert.equal(V.appliquerEnvoyees(ETAT_SERVI("vb")).decisions_projet.length, 2);              // rien de masqué : l'état tel quel
  assert.equal(V.estEnvoyee("va"), false);          // « va » n'est plus servie : purgée
  V.oublierEnvoyee("va");
});

test("appliquerEnvoyees : l'écouteur est prévenu à l'envoi et à l'échec ; 409 reste masquée, échec revient", async () => {
  let n = 0;
  const arret = V.surEnvoyees(() => { n += 1; });
  const reponses = [{ok: false, message: "Réseau coupé."}, {ok: false, message: "Cette décision a déjà reçu une réponse : x"}];
  const d = {...D, id: "v-409"};
  const e = ETAT_SERVI("v-409");
  const vus = [];
  const ctx = {etat: {agir: true}, barre: {demander: async () => { vus.push(V.appliquerEnvoyees(e).decisions_projet.length); return reponses.shift(); }}};
  const lancer = async () => {
    const {boite} = V.contenuValidation(ctx, d, {fermer() {}, hotePage: "127.0.0.1", origine: null});
    boite.tous((n2) => n2.tagName === "input" && n2.type === "radio").filter((_, i) => i % 2 === 0).forEach((r) => r.auteurs.change[0]());
    await boite.tous((n2) => n2.className.startsWith("bouton val-envoyer"))[0].auteurs.click[0]();
    return boite;
  };
  const boite = await lancer();
  assert.equal(vus[0], 1);                                                     // pendant l'envoi : déjà retirée
  assert.equal(V.appliquerEnvoyees(e).decisions_projet.length, 2);             // échec : elle revient
  assert.match(boite.textContent, /Réseau coupé/);                             // avec le message d'erreur
  await lancer();
  assert.equal(V.appliquerEnvoyees(e).decisions_projet.length, 1);             // 409 : reste masquée
  assert.equal(n, 3);                                                        // envoi, échec, envoi
  arret();
  V.oublierEnvoyee("v-409");
});

test("mémoire des envois : survit au rechargement, par projet, purgée à la disparition", async () => {
  const P = await import("../ui/projets.js");
  P.definirProjet("alpha");
  V.marquerEnvoyee("vr");
  V.oublierMemoireDePage();                                                    // la page est rechargée
  assert.equal(V.estEnvoyee("vr"), true);
  P.definirProjet("beta");
  assert.equal(V.estEnvoyee("vr"), false);                                     // une clé par projet
  P.definirProjet("alpha");
  V.oublierMemoireDePage();
  V.appliquerEnvoyees({decisions_projet: []});                                 // disparue de l'état servi
  V.oublierMemoireDePage();
  assert.equal(V.estEnvoyee("vr"), false);
  globalThis.localStorage.setItem("bureau.validations-envoyees.alpha", "pas du json");
  V.oublierMemoireDePage();
  assert.equal(V.estEnvoyee("vr"), false);                                     // stockage illisible : sans effet
  P.definirProjet(null);
});

test("« À revoir » : l'ancienne décision levée disparaît, la nouvelle (autre identifiant) s'affiche", () => {
  V.marquerEnvoyee("v1");
  const apres = V.appliquerEnvoyees({decisions_projet: [{id: "v1", genre: "valider_etape"}]});
  assert.equal(apres.decisions_projet.length, 0);
  V.appliquerEnvoyees({decisions_projet: []});                                 // le moteur a levé la décision
  const nouvelle = V.appliquerEnvoyees({decisions_projet: [{id: "v2", genre: "valider_etape"}]});
  assert.deepEqual(nouvelle.decisions_projet.map((d) => d.id), ["v2"]);        // l'élément corrigé : nouvelle décision visible
});
