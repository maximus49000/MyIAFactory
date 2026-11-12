// La visionneuse plein écran : une image à la fois, flèches gauche et droite (ou boutons), toujours AU-DESSUS de tout
// (même de la fenêtre de validation). Se ferme par le bouton « Fermer » (×), par Échap (elle seule : la fenêtre en
// dessous reste ouverte), par un clic ou un toucher sur le fond ou sur l'image ; le focus revient sur ce qui l'a ouverte.
// Tant qu'elle est ouverte, la page de fond ne défile pas (la classe `visionneuse-ouverte` du body, retirée à la fermeture
// sans toucher à `val-ouverte` que pose la fenêtre de validation).

import {el} from "./dom.js";
import {imagesLegendees} from "./texte.js";
import {reessayerImage} from "./reessai.js";

// L'image voisine dans une série de n images (on fait le tour : après la dernière, la première).
export function voisine(n, i, sens) {
  return n > 0 ? (i + sens + n) % n : 0;
}

let courante = null;    // la visionneuse ouverte (une seule à la fois) : sa fonction de fermeture

// Ferme la visionneuse ouverte, s'il y en a une (la fenêtre qui la porte se ferme, ou une autre s'ouvre).
export function fermerVisionneuse() { courante?.(); }
export const visionneuseOuverte = () => courante !== null;

// `images` : des chemins ou des `{chemin, legende}` ; la légende s'affiche sous l'image (et sert d'`alt`).
// `url` : chemin -> adresse. `declencheur` : ce qui reprend le focus à la fermeture (par défaut, l'élément focalisé).
export function ouvrirVisionneuse(images, depart, url, declencheur = document.activeElement) {
  fermerVisionneuse();
  const liste = imagesLegendees(images);
  let i = Math.min(Math.max(0, depart || 0), Math.max(0, liste.length - 1));
  const fond = el("div", "visionneuse");
  fond.setAttribute("role", "dialog");
  fond.setAttribute("aria-modal", "true");
  fond.setAttribute("aria-label", "Images du message");
  const img = document.createElement("img");
  reessayerImage(img);
  const compteur = el("div", "visionneuse-compteur", "");
  const fermer = el("button", "visionneuse-fermer", "×");
  const avant = el("button", "visionneuse-fleche gauche", "‹");
  const apres = el("button", "visionneuse-fleche droite", "›");
  for (const [b, nom] of [[fermer, "Fermer"], [avant, "Image précédente"], [apres, "Image suivante"]]) {
    b.type = "button";
    b.setAttribute("aria-label", nom);
  }
  const legende = el("p", "visionneuse-legende", "");
  const montrer = () => {
    img.src = url(liste[i].chemin);
    img.alt = liste[i].legende || `Image ${i + 1} sur ${liste.length}`;
    legende.textContent = liste[i].legende;
    legende.hidden = !liste[i].legende;
    compteur.textContent = liste.length > 1 ? `${i + 1} / ${liste.length}` : "";
    avant.hidden = apres.hidden = liste.length < 2;
  };
  const aller = (sens) => { i = voisine(liste.length, i, sens); montrer(); };
  // Capturé avant tout le reste : Échap ferme la visionneuse seule (la fenêtre de validation ignore les touches tant
  // qu'elle est là), Tab reste entre ses boutons.
  const clavier = (ev) => {
    if (ev.key === "Escape") { ev.stopPropagation(); ev.preventDefault(); clore(); }
    else if (ev.key === "ArrowLeft") { ev.stopPropagation(); if (liste.length > 1) aller(-1); }
    else if (ev.key === "ArrowRight") { ev.stopPropagation(); if (liste.length > 1) aller(1); }
    else if (ev.key === "Tab") {
      ev.stopPropagation();
      const f = [fermer, avant, apres].filter((b) => !b.hidden);
      const k = f.indexOf(document.activeElement);
      ev.preventDefault();
      f[(k + (ev.shiftKey ? -1 : 1) + f.length) % f.length].focus();
    }
  };
  const clore = () => {
    if (courante !== clore) return;
    courante = null;
    document.removeEventListener("keydown", clavier, true);
    fond.remove();
    document.body.classList?.remove("visionneuse-ouverte");
    if (declencheur && declencheur.isConnected !== false) declencheur.focus?.();
  };
  fermer.addEventListener("click", clore);
  img.addEventListener("click", clore);
  avant.addEventListener("click", () => aller(-1));
  apres.addEventListener("click", () => aller(1));
  fond.addEventListener("click", (ev) => { if (ev.target === fond) clore(); });
  document.addEventListener("keydown", clavier, true);
  fond.append(img, legende, avant, apres, compteur, fermer);
  document.body.classList?.add("visionneuse-ouverte");
  document.body.append(fond);
  courante = clore;
  montrer();
  fermer.focus();
  return clore;
}
