import test from "node:test";
import assert from "node:assert/strict";
import {
  corpsInfos, verifierInfos, corpsTour, basculer, corpsCorrection, corpsProposerMaintenant, choisir, vueEchange, texteCout,
  lignesProposition, agentsFable, installationPossible, outilsAutonomes, outilsManquants, corpsValidation, suiteValidation, lignesBrouillons,
  texteAbandonnes, texteAttente, utiliseLeFormulaireActuel, envoyer, DELAI_RELECTURE_MS,
} from "../ui/echange.js";

const CHAMPS = {parent: " C:/p ", nom: " Jeu ", mots: "x, y", facturation: true, github: false, description: " Un jeu. "};

const QUESTIONS = [{id: "style", texte: "Quel style ?", choix: ["Néon", "Rétro"]}, {id: "niveaux", texte: "Combien ?", choix: []}];

const BROUILLON = {
  id: "c0123456789ab", infos: {nom: "Jeu"}, tours: 1, tours_max: 4, tour: "libre", erreur: null, proposition: null,
  cout: {tokens: 3300, euros: 0.0312},
  echange: [{auteur: "chef", message: "Quelques questions.", questions: QUESTIONS}],
};

const PROPOSITION = {
  message: "Voici le workflow.", genre: {id: "jeu-android", nouveau: true, description: "Jeux Android."},
  workflow: {id: "w-jeu-android", genre: "jeu-android", flux: [
    {id: "dev", nom: "Développement", role: "dev", service: "dev"},
    {id: "essai", nom: "Essai de l'apk", validation: true},
    {id: "livraison", nom: "Livraison", role: "livreur", service: "dev"}]},
  raisons: {dev: "Écrire le jeu.", essai: "Vous l'essayez."},
  services: [{id: "dev", nom: "Développement"}],
  agents: [{cle: "dev-1", prenom: "Noé", role: "dev", modele: "Sonnet", justification: "Il écrit du code.", fable_suggere: false},
           {cle: "livreur-1", role: "livreur", modele: "Haiku", fable_suggere: true}],
  livrable: "Un apk signé.",
  environnement: [{outil: "JDK", version_min: "17", etat: "a_installer", raison: "pour compiler", autonome: true},
                  {outil: "Node", etat: "en_place", version: "v20.1"},
                  {outil: "Java", version_min: "17", etat: "a_installer", version: "1.8"}],
  installateur: "environnement-1",
  cout: {tokens: [120000, 450000], euros: [0.4, 1.2]},
};

test("infos exige la description", () => {
  assert.match(verifierInfos({...CHAMPS, description: "  "}), /description/i);
  assert.match(verifierInfos({...CHAMPS, description: undefined}), /description/i);
  assert.match(verifierInfos({...CHAMPS, nom: ""}), /nom/i);
  assert.match(verifierInfos({...CHAMPS, parent: ""}), /dossier/);
  assert.equal(verifierInfos(CHAMPS), null);
});

test("corpsInfos : champs nettoyés, id seulement pour reprendre un brouillon", () => {
  assert.deepEqual(corpsInfos(CHAMPS, null), {parent: "C:/p", nom: "Jeu", mots_interdits: ["x", "y"], facturation: true,
    github: false, description: "Un jeu."});
  assert.equal(corpsInfos(CHAMPS, "c0123456789ab").id, "c0123456789ab");
});

test("tour exige une reponse par question", () => {
  assert.equal(corpsTour("c1", QUESTIONS, {style: "Néon"}), null);
  assert.equal(corpsTour("c1", QUESTIONS, {style: "Néon", niveaux: "   "}), null);
  assert.deepEqual(corpsTour("c1", QUESTIONS, {style: " Néon ", niveaux: "10"}),
    {id: "c1", reponses: [{question: "style", texte: "Néon"}, {question: "niveaux", texte: "10"}]});
  assert.equal(corpsTour("c1", [], {}), null);
});

const MULTI = [{id: "attentes", texte: "Qu'attends-tu du jeu ?", choix: ["Fun", "Jouabilité", "Facile"], multiple: true},
               {id: "style", texte: "Quel style ?", choix: ["Néon", "Rétro"]}];

