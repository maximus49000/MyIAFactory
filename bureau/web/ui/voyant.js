// Le voyant de la factory dans la barre : une pastille de couleur seule (vert : en marche, orange : en pause, rouge :
// alerte, gris : inconnu). Ce que la couleur veut dire est écrit en `title`, en `aria-label` et dans une petite bulle
// (role="tooltip") qui paraît au survol, au focus et au toucher, et se ferme avec Échap, en quittant le voyant ou d'un
// clic ailleurs. La bulle est posée dans le <body>, positionnée d'après la pastille : la barre coupe ce qui la dépasse
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

  let texte = "";
  let bulle = null;

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
  function montrer() {
    if (!texte) return;
    if (!bulle) {
      bulle = document.createElement("div");
      bulle.className = "voyant-bulle";
      bulle.setAttribute("role", "tooltip");
      document.body.append(bulle);
    }
    bulle.textContent = texte;
    placer();
  }
  function cacher() {
    if (!bulle) return;
    bulle.remove();
    bulle = null;
  }

  racine.addEventListener("mouseenter", montrer);
  racine.addEventListener("mouseleave", cacher);
  racine.addEventListener("focus", montrer);
  racine.addEventListener("blur", cacher);
  racine.addEventListener("click", (e) => { e.stopPropagation?.(); montrer(); });
  racine.addEventListener("keydown", (e) => { if (e.key === "Escape") cacher(); });
  document.addEventListener("click", (e) => { if (bulle && !racine.contains(e.target)) cacher(); });

  return {
    racine,
    lampe,
    // Le texte (ce que la couleur veut dire) et le ton (`ok`, `pause`, `alerte`, ou vide).
    maj(libelle, ton) {
      texte = String(libelle || "");
      racine.title = texte;
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
