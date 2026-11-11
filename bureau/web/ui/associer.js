// « Associer un téléphone » : sur l'ordinateur, un QR code par adresse ouverte (Tailscale, Wi-Fi de la maison), qui
// porte l'adresse et un code d'association à usage unique. Le téléphone le scanne et n'a plus rien à saisir.
// « Révoquer les téléphones » change la clé : les téléphones déjà associés devront scanner à nouveau.
// Tout texte venu du serveur passe par textContent.

import qrcode from "../vendor/qrcode.js";
import {el} from "./dom.js";

const SVG = "http://www.w3.org/2000/svg";
const NOMS = {tailscale: "Tailscale", reseau_local: "Wi-Fi de la maison"};
const MENTIONS = {tailscale: "", reseau_local: "Non chiffré : seulement sur le Wi-Fi de la maison."};

// Les adresses servies par le bureau, chacune avec son lien d'association. Une adresse d'un genre inconnu ou qui
// n'est pas en http:// est écartée.
export function entreesAssociation(acces) {
  if (!acces || typeof acces.code !== "string" || !acces.code || !Array.isArray(acces.adresses)) return [];
  return acces.adresses
    .filter((a) => a && Object.hasOwn(NOMS, a.genre) && typeof a.url === "string" && a.url.startsWith("http://"))
    .map((a) => ({genre: a.genre, titre: NOMS[a.genre], url: a.url, mention: MENTIONS[a.genre],
                  lien: `${a.url}/associer?code=${encodeURIComponent(acces.code)}`}));
}

// Le QR code d'un texte : sa taille en modules et un tracé SVG (un carré par module sombre).
export function cheminQR(texte) {
  const q = qrcode(0, "M");
  q.addData(texte);
  q.make();
  const taille = q.getModuleCount();
  let d = "";
  for (let y = 0; y < taille; y++) {
    for (let x = 0; x < taille; x++) if (q.isDark(y, x)) d += `M${x} ${y}h1v1h-1z`;
  }
  return {taille, d};
}

function svgQR(texte) {
  const {taille, d} = cheminQR(texte);
  const marge = 4;
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `${-marge} ${-marge} ${taille + 2 * marge} ${taille + 2 * marge}`);
  svg.setAttribute("class", "associer-qr");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "QR code d'association");
  const fond = document.createElementNS(SVG, "rect");
  for (const [k, v] of [["x", -marge], ["y", -marge], ["width", taille + 2 * marge], ["height", taille + 2 * marge],
                        ["fill", "#fff"]]) fond.setAttribute(k, v);
  const trace = document.createElementNS(SVG, "path");
  trace.setAttribute("d", d);
  trace.setAttribute("fill", "#000");
  svg.append(fond, trace);
  return svg;
}

// Le contenu du panneau : un bloc par adresse, puis « Révoquer les téléphones ».
export function rendreAssociation(conteneur, acces, {revoquer}) {
  conteneur.replaceChildren();
  conteneur.append(el("h2", "associer-titre", "Associer un téléphone"));
  const entrees = entreesAssociation(acces);
  if (!entrees.length) {
    conteneur.append(el("p", "associer-texte", "Le bureau n'est ouvert à aucun téléphone (aucun accès dans le fichier de bureau)."));
    return;
  }
  conteneur.append(el("p", "associer-texte",
    "Scannez un QR code avec l'appareil photo du téléphone. Le code sert une fois et vaut 10 minutes."));
  for (const e of entrees) {
    const bloc = el("div", "associer-adresse");
    bloc.append(el("div", "associer-genre", e.titre), svgQR(e.lien), el("div", "associer-url", e.url));
    if (e.mention) bloc.append(el("div", "associer-mention", e.mention));
    conteneur.append(bloc);
  }
  const bouton = el("button", "bouton-barre associer-revoquer", "Révoquer les téléphones");
  bouton.type = "button";
  bouton.addEventListener("click", () => revoquer(bouton));
  conteneur.append(bouton);
}

async function lireAcces() {
  try {
    const r = await fetch("/api/acces", {cache: "no-store"});
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

// Le bouton de la barre (montré seulement sur l'ordinateur, quand une adresse distante est ouverte) et le panneau.
export async function brancherAssociation(bouton, dire) {
  bouton.hidden = true;
  const premier = await lireAcces();   // un écouteur distant répond 404 : le téléphone ne voit pas le bouton
  if (!entreesAssociation(premier).length) return;
  bouton.hidden = false;

  const fond = el("div", "associer");
  fond.hidden = true;
  const boite = el("div", "associer-boite");
  boite.setAttribute("role", "dialog");
  boite.setAttribute("aria-modal", "true");
  const contenu = el("div", "");
  const fermer = el("button", "bouton-barre associer-fermer", "Fermer");
  fermer.type = "button";
  boite.append(contenu, fermer);
  fond.append(boite);
  document.body.append(fond);
  const cacher = () => { fond.hidden = true; contenu.replaceChildren(); };   // le code ne reste pas affiché
  fermer.addEventListener("click", cacher);
  fond.addEventListener("click", (ev) => { if (ev.target === fond) cacher(); });

  async function revoquer(b) {
    if (!confirm("Révoquer tous les téléphones associés ? Ils devront scanner un nouveau QR code.")) return;
    b.disabled = true;
    try {
      const r = await fetch("/api/acces/revoquer", {method: "POST", headers: {"X-Bureau": "1", "Content-Type": "application/json"}, body: "{}"});
      dire(r.ok ? "Téléphones révoqués : scannez un nouveau QR code pour en associer un." : "La révocation a échoué.", r.ok);
    } catch {
      dire("La révocation a échoué.", false);
    }
    await ouvrir();
  }

  async function ouvrir() {
    const acces = await lireAcces();   // un code neuf à chaque ouverture
    rendreAssociation(contenu, acces, {revoquer});
    fond.hidden = false;
  }
  bouton.addEventListener("click", ouvrir);
}
