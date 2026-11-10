import test from "node:test";
import assert from "node:assert/strict";
import {ETAPES_PARCOURS, bandeau, demandeNouvelle, demandeMessage, demandeCahier, demandeMethode,
        verifierPieces, lireImage, ecrit, nouvelleApparue} from "../ui/fonctionnalite.js";

const Mo = 1024 * 1024;
const png = (nom = "a.png", size = 100) => ({name: nom, type: "image/png", size});

test("bandeau : prototype et terminee", () => {
  assert.equal(ETAPES_PARCOURS.length, 6);
  const b = bandeau("prototype");
  assert.deepEqual(b.map((x) => x.libelle), ["Cadrage", "Cahier des charges", "Découpage", "Prototype", "Méthode", "Série"]);
  assert.deepEqual(b.map((x) => x.faite), [true, true, true, false, false, false]);
  assert.deepEqual(b.map((x) => x.courante), [false, false, false, true, false, false]);
  assert.ok(bandeau("terminee").every((x) => x.faite && !x.courante));
  assert.ok(bandeau("inconnue").every((x) => !x.faite && !x.courante));
});

test("formes exactes des quatre demandes", () => {
  const img = [{nom: "a.png", type: "image/png", donnees: "AAAA"}];
  assert.deepEqual(demandeNouvelle("Une idée", []), {type: "fonctionnalite", texte: "Une idée"});
  assert.deepEqual(demandeNouvelle("Une idée", img), {type: "fonctionnalite", texte: "Une idée", images: img});
  assert.deepEqual(demandeMessage("f1", "Salut", undefined), {type: "message", fonctionnalite: "f1", texte: "Salut"});
  assert.deepEqual(demandeMessage("f1", "Salut", img), {type: "message", fonctionnalite: "f1", texte: "Salut", images: img});
  assert.deepEqual(demandeCahier("f1", "valider"), {type: "cahier", fonctionnalite: "f1", verdict: "valider"});
  assert.deepEqual(demandeCahier("f1", "corriger", "Plus court"), {type: "cahier", fonctionnalite: "f1", verdict: "corriger", texte: "Plus court"});
  assert.deepEqual(demandeCahier("f1", "valider", "  "), {type: "cahier", fonctionnalite: "f1", verdict: "valider"});
  assert.deepEqual(demandeMethode("f1", "revoir", "Autre angle"), {type: "methode", fonctionnalite: "f1", verdict: "revoir", texte: "Autre angle"});
  assert.deepEqual(demandeMethode("f1", "garder"), {type: "methode", fonctionnalite: "f1", verdict: "garder"});
});

test("verifierPieces : 5 fichiers, 6 Mo, .gif", () => {
  assert.equal(verifierPieces([png()]), null);
  assert.equal(verifierPieces([]), null);
  assert.match(verifierPieces([png("1.png"), png("2.png"), png("3.png"), png("4.png"), png("5.png")]), /4 images/);
  assert.match(verifierPieces([png("gros.png", 6 * Mo)]), /5 Mo/);
  assert.equal(verifierPieces([png("ok.png", 5 * Mo)]), null);
  assert.match(verifierPieces([{name: "a.gif", type: "image/gif", size: 10}]), /PNG ou JPEG/);
  assert.match(verifierPieces([{name: "a.png", type: "image/gif", size: 10}]), /PNG ou JPEG/);
  assert.match(verifierPieces([{name: "a.jpg", type: "image/png", size: 10}]), /ne correspond pas/);
  assert.equal(verifierPieces([{name: "A.JPEG", type: "image/jpeg", size: 10}]), null);
  assert.match(verifierPieces([png("x:y.png")]), /nom/);
});

test("lireImage rend nom, type et base64", async () => {
  const fichier = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], {type: "image/png"});
  fichier.name = "a.png";
  assert.deepEqual(await lireImage(fichier), {nom: "a.png", type: "image/png", donnees: "iVBORw=="});
});

