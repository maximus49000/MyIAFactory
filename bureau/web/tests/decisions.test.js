// Les décisions au bureau du Directeur, rendues sur un faux DOM : les trois issues d'une demande d'un autre genre,
// l'environnement à compléter, l'ouverture du formulaire de création.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.auteurs = {}; this.value = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
globalThis.Option = class extends Noeud { constructor(texte, valeur) { super("option"); this._texte = texte; this.value = valeur; } };

const {contenuDecisionsV4, corpsValiderEtape} = await import("../ui/decisions.js");

const GENRE = {id: "g1", genre: "genre_fonctionnalite", texte: "Ce n'est pas un jeu web.", propose: "jeu-mobile",
  genres_connus: ["jeu-web", "jeu-mobile"], incertain: true};
const ETAT = {agir: true, agents: [], fonctionnalites: [
  {id: "f1", nom: "Casse-briques", etape: "cadrage", decisions: [GENRE,
    {id: "e1", genre: "environnement", texte: "Le JDK ne s'est pas installé.", environnement: [{outil: "JDK"}, "Gradle"]}]}]};

function rendre(etat, barre) {
  const demandes = [];
  const ctx = {etat, ouvrirFonctionnalite() {},
    barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }, nouveauProjet: barre?.nouveauProjet || (() => false)}};
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctx, contenu);
  return {contenu, demandes};
}
const boutons = (c) => c.tous((n) => n.tagName === "button");
const bouton = (c, libelle) => boutons(c).find((b) => b.textContent === libelle);

test("decision genre_fonctionnalite trois issues, rendues", () => {
  const {contenu} = rendre(ETAT);
  assert.deepEqual(boutons(contenu).map((b) => b.textContent).filter((t) => ["Nouveau projet", "Dans ce projet", "C'est le même genre"].includes(t)),
    ["Nouveau projet", "Dans ce projet", "C'est le même genre"]);
  assert.match(contenu.textContent, /Genre proposé : jeu-mobile \(le moteur hésite\)/);
});

test("Dans ce projet envoie le genre choisi ; C'est le même genre n'en envoie pas", async () => {
  const {contenu, demandes} = rendre(ETAT);
  const menu = contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0];
  menu.value = "jeu-mobile";
  await bouton(contenu, "Dans ce projet").auteurs.click[0]();
  await bouton(contenu, "C'est le même genre").auteurs.click[0]();
  assert.deepEqual(demandes, [
    {type: "genre_fonctionnalite", decision: "g1", fonctionnalite: "f1", choix: "ici", genre: "jeu-mobile"},
    {type: "genre_fonctionnalite", decision: "g1", fonctionnalite: "f1", choix: "meme"}]);
});

test("Nouveau projet ouvre le formulaire avec la décision et le genre", () => {
  const ouvertures = [];
  const {contenu} = rendre(ETAT, {nouveauProjet: (o) => { ouvertures.push(o); return true; }});
  contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0].value = "jeu-mobile";
  bouton(contenu, "Nouveau projet").auteurs.click[0]();
  assert.equal(ouvertures.length, 1);
  assert.deepEqual(ouvertures[0].decision, {id: "g1", fonctionnalite: "f1", nom: "Casse-briques"});
  assert.equal(ouvertures[0].genre, "jeu-mobile");
});

test("un genre nouveau demande sa description avant l'envoi", async () => {
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [{...ETAT.fonctionnalites[0], decisions: [
    {...GENRE, propose: "appli-android", incertain: false}]}]});
  contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0].value = "appli-android";   // un vrai menu choisit le premier
  await bouton(contenu, "Dans ce projet").auteurs.click[0]();
  assert.deepEqual(demandes, []);
  assert.match(contenu.textContent, /demande une description/);
  assert.equal(bouton(contenu, "C'est le même genre"), undefined);   // le moteur n'hésitait pas
});

test("environnement : ce qui manque, « C'est fait » et « Continuer sans »", async () => {
  const {contenu, demandes} = rendre(ETAT);
  assert.match(contenu.textContent, /JDK/);
  assert.match(contenu.textContent, /Gradle/);
  await bouton(contenu, "C'est fait").auteurs.click[0]();
  await bouton(contenu, "Continuer sans").auteurs.click[0]();
  assert.deepEqual(demandes.map((d) => [d.type, d.verdict, d.fonctionnalite]), [["environnement", "fait", "f1"], ["environnement", "continuer", "f1"]]);
});