test("basculer ajoute et retire un choix sans modifier l'objet reçu", () => {
  const a = basculer({}, "attentes", "Fun");
  assert.deepEqual(a, {attentes: ["Fun"]});
  const b = basculer(a, "attentes", "Jouabilité");
  assert.deepEqual(b, {attentes: ["Fun", "Jouabilité"]});
  assert.deepEqual(basculer(b, "attentes", "Fun"), {attentes: ["Jouabilité"]});
  assert.deepEqual(a, {attentes: ["Fun"]});
});

test("question multiple : 1 à N choix, texte libre ajouté, refus si rien", () => {
  const simple = {style: "Néon"};
  assert.equal(corpsTour("c1", MULTI, simple, {}), null);
  assert.equal(corpsTour("c1", MULTI, {...simple, attentes: "  "}, {attentes: []}), null);
  assert.deepEqual(corpsTour("c1", MULTI, simple, {attentes: ["Fun", "Jouabilité"]}),
    {id: "c1", reponses: [{question: "attentes", texte: "Fun ; Jouabilité"}, {question: "style", texte: "Néon"}]});
  assert.deepEqual(corpsTour("c1", MULTI, {...simple, attentes: " du rythme "}, {attentes: ["Fun"]}).reponses[0],
    {question: "attentes", texte: "Fun ; Autre : du rythme"});
  // le texte seul suffit (réponse libre)
  assert.deepEqual(corpsTour("c1", MULTI, {...simple, attentes: "rien de précis"}, {}).reponses[0],
    {question: "attentes", texte: "Autre : rien de précis"});
  // une question simple garde son comportement : le texte est la réponse, les choix cochés sont ignorés
  assert.equal(corpsTour("c1", MULTI, {attentes: "x"}, {style: ["Néon"]}), null);
});

test("un choix remplit la reponse", () => {
  const v = choisir({niveaux: "10"}, "style", "Néon");
  assert.deepEqual(v, {niveaux: "10", style: "Néon"});
  assert.deepEqual(choisir({}, "style", "Rétro"), {style: "Rétro"});
  const avant = {style: "Néon"};
  choisir(avant, "style", "Rétro");
  assert.deepEqual(avant, {style: "Néon"}, "l'objet reçu n'est pas modifié");
});

test("correction et proposez maintenant", () => {
  assert.deepEqual(corpsCorrection("c1", " Ajoute une validation. "), {id: "c1", correction: "Ajoute une validation."});
  assert.equal(corpsCorrection("c1", "  "), null);
  assert.deepEqual(corpsProposerMaintenant("c1"), {id: "c1", proposer_maintenant: true});
});

test("cout affiche en euros ou en tokens", () => {
  assert.equal(texteCout({tokens: 3300, euros: 0.0312}), "Coût de l'échange : 0,03 €");
  assert.equal(texteCout({tokens: 3300, euros: 0}), "Coût de l'échange : 0,00 €");
  assert.equal(texteCout({tokens: 3300, euros: 0.004}), "Coût de l'échange : moins de 0,01 €");
  assert.equal(texteCout({tokens: 12345, euros: null}), "Coût de l'échange : 12 345 tokens (prix inconnu)");
  assert.equal(texteCout(null), "");
  assert.equal(texteCout({tokens: 0, euros: null}), "");
});

test("vueEchange : messages, questions ouvertes, coût", () => {
  const v = vueEchange(BROUILLON);
  assert.deepEqual(v.questions, QUESTIONS);
  assert.equal(v.messages[0].auteur, "chef");
  assert.match(v.messages[0].texte, /Quelques questions/);
  assert.equal(v.cout, "Coût de l'échange : 0,03 €");
  assert.equal(v.enCours, false);
  assert.equal(v.erreur, null);
  // les réponses de l'utilisateur redisent la question, puis le chef répond : plus de question ouverte
  const suite = {...BROUILLON, echange: [...BROUILLON.echange,
    {auteur: "utilisateur", reponses: [{question: "style", texte: "Néon"}, {question: "niveaux", texte: "10"}]},
    {auteur: "chef", message: "Voici le workflow."}], proposition: PROPOSITION};
  const w = vueEchange(suite);
  assert.deepEqual(w.questions, []);
  assert.equal(w.messages[1].auteur, "utilisateur");
  assert.match(w.messages[1].texte, /Quel style \?/);
  assert.match(w.messages[1].texte, /Néon/);
  assert.equal(w.proposition, PROPOSITION);
  assert.equal(vueEchange({...suite, echange: [...suite.echange, {auteur: "utilisateur", correction: "Plus court."}]})
    .messages.at(-1).texte, "Plus court.");
});