test("ecrit : trois cas", () => {
  const etat = {agents: [{id: "marie", prenom: "Marie"}], orchestrateur_actif: true};
  const f = {id: "f1", agent_cadrage: "marie", attend_reponse: true};
  assert.equal(ecrit(f, etat), "Marie est en train d'écrire…");
  assert.equal(ecrit(f, {...etat, orchestrateur_actif: false}), "En attente de l'orchestrateur");
  assert.equal(ecrit({...f, attend_reponse: false}, etat), null);
  assert.equal(ecrit({...f, agent_cadrage: null}, etat), "L'agent de cadrage est en train d'écrire…");
  assert.equal(ecrit(null, etat), null);
});

test("ecrit : celui qui travaille sur la fonctionnalité, pas toujours l'agent de cadrage", () => {
  const agents = [{id: "camille", prenom: "Camille"}, {id: "noe", prenom: "Noé"}, {id: "lou", prenom: "Lou"}];
  const f = {id: "f1", agent_cadrage: "camille", attend_reponse: true,
             discussion: [{auteur: "camille"}, {auteur: "utilisateur"}]};
  const t = (agent, maj, extra = {}) => ({id: agent, agent, fonctionnalite: "f1", active: true, maj, ...extra});
  // Une tâche active sur la fonctionnalité : son agent (la plus récente s'il y en a plusieurs).
  const e = {agents, orchestrateur_actif: true,
             taches: [t("noe", "2026-11-10T21:00:00"), t("lou", "2026-11-10T22:00:00"),
                      t("camille", "2026-11-10T23:00:00", {fonctionnalite: "f2"}),
                      t("camille", "2026-11-10T23:30:00", {active: false})]};
  assert.equal(ecrit(f, e), "Lou est en train d'écrire…");
  // Aucune tâche active : le dernier agent qui a parlé dans la discussion.
  const f2 = {...f, discussion: [{auteur: "camille"}, {auteur: "noe"}, {auteur: "utilisateur"}]};
  assert.equal(ecrit(f2, {agents, orchestrateur_actif: true, taches: []}), "Noé est en train d'écrire…");
  // Personne d'autre : l'agent de cadrage.
  assert.equal(ecrit({...f, discussion: []}, {agents, orchestrateur_actif: true}), "Camille est en train d'écrire…");
});

test("nouvelleApparue", () => {
  const avant = {fonctionnalites: [{id: "f1", discussion: [{texte: "Ancien"}]}]};
  const apres = {fonctionnalites: [{id: "f1", discussion: [{texte: "Ancien"}]},
                                   {id: "f2", discussion: [{auteur: "utilisateur", texte: "Mon idée"}]}]};
  assert.equal(nouvelleApparue(avant, apres, "Mon idée"), "f2");
  assert.equal(nouvelleApparue(avant, apres, "Autre"), null);
  assert.equal(nouvelleApparue(apres, apres, "Mon idée"), null);
  assert.equal(nouvelleApparue({}, apres, "Mon idée"), "f2");
  assert.equal(nouvelleApparue(avant, {}, "Mon idée"), null);
});

test("presentation : la discussion se replie quand le cahier attend son verdict", async () => {
  const {presentation} = await import("../ui/fonctionnalite.js");
  const cahier = {id: "f1", decisions: [{id: "d1", genre: "valider_cahier", texte: "T"}]};
  const sans = {id: "f1", decisions: []};
  assert.deepEqual(presentation(cahier, true, false), {discussionOuverte: false, envoiCorrection: false});
  assert.deepEqual(presentation(cahier, true, true), {discussionOuverte: true, envoiCorrection: true});
  assert.deepEqual(presentation(sans, true, true), {discussionOuverte: true, envoiCorrection: false});
  assert.deepEqual(presentation(cahier, false, false), {discussionOuverte: true, envoiCorrection: false});  // sans agir
  assert.deepEqual(presentation(null, true, false), {discussionOuverte: true, envoiCorrection: false});    // nouvelle
});

test("voisine : navigation circulaire entre les images d'un message", async () => {
  const {voisine} = await import("../ui/fonctionnalite.js");
  assert.equal(voisine(3, 0, 1), 1);
  assert.equal(voisine(3, 2, 1), 0);     // après la dernière : la première
  assert.equal(voisine(3, 0, -1), 2);    // avant la première : la dernière
  assert.equal(voisine(1, 0, 1), 0);
  assert.equal(voisine(0, 0, 1), 0);
});

