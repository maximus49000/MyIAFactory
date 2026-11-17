import test from "node:test";
import assert from "node:assert/strict";
import {garderDefilement} from "../ui/defilement.js";

// Un panneau dont le défilement est borné par la hauteur du contenu, comme dans le navigateur.
function panneau(hauteur, visible = 500) {
  let y = 0;
  return {
    clientHeight: visible, scrollHeight: hauteur,
    get scrollTop() { return y; },
    set scrollTop(v) { y = Math.max(0, Math.min(v, this.scrollHeight - this.clientHeight)); },
  };
}
function branchements() {
  const b = {rappel: null, geste: null, fin: null, arrets: 0};
  b.observer = (r) => { b.rappel = r; return () => { b.arrets++; }; };
  b.gesteDe = (r) => { b.geste = r; return () => {}; };
  b.minuteur = (r) => { b.fin = r; return 1; };
  return b;
}

test("contenu déjà là : la position est remise tout de suite", () => {
  const p = panneau(3000), b = branchements();
  garderDefilement(p, 1200, {observer: b.observer, geste: b.gesteDe, minuteur: b.minuteur});
  assert.equal(p.scrollTop, 1200);
  assert.equal(b.rappel, null);                       // rien à surveiller
});

test("contenu chargé après coup (facturation) : la barre revient où l'on était", () => {
  const p = panneau(600), b = branchements();
  const garde = garderDefilement(p, 1200, {observer: b.observer, geste: b.gesteDe, minuteur: b.minuteur, annuler: () => {}});
  assert.equal(p.scrollTop, 100);                     // la page est encore courte
  assert.equal(garde.actif(), true);
  p.scrollHeight = 3000; b.rappel();                  // la facturation arrive
  assert.equal(p.scrollTop, 1200);
  assert.equal(b.arrets, 1);                          // fini : on ne touche plus à rien
  assert.equal(garde.actif(), false);
});

test("l'utilisateur fait défiler avant l'arrivée du contenu : on le laisse", () => {
  const p = panneau(600), b = branchements();
  garderDefilement(p, 1200, {observer: b.observer, geste: b.gesteDe, minuteur: b.minuteur, annuler: () => {}});
  b.geste();
  p.scrollTop = 0; p.scrollHeight = 3000; b.rappel();
  assert.equal(p.scrollTop, 0);
});

test("en haut : rien à garder", () => {
  const p = panneau(600), b = branchements();
  garderDefilement(p, 0, {observer: b.observer});
  assert.equal(b.rappel, null);
});
