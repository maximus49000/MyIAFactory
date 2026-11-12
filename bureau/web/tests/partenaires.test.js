import test from "node:test";
import assert from "node:assert/strict";
import {libelleCategorie, popularite, trier, lienHttps, etatConnexion, libelleConnexion, quotaEnClair, lignePlan, parties, lignes, creerVue, rendrePartenaires,
        MAX_REGLE, MAX_NOTE_INSCRIPTION, estInscrit, etatPartenaire, libelleEtat, inscriptionNotee} from "../ui/partenaires.js";
import {lignesPartenaires, coutDePartenaire} from "../ui/facturation.js";
import {creerPlan} from "../logique/plan.js";
import {COLS} from "./donnees.js";

// Un DOM minimal : assez pour vérifier ce que l'espace construit, que les textes passent par textContent et que
// les boutons envoient les bonnes demandes.
class Noeud {
  constructor(tag) {
    this.tagName = tag; this.enfants = []; this.attributs = {}; this.ecouteurs = {};
    this.className = ""; this._texte = ""; this.value = ""; this.href = undefined;
  }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  set innerHTML(v) { throw new Error("innerHTML interdit"); }
  append(...e) { for (const x of e) if (x && typeof x === "object") x.parent = this; this.enfants.push(...e); }
  replaceChildren(...e) { this.enfants = []; this._texte = ""; this.append(...e); }
  replaceWith(n) { const p = this.parent; p.enfants[p.enfants.indexOf(this)] = n; n.parent = p; }
  focus() { this.focalise = true; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(t, f) { (this.ecouteurs[t] ||= []).push(f); }
  async declencher(t) { for (const f of this.ecouteurs[t] || []) await f({}); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const carte = (id, nom, categorie, extra = {}) => ({
  id, nom, categorie, sous_categorie: "generation", site: "https://exemple.org", inscription: `https://exemple.org/${id}/inscription`,
  connexions: [{type: "mcp", url: "https://mcp.exemple.org", commande: `claude mcp add --transport http ${id} https://mcp.exemple.org`},
               {type: "api", url: `https://exemple.org/${id}/cles`, variables: ["EXEMPLE_API_KEY"]}],
  plans: [{nom: "Gratuit", prix: 0, devise: "USD", periode: "mois", quota: "10 crédits", tarif: "gratuit"},
          {nom: "Pro", prix: 20, devise: "USD", periode: "mois", quota: null, tarif: "inclus"}],
  gratuit: "10 crédits", quota_lisible: "oui", illimite: false, statut: "actif", fiabilite: "officielle",
  verifie_le: "2026-11-11", ...extra,
});

const DONNEES = {
  categories: {
    "voix-audio": [carte("vox", "Vox", "voix-audio"), carte("echo", "Echo", "voix-audio", {fiabilite: "tiers"})],
    "video-3d-avatars": [carte("tripo", "Tripo", "video-3d-avatars", {quota_lisible: "inconnu"})],
    "mise-en-ligne-equipe": [carte("libre", "Libre", "mise-en-ligne-equipe", {illimite: true})],
  },
  etat: {
    connexions: {vox: {etat: "connecte", source: "serveur MCP déclaré", abonnement: "Pro", vu_le: "2026-11-11T10:00:00"},
                 tripo: {etat: "declare", source: "déclaré par l'utilisateur", vu_le: "2026-11-11"}},
    quotas: {vox: {reste: 4200, unite: "caractères", lu_le: "2026-11-11T10:05:00"},
             libre: {illimite: true, lu_le: "2026-11-11T10:05:00"}},
    limites: {echo: {depuis: "2026-11-11T09:00:00", raison: "quota épuisé"}},
    regles: {tripo: [{id: "r1", texte: "Générer en un seul prompt.", cree_le: "2026-11-11"}]},
  },
  conseils: {voix: [{id: "vox", raison: "Voix naturelles."}, {id: "echo", raison: "Secours."}]},
  maj_catalogue: "2026-11-11",
  cout_maj: {euros: 0.4, texte: "Environ 40 fiches sur Sonnet."},
};

const rendre = (donnees = DONNEES, vue = creerVue(), envoyes = []) => {
  const racine = rendrePartenaires(donnees, async (d) => { envoyes.push(d); return {ok: true, message: "Demande envoyée"}; }, vue);
  return {racine, vue, envoyes};
};
const bouton = (racine, texte) => racine.tous((n) => n.tagName === "button" && n.textContent === texte)[0];

test("lienHttps : https seulement, jamais javascript: ni data: ni http:", () => {
  assert.equal(lienHttps("https://exemple.org/a"), "https://exemple.org/a");
  for (const mauvais of ["javascript:alert(1)", "data:text/html,x", "http://exemple.org", "//exemple.org", "https://", "https://a b.org",
                         "HTTPS://exemple.org/\n", "", null, 12, undefined]) assert.equal(lienHttps(mauvais), null, String(mauvais));
});

test("etat de connexion : connecté, déclaré, sinon non connecté", () => {
  assert.equal(libelleConnexion(DONNEES, "vox"), "connecté");
  assert.equal(libelleConnexion(DONNEES, "tripo"), "déclaré, à vérifier");
  assert.equal(libelleConnexion(DONNEES, "echo"), "non connecté");
  assert.equal(etatConnexion(null, "x"), "non_connecte");
});

test("quotaEnClair : reste N, illimité, quota inconnu, limite atteinte", () => {
  const c = DONNEES.categories;
  assert.equal(quotaEnClair(DONNEES, c["voix-audio"][0]).texte, "reste 4 200 caractères");
  assert.ok(quotaEnClair(DONNEES, c["voix-audio"][0]).date);
  assert.equal(quotaEnClair(DONNEES, c["mise-en-ligne-equipe"][0]).texte, "illimité");
  assert.equal(quotaEnClair(DONNEES, c["video-3d-avatars"][0]).texte, "quota inconnu");
  assert.equal(quotaEnClair(DONNEES, c["video-3d-avatars"][0]).date, "");
  assert.equal(quotaEnClair(DONNEES, c["voix-audio"][1]).limite.raison, "quota épuisé");
  assert.equal(quotaEnClair(DONNEES, {id: "x", illimite: true}).texte, "illimité");
});

test("lignePlan : gratuit, prix par période, à l'usage", () => {
  assert.equal(lignePlan({nom: "Gratuit", prix: 0, tarif: "gratuit", quota: "10 crédits"}), "Gratuit : gratuit · 10 crédits");
  assert.equal(lignePlan({nom: "Pro", prix: 7.49, devise: "EUR", periode: "mois", tarif: "inclus", quota: null}), "Pro : 7,49 EUR/mois");
  assert.equal(lignePlan({nom: "API", prix: null, periode: "usage", tarif: "usage"}), "API : à l'usage");
  assert.equal(lignePlan({nom: "X", prix: null, tarif: "inconnu"}), "X : prix non lu");
});

test("parties : connectés, conseillés dans l'ordre avec leur raison, tous par catégorie, filtre", () => {
  const p = parties(DONNEES);
  assert.deepEqual(p.connectes.map((c) => c.id), ["vox"]);
  assert.deepEqual(p.conseilles.map((c) => [c.besoin, c.carte.id, c.raison]), [["voix", "vox", "Voix naturelles."], ["voix", "echo", "Secours."]]);
  assert.deepEqual(p.categories.map((g) => g.id), ["voix-audio", "video-3d-avatars", "mise-en-ligne-equipe"]);
  assert.equal(p.total, 4);
  assert.deepEqual(parties(DONNEES, "tri").categories.map((g) => g.cartes.map((c) => c.id)), [["tripo"]]);
  assert.deepEqual(parties(DONNEES, "VOIX").categories.map((g) => g.id), ["voix-audio"]);   // la catégorie compte
  assert.deepEqual(parties({}).categories, []);
  assert.deepEqual(parties(null).connectes, []);
});

test("lignes : un seul tableau, connectés puis conseillés en tête, filtre par type et par texte", () => {
  const ids = (o) => lignes(DONNEES, o).map((l) => l.carte.id);
  assert.deepEqual(ids({}), ["vox", "echo", "tripo", "libre"]);
  const vox = lignes(DONNEES, {})[0];
  assert.equal(vox.connecte, true);
  assert.deepEqual(vox.conseils, [{besoin: "voix", raison: "Voix naturelles."}]);
  assert.deepEqual(ids({type: "connectes"}), ["vox"]);
  assert.deepEqual(ids({type: "conseilles"}), ["vox", "echo"]);
  assert.deepEqual(ids({type: "video-3d-avatars"}), ["tripo"]);
  assert.deepEqual(ids({type: "voix-audio", filtre: "echo"}), ["echo"]);
  assert.deepEqual(lignes({}, {}), []);
  assert.deepEqual(lignes(null, {type: "connectes"}), []);
});

test("rendu : un seul tableau et un filtre par type en haut (essai réel)", () => {
  const {racine, vue} = rendre();
  const t = racine.textContent;
  assert.ok(!/Conseillés pour ce projet|Tous les partenaires \(/.test(t), "plus de sections séparées");
  assert.match(t, /Conseillé : voix — Voix naturelles\./);
  assert.match(t, /facultatifs/);
  const type = racine.tous((n) => n.className === "partenaires-type")[0];
  const options = type.tous((n) => n.tagName === "option").map((o) => o.textContent);
  assert.deepEqual(options.slice(0, 3), ["Tous les types (4)", "Connectés (1)", "Conseillés (2)"]);
  assert.ok(options.includes("Vidéo, 3D, avatars (1)") || options.length === 6);
  const liste = racine.tous((n) => n.className === "partenaires-liste")[0];
  type.value = "connectes";
  type.ecouteurs.change.forEach((f) => f());
  assert.equal(vue.type, "connectes");
  assert.match(liste.textContent, /Vox/);
  assert.ok(!/Tripo/.test(liste.textContent));
  const vide = rendre({categories: {}}).racine.textContent;
  assert.match(vide, /Aucun partenaire connecté/);
});

test("carte : illimité, quota inconnu, prix à vérifier, limite atteinte, abonnement", () => {
  const t = rendre().racine.textContent;
  assert.match(t, /illimité/);
  assert.match(t, /quota inconnu/);
  assert.match(t, /reste 4.200 caractères \(relevé du/);
  assert.match(t, /abonnement : Pro/);
  assert.match(t, /limite atteinte/);
  const echo = rendre().racine.tous((n) => n.className === "partenaire-carte" && /Echo/.test(n.textContent));
  assert.ok(echo.every((c) => /prix à vérifier/.test(c.textContent)));
  assert.ok(!/prix à vérifier/.test(rendre().racine.tous((n) => n.className === "partenaire-carte" && /Tripo/.test(n.textContent))[0].textContent));
});

test("carte dépliée : plans, date de vérification, liens https, commande MCP à copier, variable", () => {
  const vue = creerVue();
  vue.ouvertes.add("vox");
  const {racine} = rendre(DONNEES, vue);
  const t = racine.textContent;
  assert.match(t, /Pro : 20 USD\/mois/);
  assert.match(t, /Offres vérifiées le/);
  assert.match(t, /claude mcp add --transport http vox https:\/\/mcp\.exemple\.org/);
  assert.match(t, /Variable d'environnement : EXEMPLE_API_KEY/);
  const liens = racine.tous((n) => n.tagName === "a");
  assert.ok(liens.length >= 2);
  for (const a of liens) {
    assert.match(a.href, /^https:\/\//);
    assert.equal(a.target, "_blank");
    assert.equal(a.rel, "noopener noreferrer");
  }
  assert.ok(liens.some((a) => a.textContent === "S'inscrire"));
  assert.ok(liens.some((a) => /Se connecter/.test(a.textContent)));
  assert.ok(bouton(racine, "Copier"));
});

test("un lien javascript: n'est pas rendu", () => {
  const hostile = JSON.parse(JSON.stringify(DONNEES));
  hostile.categories["voix-audio"][0].inscription = "javascript:alert(1)";
  hostile.categories["voix-audio"][0].connexions = [{type: "api", url: "javascript:alert(2)"}, {type: "studio", url: "data:text/html,x"}];
  const vue = creerVue();
  vue.ouvertes.add("vox");
  const {racine} = rendre(hostile, vue);
  assert.equal(racine.tous((n) => n.tagName === "a" && /javascript|data:/.test(String(n.href))).length, 0);
  assert.ok(!racine.tous((n) => n.tagName === "a").some((a) => a.textContent === "S'inscrire"));
});

test("texte hostile : littéral, jamais interprété (aucun innerHTML)", () => {
  const hostile = JSON.parse(JSON.stringify(DONNEES));
  hostile.categories["voix-audio"][0].nom = "<img src=x onerror=alert(1)>";
  hostile.etat.regles.vox = [{id: "r9", texte: "<script>alert(1)</script>", cree_le: "2026-11-11"}];
  hostile.etat.limites.vox = {depuis: "2026-11-11", raison: "<b>x</b>"};
  const vue = creerVue();
  vue.ouvertes.add("vox");
  const t = rendre(hostile, vue).racine.textContent;
  assert.match(t, /<img src=x onerror=alert\(1\)>/);
  assert.match(t, /<script>alert\(1\)<\/script>/);
});

test("filtre texte : ne garde que les partenaires qui correspondent", () => {
  const {racine} = rendre();
  const saisie = racine.tous((n) => n.tagName === "input")[0];
  saisie.value = "tripo";
  saisie.ecouteurs.input.forEach((f) => f());
  const liste = racine.tous((n) => n.className === "partenaires-liste")[0];
  assert.match(liste.textContent, /Tripo/);
  assert.ok(!/Echo/.test(liste.textContent));
  saisie.value = "zzz";
  saisie.ecouteurs.input.forEach((f) => f());
  assert.match(liste.textContent, /Aucun partenaire ne correspond/);
});

test("règles : ajouter, modifier, supprimer sont des demandes ; texte vide ou trop long refusé", async () => {
  const vue = creerVue();
  vue.ouvertes.add("tripo");
  const envoyes = [];
  let {racine} = rendre(DONNEES, vue, envoyes);
  assert.match(racine.textContent, /Générer en un seul prompt\./);
  await bouton(racine, "Supprimer").declencher("click");
  assert.deepEqual(envoyes.pop(), {type: "partenaire_regle", partenaire: "tripo", operation: "supprimer", id: "r1"});
  // ajouter
  const zone = racine.tous((n) => n.tagName === "textarea")[0];
  assert.equal(zone.attributs.maxlength, String(MAX_REGLE));
  zone.value = "   ";
  await bouton(racine, "Ajouter la règle").declencher("click");
  assert.equal(envoyes.length, 0);
  assert.match(racine.textContent, /La règle est vide/);
  zone.value = "x".repeat(MAX_REGLE + 1);
  await bouton(racine, "Ajouter la règle").declencher("click");
  assert.equal(envoyes.length, 0);
  zone.value = "Un seul prompt.";
  await bouton(racine, "Ajouter la règle").declencher("click");
  assert.deepEqual(envoyes.pop(), {type: "partenaire_regle", partenaire: "tripo", operation: "ajouter", texte: "Un seul prompt."});
  // modifier : ouvre l'édition puis envoie
  await bouton(racine, "Modifier").declencher("click");
  const edition = racine.tous((n) => n.tagName === "textarea")[0];
  assert.equal(edition.value, "Générer en un seul prompt.");
  edition.value = "Autre règle.";
  await bouton(racine, "Enregistrer").declencher("click");
  assert.deepEqual(envoyes.pop(), {type: "partenaire_regle", partenaire: "tripo", operation: "modifier", id: "r1", texte: "Autre règle."});
});

test("sans le droit d'agir : ni boutons de demande, ni édition des règles", () => {
  const vue = creerVue({agir: false});
  vue.ouvertes.add("tripo");
  const {racine} = rendre(DONNEES, vue);
  assert.equal(bouton(racine, "Actualiser"), undefined);
  assert.equal(bouton(racine, "Mettre à jour les offres"), undefined);
  assert.equal(bouton(racine, "Supprimer"), undefined);
  assert.equal(bouton(racine, "Ajouter la règle"), undefined);
  assert.match(racine.textContent, /Générer en un seul prompt\./);
});

test("Actualiser envoie la demande sans champ", async () => {
  const {racine, envoyes} = rendre();
  await bouton(racine, "Actualiser").declencher("click");
  assert.deepEqual(envoyes, [{type: "partenaires_actualiser"}]);
  assert.match(racine.textContent, /Demande envoyée/);
});

test("mettre à jour les offres : la confirmation montre le coût estimé AVANT toute demande", async () => {
  const {racine, envoyes, vue} = rendre();
  await bouton(racine, "Mettre à jour les offres").declencher("click");
  assert.equal(envoyes.length, 0);
  assert.match(racine.textContent, /Coût estimé : ≈ 0,40 € — Environ 40 fiches sur Sonnet\./);
  // Annuler ne demande rien
  await bouton(racine, "Annuler").declencher("click");
  assert.equal(envoyes.length, 0);
  assert.ok(!/Coût estimé/.test(racine.textContent));
  // Confirmer envoie la demande avec confirme: true
  await bouton(racine, "Mettre à jour les offres").declencher("click");
  await bouton(racine, "Lancer la mise à jour").declencher("click");
  assert.deepEqual(envoyes, [{type: "partenaires_maj", confirme: true}]);
  assert.equal(vue.confirmation, false);
});

test("mise à jour sans coût fourni : « coût estimé inconnu »", async () => {
  const {racine} = rendre({...DONNEES, cout_maj: null});
  await bouton(racine, "Mettre à jour les offres").declencher("click");
  assert.match(racine.textContent, /coût estimé inconnu/);
});

test("facturation : une ligne par partenaire, coût d'origine, estimé, non chiffré", () => {
  const f = {partenaires: {
    tripo: {nom: "Tripo", total: 1.5, origine: [{montant: 1.6, devise: "USD"}], estime: true, non_chiffre: 0, usages: 3},
    vox: {nom: "Vox", total: 4, origine: [{montant: 4.3, devise: "USD"}, {montant: 1, devise: "EUR"}], estime: false, non_chiffre: 2, usages: 5},
    mut: {nom: "Muet", total: 0, origine: [], estime: false, non_chiffre: 2, usages: 2},
    zero: {total: 0, usages: 0}}};
  const l = lignesPartenaires(f);
  assert.deepEqual(l.map((x) => x.id), ["vox", "tripo", "mut", "zero"]);
  assert.equal(l[0].origine, "4,3 USD + 1 EUR");
  assert.equal(coutDePartenaire(l[0]), "≈ 4,00 € + non chiffré");
  assert.equal(coutDePartenaire(l[1]), "≈ 1,50 € · estimé");
  assert.equal(coutDePartenaire(l[2]), "non chiffré");   // jamais 0
  assert.equal(l[3].nom, "zero");
  assert.deepEqual(lignesPartenaires({}), []);
  assert.deepEqual(lignesPartenaires(null), []);
});

test("plan : la pièce « Partenaires » n'existe que si le relevé porte l'espace partenaire", () => {
  const services = [{id: "a", nom: "A"}, {id: "b", nom: "B"}];
  assert.ok(!creerPlan(services, COLS).pieces.some((r) => r.type === "partenaires"));
  for (let n = 1; n <= 6; n++) {
    const s = Array.from({length: n}, (_, i) => ({id: "s" + i, nom: "S" + i}));
    const p = creerPlan(s, COLS, {partenaires: true});
    const piece = p.pieces.find((r) => r.type === "partenaires");
    assert.ok(piece, `n=${n}`);
    assert.equal(piece.id, "partenaires");
    const toutes = [...p.pieces, p.openspace];
    for (let i = 0; i < toutes.length; i++) for (let j = i + 1; j < toutes.length; j++) {
      const a = toutes[i], b = toutes[j];
      assert.ok(!(Math.abs(a.x - b.x) < (a.largeur + b.largeur) / 2 - 1e-9 && Math.abs(a.z - b.z) < (a.profondeur + b.profondeur) / 2 - 1e-9),
                `n=${n} : ${a.id} chevauche ${b.id}`);
    }
    for (const r of toutes) assert.ok(Math.abs(r.x) + r.largeur / 2 <= p.batiment.largeur / 2 + 1e-9, `n=${n} ${r.id} dépasse du bâtiment`);
    assert.ok(p.meubles.some((m) => m.piece === "partenaires"));
    assert.equal(p.aService("partenaires"), false);
  }
});

test("popularité : ●●●○○ avec les signaux en info-bulle, rien si non mesurée ou mal formée", () => {
  const p = popularite({popularite: {niveau: 3, base: "Étoiles GitHub du SDK", date: "2026-11-12"}});
  assert.equal(p.texte, "●●●○○");
  assert.match(p.info, /Étoiles GitHub du SDK \(mesurée le/);
  for (const v of [null, undefined, {niveau: 0, base: "x"}, {niveau: 6, base: "x"}, {niveau: 2.5}, "beaucoup"]) {
    assert.equal(popularite({popularite: v}), null, JSON.stringify(v));
  }
  const {racine} = rendre(popDonnees());
  const carteVox = racine.tous((n) => n.className === "partenaire-carte" && /Vox/.test(n.textContent))[0];
  assert.match(carteVox.textContent, /Popularité : ●●●●○/);
  const info = carteVox.tous((n) => n.className === "partenaire-popularite")[0];
  assert.match(info.title, /Téléchargements npm/);
  const echo = racine.tous((n) => n.className === "partenaire-carte" && /Echo/.test(n.textContent))[0];
  assert.ok(!/Popularité/.test(echo.textContent));
});

const popDonnees = () => {
  const d = JSON.parse(JSON.stringify(DONNEES));
  d.categories["voix-audio"][0].popularite = {niveau: 4, base: "Téléchargements npm du SDK", date: "2026-11-12"};
  d.categories["voix-audio"].push(carte("zeta", "Zeta", "voix-audio", {popularite: {niveau: 5, base: "Notoriété", date: "2026-11-12"}}));
  return d;
};

test("tri par popularité : les plus populaires d'abord, les non mesurés à la fin dans l'ordre du catalogue", () => {
  const d = popDonnees();
  assert.deepEqual(trier(d.categories["voix-audio"], "popularite").map((c) => c.id), ["zeta", "vox", "echo"]);
  assert.deepEqual(trier(d.categories["voix-audio"], "catalogue").map((c) => c.id), ["vox", "echo", "zeta"]);
  assert.deepEqual(parties(d, "", "popularite").categories[0].cartes.map((c) => c.id), ["zeta", "vox", "echo"]);
  const {racine, vue} = rendre(d);
  const choix = racine.tous((n) => n.className === "partenaires-tri")[0];
  choix.value = "popularite";
  choix.ecouteurs.change.forEach((f) => f());
  assert.equal(vue.tri, "popularite");
  const liste = racine.tous((n) => n.className === "partenaires-liste")[0];
  assert.ok(liste.textContent.indexOf("Zeta") < liste.textContent.indexOf("Vox"));
});

test("la description s'affiche sous le nom et le filtre la trouve", () => {
  const d = JSON.parse(JSON.stringify(DONNEES));
  d.categories["voix-audio"][0].description = "Voix de synthèse très naturelles pour narrer un jeu.";
  d.categories["voix-audio"][1].description = "<b>Pas de balise</b>";
  const {racine} = rendre(d);
  const carteVox = racine.tous((n) => n.className === "partenaire-carte" && /Vox/.test(n.textContent))[0];
  const desc = carteVox.tous((n) => n.className === "partenaire-description")[0];
  assert.equal(desc.textContent, "Voix de synthèse très naturelles pour narrer un jeu.");
  assert.equal(desc.tagName, "p");
  const carteEcho = racine.tous((n) => n.className === "partenaire-carte" && /Echo/.test(n.textContent))[0];
  assert.equal(carteEcho.tous((n) => n.className === "partenaire-description")[0].textContent, "<b>Pas de balise</b>");   // textContent, jamais du HTML
  const sans = racine.tous((n) => n.className === "partenaire-carte" && /Tripo/.test(n.textContent))[0];
  assert.equal(sans.tous((n) => n.className === "partenaire-description").length, 0);
  assert.deepEqual(parties(d, "narrer").categories.map((g) => g.cartes.map((c) => c.id)), [["vox"]]);
  assert.deepEqual(parties(d, "NARRER").categories.map((g) => g.id), ["voix-audio"]);
});

test("les nouvelles catégories ont un libellé lisible", () => {
  for (const id of ["hubs-mcp", "ia-texte-code", "documents-donnees", "infrastructure", "jeu", "publication-sites", "agenda-messageries"]) {
    assert.notEqual(libelleCategorie(id), id, id);
  }
});

test("déplier une carte la redessine sur place : le reste du panneau (et son défilement) ne bouge pas", async () => {
  const {racine} = rendre();
  const titre = racine.enfants[0];
  const cartes = () => racine.tous((n) => n.className === "partenaire-carte" && n.textContent.includes("Libre"));
  const avant = cartes()[0];
  const plie = avant.tous((n) => n.tagName === "button" && n.textContent === "▸")[0];
  await plie.declencher("click");
  assert.equal(racine.enfants[0], titre, "le panneau n'est pas reconstruit");
  const apres = cartes()[0];
  assert.notEqual(apres, avant);
  assert.ok(apres.textContent.includes("Plans et prix"));
  assert.ok(apres.tous((n) => n.textContent === "▾")[0].focalise, "le bouton garde le focus : pas de rafraîchissement en dessous");
});

// --- « Inscrit » : un compte chez le partenaire, hors liaison directe.
const AVEC_COMPTE = {...DONNEES, etat: {...DONNEES.etat, inscriptions: {
  tripo: {depuis: "2026-11-12T10:00:00+01:00", note: "compte gratuit"}, vox: {depuis: "2026-11-12T10:00:00+01:00"}}}};

test("inscrit : un compte sans liaison directe ; un partenaire connecté reste connecté", () => {
  assert.equal(estInscrit(AVEC_COMPTE, "tripo"), true);
  assert.equal(estInscrit(AVEC_COMPTE, "vox"), false);          // connecté : on l'appelle directement
  assert.equal(estInscrit(AVEC_COMPTE, "echo"), false);
  assert.equal(estInscrit(DONNEES, "tripo"), false);            // état d'avant : aucune inscription
  assert.equal(estInscrit(null, "tripo"), false);
  assert.deepEqual(["vox", "tripo", "echo"].map((i) => etatPartenaire(AVEC_COMPTE, i)), ["connecte", "inscrit", "non_connecte"]);
  assert.equal(libelleEtat(AVEC_COMPTE, "tripo"), "inscrit (hors liaison directe)");
  assert.equal(libelleEtat(AVEC_COMPTE, "vox"), "connecté");
  assert.equal(libelleEtat(DONNEES, "tripo"), "déclaré, à vérifier");     // déclaré sans compte : comme avant
  assert.deepEqual(inscriptionNotee(AVEC_COMPTE, "tripo"), AVEC_COMPTE.etat.inscriptions.tripo);
  assert.equal(inscriptionNotee({etat: {inscriptions: {x: 3}}}, "x"), null);
});

test("inscrit : les parties et le tableau le rangent après les connectés, filtre « Inscrits » seulement s'il y en a", () => {
  assert.deepEqual(parties(AVEC_COMPTE).inscrits.map((c) => c.id), ["tripo"]);
  const ids = (o) => lignes(AVEC_COMPTE, o).map((l) => l.carte.id);
  assert.deepEqual(ids({}), ["vox", "tripo", "echo", "libre"]);       // connecté, inscrit, conseillé, autres
  assert.deepEqual(ids({type: "inscrits"}), ["tripo"]);
  assert.equal(lignes(AVEC_COMPTE, {})[1].inscrit, true);
  const options = (d) => rendre(d).racine.tous((n) => n.className === "partenaires-type")[0].tous((n) => n.tagName === "option").map((o) => o.textContent);
  assert.ok(options(AVEC_COMPTE).includes("Inscrits (compte, sans liaison directe) (1)"));
  assert.ok(!options(DONNEES).some((t) => /Inscrits/.test(t)));
});

test("carte inscrite : l'état, la note du compte et « Je ne suis plus inscrit »", async () => {
  const {racine, envoyes} = rendre(AVEC_COMPTE);
  const t = racine.textContent;
  assert.match(t, /inscrit \(hors liaison directe\)/);
  assert.match(t, /compte : compte gratuit/);
  const retirer = racine.tous((n) => n.tagName === "button" && n.textContent === "Je ne suis plus inscrit");
  assert.equal(retirer.length, 2);                                       // vox (connecté et inscrit) puis tripo
  await retirer[1].declencher("click");
  assert.deepEqual(envoyes, [{type: "partenaire_inscrit", partenaire: "tripo", inscrit: false}]);
});

test("« Je suis inscrit » envoie le fait, sans note ; un partenaire connecté peut aussi l'être", async () => {
  const {racine, envoyes} = rendre(AVEC_COMPTE);
  const boutons = racine.tous((n) => n.tagName === "button" && n.textContent === "Je suis inscrit");
  assert.equal(boutons.length, 2);                                      // echo et libre
  await boutons[0].declencher("click");
  assert.deepEqual(envoyes, [{type: "partenaire_inscrit", partenaire: "echo", inscrit: true}]);
  assert.match(racine.textContent, /connectéinscrit/);                  // vox : connecté ET inscrit
});

test("la note du compte : enregistrée avec l'inscription, 200 caractères au plus", async () => {
  const vue = creerVue();
  vue.ouvertes.add("tripo");
  const {racine, envoyes} = rendre(AVEC_COMPTE, vue);
  const zone = racine.tous((n) => n.attributs["aria-label"] === "Note sur mon compte")[0];
  assert.equal(zone.value, "compte gratuit");
  assert.equal(zone.attributs.maxlength, String(MAX_NOTE_INSCRIPTION));
  zone.value = "  offre Pro  ";
  await bouton(racine, "Enregistrer la note").declencher("click");
  assert.deepEqual(envoyes, [{type: "partenaire_inscrit", partenaire: "tripo", inscrit: true, note: "offre Pro"}]);
  zone.value = "x".repeat(MAX_NOTE_INSCRIPTION + 1);
  await bouton(racine, "Enregistrer la note").declencher("click");
  assert.equal(envoyes.length, 1);                                       // trop long : rien ne part
  zone.value = "";
  await bouton(racine, "Enregistrer la note").declencher("click");
  assert.deepEqual(envoyes[1], {type: "partenaire_inscrit", partenaire: "tripo", inscrit: true});   // note vidée
});

test("sans le droit d'agir, aucun bouton d'inscription ; un partenaire fermé ne propose pas de s'inscrire", () => {
  const sans = rendre(AVEC_COMPTE, creerVue({agir: false})).racine;
  assert.equal(sans.tous((n) => /inscrit/.test(n.textContent) && n.tagName === "button").length, 0);
  const ferme = {...AVEC_COMPTE, categories: {...AVEC_COMPTE.categories, "voix-audio": [carte("vox", "Vox", "voix-audio"), carte("echo", "Echo", "voix-audio", {statut: "ferme"})]}};
  assert.equal(rendre(ferme).racine.tous((n) => n.tagName === "button" && n.textContent === "Je suis inscrit").length, 1);   // libre seulement
});
