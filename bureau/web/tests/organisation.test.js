import test from "node:test";
import assert from "node:assert/strict";
import {libelleCout, resumeOrganisation, demandeOrganisation, rendreOrganisation, resumeWorkflow, agentsOrganisation,
  lignesEnvironnement} from "../ui/organisation.js";
import {decisionsDirecteur} from "../ui/actions.js";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  set innerHTML(v) { throw new Error("innerHTML interdit"); }
  append(...e) { this.enfants.push(...e); }
  setAttribute() {}
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const ETAT = {
  agir: true,
  services: [{id: "metier", nom: "Métier"}, {id: "dev", nom: "Dev"}],
  colonnes: [{id: "cadrage", nom: "Cadrage"}, {id: "dev", nom: "Développement"}, {id: "fait", nom: "Fait", terminee: true}],
};
const DECISION = {
  id: "d9", genre: "organisation", texte: "Un service son pour les bruitages",
  organisation: {
    services: [{id: "metier", nom: "Métier"}, {id: "dev", nom: "Dev"}, {id: "son", nom: "Son"}],
    flux: [{id: "dev", nom: "Développement"}, {id: "son", nom: "Sonorisation"}],
    agents: [{cle: "son-1", prenom: "Mia", role: "son", modele: "Sonnet", lieu: "local"}],
    briefs: {son: "# Brief"}, cout: {tokens: [20000, 60000], euros: null},
  },
};

test("resumeOrganisation : services ajoutés, colonnes qui changent, agents, coût", () => {
  const r = resumeOrganisation(DECISION, ETAT);
  assert.deepEqual(r.services, [{id: "son", nom: "Son"}]);
  assert.deepEqual(r.colonnes, [{id: "son", nom: "Sonorisation", etat: "ajoutée"}]);
  assert.deepEqual(r.agents.map((a) => [a.cle, a.role, a.modele, a.lieu]), [["son-1", "son", "Sonnet", "local"]]);
  assert.equal(r.cout, "20,0 k à 60,0 k tokens, prix inconnu");
});

test("resumeOrganisation : une colonne retirée ou renommée est signalée", () => {
  const d = {...DECISION, organisation: {...DECISION.organisation, flux: [{id: "dev", nom: "Code"}]}};
  const r = resumeOrganisation(d, {...ETAT, colonnes: [...ETAT.colonnes, {id: "relecture", nom: "Relecture"}]});
  assert.deepEqual(r.colonnes.map((c) => [c.id, c.etat]), [["dev", "renommée"], ["relecture", "retirée"]]);
});

test("libelleCout : euros présents, absents, tokens manquants", () => {
  assert.match(libelleCout({tokens: [1000, 2000], euros: [0.4, 1.2]}), /1,0 k à 2,0 k tokens, ≈ 0,40 € à ≈ 1,20 €/);
  assert.match(libelleCout({tokens: [1000, 2000], euros: null}), /prix inconnu$/);
  assert.match(libelleCout(null), /tokens inconnus, prix inconnu/);
});

test("decisionsDirecteur range les décisions d'organisation", () => {
  const d = decisionsDirecteur({decisions_projet: [DECISION, {id: "x", genre: "session_cloud"}]});
  assert.deepEqual(d.organisations.map((x) => x.id), ["d9"]);
  assert.equal(d.sessions.length, 1);
});

test("demandeOrganisation", () => {
  assert.deepEqual(demandeOrganisation("d9", "accepter"), {type: "organisation", decision: "d9", verdict: "accepter"});
});