test("documentsParEtape : rangés par étape (parcours puis colonnes), les plus récents d'abord", async () => {
  const {documentsParEtape} = await import("../ui/fonctionnalite.js");
  const f = {documents: [
    {chemin: "pieces/a.png", titre: "a.png", etape: "cadrage", date: "2026-11-10T10:00:00+01:00"},
    {chemin: "captures/e1.png", titre: "e1", etape: "dev", date: "2026-11-10T12:00:00+01:00"},
    {chemin: "pieces/m.png", titre: "Maquette", etape: "cahier", date: "2026-11-10T11:00:00+01:00"},
    {chemin: "pieces/b.png", titre: "b.png", etape: "cadrage", date: "2026-11-10T10:30:00+01:00"},
    {chemin: "notes.md", titre: "Notes"}]};
  const g = documentsParEtape(f, [{id: "dev", nom: "Développement"}]);
  assert.deepEqual(g.map((x) => x.libelle), ["Cadrage", "Cahier des charges", "Développement", "Autres"]);
  assert.deepEqual(g[0].documents.map((d) => d.chemin), ["pieces/b.png", "pieces/a.png"]);
  assert.equal(g[3].documents[0].titre, "Notes");
  assert.deepEqual(documentsParEtape({}, []), []);
});

test("echelle : tokens et lignes produites à côté du prix", async () => {
  const {echelle} = await import("../ui/fonctionnalite.js");
  assert.equal(echelle({tokens: 850, lignes: 85}), "850 tokens · 85 lignes");
  assert.equal(echelle({tokens: 120400, lignes: 1}), "120 k tokens · 1 ligne");
  assert.equal(echelle({tokens: 1234567, lignes: null}), "1,2 M tokens");
  assert.equal(echelle({tokens: 0}), "");
});

test("reponseComposee : les choix deviennent un message lisible ; passer demande une explication", async () => {
  const {reponseComposee, questionsEnAttente} = await import("../ui/fonctionnalite.js");
  const q = [{texte: "Quelle taille ?", choix: ["28 px", "56 px"]},
             {texte: "Quels fonds ?", choix: ["Clair", "Sombre"], multiple: true}];
  assert.deepEqual(reponseComposee(q, {0: {choix: ["56 px"]}, 1: {choix: ["Clair", "Sombre"]}}, "  "),
                   {texte: "Quelle taille ? → 56 px\nQuels fonds ? → Clair, Sombre"});
  assert.deepEqual(reponseComposee(q, {0: {choix: ["28 px"]}, 1: {passee: true}}, "Je ne sais pas encore."),
                   {texte: "Quelle taille ? → 28 px\nQuels fonds ? → (passée)\n\nJe ne sais pas encore."});
  assert.match(reponseComposee(q, {0: {choix: ["28 px"]}, 1: {passee: true}}, "").erreur, /pourquoi/);
  assert.match(reponseComposee(q, {0: {choix: ["28 px"]}}, "").erreur, /Quels fonds/);   // sans réponse
  assert.deepEqual(reponseComposee([], {}, "Bonjour"), {texte: "Bonjour"});
  assert.match(reponseComposee([], {}, " ").erreur, /message/);
  // Les questions ne s'affichent que sur le dernier message, s'il est d'un agent.
  const f = {discussion: [{id: "m1", auteur: "a", questions: q}, {id: "m2", auteur: "utilisateur"}]};
  assert.equal(questionsEnAttente(f), null);
  assert.deepEqual(questionsEnAttente({discussion: [{id: "m1", auteur: "a", questions: q}]}), {message: "m1", questions: q});
  assert.equal(questionsEnAttente({discussion: [{id: "m1", auteur: "a"}]}), null);
});

test("reponseComposee : « Autre » et sa valeur libre", async () => {
  const {reponseComposee} = await import("../ui/fonctionnalite.js");
  const q = [{texte: "Quelle taille ?", choix: ["28 px", "56 px"]},
             {texte: "Quels fonds ?", choix: ["Clair", "Sombre"], multiple: true}];
  assert.deepEqual(reponseComposee(q, {0: {choix: [], autre: "40 px"}, 1: {choix: ["Clair"], autre: "Transparent"}}, ""),
                   {texte: "Quelle taille ? → Autre : 40 px\nQuels fonds ? → Clair, Autre : Transparent"});
  // « Autre » ouvert mais vide : il faut le préciser.
  assert.match(reponseComposee(q, {0: {choix: [], autre: "  "}, 1: {choix: ["Clair"]}}, "").erreur, /Autre/);
});

