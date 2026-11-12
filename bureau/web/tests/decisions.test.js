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

const {contenuDecisionsV4, corpsValiderEtape, enteteValidation} = await import("../ui/decisions.js");

const GENRE = {id: "g1", genre: "genre_fonctionnalite", texte: "Ce n'est pas un jeu web.", propose: "jeu-mobile",
  genres_connus: ["jeu-web", "jeu-mobile"], incertain: true};
const ETAT = {agir: true, agents: [], fonctionnalites: [
  {id: "f1", nom: "Casse-briques", etape: "cadrage", decisions: [GENRE,
    {id: "e1", genre: "environnement", texte: "Le JDK ne s'est pas installé.", environnement: [{outil: "JDK"}, "Gradle"]}]}]};

function rendre(etat, barre, plus = {}) {
  const demandes = [];
  const ctx = {etat, ouvrirFonctionnalite() {}, ...plus,
    barre: {demander: async (d) => { demandes.push(d); return {ok: true}; }, nouveauProjet: barre?.nouveauProjet || (() => false)}};
  const contenu = new Noeud("div");
  contenuDecisionsV4(ctx, contenu);
  return {contenu, demandes, ctx};
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

const OUTIL = {id: "o1", genre: "outil_agent", texte: "Atlas (livreur) est arrêté : il lui faut le programme « curl ».",
  agent: "livreur", tache: "t44", outil: "Bash(curl:*)", programme: "curl", commande: "curl -O https://exemple.test/x.zip"};

test("outil à ouvrir à un agent : la commande refusée, puis autoriser le programme ou refuser", async () => {
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [OUTIL]});
  assert.match(contenu.textContent, /Outils à ouvrir à un agent/);
  assert.match(contenu.textContent, /Commande refusée : curl -O https:\/\/exemple.test\/x.zip/);
  await bouton(contenu, "Autoriser ce programme pour cet agent").auteurs.click[0]();
  await bouton(contenu, "Refuser").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "outil_agent", decision: "o1", verdict: "autoriser"},
    {type: "outil_agent", decision: "o1", verdict: "refuser"}]);
});

test("outil à ouvrir : sans programme à nommer, pas d'autorisation, mais « relancer » une fois la fiche complétée", async () => {
  const sans = {...OUTIL, programme: undefined, commande: undefined, outil: "WebSearch"};
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [sans]});
  assert.equal(boutons(contenu).filter((b) => /Autoriser/.test(b.textContent)).length, 0);
  await bouton(contenu, "C'est fait, relancer").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "outil_agent", decision: "o1", verdict: "relancer"}]);
  assert.equal(boutons(rendre({...ETAT, agir: false, fonctionnalites: [], decisions_projet: [OUTIL]}).contenu).length, 0);
});

const ACCORD = {id: "a1", genre: "accord_agent", texte: "Atlas (livreur) demande votre accord, tâche « Livrer » : adb install de l'apk.",
  agent: "livreur", tache: "t9", quoi: "adb install de l'apk", partenaire: "aucun", cout: "0", pourquoi: "Tester sur le téléphone.",
  implique: "Brancher le téléphone, débogage USB.", appareil: true,
  regle: "Règle du projet : tests automatiques sur émulateur, validation de version par la fenêtre de validation."};

test("demande d'accord d'un agent : partie dédiée, règle rappelée, accepter ou refuser avec consigne facultative", async () => {
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [ACCORD]});
  assert.match(contenu.textContent, /Demandes d'accord des agents/);
  assert.match(contenu.textContent, /Pourquoi : Tester sur le téléphone/);
  assert.match(contenu.textContent, /Ce que cela implique : Brancher le téléphone/);
  assert.match(contenu.textContent, /émulateur, validation de version par la fenêtre de validation/);
  await bouton(contenu, "J'accepte").auteurs.click[0]();
  contenu.tous((n) => n.tagName === "input")[0].value = "  Utilise l'émulateur.  ";
  await bouton(contenu, "Je refuse").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "accord_agent", decision: "a1", verdict: "accepter"},
    {type: "accord_agent", decision: "a1", verdict: "refuser", texte: "Utilise l'émulateur."}]);
});

const APPAREIL = "Pas d'installation ni de test sur un appareil physique : tests automatiques sur émulateur, validation de version par la fenêtre de validation.";
const AVEC_REGLES = {...ETAT, fonctionnalites: [], regles_projet: []};