test("pendant un tour, pas de question à remplir et l'attente est dite", () => {
  const v = vueEchange({...BROUILLON, tour: "en_cours"});
  assert.deepEqual(v.questions, []);
  assert.equal(v.enCours, true);
  assert.match(texteAttente(0), /réfléchit/);
  assert.match(texteAttente(12), /12 s/);
  assert.ok(DELAI_RELECTURE_MS >= 1000 && DELAI_RELECTURE_MS <= 5000);
  const interrompu = vueEchange({...BROUILLON, tour: "interrompu", erreur: "Le tour a été interrompu."});
  assert.equal(interrompu.enCours, false);
  assert.equal(interrompu.erreur, "Le tour a été interrompu.");
  assert.deepEqual(interrompu.questions.map((q) => q.id), ["style", "niveaux"]);
});

test("proposition montre les validations et les raisons", () => {
  const l = lignesProposition(PROPOSITION);
  const texte = l.join("\n");
  assert.match(l[0], /jeu-android/);
  assert.match(l[0], /nouveau/);
  assert.ok(l.some((x) => /Développement/.test(x) && /dev/.test(x) && /Développement/.test(x) && /Écrire le jeu\./.test(x)));
  assert.ok(l.some((x) => /Essai de l'apk/.test(x) && /Validation du Directeur/.test(x) && /Vous l'essayez\./.test(x)));
  assert.ok(l.some((x) => /Livraison/.test(x) && /livreur/.test(x)));
  assert.match(texte, /Noé/);
  assert.match(texte, /Un apk signé/);
  assert.match(texte, /JDK.*17/);
  assert.match(texte, /à installer/i);
  assert.match(texte, /Node.*v20\.1/);
  assert.match(texte, /0,40 à 1,20 €|0,4 à 1,2 €/);
  assert.match(texte, /120 000/);
  // prix inconnus : les tokens seuls
  const sans = lignesProposition({...PROPOSITION, cout: {tokens: [1000, 2000], euros: null}}).join("\n");
  assert.match(sans, /1 000 à 2 000 tokens/);
  // sans validation, la ligne n'apparaît pas
  const nue = lignesProposition({...PROPOSITION, workflow: {...PROPOSITION.workflow, flux: [PROPOSITION.workflow.flux[0]]}});
  assert.ok(!nue.join("\n").includes("Validation du Directeur"));
});

test("le poste dit la version lue et la version demandée", () => {
  const texte = lignesProposition(PROPOSITION).join("\n");
  assert.match(texte, /Java.*1\.8.*17/);
});

test("fable seulement si suggere", () => {
  assert.deepEqual(agentsFable(PROPOSITION).map((a) => a.cle), ["livreur-1"]);
  assert.deepEqual(agentsFable({...PROPOSITION, agents: []}), []);
  assert.deepEqual(agentsFable(null), []);
});

test("installer seulement si un outil manque et qu'un agent peut l'installer", () => {
  assert.equal(installationPossible(PROPOSITION), true);
  assert.equal(installationPossible({...PROPOSITION, installateur: null}), false);
  assert.equal(installationPossible({...PROPOSITION, environnement: [{outil: "Node", etat: "en_place"}]}), false);
  assert.equal(installationPossible(null), false);
  // la case « installer » est limitée aux outils autonomes : sans eux, rien à confier à l'agent
  assert.deepEqual(outilsAutonomes(PROPOSITION).map((x) => x.outil), ["JDK"]);
  assert.deepEqual(outilsManquants(PROPOSITION).map((x) => x.outil), ["JDK", "Java"]);
  const manuel = {...PROPOSITION, environnement: PROPOSITION.environnement.map((x) => ({...x, autonome: false}))};
  assert.equal(installationPossible(manuel), false);
  assert.deepEqual(outilsAutonomes(null), []);
});

test("corpsValidation : Fable coché, installer, description du genre nouveau", () => {
  assert.deepEqual(corpsValidation("c1", {fable: ["livreur-1"], installer: true, genreDescription: " Jeux Android. "}),
    {id: "c1", fable: ["livreur-1"], installer: true, genre_description: "Jeux Android."});
  assert.deepEqual(corpsValidation("c1", {}), {id: "c1", fable: [], installer: false});
});