test("decouperTermes : les mots du glossaire, sans casse ni accents, mots entiers, le plus long d'abord", async () => {
  const {decouperTermes, glossaireDe} = await import("../ui/fonctionnalite.js");
  const g = [{mot: "tesselle", definition: "Petit cube de mosaïque."},
             {mot: "or byzantin", definition: "Fond doré des mosaïques."},
             {mot: "or", definition: "Métal jaune."}];
  assert.deepEqual(decouperTermes("Des Tesselles sur fond d'OR BYZANTIN, et de l'or.", g), [
    {texte: "Des "}, {texte: "Tesselles", definition: "Petit cube de mosaïque."}, {texte: " sur fond d'"},
    {texte: "OR BYZANTIN", definition: "Fond doré des mosaïques."}, {texte: ", et de l'"},
    {texte: "or", definition: "Métal jaune."}, {texte: "."}]);
  assert.deepEqual(decouperTermes("La tessellation dorée", g), [{texte: "La tessellation dorée"}]);   // pas dans un mot
  assert.deepEqual(decouperTermes("Une tésselle", g), [{texte: "Une "}, {texte: "tésselle", definition: "Petit cube de mosaïque."}]);
  assert.deepEqual(decouperTermes("Rien", []), [{texte: "Rien"}]);
  assert.deepEqual(decouperTermes("<b>tesselle</b>", g),
    [{texte: "<b>"}, {texte: "tesselle", definition: "Petit cube de mosaïque."}, {texte: "</b>"}]);   // texte brut
  // Le glossaire d'une fonctionnalité : tous ses messages ; la dernière définition d'un mot l'emporte.
  const f = {discussion: [{glossaire: [{mot: "Tesselle", definition: "A"}]}, {}, {glossaire: [{mot: "tesselle", definition: "B"}, {mot: "Smalt", definition: "C"}]}]};
  assert.deepEqual(glossaireDe(f), [{mot: "tesselle", definition: "B"}, {mot: "Smalt", definition: "C"}]);
});

test("livrablesParElement et demandeRetourLivrable", async () => {
  const {livrablesParElement, demandeRetourLivrable} = await import("../ui/fonctionnalite.js");
  const f = {id: "f1", documents: [
    {chemin: "a.png", titre: "Pape 28", element: "pape", livrable: true, date: "2026-11-10T22:00:00+01:00"},
    {chemin: "b.png", titre: "Pape 112", element: "pape", livrable: true, date: "2026-11-10T22:05:00+01:00"},
    {chemin: "c.png", titre: "Roi", element: "roi", livrable: true, date: "2026-11-10T23:00:00+01:00"},
    {chemin: "brouillon.png", titre: "Essai", element: "roi"},                         // pas un livrable
    {chemin: "d.md", titre: "Sans élément", livrable: true, date: "2026-11-10T21:00:00+01:00"}]};
  const g = livrablesParElement(f);
  assert.deepEqual(g.map((x) => x.element), ["roi", "pape", null]);
  assert.deepEqual(g[1].documents.map((d) => d.chemin), ["b.png", "a.png"]);
  assert.deepEqual(livrablesParElement({}), []);
  assert.deepEqual(demandeRetourLivrable({id: "f1", catalogue: true}, "roi", "La couronne est trop petite."),
    {type: "retour_element", fonctionnalite: "f1", element: "roi", texte: "La couronne est trop petite."});
  assert.deepEqual(demandeRetourLivrable({id: "f1", catalogue: false}, "roi", "Trop petit."),
    {type: "message", fonctionnalite: "f1", texte: "Retour sur le livrable de « roi » : Trop petit."});
});

