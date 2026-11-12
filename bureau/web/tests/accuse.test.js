// L'accusé de réception : « Reçu, en cours de traitement… » jusqu'à ce que le relevé montre la demande traitée, puis le
// retard dit après 3 minutes avec son motif. Rendu sur un faux DOM.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.hidden = false; this.attributs = {}; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  setAttribute(k, v) { this.attributs[k] = String(v); }
}
globalThis.document = {createElement: (t) => new Noeud(t)};
const A = await import("../ui/accuse.js");

const decision = (id, genre = "valider_etape") => ({id, genre});
const etatAvec = (decisions, discussion = []) => ({orchestrateur_present: true, decisions_projet: decisions,
  fonctionnalites: [{id: "f1", discussion, decisions: []}]});

test("une décision envoyée : « Reçu » tant qu'elle est au relevé, plus rien quand elle a disparu", () => {
  A.viderAccuses();
  const avant = etatAvec([decision("v7")]);
  const a = A.accuseDe({type: "valider_etape", decision: "v7", verdict: "valider"}, avant);
  A.noterAccuse(a, 1000);
  assert.deepEqual(A.evaluerAccuses(avant, 2000).map((x) => [x.phase, x.texte]), [["recu", A.TEXTE_RECU]]);
  assert.deepEqual(A.evaluerAccuses(etatAvec([]), 3000), []);
  assert.deepEqual(A.evaluerAccuses(avant, 4000), [], "résolu une fois : on ne le remontre plus");
});

test("le cahier : traité quand sa décision n'y est plus, ou remplacée par une nouvelle", () => {
  A.viderAccuses();
  const f = (decisions) => ({fonctionnalites: [{id: "f1", discussion: [], decisions}]});
  const avant = f([decision("c1", "valider_cahier")]);
  A.noterAccuse(A.accuseDe({type: "cahier", fonctionnalite: "f1", verdict: "valider"}, avant), 0);
  assert.equal(A.evaluerAccuses(avant, 1).length, 1);
  assert.equal(A.evaluerAccuses(f([decision("c2", "valider_cahier")]), 2).length, 0, "nouvelle décision : la demande est traitée");
});

test("un message : traité quand il entre dans la discussion", () => {
  A.viderAccuses();
  const avant = etatAvec([], [{auteur: "agent", texte: "Bonjour"}]);
  A.noterAccuse(A.accuseDe({type: "message", fonctionnalite: "f1", texte: "Salut"}, avant), 0);
  assert.equal(A.evaluerAccuses(avant, 1).length, 1);
  const apres = etatAvec([], [{auteur: "agent", texte: "Bonjour"}, {auteur: "utilisateur", texte: "Salut"}]);
  assert.equal(A.evaluerAccuses(apres, 2).length, 0);
});

test("3 minutes sans effet : « Le moteur n'a pas encore traité votre demande » avec le motif", () => {
  A.viderAccuses();
  const avant = etatAvec([decision("v1")]);
  A.noterAccuse(A.accuseDe({type: "valider_etape", decision: "v1", verdict: "valider"}, avant), 0);
  assert.equal(A.evaluerAccuses(avant, A.DELAI_TARDE_MS - 1)[0].phase, "recu");
  const arrete = {...avant, orchestrateur_present: false};
  const [x] = A.evaluerAccuses(arrete, A.DELAI_TARDE_MS);
  assert.equal(x.phase, "tarde");
  assert.match(x.texte, /^Le moteur n'a pas encore traité votre demande/);
  assert.match(x.texte, /le moteur est arrêté/);
  const pause = {...avant, pause_installation: {texte: "Pause : installation de JDK 21 (a)"}};
  assert.match(A.evaluerAccuses(pause, A.DELAI_TARDE_MS + 1)[0].texte, /en pause : installation de JDK 21/);
});

test("les gestes sans effet suivi n'ont pas d'accusé ; la sécurité efface un accusé jamais résolu", () => {
  A.viderAccuses();
  assert.equal(A.accuseDe({type: "deplacer", tache: "t1", colonne: "fait"}, {}), null);
  assert.equal(A.accuseDe(null, {}), null);
  A.noterAccuse(A.accuseDe({type: "valider_etape", decision: "v1", verdict: "valider"}, etatAvec([decision("v1")])), 0);
  assert.equal(A.evaluerAccuses(etatAvec([decision("v1")]), A.SECURITE_MS).length, 0);
});

test("le bloc : montré à l'envoi, mis à jour avec l'état brut, filtré par clé", () => {
  A.viderAccuses();
  const etat = etatAvec([decision("v9")]);
  A.majEtatAccuses(etat, 0);
  const tout = A.creerAccuses(), autre = A.creerAccuses("message:");
  assert.equal(tout.racine.hidden, true);
  A.noterAccuse(A.accuseDe({type: "valider_etape", decision: "v9", verdict: "valider"}, etat), Date.now());
  assert.equal(tout.racine.hidden, false);
  assert.match(tout.racine.textContent, /Reçu, en cours de traitement…/);
  assert.equal(autre.racine.hidden, true, "un autre endroit ne montre pas cet accusé");
  A.majEtatAccuses(etatAvec([]));
  assert.equal(tout.racine.hidden, true);
});
