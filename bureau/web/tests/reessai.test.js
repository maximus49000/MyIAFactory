import test from "node:test";
import assert from "node:assert/strict";
import {reessayerImage, adresseDeBase, adresseDEssai, DELAIS_REESSAI_MS} from "../ui/reessai.js";

function fausseImage(src) {
  const ecouteurs = [];
  return {src, addEventListener: (nom, f) => { if (nom === "error") ecouteurs.push(f); }, echec: () => ecouteurs.forEach((f) => f())};
}
function minuterie() {
  const taches = [];
  return {taches, planifier: (f, ms) => taches.push({f, ms}), lancer: () => taches.shift().f()};
}

test("les délais sont 2 s, 5 s, 10 s", () => {
  assert.deepEqual(DELAIS_REESSAI_MS, [2000, 5000, 10000]);
});

test("trois essais avec paramètre anti-cache, puis l'image reste cassée", () => {
  const img = fausseImage("/api/image?chemin=a.png&t=1");
  const m = minuterie();
  let echecs = 0;
  reessayerImage(img, {planifier: m.planifier, apresEchec: () => { echecs += 1; }});
  img.echec();
  assert.deepEqual(m.taches.map((t) => t.ms), [2000]);
  m.lancer();
  assert.equal(img.src, "/api/image?chemin=a.png&t=1&r=1");
  img.echec();
  assert.equal(m.taches[0].ms, 5000);
  m.lancer();
  assert.equal(img.src, "/api/image?chemin=a.png&t=1&r=2");
  img.echec();
  assert.equal(m.taches[0].ms, 10000);
  m.lancer();
  assert.equal(img.src, "/api/image?chemin=a.png&t=1&r=3");
  assert.equal(echecs, 0);
  img.echec();
  assert.equal(m.taches.length, 0);
  assert.equal(img.src, "/api/image?chemin=a.png&t=1&r=3");
  assert.equal(echecs, 1);
});

test("une adresse qui n'est pas /api/image n'est pas redemandée", () => {
  const img = fausseImage("data:image/png;base64,AAAA");
  const m = minuterie();
  reessayerImage(img, {planifier: m.planifier});
  img.echec();
  assert.equal(m.taches.length, 0);
});

test("une image changée entre-temps (visionneuse) n'est pas écrasée et repart de zéro", () => {
  const img = fausseImage("/api/image?chemin=a.png");
  const m = minuterie();
  reessayerImage(img, {planifier: m.planifier});
  img.echec();
  img.src = "/api/image?chemin=b.png";
  m.lancer();
  assert.equal(img.src, "/api/image?chemin=b.png");
  img.echec();
  m.lancer();
  assert.equal(img.src, "/api/image?chemin=b.png&r=1");
});

test("adresses", () => {
  assert.equal(adresseDeBase("/api/image?chemin=a.png&r=2"), "/api/image?chemin=a.png");
  assert.equal(adresseDeBase("/api/image?r=2&chemin=a.png"), "/api/image?chemin=a.png");
  assert.equal(adresseDEssai("/api/image?chemin=a.png", 1), "/api/image?chemin=a.png&r=1");
});