test("retour infos garde l echange", () => {
  const etat = {ecran: "echange", brouillon: BROUILLON, message: ""};
  const retour = suiteValidation(etat, {ok: false, retour: "infos", message: "« Jeu » existe déjà."});
  assert.equal(retour.ecran, "infos");
  assert.equal(retour.brouillon, BROUILLON);
  assert.equal(retour.brouillon.echange.length, 1);
  assert.equal(retour.message, "« Jeu » existe déjà.");
  // un autre refus reste sur place, avec son message
  const autre = suiteValidation(etat, {ok: false, message: "Fable non suggéré."});
  assert.equal(autre.ecran, "echange");
  assert.equal(autre.message, "Fable non suggéré.");
  // le succès termine
  assert.equal(suiteValidation(etat, {ok: true, projet: "jeu"}).ecran, "fini");
});

test("envoyer rend le retour infos du serveur", async () => {
  const rep = (status, corps) => async () => ({ok: status < 400, status, json: async () => corps});
  assert.deepEqual(await envoyer("/api/creations/valider", {id: "c1"}, rep(200, {ok: true, projet: "jeu"})), {ok: true, projet: "jeu"});
  assert.deepEqual(await envoyer("/api/creations/valider", {}, rep(409, {erreur: "Existe déjà.", retour: "infos"})),
    {ok: false, status: 409, message: "Existe déjà.", retour: "infos"});
  assert.deepEqual(await envoyer("/api/creations/tour", {}, rep(409, {erreur: "Un tour est déjà en cours pour ce projet."})),
    {ok: false, status: 409, message: "Un tour est déjà en cours pour ce projet.", retour: undefined});
  assert.match((await envoyer("/x", {}, async () => { throw new Error("x"); })).message, /injoignable/);
});

test("lignes des brouillons à reprendre et coût abandonné", () => {
  const l = lignesBrouillons([
    {id: "c1", nom: "Jeu", etat: "proposition", tours: 2, tour: "libre", euros: 0.031},
    {id: "c2", nom: "", etat: "questions", tours: 0, tour: "en_cours", euros: null}]);
  assert.equal(l[0].id, "c1");
  assert.match(l[0].titre, /Jeu/);
  assert.match(l[0].detail, /proposition/);
  assert.match(l[0].detail, /0,03 €/);
  assert.match(l[1].titre, /sans nom/i);
  assert.match(l[1].detail, /en cours/);
  assert.equal(texteAbandonnes({euros: 0.12}), "Échanges abandonnés : 0,12 €");
  assert.equal(texteAbandonnes({euros: 0}), "");
  assert.equal(texteAbandonnes(null), "");
});

test("depuis une decision le formulaire actuel reste", () => {
  assert.equal(utiliseLeFormulaireActuel({decision: {id: "g1", fonctionnalite: "f1"}}), true);
  assert.equal(utiliseLeFormulaireActuel({projets: [], parents: []}), false);
  assert.equal(utiliseLeFormulaireActuel(undefined), false);
});

test("lignesProposition montre les métiers et le nombre d'agents", () => {
  const {agents, ...sansAgents} = PROPOSITION;
  const poly = {...sansAgents, metiers: [
    {role: "dev", service: "dev", modele: "Sonnet", specialite: "écrans du jeu", brief: "Écris."},
    {role: "livreur", service: "dev", brief: "Remets."}], agents: {locaux: 2, cloud: 1}};
  const texte = lignesProposition(poly).join("\n");
  assert.match(texte, /Métiers/);
  assert.match(texte, /- dev, service .*écrans du jeu/);
  assert.match(texte, /- livreur, service/);
  assert.match(texte, /Équipe : 2 agents locaux, 1 agent cloud/);
  assert.doesNotMatch(texte, /Équipe à recruter|plafond/);
  assert.match(lignesProposition({...poly, agents: {locaux: 1, cloud: 0}}).join("\n"), /Équipe : 1 agent local, 0 agent cloud/);
  // sans nombre (le projet a déjà son équipe) : les métiers seuls ; Fable ne se coche plus par agent
  assert.doesNotMatch(lignesProposition({...poly, agents: undefined}).join("\n"), /Équipe/);
  assert.deepEqual(agentsFable(poly), []);
  // l'ancien format est inchangé
  assert.match(lignesProposition(PROPOSITION).join("\n"), /Équipe à recruter/);
});