test("versionsDe : la dernière version d'abord, l'historique derrière", async () => {
  const {versionsDe} = await import("../ui/fonctionnalite.js");
  const docs = [
    {chemin: "p/v1.png", titre: "Pape 112", element: "pape", date: "2026-11-10T20:00:00+01:00"},
    {chemin: "p/v3.png", titre: "Pape 112 (tour 3)", element: "pape", remplace: "p/v2.png", date: "2026-11-10T22:00:00+01:00"},
    {chemin: "p/v2.png", titre: "Pape 112", element: "pape", date: "2026-11-10T21:00:00+01:00"},   // même titre et élément
    {chemin: "m/planche.svg", titre: "Maquette", date: "2026-11-10T19:00:00+01:00"},
    {chemin: "m/planche.png", titre: "Maquette", date: "2026-11-10T23:00:00+01:00"},             // même titre, sans élément
    {chemin: "roi.png", titre: "Pape 112", element: "roi", date: "2026-11-10T22:30:00+01:00"}];  // autre élément
  const v = versionsDe(docs);
  assert.deepEqual(v.map((x) => x.dernier.chemin), ["m/planche.png", "roi.png", "p/v3.png"]);
  assert.deepEqual(v[2].anciens.map((d) => d.chemin), ["p/v2.png", "p/v1.png"]);
  assert.deepEqual(v[0].anciens.map((d) => d.chemin), ["m/planche.svg"]);
  assert.deepEqual(v[1].anciens, []);
  assert.deepEqual(versionsDe([]), []);
});

test("tachesDeFonctionnalite : réalisées et à venir (la file de la fonctionnalité comprise)", async () => {
  const {tachesDeFonctionnalite} = await import("../ui/fonctionnalite.js");
  const etat = {
    colonnes: [{id: "dev", nom: "Développement"}, {id: "fait", nom: "Fait", terminee: true}],
    agents: [{id: "dev-1", prenom: "Noé"}],
    taches: [{id: "t1", titre: "Dev : Pape", colonne: "fait", fonctionnalite: "f1", agent: "dev-1", maj: "2026-11-10T20:00:00"},
             {id: "t2", titre: "Correction", colonne: "dev", fonctionnalite: "f1", agent: "dev-1", maj: "2026-11-10T23:00:00", active: true},
             {id: "t3", titre: "Relecture", colonne: "fait", fonctionnalite: "f1", maj: "2026-11-10T22:00:00"},
             {id: "t4", titre: "Autre", colonne: "dev", fonctionnalite: "f2"},
             {id: "orchestration", titre: "Orchestration", colonne: "dev", postit: false}],
    file: {visibles: [{id: "f1/roi", titre: "Roi"}, {id: "f2/x", titre: "X"}], suite: [{id: "f1/reine", titre: "Reine"}]}};
  const r = tachesDeFonctionnalite(etat, {id: "f1"});
  assert.deepEqual(r.realisees.map((t) => t.id), ["t3", "t1"]);                 // les plus récentes d'abord
  assert.deepEqual(r.aVenir.map((t) => t.id), ["t2", "f1/roi", "f1/reine"]);    // en cours, puis la file dans l'ordre
  assert.equal(r.aVenir[0].prenom, "Noé");
  assert.equal(r.aVenir[0].colonne, "Développement");
  assert.equal(r.aVenir[1].file, true);
  assert.deepEqual(tachesDeFonctionnalite({}, {id: "f1"}), {realisees: [], aVenir: []});
  // Une tâche finie restée dans sa colonne (inactive) compte comme réalisée.
  const e2 = {...etat, taches: [...etat.taches, {id: "t5", titre: "Ancienne correction", colonne: "dev", fonctionnalite: "f1",
                                                 active: false, maj: "2026-11-10T21:00:00"}]};
  assert.ok(tachesDeFonctionnalite(e2, {id: "f1"}).realisees.some((t) => t.id === "t5"));
});

test("texteACopier : tout le contenu d'un message", async () => {
  const {texteACopier} = await import("../ui/fonctionnalite.js");
  assert.equal(texteACopier({texte: "Bonjour"}), "Bonjour");
  assert.equal(texteACopier({texte: "Voici", images: ["pieces/a.png", "pieces/b.png"]}),
               "Voici\n\nImages :\n- pieces/a.png\n- pieces/b.png");
  assert.equal(texteACopier({texte: "Choisissez", questions: [{texte: "Taille ?", choix: ["28", "56"]}]}),
               "Choisissez\n\nTaille ? (28 / 56)");
});
