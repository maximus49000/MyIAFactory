// Le voyant de la factory dans la barre : une pastille de couleur seule (vert : en marche, orange : en pause, rouge :
// alerte, gris : inconnu). Ce que la couleur veut dire est écrit en `aria-label` (pas de `title` : il doublerait la
// bulle) et dans une petite bulle (role="tooltip") qui paraît au survol, au focus et au toucher ; un clic ou un toucher
// sur la pastille l'ouvre puis la referme. Elle se ferme aussi avec Échap (écouté sur le document tant qu'elle est
// ouverte, même ouverte au survol), en quittant le voyant ou d'un clic ailleurs. Un changement d'état est annoncé par
// une région vive cachée à l'œil (`annonce`, role="status") que l'appelant pose à côté de la pastille. La bulle est posée dans le <body>, positionnée d'après la pastille : la barre coupe ce qui la dépasse
// (overflow: hidden) et ne la cacherait pas autrement. Tout texte passe par textContent.

const ECART = 8;

export function creerVoyant() {
  const lampe = document.createElement("span");
  lampe.className = "voyant-lampe";
  lampe.setAttribute("aria-hidden", "true");
  const racine = document.createElement("div");
  racine.className = "voyant";
  racine.setAttribute("role", "img");
  racine.setAttribute("tabindex", "0");
  racine.append(lampe);
  // La pastille (role="img") n'est pas une région vive : l'annonce d'un changement passe par cet élément caché.
  const annonce = document.createElement("span");
  annonce.className = "sr-seulement";
  annonce.setAttribute("role", "status");
  annonce.setAttribute("aria-live", "polite");

  let texte = "";
  let bulle = null;
  let ouvertLe = 0;   // le survol et le focus ouvrent la bulle juste avant le clic du même geste : il ne la referme pas

  function placer() {
    if (!bulle || typeof racine.getBoundingClientRect !== "function") return;
    const r = racine.getBoundingClientRect();
    const largeur = bulle.offsetWidth || 0;
    const fenetre = (typeof window !== "undefined" && window.innerWidth) || 0;
    let gauche = r.left;
    if (fenetre && largeur) gauche = Math.min(gauche, fenetre - largeur - ECART);
    bulle.style.top = Math.round(r.bottom + ECART) + "px";
    bulle.style.left = Math.max(ECART, Math.round(gauche)) + "px";
  }
  function surEchap(e) { if (e.key === "Escape") cacher(); }
  function surClicAilleurs(e) { if (bulle && !racine.contains(e.target)) cacher(); }
  function montrer() {
    if (!texte) return;
    if (!bulle) {
      bulle = document.createElement("div");
      bulle.className = "voyant-bulle";
      bulle.setAttribute("role", "tooltip");
      document.body.append(bulle);
      document.addEventListener("keydown", surEchap);
      document.addEventListener("click", surClicAilleurs);
    }
    bulle.textContent = texte;
    placer();
  }
  function cacher() {
    if (!bulle) return;
    bulle.remove();
    bulle = null;
    document.removeEventListener("keydown", surEchap);
    document.removeEventListener("click", surClicAilleurs);
  }
  function survol() { ouvertLe = Date.now(); montrer(); }

  racine.addEventListener("mouseenter", survol);
  racine.addEventListener("mouseleave", cacher);
  racine.addEventListener("focus", survol);
  racine.addEventListener("blur", cacher);
  racine.addEventListener("click", (e) => {
    e.stopPropagation?.();
    if (bulle && Date.now() - ouvertLe > 400) cacher();   // un second clic ou toucher la ferme
    else montrer();
  });

  return {
    racine,
    lampe,
    annonce,
    // Le texte (ce que la couleur veut dire) et le ton (`ok`, `pause`, `alerte`, ou vide).
    maj(libelle, ton) {
      texte = String(libelle || "");
      if (annonce.textContent !== texte) annonce.textContent = texte;
      racine.setAttribute("aria-label", texte);
      if (ton === undefined || ton === null || ton === "") delete racine.dataset.ton;
      else racine.dataset.ton = ton;
      if (bulle) { bulle.textContent = texte; placer(); }
    },
    montrer,
    cacher,
    bulleVisible: () => bulle !== null,
  };
}
