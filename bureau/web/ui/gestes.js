// Les gestes du doigt sur la scène 3D : glisser à un doigt déplace la vue, pincer zoome. Un simple toucher reste le
// clic (le navigateur l'envoie tel quel) ; un geste qui a bougé n'envoie pas de clic. La souris n'est pas concernée.

import {zoomPincement} from "../logique/mobile.js";

const SEUIL_GLISSE_PX = 8;    // en dessous, c'est un toucher (un tremblement du doigt n'est pas un glissement)
const DELAI_CLIC_MS = 60;     // le clic du navigateur arrive juste après le relâchement

// `surChangement()` : la vue a bougé, une image est à refaire.
export function brancherGestes(conteneur, sc, surChangement) {
  const doigts = new Map();   // pointerId -> {x, y, x0, y0}
  let pincement = null;       // {ecart, zoom} au moment où le deuxième doigt est posé
  let aBouge = false;

  const ecart = () => {
    const [a, b] = [...doigts.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  conteneur.addEventListener("pointerdown", (ev) => {
    if (ev.pointerType === "mouse") return;
    doigts.set(ev.pointerId, {x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY});
    if (doigts.size === 2) {
      pincement = {ecart: ecart(), zoom: sc.zoom()};
      aBouge = true;
    }
  });

  conteneur.addEventListener("pointermove", (ev) => {
    const d = doigts.get(ev.pointerId);
    if (!d) return;
    if (doigts.size === 1) {
      if (!aBouge && Math.hypot(ev.clientX - d.x0, ev.clientY - d.y0) < SEUIL_GLISSE_PX) return;
      aBouge = true;
      sc.deplacer(ev.clientX - d.x, ev.clientY - d.y);
      d.x = ev.clientX; d.y = ev.clientY;
    } else if (doigts.size === 2 && pincement) {
      d.x = ev.clientX; d.y = ev.clientY;
      sc.zoomer(zoomPincement(pincement.ecart, ecart(), pincement.zoom));
    } else {
      return;
    }
    surChangement();
  });

  const lacher = (ev) => {
    if (!doigts.delete(ev.pointerId)) return;
    pincement = null;
    if (doigts.size === 1) {   // il reste un doigt : il repart de sa position, sans à-coup
      const [reste] = doigts.values();
      reste.x0 = reste.x; reste.y0 = reste.y;
    }
    if (doigts.size === 0) setTimeout(() => { aBouge = false; }, DELAI_CLIC_MS);
  };
  conteneur.addEventListener("pointerup", lacher);
  conteneur.addEventListener("pointercancel", lacher);

  // Un glissement ou un pincement ne doit pas finir en clic (il fermerait le panneau ouvert).
  conteneur.addEventListener("click", (ev) => {
    if (!aBouge) return;
    ev.stopImmediatePropagation();
    ev.preventDefault();
  }, true);
}