test("decision environnement de projet : sans fonctionnalite, la reponse n'en porte pas", async () => {
  const {contenu, demandes} = rendre({agir: true, agents: [], fonctionnalites: [], decisions_projet: [
    {id: "n1", genre: "environnement", texte: "Il manque encore des outils sur le poste.", environnement: [{outil: "JDK 17"}]}]});
  assert.match(contenu.textContent, /JDK 17/);
  assert.match(contenu.textContent, /Le projet/);
  await bouton(contenu, "C'est fait").auteurs.click[0]();
  await bouton(contenu, "Continuer sans").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "environnement", decision: "n1", verdict: "fait"},
                              {type: "environnement", decision: "n1", verdict: "continuer"}]);
});

const OUTIL_RICHE = {outil: "JDK 17", etat: "a_installer", pour: "livraison", autonome: true,
  objectif: "Compiler le jeu et signer l'apk à l'étape « Livraison de l'apk signé ».",
  telechargement: "https://adoptium.net/temurin/releases/",
  etapes: ["Ouvrir la page.", "Télécharger le .zip.", "L'extraire dans le profil.", "Lancer java -version."]};
const decisionDuPoste = (outils, ...reste) => ({agir: true, agents: [], fonctionnalites: [{id: "f1", nom: "Casse-briques", decisions: [
  {id: "e1", genre: "environnement", texte: "Il manque encore des outils sur le poste : JDK 17.", environnement: outils}]}],
  decisions_projet: reste});

test("environnement : par outil, l'objectif, le lien officiel, le mode opératoire et le bouton d'autonomie", async () => {
  const manuel = {outil: "Android Studio", etat: "a_installer", pour: "dev", autonome: false,
    telechargement: "https://developer.android.com/studio", etapes: ["Télécharger.", "Installer."]};
  const {contenu, demandes} = rendre(decisionDuPoste([OUTIL_RICHE, manuel]));
  const texte = contenu.textContent;
  assert.match(texte, /Compiler le jeu et signer l'apk/);                 // l'objectif en tête, concret
  assert.match(texte, /Utilisé à l'étape « dev »/);                       // repli : l'étape, sans objectif
  const liens = contenu.tous((n) => n.tagName === "a");
  assert.deepEqual(liens.map((a) => [a.href, a.target, a.rel]), [
    ["https://adoptium.net/temurin/releases/", "_blank", "noopener noreferrer"],
    ["https://developer.android.com/studio", "_blank", "noopener noreferrer"]]);
  assert.deepEqual(contenu.tous((n) => n.tagName === "ol")[0].enfants.map((li) => li.textContent),
    ["Ouvrir la page.", "Télécharger le .zip.", "L'extraire dans le profil.", "Lancer java -version."]);
  const autonomes = boutons(contenu).filter((b) => b.textContent === "Installer en autonomie");
  assert.equal(autonomes.length, 1);                                       // seulement pour l'outil autonome
  await autonomes[0].auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "installer_outil", decision: "e1", fonctionnalite: "f1", outil: "JDK 17"}]);
  assert.ok(bouton(contenu, "C'est fait") && bouton(contenu, "Continuer sans"));   // inchangés
  assert.doesNotMatch(texte, /Il manque : /);                              // plus de ligne brute collée dans une phrase
});

test("environnement : une adresse qui n'est pas https n'est jamais un lien ; un outil en cours n'a plus de bouton", () => {
  const {contenu} = rendre(decisionDuPoste([{...OUTIL_RICHE, telechargement: "javascript:alert(1)", en_cours: true}]));
  assert.equal(contenu.tous((n) => n.tagName === "a").length, 0);
  assert.equal(bouton(contenu, "Installer en autonomie"), undefined);
  assert.match(contenu.textContent, /en cours/);
  const http = rendre(decisionDuPoste([{...OUTIL_RICHE, telechargement: "http://adoptium.net/"}]));
  assert.equal(http.contenu.tous((n) => n.tagName === "a").length, 0);
});

test("environnement de projet : le bouton d'autonomie n'envoie pas de fonctionnalité ; lecture seule sans bouton", async () => {
  const etat = {agir: true, agents: [], fonctionnalites: [], decisions_projet: [
    {id: "n1", genre: "environnement", texte: "Il manque.", environnement: [OUTIL_RICHE]}]};
  const {contenu, demandes} = rendre(etat);
  await bouton(contenu, "Installer en autonomie").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "installer_outil", decision: "n1", outil: "JDK 17"}]);
  const lecture = rendre({...etat, agir: false}).contenu;
  assert.equal(boutons(lecture).length, 0);
  assert.equal(lecture.tous((n) => n.tagName === "a").length, 1);          // le lien reste lisible
});