test("accord d'un appareil physique : case « Retenir comme règle du projet » cochée, texte proposé modifiable, envoyé avec la réponse", async () => {
  const accord = {...ACCORD, regle_proposee: APPAREIL};
  const {contenu, demandes} = rendre({...AVEC_REGLES, decisions_projet: [accord]});
  const [consigne, case_] = contenu.tous((n) => n.tagName === "input");
  assert.equal(case_.type, "checkbox");
  assert.equal(case_.checked, true);
  const zone = contenu.tous((n) => n.tagName === "textarea" && n.value === APPAREIL)[0];
  assert.ok(zone);
  assert.equal(zone.hidden, false);
  zone.value = "  Pas de téléphone branché.  ";
  consigne.value = "Utilise l'émulateur.";
  await bouton(contenu, "Je refuse").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "accord_agent", decision: "a1", verdict: "refuser", texte: "Utilise l'émulateur.", regle: "Pas de téléphone branché."}]);
});

test("accord sans proposition du moteur : case décochée, texte « Pas de : … », rien n'est retenu tant qu'elle n'est pas cochée", async () => {
  const {contenu, demandes} = rendre({...AVEC_REGLES, decisions_projet: [{...ACCORD, appareil: undefined}]});
  const case_ = contenu.tous((n) => n.tagName === "input" && n.type === "checkbox")[0];
  const zone = contenu.tous((n) => n.tagName === "textarea")[0];
  assert.equal(case_.checked, false);
  assert.equal(zone.hidden, true);
  assert.equal(zone.value, "Pas de : adb install de l'apk");
  await bouton(contenu, "J'accepte").auteurs.click[0]();
  case_.checked = true;
  case_.auteurs.change[0]();
  assert.equal(zone.hidden, false);
  zone.value = "   ";           // cochée mais vide : rien ne part
  await bouton(contenu, "J'accepte").auteurs.click[0]();
  zone.value = "x".repeat(501);
  await bouton(contenu, "J'accepte").auteurs.click[0]();
  zone.value = "Autorisé : adb sur l'émulateur.";
  await bouton(contenu, "J'accepte").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "accord_agent", decision: "a1", verdict: "accepter"},
    {type: "accord_agent", decision: "a1", verdict: "accepter", regle: "Autorisé : adb sur l'émulateur."}]);
});

test("accord : la règle du projet touchée est rappelée, rien n'est refusé d'office", () => {
  const touchee = {...ACCORD, regles_touchees: [{id: "r1", texte: APPAREIL}]};
  const {contenu} = rendre({...AVEC_REGLES, regles_projet: [{id: "r1", texte: APPAREIL}], decisions_projet: [touchee]});
  assert.match(contenu.textContent, /Cette demande contredit la règle du projet : Pas d'installation ni de test sur un appareil physique/);
  assert.ok(bouton(contenu, "J'accepte"));
  assert.ok(bouton(contenu, "Je refuse"));
});

test("accord avec des choix de l'agent : ses boutons remplacent J'accepte / Je refuse, avec consigne et règle", async () => {
  const accord = {...ACCORD, choix: ["Oui, je branche le téléphone", "Non, livrer sans ce test"], regles_touchees: [{id: "r1", texte: APPAREIL}]};
  const {contenu, demandes} = rendre({...AVEC_REGLES, decisions_projet: [accord]});
  assert.equal(bouton(contenu, "J'accepte"), undefined);
  assert.equal(bouton(contenu, "Je refuse"), undefined);
  assert.match(contenu.textContent, /Cette demande contredit la règle du projet/);
  contenu.tous((n) => n.tagName === "input")[0].value = "Merci.";
  const case_ = contenu.tous((n) => n.tagName === "input" && n.type === "checkbox")[0];
  case_.checked = true;
  contenu.tous((n) => n.tagName === "textarea")[0].value = "Livrer sans test sur téléphone.";
  await bouton(contenu, "Non, livrer sans ce test").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "accord_agent", decision: "a1", verdict: "choisir", choix: "Non, livrer sans ce test",
    texte: "Merci.", regle: "Livrer sans test sur téléphone."}]);
});

test("projet sans règles au relevé : ni case ni partie « Règles du projet »", () => {
  const {contenu} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [ACCORD]});
  assert.doesNotMatch(contenu.textContent, /Règles du projet/);
  assert.doesNotMatch(contenu.textContent, /Retenir comme règle/);
});

