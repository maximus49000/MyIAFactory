// Les deux bouts de la barre du haut (maquette validée par le Directeur, 2026-11-23) : l'heure et la date à gauche, la
// roue crantée et son menu à droite ; et le resserrement qui garde la barre sur une seule ligne (ce qui ne tient pas passe
// dans le groupe « Actions » du menu). Tout texte passe par textContent ; aucune icône par innerHTML.

const SVG = "http://www.w3.org/2000/svg";
const JOURS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const INTERVALLE_HEURE = 15000;

// Classes posées par `resserrer`, lues par style.css.
export const CLASSE_ICONES = "barre-icones";      // (1) libellés courts
export const CLASSE_COMPACTE = "barre-compacte";  // (2) la charge réduite à son pourcentage
export const CLASSE_REPLIE = "replie";            // (3) un élément passé dans le menu
export const CLASSE_ETROITE = "barre-etroite";    // (4) tout est replié et la barre déborde encore

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

const deux = (n) => String(n).padStart(2, "0");

// {heure: "14:32", date: "lun. 23 nov."} : l'heure locale et la date courte en français. Pur.
export function formaterHeure(date) {
  return {heure: `${deux(date.getHours())}:${deux(date.getMinutes())}`,
          date: `${JOURS[date.getDay()]} ${date.getDate()} ${MOIS[date.getMonth()]}`};
}

// Le bloc de l'heure (grande) et de la date (petite, dessous), remis à l'heure toutes les 15 s.
export function creerHorloge(maintenant = () => new Date()) {
  const racine = el("div", "barre-horloge");
  const heure = el("time", "barre-heure");
  const date = el("span", "barre-date");
  racine.append(heure, date);
  function maj() {
    const d = maintenant();
    const f = formaterHeure(d);
    heure.textContent = f.heure;
    date.textContent = f.date;
    racine.title = d.toLocaleDateString("fr-FR", {weekday: "long", day: "numeric", month: "long", year: "numeric"});
  }
  maj();
  setInterval(maj, INTERVALLE_HEURE);
  return {racine, maj};
}

// Un bouton de la barre qui sait se raccourcir : libellé long en temps normal, forme courte quand la place manque
// (style.css, `.barre-icones`). Le libellé long reste le nom accessible et l'infobulle.
export function raccourcir(bouton, court) {
  const long = bouton.textContent;
  bouton.dataset.libelle = long;
  bouton.title = long;
  bouton.setAttribute("aria-label", long);
  const c = el("span", "libelle-court", court);
  c.setAttribute("aria-hidden", "true");
  bouton.replaceChildren(el("span", "libelle-long", long), c);
}

// L'icône de la roue : un SVG en ligne, décoratif (le bouton porte son nom).
function icone() {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "20");
  svg.setAttribute("height", "20");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  const centre = document.createElementNS(SVG, "circle");
  centre.setAttribute("cx", "12");
  centre.setAttribute("cy", "12");
  centre.setAttribute("r", "3");
  const dents = document.createElementNS(SVG, "path");
  dents.setAttribute("d", "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0"
    + "-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l"
    + "-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2"
    + " 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65"
    + " 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0"
    + " 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2"
    + " 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z");
  svg.append(centre, dents);
  return svg;
}

let compteur = 0;

