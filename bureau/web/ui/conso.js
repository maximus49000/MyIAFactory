// Le rond du bandeau : la synthèse, ce qu'il reste du forfait Claude Code sur la fenêtre la plus tendue. Un clic ouvre
// la répartition par modèle, la part estimée des coûts et, quand la barre manque de place (téléphone), les deux fenêtres
// (5 h, semaine) que les jauges montrent à côté du rond. C'est aussi la source unique des jauges (mesure.js).
// Quand la lecture directe du compte manque, le serveur se rabat sur le dernier appel du moteur et le dit.
// Tout texte venu du serveur passe par textContent.

import {tonReste, agePhrase, lignePart, definirConsoCourante} from "./mesure.js";

export {tonReste};

const INTERVALLE = 60000;
const RAYON = 15;
const PRINCIPALES = ["five_hour", "seven_day"];
export const CIRCONFERENCE = 2 * Math.PI * RAYON;

// La part du cercle encore pleine (0..1).
export function partRestante(reste) {
  return Number.isFinite(reste) ? Math.max(0, Math.min(1, reste / 100)) : 0;
}

// « dans 2 h 10 », « dans 3 j », ou la date quand elle est lointaine ; vide si la remise à zéro est inconnue.
export function remiseDans(remise, maintenant = Date.now()) {
  const t = Date.parse(remise);
  if (!Number.isFinite(t)) return "";
  const minutes = Math.round((t - maintenant) / 60000);
  if (minutes <= 0) return "maintenant";
  if (minutes < 60) return `dans ${minutes} min`;
  const heures = Math.floor(minutes / 60);
  if (heures < 24) return `dans ${heures} h${minutes % 60 ? " " + String(minutes % 60).padStart(2, "0") : ""}`;
  return `dans ${Math.round(heures / 24)} j`;
}

export function libelleRond(c, maintenant = Date.now() / 1000) {
  if (!c || !c.disponible) return c?.raison || "Consommation indisponible";
  const f = (c.fenetres || []).find((x) => x.cle === c.pire);
  const age = agePhrase(c, maintenant);
  return `Il reste ${Math.round(c.reste)} % (${f ? f.libelle : "forfait"})` + (c.source === "moteur" && age ? ` — ${age}` : "");
}

// La ligne d'une fenêtre dans le panneau : nom, reste, barre d'utilisation, remise à zéro.
function ligneFenetre(f) {
  const ligne = el("div", "conso-ligne");
  ligne.dataset.ton = tonReste(f.reste);
  const tete = el("div", "conso-tete");
  tete.append(el("span", "conso-nom", f.libelle), el("span", "conso-reste", `${Math.round(f.reste)} % restants`));
  const piste = el("div", "conso-piste");
  const plein = el("div", "conso-plein");
  plein.style.width = Math.max(0, Math.min(100, f.utilise)) + "%";
  piste.append(plein);
  const remise = remiseDans(f.remise);
  ligne.append(tete, piste, el("div", "conso-remise",
    `${Math.round(f.utilise)} % utilisés` + (remise ? ` · remise à zéro ${remise}` : "")));
  return ligne;
}

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

function svg(tag, attrs) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

export function creerConso(url = "/api/conso") {
  const racine = el("div", "conso");
  const bouton = el("button", "conso-rond");
  bouton.type = "button";
  bouton.setAttribute("aria-haspopup", "true");
  bouton.setAttribute("aria-expanded", "false");
  const dessin = svg("svg", {viewBox: "0 0 36 36", width: "30", height: "30", "aria-hidden": "true"});
  const fond = svg("circle", {cx: 18, cy: 18, r: RAYON, class: "conso-fond"});
  const arc = svg("circle", {cx: 18, cy: 18, r: RAYON, class: "conso-arc", transform: "rotate(-90 18 18)"});
  arc.style.strokeDasharray = String(CIRCONFERENCE);
  dessin.append(fond, arc);
  const chiffre = el("span", "conso-chiffre", "—");
  bouton.append(dessin, chiffre);
  const panneau = el("div", "conso-panneau");
  panneau.hidden = true;
  racine.append(bouton, panneau);

  let donnees = null;

  function afficher() {
    const c = donnees;
    bouton.title = libelleRond(c);
    const dispo = !!c && c.disponible === true;
    racine.dataset.ton = dispo ? tonReste(c.reste) : "inconnu";
    racine.dataset.source = dispo ? c.source || "compte" : "";
    arc.style.strokeDashoffset = String(CIRCONFERENCE * (1 - (dispo ? partRestante(c.reste) : 0)));
    chiffre.textContent = dispo ? Math.round(c.reste) + " %" : "—";
    panneau.replaceChildren();
    panneau.append(el("div", "conso-titre", "Consommation Claude Code"));
    if (!dispo) {
      panneau.append(el("p", "conso-vide", c?.raison || "Consommation indisponible."));
      return;
    }
    if (c.source === "moteur") {
      panneau.append(el("p", "conso-source", `Lecture directe indisponible (${c.raison || "compte injoignable"}) : ` +
        `${agePhrase(c)}.`));
    }
    // Les deux fenêtres sont celles des jauges : le panneau ne les montre que lorsque les jauges sont repliées (étroit).
    const principales = c.fenetres.filter((f) => PRINCIPALES.includes(f.cle));
    const modeles = c.fenetres.filter((f) => !PRINCIPALES.includes(f.cle));
    if (principales.length) {
      const bloc = el("div", "conso-principales");
      for (const f of principales) bloc.append(ligneFenetre(f));
      panneau.append(bloc);
    }
    if (modeles.length) {
      panneau.append(el("div", "conso-sous-titre", "Par modèle"));
      for (const f of modeles) panneau.append(ligneFenetre(f));
    }
    const part = lignePart(c.part);
    if (part) panneau.append(el("p", "conso-part", part));
  }

  async function rafraichir() {
    try {
      const r = await fetch(url, {cache: "no-store"});
      if (r.ok) {
        donnees = await r.json();
        definirConsoCourante(donnees);   // les jauges lisent la même lecture : jamais deux valeurs différentes
      }
    } catch { /* on garde la dernière mesure */ }
    afficher();
  }

  function ouvrir(ouvert) {
    panneau.hidden = !ouvert;
    bouton.setAttribute("aria-expanded", String(ouvert));
    if (ouvert) rafraichir();
  }
  bouton.addEventListener("click", () => ouvrir(panneau.hidden));
  document.addEventListener("click", (e) => { if (!panneau.hidden && !racine.contains(e.target)) ouvrir(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panneau.hidden) ouvrir(false); });

  afficher();
  rafraichir();
  setInterval(() => { if (!document.hidden) rafraichir(); }, INTERVALLE);
  return racine;
}