test("environnement revérifié : trouvé / non trouvé par outil, ce qui a été cherché, l'heure, et « Forcer » confirmé", async () => {
  const trouve = {outil: "Gradle", etat: "en_place", chemin: "C:/g/gradle.exe", verification: {trouve: true, cherche: ["gradle"], introuvables: []}};
  const absent = {...OUTIL_RICHE, outil: "JDK 17", version_min: "17", verification: {trouve: false, cherche: ["java", "javac"],
    introuvables: ["java", "javac"], version_demandee: "17", version_trouvee: null}};
  const ancien = {...OUTIL_RICHE, outil: "Java 8", verification: {trouve: false, cherche: ["java"], introuvables: [],
    version_demandee: "17", version_trouvee: "java version \"1.8.0\""}};
  const etat = decisionDuPoste([trouve, absent, ancien]);
  etat.fonctionnalites[0].decisions[0].verifie_le = "2026-11-12T14:05:09+01:00";
  const {contenu, demandes} = rendre(etat);
  const texte = contenu.textContent;
  assert.match(texte, /Gradle : trouvé/);
  assert.match(texte, /JDK 17 : non trouvé/);
  assert.match(texte, /Cherché : java, javac/);
  assert.match(texte, /version 17 minimum demandée/);
  assert.match(texte, /version trouvée : java version "1.8.0"/);
  assert.match(texte, /Dernière vérification : \d\d\/\d\d\/\d{4} \d\d:\d\d/);
  const forcer = boutons(contenu).filter((b) => b.textContent === "Forcer : c'est installé");
  assert.equal(forcer.length, 2);                                        // un par outil non trouvé, pas pour celui qui est trouvé
  const questions = [];
  globalThis.confirm = (m) => { questions.push(m); return questions.length > 1; };
  await forcer[0].auteurs.click[0]();
  assert.deepEqual(demandes, []);                                        // refusé à la confirmation : rien ne part
  await forcer[0].auteurs.click[0]();
  assert.match(questions[0], /JDK 17/);
  assert.deepEqual(demandes, [{type: "environnement", decision: "e1", fonctionnalite: "f1", verdict: "forcer", outil: "JDK 17"}]);
  await bouton(contenu, "Forcer : tout est installé").auteurs.click[0]();
  assert.deepEqual(demandes[1], {type: "environnement", decision: "e1", fonctionnalite: "f1", verdict: "forcer"});
  delete globalThis.confirm;
  // jamais de bouton « Forcer » avant qu'une vérification ait dit « non trouvé », ni en lecture seule
  assert.equal(bouton(rendre(decisionDuPoste([OUTIL_RICHE])).contenu, "Forcer : c'est installé"), undefined);
  assert.equal(bouton(rendre(decisionDuPoste([OUTIL_RICHE])).contenu, "Forcer : tout est installé"), undefined);
  assert.equal(boutons(rendre({...etat, agir: false}).contenu).filter((b) => /Forcer|C'est fait|Continuer/.test(b.textContent)).length, 0);
});

test("environnement : un outil déclaré installé par le Directeur le dit", () => {
  const {contenu} = rendre(decisionDuPoste([{outil: "Gradle", etat: "en_place", declare: true}]));
  assert.match(contenu.textContent, /Gradle : déclaré installé par le Directeur \(non vérifié\)/);
});

const ELARGIR = {id: "e1", genre: "elargir_genre", texte: "Élargir la description ?", cible: "badges",
  ancienne: "Badges de chat", propose: "Badges de chat, et aussi logos de chaîne", fonctionnalite: "f1"};

test("élargir un genre : ancienne et nouvelle description pré-remplie, valider ou garder l'ancienne", async () => {
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [ELARGIR]});
  assert.match(contenu.textContent, /Description actuelle : Badges de chat/);
  const zone = contenu.tous((n) => n.tagName === "textarea")[0];
  assert.equal(zone.value, ELARGIR.propose);
  await bouton(contenu, "Valider la nouvelle description").auteurs.click[0]();
  zone.value = "Badges, emotes et logos";
  await bouton(contenu, "Valider la nouvelle description").auteurs.click[0]();
  await bouton(contenu, "Garder l'ancienne").auteurs.click[0]();
  assert.deepEqual(demandes, [
    {type: "elargir_genre", decision: "e1", verdict: "valider"},
    {type: "elargir_genre", decision: "e1", verdict: "valider", description: "Badges, emotes et logos"},
    {type: "elargir_genre", decision: "e1", verdict: "refuser"}]);
});

