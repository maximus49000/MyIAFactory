// Le Markdown lu dans la page : rendu sûr (aucun HTML interprété, seuls les liens http(s)), bloc repliable, lecture limitée.
import test from "node:test";
import assert from "node:assert/strict";

class Noeud {
  constructor(tag) { this.tagName = tag; this.enfants = []; this.className = ""; this._texte = ""; this.auteurs = {}; this.attributs = {}; }
  set textContent(v) { this._texte = String(v); this.enfants = []; }
  get textContent() { return this._texte + this.enfants.map((e) => e.textContent).join(""); }
  append(...e) { this.enfants.push(...e); }
  replaceChildren(...e) { this._texte = ""; this.enfants = e; }
  setAttribute(k, v) { this.attributs[k] = String(v); }
  addEventListener(nom, f) { (this.auteurs[nom] ||= []).push(f); }
  tous(pred) { return [...(pred(this) ? [this] : []), ...this.enfants.flatMap((e) => e.tous(pred))]; }
}
globalThis.document = {createElement: (t) => new Noeud(t)};

const M = await import("../ui/markdown.js");
const racine = (noeuds) => { const r = new Noeud("div"); r.append(...noeuds); return r; };
const attente = () => new Promise((r) => setTimeout(r, 0));

test("rendu : titres, listes, gras, italique, code, citation, bloc de code", () => {
  const r = racine(M.rendreMarkdown("# Titre\n\nUn **gras**, un *italique* et du `code`.\n\n- un\n- deux\n\n1. a\n2. b\n\n> cité\n\n```\nx < y\n```"));
  assert.deepEqual(r.tous((n) => /^h\d$/.test(n.tagName)).map((n) => n.textContent), ["Titre"]);
  assert.equal(r.tous((n) => n.tagName === "strong")[0].textContent, "gras");
  assert.equal(r.tous((n) => n.tagName === "em")[0].textContent, "italique");
  assert.equal(r.tous((n) => n.tagName === "code" && n.className === "md-code")[0].textContent, "code");
  assert.equal(r.tous((n) => n.tagName === "ul")[0].enfants.length, 2);
  assert.equal(r.tous((n) => n.tagName === "ol")[0].enfants.length, 2);
  assert.equal(r.tous((n) => n.tagName === "blockquote")[0].textContent, "cité");
  assert.equal(r.tous((n) => n.tagName === "pre")[0].textContent, "x < y");
});

test("sûr : le HTML brut reste du texte, un lien javascript: ou data: n'est pas un lien", () => {
  const r = racine(M.rendreMarkdown("<script>alert(1)</script> <img src=x onerror=alert(1)>\n\n"
    + "[piège](javascript:alert(1)) [autre](data:text/html,x) [relatif](/etc/passwd) [bon](https://exemple.fr/a?b=1)\n\n"
    + "# <b>gras ?</b>"));
  assert.match(r.textContent, /<script>alert\(1\)<\/script> <img src=x onerror=alert\(1\)>/);
  assert.equal(r.tous((n) => n.tagName === "script" || n.tagName === "img" || n.tagName === "b").length, 0);
  const liens = r.tous((n) => n.tagName === "a");
  assert.deepEqual(liens.map((a) => a.href), ["https://exemple.fr/a?b=1"]);
  assert.equal(liens[0].target, "_blank");
  assert.match(liens[0].rel, /noopener/);
  assert.match(r.textContent, /piège autre relatif bon/);
  assert.equal(M.lienSur("javascript:alert(1)"), null);
  assert.equal(M.lienSur("http://a.b/c"), "http://a.b/c");
});

test("aperçu : les premières lignes ; un bloc de code entamé est refermé", () => {
  const long = Array.from({length: 20}, (_, i) => `ligne ${i}`).join("\n");
  const a = M.apercu(long);
  assert.equal(a.coupe, true);
  assert.equal(a.texte.split("\n").length, M.LIGNES_APERCU);
  assert.equal(M.apercu("court").coupe, false);
  assert.match(M.apercu("```\n" + long).texte, /```$/);
});

const reponse = (corps, plus = {}) => ({ok: true, status: 200, headers: {get: () => null}, text: async () => corps, ...plus});

test("bloc : replié avec l'aperçu, « Afficher tout » / « Réduire », la flèche suit", async () => {
  M.oublierMarkdowns();
  const long = Array.from({length: 20}, (_, i) => `ligne ${i}`).join("\n\n");
  const bloc = M.blocMarkdown({titre: "Notes", adresse: "/doc/1", lire: async () => reponse(long)});
  const bascule = bloc.tous((n) => n.className === "md-bascule")[0];
  assert.match(bloc.textContent, /Chargement/);
  await attente();
  assert.equal(bascule.textContent, "▸ Notes");
  assert.match(bloc.textContent, /ligne 0/);
  assert.doesNotMatch(bloc.textContent, /ligne 19/);
  bloc.tous((n) => n.className.includes("md-tout"))[0].auteurs.click[0]();
  assert.equal(bascule.textContent, "▾ Notes");
  assert.equal(bascule.attributs["aria-expanded"], "true");
  assert.match(bloc.textContent, /ligne 19/);
  assert.equal(bloc.tous((n) => n.className.includes("md-tout"))[0].textContent, "Réduire");
  bascule.auteurs.click[0]();
  assert.doesNotMatch(bloc.textContent, /ligne 19/);
});

test("lecture : au-delà de 512 Ko ou refusée en 413 -> téléchargement seulement ; erreur non gardée", async () => {
  M.oublierMarkdowns();
  assert.deepEqual(await M.lireMarkdown("/a", async () => reponse("x".repeat(M.MAX_MARKDOWN + 1))), {trop: true});
  assert.deepEqual(await M.lireMarkdown("/b", async () => reponse("", {ok: false, status: 413})), {trop: true});
  assert.deepEqual(await M.lireMarkdown("/c", async () => reponse("", {headers: {get: () => String(M.MAX_MARKDOWN + 1)}})), {trop: true});
  assert.ok((await M.lireMarkdown("/d", async () => { throw new Error("réseau"); })).erreur);
  assert.deepEqual(await M.lireMarkdown("/d", async () => reponse("ok")), {texte: "ok"});
  const bloc = M.blocMarkdown({titre: "Gros", adresse: "/a", lire: async () => reponse("")});
  await attente();
  assert.match(bloc.textContent, /trop long/);
  assert.equal(M.estMarkdown("a/B.MD"), true);
  assert.equal(M.estMarkdown("a/b.mdx"), false);
});
