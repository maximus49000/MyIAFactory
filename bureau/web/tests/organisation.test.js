import test from "node:test";
import assert from "node:assert/strict";
import {libelleCout, resumeOrganisation, demandeOrganisation, rendreOrganisation} from "../ui/organisation.js";
import {decisionsDirecteur} from "../ui/actions.js";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  set innerHTML(v) { throw new Error("innerHTML interdit"); }
  append(...e) { this.enfants.push(...e); }
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
