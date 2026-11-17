// Garder la lecture où elle était quand un panneau se redessine : le contenu peut arriver après coup (la facturation
// se charge par le réseau) ; la position est remise dès que la page est assez haute, tant que l'utilisateur n'a pas
// bougé lui-même. Sans DOM : `panneau` a `scrollTop`, `scrollHeight`, `clientHeight` ; `observer(rappel)` rend
// une fonction d'arrêt ; `geste(rappel)` aussi (molette, toucher, clavier, clic de l'utilisateur).
export const DUREE_GARDE_MS = 8000;

export function garderDefilement(panneau, y, {observer, geste, minuteur = setTimeout, annuler = clearTimeout,
                                             duree = DUREE_GARDE_MS} = {}) {
  panneau.scrollTop = y;
  if (!(y > 0) || panneau.scrollTop >= y - 1 || !observer) return Object.assign(() => {}, {actif: () => false, y});
  let fini = false, arretObs = () => {}, arretGeste = () => {}, temps = null;
  const arreter = () => {
    if (fini) return;
    fini = true;
    arretObs(); arretGeste(); if (temps !== null) annuler(temps);
  };
  arretObs = observer(() => {
    if (fini) return;
    panneau.scrollTop = y;
    if (panneau.scrollTop >= y - 1) arreter();     // la page est revenue à sa hauteur : position retrouvée
  });
  if (geste) arretGeste = geste(arreter);           // l'utilisateur fait défiler : on le laisse faire
  temps = minuteur(arreter, duree);
  // `actif()` : la position attendue (`y`) n'est pas encore retrouvée ; un nouveau dessin repart de `y`, pas du haut.
  return Object.assign(arreter, {actif: () => !fini, y});
}

// Les branchements du navigateur : la hauteur du contenu observée, les gestes de l'utilisateur sur le panneau.
export function garderDefilementDOM(panneau, contenu, y) {
  return garderDefilement(panneau, y, {
    // La taille (images qui arrivent) et les ajouts de contenu (la facturation chargée) : les ajouts suffisent même
    // quand la page n'est pas affichée (pas de rendu, donc pas de ResizeObserver).
    observer: (rappel) => {
      const arrets = [];
      if (typeof ResizeObserver !== "undefined") {
        const o = new ResizeObserver(() => rappel());
        o.observe(contenu);
        arrets.push(() => o.disconnect());
      }
      if (typeof MutationObserver !== "undefined") {
        const m = new MutationObserver(() => rappel());
        m.observe(contenu, {childList: true, subtree: true, characterData: true});
        arrets.push(() => m.disconnect());
      }
      return () => { for (const a of arrets) a(); };
    },
    geste: (rappel) => {
      const types = ["wheel", "touchstart", "keydown", "pointerdown"];
      for (const t of types) panneau.addEventListener(t, rappel, {passive: true});
      return () => { for (const t of types) panneau.removeEventListener(t, rappel); };
    },
  });
}