test("rendreOrganisation : textes hostiles littéraux, deux boutons, rien sans agir", () => {
  const hostile = {...DECISION, texte: "<img src=x onerror=alert(1)>",
    organisation: {...DECISION.organisation, services: [{id: "son", nom: "<b>Son</b>"}]}};
  const faits = [];
  const bouton = (libelle, classe, fabrique) => { const n = new Noeud("button"); n.textContent = libelle; faits.push([libelle, fabrique()]); return n; };
  const li = rendreOrganisation({etat: ETAT}, hostile, bouton);
  assert.match(li.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.match(li.textContent, /<b>Son<\/b>/);
  assert.match(li.textContent, /prix inconnu/);
  assert.deepEqual(faits.map((f) => f[0]), ["Accepter", "Refuser"]);
  assert.equal(faits[1][1].verdict, "refuser");
  const sans = [];
  rendreOrganisation({etat: {...ETAT, agir: false}}, DECISION, (...a) => { sans.push(a); return new Noeud("button"); });
  assert.equal(sans.length, 0);
});

// --- La décision d'organisation d'un workflow de fonctionnalité (phase D).

const WORKFLOW = {
  id: "d12", genre: "organisation", texte: "Un workflow pour « Casse-briques »",
  organisation: {
    services: [{id: "metier", nom: "Métier"}, {id: "dev", nom: "Dev"}, {id: "android", nom: "Android"}],
    flux: [{id: "f2-visuels", nom: "Visuels", role: "graphiste", service: "metier"},
           {id: "f2-apk", nom: "Livraison de l'apk signé", role: "android", service: "android"}],
    agents: [
      {cle: "android-1", prenom: "Léa", role: "android", service: "android", modele: "Sonnet", lieu: "local",
       justification: "Il faut signer l'apk.", fable_suggere: true},
      {cle: "env-1", role: "environnement", service: "dev", modele: "Sonnet", lieu: "local", justification: "Installe le JDK."}],
    cout: {tokens: [100000, 300000], euros: [0.5, 1.5]}, livrable: "Un apk signé",
    workflow: {id: "w-f2", genre: "jeu-mobile", flux: [], genre_nouveau: {description: "Jeux pour mobiles"}},
    environnement: [{outil: "JDK", pour: "f2-apk", executables: ["java"], installation: "Bash(curl:*)", etat: "a_installer"},
                    {outil: "Git", pour: "f2-apk", executables: ["git"], installation: "", etat: "en_place", version: "2.45", chemin: "C:/git"}],
  },
};
const ETAT_WF = {...ETAT, colonnes: [...ETAT.colonnes, {id: "f1-dev", nom: "Développement", workflow: "w-f1", genre: "x"}]};

test("resumeOrganisation : un workflow de fonctionnalité n'enlève aucune colonne des autres", () => {
  const r = resumeOrganisation(WORKFLOW, ETAT_WF);
  assert.deepEqual(r.colonnes.map((c) => [c.id, c.etat]), [["f2-visuels", "ajoutée"], ["f2-apk", "ajoutée"]]);
  assert.deepEqual(r.services, [{id: "android", nom: "Android"}]);
});

test("resumeOrganisation : une évolution du principal ne retire pas les colonnes d'un autre workflow", () => {
  const d = {...DECISION, organisation: {...DECISION.organisation, flux: [{id: "dev", nom: "Développement"}]}};
  const etat = {...ETAT, colonnes: [{id: "cadrage", nom: "Cadrage", workflow: null}, {id: "dev", nom: "Développement", workflow: "principal"},
    {id: "f1-dev", nom: "Dev", workflow: "w-f1"}, {id: "fait", nom: "Fait", terminee: true}]};
  assert.deepEqual(resumeOrganisation(d, etat).colonnes, []);
});

test("resumeWorkflow : étapes dans l'ordre avec rôle et service, livrable, genre nouveau", () => {
  const w = resumeWorkflow(WORKFLOW, ETAT);
  assert.deepEqual(w.etapes.map((e) => [e.rang, e.nom, e.role, e.service]),
    [[1, "Visuels", "graphiste", "Métier"], [2, "Livraison de l'apk signé", "android", "Android"]]);
  assert.equal(w.livrable, "Un apk signé");
  assert.equal(w.genre, "jeu-mobile");
  assert.equal(w.genreNouveau, "Jeux pour mobiles");
  assert.equal(resumeWorkflow(DECISION, ETAT), null);
});

test("organisation montre la case Fable seulement si suggeree", () => {
  const a = agentsOrganisation(WORKFLOW);
  assert.deepEqual(a.map((x) => [x.cle, x.fableSuggere]), [["android-1", true], ["env-1", false]]);
  const faits = [];
  const bouton = (libelle, classe, fabrique) => { const n = new Noeud("button"); faits.push([libelle, fabrique]); return n; };
  const li = rendreOrganisation({etat: ETAT}, WORKFLOW, bouton);
  const cases = li.tous((n) => n.tagName === "input" && n.type === "checkbox");
  assert.equal(cases.length, 1);                                  // une seule, pour l'agent suggéré
  assert.match(li.textContent, /Léa : utiliser Fable/);
  assert.doesNotMatch(li.textContent, /env-1 : utiliser Fable/);
  // sans suggestion : aucune case
  const sans = {...WORKFLOW, organisation: {...WORKFLOW.organisation, agents: [WORKFLOW.organisation.agents[1]]}};
  assert.equal(rendreOrganisation({etat: ETAT}, sans, bouton).tous((n) => n.type === "checkbox").length, 0);
  // cocher la case envoie la clé de l'agent avec « accepter »
  cases[0].checked = true;
  assert.deepEqual(faits.find((f) => f[0] === "Accepter")[1](), {type: "organisation", decision: "d12", verdict: "accepter", fable: ["android-1"]});
  cases[0].checked = false;
  assert.deepEqual(faits.find((f) => f[0] === "Accepter")[1](), {type: "organisation", decision: "d12", verdict: "accepter"});
});

test("organisation : la justification de chaque agent et trois issues pour un workflow", () => {
  const faits = [];
  const bouton = (libelle) => { faits.push(libelle); return new Noeud("button"); };
  const li = rendreOrganisation({etat: ETAT}, WORKFLOW, bouton);
  assert.match(li.textContent, /Il faut signer l'apk\./);
  assert.match(li.textContent, /Livraison de l'apk signé \(android, Android\)/);
  assert.deepEqual(faits, ["Accepter", "Refuser", "Abandonner la demande"]);
});

test("organisation montre l environnement", () => {
  const l = lignesEnvironnement(WORKFLOW);
  assert.deepEqual(l.map((x) => [x.outil, x.enPlace, x.libelle]),
    [["JDK", false, "JDK : à installer"], ["Git", true, "Git : déjà en place"]]);
  assert.equal(l[1].detail, "2.45 · C:/git");
  const ancien = lignesEnvironnement({organisation: {environnement: [{outil: "JDK 17", etat: "a_installer", installation: "winget", raison: "version trouvée : java version \"1.8.0_351\" ; 17 minimum demandée"}]}});
  assert.match(ancien[0].detail, /1\.8\.0_351.*winget/);
  const li = rendreOrganisation({etat: ETAT}, WORKFLOW, () => new Noeud("button"));
  assert.match(li.textContent, /JDK : à installer/);
  assert.match(li.textContent, /Git : déjà en place/);
  assert.match(li.textContent, /2\.45/);
});

test("organisation montre la version demandee", () => {
  const l = lignesEnvironnement({organisation: {environnement: [
    {outil: "JDK", etat: "a_installer", installation: "winget", version: 'java version "1.8.0_351"', version_min: "17",
     raison: "version trouvée : java version \"1.8.0_351\" ; 17 minimum demandée"},
    {outil: "Gradle", etat: "en_place", version: "Gradle 8.7", version_min: "8.5", chemin: "C:/gradle"},
    {outil: "Android", etat: "a_installer", installation: "sdkmanager", version_min: "34"}]}});
  assert.equal(l[0].detail, 'version lue : java version "1.8.0_351" · version demandée : 17 · winget');
  assert.equal(l[1].detail, "version lue : Gradle 8.7 · version demandée : 8.5 · C:/gradle");
  assert.equal(l[2].detail, "version demandée : 34 · sdkmanager");
  assert.deepEqual([l[0].lue, l[0].demandee], ['java version "1.8.0_351"', "17"]);
});

test("demandeOrganisation : le texte du refus, Fable seulement avec accepter, abandonner", () => {
  assert.deepEqual(demandeOrganisation("d1", "refuser", {texte: "  plus court  "}), {type: "organisation", decision: "d1", verdict: "refuser", texte: "plus court"});
  assert.deepEqual(demandeOrganisation("d1", "refuser", {texte: "  "}), {type: "organisation", decision: "d1", verdict: "refuser"});
  assert.deepEqual(demandeOrganisation("d1", "refuser", {fable: ["a"]}), {type: "organisation", decision: "d1", verdict: "refuser"});
  assert.deepEqual(demandeOrganisation("d1", "abandonner"), {type: "organisation", decision: "d1", verdict: "abandonner"});
});

test("workflow montre l etape de validation", () => {
  const avec = {...WORKFLOW, organisation: {...WORKFLOW.organisation, flux: [
    {id: "f2-visuels", nom: "Visuels", role: "graphiste", service: "metier"},
    {id: "f2-valider", nom: "Validation du Directeur", validation: true},
    {id: "f2-apk", nom: "Livraison", role: "android", service: "android"}]}};
  const w = resumeWorkflow(avec, ETAT);
  assert.deepEqual(w.etapes.map((e) => [e.rang, e.nom, e.role, e.service, e.validation === true]),
    [[1, "Visuels", "graphiste", "Métier", false], [2, "Validation du Directeur", null, null, true],
     [3, "Livraison", "android", "Android", false]]);
  const li = rendreOrganisation({etat: ETAT}, avec, () => new Noeud("button"));
  assert.match(li.textContent, /2\. Validation du Directeur \(validation du Directeur\)/);
  assert.match(li.textContent, /1\. Visuels \(graphiste, Métier\)/);
});
