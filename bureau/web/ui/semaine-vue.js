// La fenêtre « Voir plus » : le graphique d'une semaine du forfait (en cours ou archivée), des listes déroulantes en
// cascade (semaine, projet, fonctionnalité, tâche, sous-tâche) et la liste des sujets ayant utilisé Claude, tous projets
// réunis. Choisir un filtre ou cliquer un sujet règle les mêmes listes : le graphique met en évidence (bandes) les moments
// où la sélection a appelé Claude, et le total (€, part de la semaine, CO₂) suit. La courbe, elle, est le compteur du
// compte entier : elle ne se filtre pas.
// Fenêtre modale : fond assombri, Fermer / Échap / clic hors fenêtre, focus piégé puis rendu au bouton, plein écran au
// téléphone. Tout texte venu du serveur passe par textContent.

import {NIVEAUX, apresChoix, lignesListe, marquesSelection, marquesDe, trouver, totalSelection, niveaux, dessiner,
        instantA, valeurA, heureLocale, SEP} from "./semaine.js";
import {euros} from "./texte.js";
import {etiquettePart} from "./abonnement.js";
import {etiquetteCO2, infobulleCO2} from "./empreinte.js";

export const LEGENDE = "La courbe est le compteur de tout le compte. Les bandes montrent quand la sélection a utilisé Claude.";

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