test("genre du projet : la phrase du genre nouveau est proposée et pré-remplie", async () => {
  const sans = {id: "p1", genre: "confirmer_genre", texte: "Genre ?", propose: "jeu-mobile", genres_connus: ["jeu-web"],
    description: "Jeux pour téléphone"};
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [sans]});
  assert.match(contenu.textContent, /Description proposée : Jeux pour téléphone/);
  const menu = contenu.tous((n) => n.tagName === "select" && n.className === "genre-choix")[0];
  menu.value = "jeu-mobile";               // un vrai menu choisit d'emblée le genre proposé
  menu.auteurs.change[0]();
  const zone = contenu.tous((n) => n.tagName === "textarea")[0];
  assert.equal(zone.value, "Jeux pour téléphone");
  await bouton(contenu, "Confirmer le genre").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "genre", decision: "p1", genre: "jeu-mobile", description: "Jeux pour téléphone"}]);
});

test("décision d'un autre genre : la phrase du genre nouveau est montrée", () => {
  const nouveau = {...GENRE, nouveau: {id: "jeu-mobile", description: "Jeux pour téléphone"}};
  const {contenu} = rendre({...ETAT, fonctionnalites: [{...ETAT.fonctionnalites[0], decisions: [nouveau]}]});
  assert.match(contenu.textContent, /Description proposée : Jeux pour téléphone/);
});

const VALIDATION = {id: "v1", genre: "valider_etape", texte: "L'élément « Accueil » attend votre validation : « Validation du Directeur ».",
  fonctionnalite: "f1", element: {id: "e1", nom: "Accueil"}, etape: "f1-valider", tache: "t4",
  compte_rendu: "Tout est vert, apk d'essai prêt.",
  fichiers: [{chemin: "pieces/f1/essai.png", titre: "Capture de l'essai"}, {chemin: "pieces/f1/jeu.apk", titre: "L'apk d'essai"}]};

test("valider_etape montre le compte rendu et les fichiers", () => {
  const {contenu} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [VALIDATION]});
  assert.match(contenu.textContent, /Élément : Accueil/);
  assert.match(contenu.textContent, /Tout est vert, apk d'essai prêt\./);
  const images = contenu.tous((n) => n.tagName === "img");
  assert.equal(images.length, 1);                                              // l'image se voit
  assert.match(images[0].src, /\/api\/image\?chemin=pieces%2Ff1%2Fessai\.png/);
  assert.match(contenu.textContent, /L'apk d'essai : pieces\/f1\/jeu\.apk/);  // l'autre fichier : titre et chemin
  assert.ok(bouton(contenu, "Valider") && bouton(contenu, "Renvoyer avec une remarque"));
});

test("renvoyer exige une remarque", async () => {
  assert.equal(corpsValiderEtape(VALIDATION, "renvoyer", "   "), null);
  assert.equal(corpsValiderEtape(VALIDATION, "renvoyer"), null);
  assert.deepEqual(corpsValiderEtape(VALIDATION, "renvoyer", " Le menu est trop chargé. "),
    {type: "valider_etape", decision: "v1", verdict: "renvoyer", texte: "Le menu est trop chargé."});
  assert.deepEqual(corpsValiderEtape(VALIDATION, "valider", "ignoré"), {type: "valider_etape", decision: "v1", verdict: "valider"});
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [VALIDATION]});
  await bouton(contenu, "Renvoyer avec une remarque").auteurs.click[0]();
  assert.deepEqual(demandes, []);                                              // sans remarque, rien ne part
  assert.match(contenu.textContent, /Dites ce qu'il faut changer/);
  contenu.tous((n) => n.tagName === "textarea")[0].value = "Le menu est trop chargé.";
  await bouton(contenu, "Renvoyer avec une remarque").auteurs.click[0]();
  await bouton(contenu, "Valider").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "valider_etape", decision: "v1", verdict: "renvoyer", texte: "Le menu est trop chargé."},
                              {type: "valider_etape", decision: "v1", verdict: "valider"}]);
});