test("Règles du projet : liste, ajouter, modifier, supprimer après confirmation", async () => {
  const regles = [{id: "r1", texte: "Pas de Docker."}, {id: "r2", texte: APPAREIL, origine: {decision: "d3", agent: "livreur"}}];
  const {contenu, demandes} = rendre({...AVEC_REGLES, regles_projet: regles});
  assert.match(contenu.textContent, /Règles du projet/);
  assert.match(contenu.textContent, /Pas de Docker\./);
  // ajouter : une règle vide ou trop longue ne part pas
  const ajout = contenu.tous((n) => n.tagName === "textarea")[0];
  await bouton(contenu, "Ajouter la règle").auteurs.click[0]();
  ajout.value = "x".repeat(501);
  await bouton(contenu, "Ajouter la règle").auteurs.click[0]();
  ajout.value = "  Textes en français.  ";
  await bouton(contenu, "Ajouter la règle").auteurs.click[0]();
  // modifier : un champ s'ouvre avec le texte actuel
  contenu.tous((n) => n.tagName === "button" && n.textContent === "Modifier")[0].auteurs.click[0]();
  const edition = contenu.tous((n) => n.tagName === "textarea" && n.value === "Pas de Docker.")[0];
  edition.value = "Pas de Docker ni de WSL.";
  await bouton(contenu, "Enregistrer").auteurs.click[0]();
  // supprimer : demande confirmée, puis refusée
  const bouton_ = contenu.tous((n) => n.tagName === "button" && n.textContent === "Supprimer")[1];
  globalThis.confirm = () => false;
  await bouton_.auteurs.click[0]();
  assert.equal(demandes.length, 2);
  globalThis.confirm = () => true;
  await bouton_.auteurs.click[0]();
  delete globalThis.confirm;
  assert.deepEqual(demandes, [
    {type: "regle_projet", operation: "ajouter", texte: "Textes en français."},
    {type: "regle_projet", operation: "modifier", id: "r1", texte: "Pas de Docker ni de WSL."},
    {type: "regle_projet", operation: "supprimer", id: "r2"}]);
});

test("Règles du projet en lecture seule : aucune saisie ni bouton", () => {
  const {contenu} = rendre({...AVEC_REGLES, agir: false, regles_projet: [{id: "r1", texte: "Pas de Docker."}]});
  assert.match(contenu.textContent, /Pas de Docker/);
  assert.equal(boutons(contenu).length, 0);
  assert.equal(contenu.tous((n) => n.tagName === "textarea").length, 0);
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

const SESSION = {id: "s1", genre: "session_cloud", agent: "dev-1", tache: "t7", modele: "Sonnet",
  texte: "Le moteur n'a pas pu lancer la session cloud de Lucas : terminal. Créez-la vous-même.",
  lien: "https://claude.ai/code", depot: "https://github.com/moi/jeu",
  depart: "Tu repars de zéro.\nÉcris ton rapport dans .factory/rapports/t7.json."};

test("session cloud à créer à la main : lien, dépôt, message à copier, adresse à coller, « C'est fait »", async () => {
  const {contenu, demandes} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [SESSION]});
  const liens = contenu.tous((n) => n.tagName === "a");
  assert.deepEqual(liens.map((a) => [a.href, a.target, a.rel]), [
    ["https://claude.ai/code", "_blank", "noopener noreferrer"], ["https://github.com/moi/jeu", "_blank", "noopener noreferrer"]]);
  assert.match(contenu.textContent, /Modèle : Sonnet/);
  const message = contenu.tous((n) => n.tagName === "textarea")[0];
  assert.equal(message.value, SESSION.depart);
  assert.equal(message.readOnly, true);
  const copies = [];
  const avant = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", {configurable: true,
    value: {clipboard: {writeText: async (t) => { copies.push(t); }}}});
  const copier = bouton(contenu, "Copier le message");
  try {
    await copier.auteurs.click[0]();
  } finally {
    if (avant) Object.defineProperty(globalThis, "navigator", avant); else delete globalThis.navigator;
  }
  assert.deepEqual(copies, [SESSION.depart]);
  assert.equal(copier.textContent, "Copié");
  const champ = contenu.tous((n) => n.tagName === "input")[0];
  champ.value = "Ma session";                                       // ni une adresse ni un identifiant
  await bouton(contenu, "C'est fait").auteurs.click[0]();
  assert.deepEqual(demandes, []);
  assert.match(contenu.textContent, /claude\.ai\/code/);
  champ.value = " https://claude.ai/code/session_01AbC ";
  await bouton(contenu, "C'est fait").auteurs.click[0]();
  assert.deepEqual(demandes, [{type: "session_cloud", decision: "s1", session: "https://claude.ai/code/session_01AbC"}]);
});

test("session cloud : une adresse qui n'est pas https n'est pas un lien ; la forme d'avant garde son champ de nom", async () => {
  const {contenu} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [{...SESSION, lien: "javascript:x", depot: "http://x"}]});
  assert.equal(contenu.tous((n) => n.tagName === "a").length, 0);
  const avant = rendre({...ETAT, fonctionnalites: [], decisions_projet: [{id: "s0", genre: "session_cloud", agent: "dev-1", texte: "T"}]});
  avant.contenu.tous((n) => n.tagName === "input")[0].value = "Ma session";
  await bouton(avant.contenu, "C'est fait").auteurs.click[0]();
  assert.deepEqual(avant.demandes, [{type: "session_cloud", decision: "s0", session: "Ma session"}]);
  assert.equal(avant.contenu.tous((n) => n.tagName === "textarea").length, 0);
});