// La roue et son menu. Chaque option est lue à l'ouverture (un accesseur convient) : une fonction propose l'entrée, une
// valeur vide la cache. `actions()` rend les actions repliées [{libelle, element, desactive}] ; leur entrée clique
// l'élément d'origine (aucun comportement dupliqué). Échap et un clic ailleurs ferment ; la roue reprend le focus.
export function creerMenuParametres(options) {
  const racine = el("div", "barre-parametres");
  const roue = el("button", "barre-roue");
  roue.type = "button";
  roue.title = "Paramètres";
  roue.setAttribute("aria-label", "Paramètres");
  roue.setAttribute("aria-haspopup", "menu");
  roue.setAttribute("aria-expanded", "false");
  roue.append(icone());
  const liste = el("div", "menu-parametres");
  const id = `menu-parametres-${++compteur}`;
  liste.setAttribute("id", id);
  liste.setAttribute("role", "menu");
  liste.setAttribute("aria-label", "Paramètres");
  liste.hidden = true;
  roue.setAttribute("aria-controls", id);
  racine.append(roue, liste);

  let items = [];   // les entrées montrées, dans l'ordre (flèches haut et bas)

  function entree(libelle, legende, agir) {
    const b = el("button", "menu-parametres-entree");
    b.type = "button";
    b.setAttribute("role", "menuitem");
    b.append(el("span", "menu-parametres-libelle", libelle));
    if (legende) b.append(el("span", "menu-parametres-legende", legende));
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();   // un clic de menu n'est pas « un clic ailleurs » pour les autres menus de la barre
      if (b.disabled) return;
      fermer();
      agir();
    });
    return b;
  }

  const fixes = [
    ["ouvrirReglages", "Réglages", "Global, type, projet"],
    ["ouvrirServeurs", "Serveurs de travail", "État et aptitude des lieux"],
    ["associerTelephone", "Associer un téléphone", ""],
  ];

  function remplir() {
    items = [];
    const enfants = [];
    for (const [cle, libelle, legende] of fixes) {
      const f = options[cle];
      const b = entree(libelle, legende, () => { const g = options[cle]; if (typeof g === "function") g(); });
      b.hidden = typeof f !== "function";
      if (!b.hidden) items.push(b);
      enfants.push(b);
    }
    const repliees = (typeof options.actions === "function" ? options.actions() : null) || [];
    const groupe = el("div", "menu-parametres-groupe");
    groupe.setAttribute("role", "group");
    groupe.setAttribute("aria-label", "Actions");
    groupe.hidden = repliees.length === 0;
    const titre = el("div", "menu-parametres-titre", "Actions");
    titre.setAttribute("aria-hidden", "true");
    groupe.append(titre);
    for (const a of repliees) {
      const b = entree(a.libelle, "", () => a.element.click());
      b.disabled = a.desactive === true;
      groupe.append(b);
      if (!b.disabled) items.push(b);
    }
    enfants.push(groupe);
    liste.replaceChildren(...enfants);
  }

  function ouvert() { return !liste.hidden; }

  function ouvrir() {
    remplir();
    liste.hidden = false;
    roue.setAttribute("aria-expanded", "true");
    racine.classList.add("ouvert");
    items[0]?.focus();
  }

  function fermer({rendreFocus = true} = {}) {
    if (!ouvert()) return;
    liste.hidden = true;
    roue.setAttribute("aria-expanded", "false");
    racine.classList.remove("ouvert");
    if (rendreFocus) roue.focus();
  }

  roue.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (ouvert()) fermer(); else ouvrir();
  });

  racine.addEventListener("keydown", (ev) => {
    if (!ouvert()) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();   // Échap ferme le menu, pas aussi le panneau de droite
      fermer();
      return;
    }
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      const i = items.indexOf(document.activeElement);
      const pas = ev.key === "ArrowDown" ? 1 : -1;
      items[(i + pas + items.length) % items.length]?.focus();
    }
  });

  // Un clic ailleurs ferme ; la roue ne reprend le focus que s'il était resté dans le menu (sinon il suit le clic).
  document.addEventListener("click", (ev) => {
    if (!ouvert() || racine.contains(ev.target)) return;
    const focusDedans = racine.contains(document.activeElement);
    fermer({rendreFocus: focusDedans});
  });

  return {racine, fermer, ouvrir, ouvert};
}

// Garde la barre sur une ligne. Dans cet ordre, tant qu'elle déborde : (1) libellés courts, (2) charge réduite à son
// pourcentage, (3) les éléments `pliables` passent dans le menu, un à un, en partant de la droite, (4) le nom du bureau
// (le projet reste), la retenue et les jauges d'abonnement s'effacent (la roue reste visible). Sur téléphone, tous les
// pliables visibles passent dans le menu. Rend les éléments repliés, dans l'ordre de la barre.
export function resserrer(entete, pliables, {telephone = false} = {}) {
  const deborde = () => entete.scrollWidth > entete.clientWidth + 1;
  entete.classList.remove(CLASSE_ICONES, CLASSE_COMPACTE, CLASSE_ETROITE);
  for (const p of pliables) p.classList.remove(CLASSE_REPLIE);
  const visibles = pliables.filter((p) => !p.hidden);
  if (telephone) {
    for (const p of visibles) p.classList.add(CLASSE_REPLIE);
    return visibles;
  }
  if (!deborde()) return [];
  entete.classList.add(CLASSE_ICONES);
  if (!deborde()) return [];
  entete.classList.add(CLASSE_COMPACTE);
  const replies = [];
  for (let i = visibles.length - 1; i >= 0 && deborde(); i--) {
    visibles[i].classList.add(CLASSE_REPLIE);
    replies.unshift(visibles[i]);
  }
  if (deborde()) entete.classList.add(CLASSE_ETROITE);   // (4) toujours trop large : le nom du bureau et la retenue s'effacent
  return replies;
}