async function lireJson(url) {
  try {
    const r = await fetch(url, {cache: "no-store"});
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

export const lireSemaines = () => lireJson("/api/semaines");
export const lireSerie = (id) => lireJson("/api/semaine?id=" + encodeURIComponent(id));
export const lireSujets = (id) => lireJson("/api/sujets?semaine=" + encodeURIComponent(id));

export function libelleSemaine(s) {
  const fin = new Date(s.remise * 1000);
  const debut = new Date(s.debut * 1000);
  const jour = (d) => d.toLocaleDateString("fr-FR", {day: "numeric", month: "short"});
  return `${jour(debut)} → ${jour(fin)}${s.courante ? " (en cours)" : ""}`;
}

// La ligne du total de la sélection : « Alpha › Accueil : ≈ 0,34 € · ≈ 0,7 % semaine · ≈ 1,2 g CO₂e · 5 appels ».
export function ligneTotal(total) {
  const morceaux = [euros(total.euros) + (total.sans_prix ? ` + ${total.sans_prix} à prix inconnu` : "")];
  const part = etiquettePart(total.euros, {court: true});
  if (part) morceaux.push(part);
  const co2 = etiquetteCO2(total.co2);
  if (co2) morceaux.push(co2);
  morceaux.push(`${total.n} appel${total.n > 1 ? "s" : ""}`);
  return `${total.nom} : ${morceaux.join(" · ")}`;
}

export function ouvrirSemaines({declencheur = null} = {}) {
  const fond = el("div", "sem-fond");
  const boite = el("div", "sem-boite");
  boite.setAttribute("role", "dialog");
  boite.setAttribute("aria-modal", "true");
  boite.setAttribute("aria-labelledby", "sem-titre");
  const tete = el("div", "sem-tete");
  const titre = el("h2", "sem-titre", "Consommation de Claude sur la semaine");
  titre.id = "sem-titre";
  const fermer = el("button", "bouton-barre sem-fermer", "Fermer");
  fermer.type = "button";
  fermer.setAttribute("aria-label", "Fermer la fenêtre");
  tete.append(titre, fermer);
  const filtres = el("div", "sem-filtres");
  const message = el("p", "sem-message");
  message.setAttribute("role", "status");
  const zoneGraphique = el("div", "sem-graphique");
  const legende = el("p", "sem-legende", LEGENDE);
  const total = el("p", "sem-total");
  const tableau = el("details", "sem-tableau");
  const liste = el("ul", "sem-liste");
  boite.append(tete, filtres, message, zoneGraphique, legende, total, tableau, liste);
  fond.append(boite);

  const etat = {semaines: [], semaine: null, serie: null, arbre: null, selection: "", maintenant: Date.now() / 1000};
  const bulle = el("div", "sem-bulle");
  bulle.hidden = true;

  // --- Rendu.
  function rendreFiltres() {
    filtres.replaceChildren();
    const champ = (libelle, options, valeur, actif, surChoix) => {
      const l = el("label", "sem-champ");
      l.append(el("span", "sem-champ-nom", libelle));
      const s = el("select", "sem-select");
      s.disabled = !actif;
      for (const [v, t] of options) {
        const o = el("option", "", t);
        o.value = v;
        s.append(o);
      }
      s.value = valeur;
      s.addEventListener("change", () => surChoix(s.value));
      l.append(s);
      filtres.append(l);
    };
    champ("Semaine", etat.semaines.map((s) => [s.id, libelleSemaine(s)]), etat.semaine || "", etat.semaines.length > 0,
      (id) => choisirSemaine(id));
    const sujets = etat.arbre?.sujets || [];
    niveaux(sujets, etat.selection).forEach((n, k) => {
      champ(n.libelle, [["", "Tous"], ...n.options.map((o) => [o.id, o.nom])], n.valeur, n.actif,
        (id) => { etat.selection = apresChoix(sujets, etat.selection, k, id); rendre(); });
    });
  }

  function rendreGraphique() {
    zoneGraphique.replaceChildren();
    const s = etat.serie;
    if (!s) {
      zoneGraphique.append(el("p", "sem-vide", etat.semaine ? "Courbe indisponible." : "Aucune semaine archivée pour l'instant."));
      return;
    }
    const sujets = etat.arbre?.sujets || [];
    const largeur = Math.max(280, Math.floor(zoneGraphique.clientWidth || boite.clientWidth - 32 || 640));
    const choisi = etat.selection ? trouver(sujets, etat.selection) : null;
    const toutes = (etat.arbre?.sujets || []).flatMap(marquesDe);
    const svg = dessiner({semaine: s, points: s.points, maintenant: etat.maintenant, largeur, hauteur: largeur < 480 ? 220 : 300,
                          marques: choisi ? marquesDe(choisi) : toutes, autres: choisi ? toutes : []});
    zoneGraphique.append(svg, bulle);
    brancherSurvol(svg);
    // la même série en tableau : lisible sans voir la courbe
    tableau.replaceChildren(el("summary", "", "Voir les valeurs en tableau"));
    const t = el("table", "sem-table");
    const tr = el("tr");
    tr.append(el("th", "", "Instant"), el("th", "", "% utilisé"), el("th", "", "Source"));
    t.append(tr);
    for (const p of s.points.slice(-200)) {
      const l = el("tr");
      l.append(el("td", "", heureLocale(p.t)), el("td", "", String(p.pourcent).replace(".", ",") + " %"),
        el("td", "", p.source === "compte" ? "compte" : "dernier appel"));
      t.append(l);
    }
    tableau.append(t);
  }

  function brancherSurvol(svg) {
    const g = svg.geometrie;
    const trait = document.createElementNS("http://www.w3.org/2000/svg", "line");
    trait.setAttribute("class", "sem-reperage");
    trait.setAttribute("y1", g.marges.h);
    trait.setAttribute("y2", g.marges.h + g.h);
    trait.style.display = "none";
    svg.append(trait);
    const survol = (ev) => {
      const r = svg.getBoundingClientRect();
      const x = ((ev.clientX - r.left) / r.width) * g.largeur;
      if (x < g.marges.g || x > g.marges.g + g.w) { masquer(); return; }
      const t = instantA(svg, x);
      trait.setAttribute("x1", x);
      trait.setAttribute("x2", x);
      trait.style.display = "";
      const v = valeurA(etat.serie.points, t);
      const proches = marquesSelection(etat.arbre, etat.selection)
        .filter((m) => Math.abs(m.t - t) <= ((g.t1 - g.t0) / g.w) * 4 + (m.duree || 0));
      bulle.replaceChildren(el("strong", "", heureLocale(t)),
        el("span", "", v === null ? "pas de mesure" : String(v).replace(".", ",") + " % utilisé"));
      if (proches.length) bulle.append(el("span", "", `${proches.length} appel${proches.length > 1 ? "s" : ""} de la sélection`));
      bulle.hidden = false;
      const gauche = (x / g.largeur) * r.width;
      bulle.style.left = Math.min(r.width - 160, Math.max(0, gauche + 10)) + "px";
    };
    const masquer = () => { trait.style.display = "none"; bulle.hidden = true; };
    svg.addEventListener("pointermove", survol);
    svg.addEventListener("pointerleave", masquer);
  }

  function rendreListe() {
    liste.replaceChildren();
    const racine = el("li", "sem-ligne-tout");
    const tout = el("button", "sem-sujet sem-tout", "Tout (tous les projets)");
    tout.type = "button";
    tout.setAttribute("aria-pressed", String(!etat.selection));
    tout.addEventListener("click", () => { etat.selection = ""; rendre(); });
    racine.append(tout);
    liste.append(racine);
    if (!etat.arbre) { liste.append(el("li", "sem-vide", "Sujets indisponibles.")); return; }
    const lignes = lignesListe(etat.arbre, etat.selection);
    if (!lignes.length) liste.append(el("li", "sem-vide", "Aucun appel à Claude enregistré pour cette sélection cette semaine."));
    for (const {noeud, profondeur, parents} of lignes) {
      const li = el("li", "sem-item");
      li.style.setProperty("--profondeur", String(profondeur));
      const b = el("button", "sem-sujet");
      b.type = "button";
      b.setAttribute("aria-pressed", String(noeud.id === etat.selection));
      b.classList.toggle("choisi", noeud.id === etat.selection);
      b.title = NIVEAUX[noeud.id.split(SEP).length - 1] ? `${NIVEAUX[noeud.id.split(SEP).length - 1]} — afficher ses appels sur le graphique` : "";
      const nom = el("span", "sem-sujet-nom", noeud.nom);
      if (parents.length) nom.append(el("span", "sem-chemin", parents.join(" › ")));
      const chiffres = el("span", "sem-sujet-chiffres");
      const morceaux = [euros(noeud.euros) + (noeud.sans_prix ? " +?" : "")];
      const part = etiquettePart(noeud.euros, {court: true});
      if (part) morceaux.push(part);
      const co2 = etiquetteCO2(noeud.co2);
      chiffres.textContent = morceaux.join(" · ");
      if (co2) {
        const c = el("span", "sem-co2", co2);
        c.title = infobulleCO2(noeud.co2);
        chiffres.append(" · ", c);
      }
      b.append(nom, chiffres);
      b.addEventListener("click", () => { etat.selection = noeud.id === etat.selection ? "" : noeud.id; rendre(); });
      li.append(b);
      liste.append(li);
    }
  }

  function rendre() {
    rendreFiltres();
    rendreGraphique();
    total.replaceChildren();
    if (etat.arbre) {
      total.textContent = ligneTotal(totalSelection(etat.arbre, etat.selection));
      total.title = "estimation : les % du compte comptent aussi vos autres sessions Claude";
    }
    rendreListe();
  }

  async function choisirSemaine(id) {
    etat.semaine = id;
    etat.selection = "";
    message.textContent = "Chargement…";
    const [serie, arbre] = await Promise.all([lireSerie(id), lireSujets(id)]);
    if (etat.semaine !== id || !fond.isConnected) return;   // un autre choix, ou la fenêtre fermée, entre-temps
    etat.serie = serie ? {...serie, courante: (etat.semaines.find((s) => s.id === id) || {}).courante === true} : null;
    etat.arbre = arbre;
    message.textContent = serie ? "" : "Cette semaine n'a pas pu être lue.";
    rendre();
  }

  // --- Fenêtre : fermeture, focus piégé.
  function fermerFenetre() {
    document.removeEventListener("keydown", clavier, true);
    window.removeEventListener("resize", surTaille);
    fond.remove();
    document.body.classList.remove("sem-ouverte");
    if (declencheur && declencheur.isConnected) declencheur.focus();
  }
  function focalisables() {
    return [...boite.querySelectorAll("button:not([disabled]), select:not([disabled]), summary, a[href]")].filter((x) => !x.hidden);
  }
  function clavier(ev) {
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); fermerFenetre(); return; }
    if (ev.key !== "Tab") return;
    const f = focalisables();
    if (!f.length) { ev.preventDefault(); return; }
    const premier = f[0], dernier = f[f.length - 1];
    if (!boite.contains(document.activeElement)) { ev.preventDefault(); premier.focus(); }
    else if (ev.shiftKey && document.activeElement === premier) { ev.preventDefault(); dernier.focus(); }
    else if (!ev.shiftKey && document.activeElement === dernier) { ev.preventDefault(); premier.focus(); }
  }
  let reDessin = null;
  function surTaille() {
    clearTimeout(reDessin);
    reDessin = setTimeout(() => { if (etat.serie) rendreGraphique(); }, 120);
  }
  fermer.addEventListener("click", fermerFenetre);
  fond.addEventListener("mousedown", (ev) => { if (ev.target === fond) fermerFenetre(); });
  document.addEventListener("keydown", clavier, true);
  window.addEventListener("resize", surTaille);
  document.body.classList.add("sem-ouverte");
  document.body.append(fond);
  fermer.focus();

  (async () => {
    message.textContent = "Chargement…";
    const lues = await lireSemaines();
    if (!fond.isConnected) return;
    etat.semaines = lues?.semaines || [];
    etat.maintenant = lues?.maintenant ?? etat.maintenant;
    if (!etat.semaines.length) { message.textContent = ""; rendre(); return; }
    await choisirSemaine((etat.semaines.find((s) => s.courante) || etat.semaines[0]).id);
  })();

  return {fond, fermer: fermerFenetre, etat};
}