const VALIDATION = {id: "v1", genre: "valider_etape", texte: "L'élément « Accueil » attend votre validation : « Validation du Directeur ».",
  fonctionnalite: "f1", element: {id: "e1", nom: "Accueil"}, etape: "f1-valider", tache: "t4",
  compte_rendu: "Tout est vert, apk d'essai prêt.",
  fichiers: [{chemin: "pieces/f1/essai.png", titre: "Capture de l'essai"}, {chemin: "pieces/f1/jeu.apk", titre: "L'apk d'essai"}]};

test("valider_etape : au bureau, le résumé et « Ouvrir la validation » seulement", () => {
  const ouvertes = [];
  const {contenu, demandes, ctx} = rendre({...ETAT, fonctionnalites: [], decisions_projet: [VALIDATION]}, null,
    {ouvrirValidation: (c, d, b) => ouvertes.push([c, d, b])});
  assert.match(contenu.textContent, /Élément : Accueil/);
  assert.match(contenu.textContent, /1 livrable · 1 image · 1 point à vérifier/);
  assert.doesNotMatch(contenu.textContent, /Tout est vert/);                   // le compte rendu est dans la fenêtre
  assert.equal(contenu.tous((n) => n.tagName === "img").length, 0);
  assert.equal(bouton(contenu, "Valider"), undefined);                         // plus de validation hors de la fenêtre
  assert.equal(bouton(contenu, "Renvoyer avec une remarque"), undefined);
  const b = bouton(contenu, "Ouvrir la validation");
  b.auteurs.click[0]();
  assert.deepEqual(ouvertes, [[ctx, VALIDATION, b]]);
  assert.deepEqual(demandes, []);
});

test("valider_etape envoyée : retirée de la liste (plus d'« Envoyée »), même si l'état servi la contient encore", async () => {
  const V = await import("../ui/validation.js");
  const etat = {...ETAT, fonctionnalites: [], decisions_projet: [{...VALIDATION, id: "v-envoyee"}]};
  assert.ok(bouton(rendre(etat).contenu, "Ouvrir la validation"));
  V.marquerEnvoyee("v-envoyee");
  const apres = rendre(etat).contenu;                                         // état servi rafraîchi : toujours masquée
  assert.equal(bouton(apres, "Ouvrir la validation"), undefined);
  assert.doesNotMatch(apres.textContent, /Envoyée|Accueil/);
  assert.match(apres.textContent, /Aucun élément n'attend votre validation/);
  V.oublierEnvoyee("v-envoyee");
  assert.ok(bouton(rendre(etat).contenu, "Ouvrir la validation"));            // l'envoi a échoué : elle revient
});

test("valider_etape rappelle l'objectif et ce qu'il y a à valider, avant le compte rendu", () => {
  const d = {...VALIDATION, objectif: "L'écran d'accueil, avec le logo et le bouton Jouer.",
             a_valider: "Validation de la direction artistique — le style avant de faire le jeu"};
  assert.deepEqual(enteteValidation(d), [
    {libelle: "Objectif", texte: "L'écran d'accueil, avec le logo et le bouton Jouer."},
    {libelle: "À valider", texte: "Validation de la direction artistique — le style avant de faire le jeu"}]);
  assert.deepEqual(enteteValidation(VALIDATION), []);                            // une décision d'avant : rien
  const texte = rendre({...ETAT, fonctionnalites: [], decisions_projet: [d]}).contenu.textContent;
  const [o, v, b] = ["Objectif : L'écran", "À valider : Validation de la direction", "Ouvrir la validation"]
    .map((x) => texte.indexOf(x));
  assert.ok(o >= 0 && o < v && v < b, texte);
});

test("la forme d'avant (sans réponses par point) : renvoyer exige une remarque", () => {
  assert.equal(corpsValiderEtape(VALIDATION, "renvoyer", "   "), null);
  assert.equal(corpsValiderEtape(VALIDATION, "renvoyer"), null);
  assert.deepEqual(corpsValiderEtape(VALIDATION, "renvoyer", " Le menu est trop chargé. "),
    {type: "valider_etape", decision: "v1", verdict: "renvoyer", texte: "Le menu est trop chargé."});
  assert.deepEqual(corpsValiderEtape(VALIDATION, "valider", "ignoré"), {type: "valider_etape", decision: "v1", verdict: "valider"});
});
