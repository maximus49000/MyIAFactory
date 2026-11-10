// Le bandeau du haut : nom du projet, voyant de la factory, barre de charge de l'ordinateur.
// Plus, sous la barre, le bandeau d'erreur quand le relevé est indisponible.
// Tout texte venu du serveur passe par textContent.

import {voyant, libelleCharge, listeDisponible, dateFr} from "./texte.js";
import {boutons, envoyer} from "./actions.js";
import {urlProjet, livrables, projetCourant, memoriser} from "./projets.js";

const INTERVALLE_CHARGE = 5000;
const DUREE_MESSAGE = 4000;

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

export function creerBarre(entete, bandeau) {
  const titre = el("div", "barre-titre");
  const logo = el("span", "barre-logo", "Le bureau vivant");
  const projet = el("span", "barre-projet", "");
  const choixProjet = el("select", "barre-choix");
  choixProjet.setAttribute("aria-label", "Projet");
  choixProjet.hidden = true;   // montré seulement quand le bureau suit plusieurs projets
  titre.append(logo, projet, choixProjet);

  const lampe = el("span", "voyant-lampe");
  const libelle = el("span", "voyant-libelle", "…");
  const leVoyant = el("div", "voyant");
  leVoyant.setAttribute("role", "status");
  leVoyant.append(lampe, libelle);

  const charge = el("div", "charge");
  const etiquette = el("span", "charge-etiquette", "Charge");
  const piste = el("div", "charge-piste");
  const remplissage = el("div", "charge-remplissage");
  const trait = el("div", "charge-trait");
  trait.title = "Charge maximum pour lancer une nouvelle étape";
  piste.append(remplissage, trait);
  const valeur = el("span", "charge-valeur", "—");
  charge.append(etiquette, piste, valeur);

  const zoneActions = el("div", "barre-actions");
  const boutonListe = el("button", "bouton-barre bouton-liste", "Toutes les tâches");
  boutonListe.type = "button";
  boutonListe.hidden = true;  // montré seulement pour un relevé qui a la vue liste (version 2)
  const boutonNouvelle = el("button", "bouton-barre", "+ Nouvelle fonctionnalité");
  const boutonFonctions = el("button", "bouton-barre", "Fonctionnalités");
  for (const b of [boutonNouvelle, boutonFonctions]) { b.type = "button"; b.hidden = true; }   // relevé v4 et `agir`
  const zoneLivrable = el("span", "barre-livrable");
  zoneLivrable.hidden = true;
  entete.append(titre, leVoyant, zoneActions, boutonNouvelle, boutonFonctions, zoneLivrable, boutonListe, charge);

  // Message temporaire sous la barre : le résultat d'un envoi (jamais l'effet de la demande).
  const retour = el("div", "message-demande");
  retour.setAttribute("role", "status");
  retour.hidden = true;
  entete.after(retour);
  let minuteur = null;
  function dire(texte, ok) {
    retour.textContent = texte;
    retour.dataset.ton = ok ? "ok" : "alerte";
    retour.hidden = false;
    clearTimeout(minuteur);
    minuteur = setTimeout(() => { retour.hidden = true; }, DUREE_MESSAGE);
  }

  // Dépose une demande au projet ; `bouton` (facultatif) est grisé jusqu'à la réponse.
  let enCours = 0;
  async function demander(demande, bouton) {
    if (bouton) bouton.disabled = true;
    enCours++;
    try {
      const r = await envoyer(demande);
      dire(r.message, r.ok);
      return r;
    } finally {
      enCours--;
      if (bouton) bouton.disabled = false;
    }
  }

  let signatureActions = "";
  function majActions(etat) {
    const liste = boutons(etat);
    const signature = JSON.stringify(liste);
    if (signature === signatureActions) return;
    signatureActions = signature;
    zoneActions.replaceChildren();
    for (const b of liste) {
      if (b.lien) {
        const a = el("a", "bouton-barre", b.libelle);
        a.href = b.lien;
        a.target = "_blank";
        a.rel = "noopener";
        zoneActions.append(a);
        continue;
      }
      const bouton = el("button", "bouton-barre", b.libelle);
      bouton.type = "button";
      bouton.disabled = !b.actif;
      bouton.addEventListener("click", () => {
        if (b.confirmer && !confirm(b.confirmer)) return;
        demander({type: "bouton", id: b.id}, bouton);
      });
      zoneActions.append(bouton);
    }
  }

  // « Dernier livrable » : un lien direct, ou un petit menu s'il y en a plusieurs ;
  // le catalogue de chaque fonctionnalité qui en a un s'y ajoute (il s'ouvre dans le panneau de droite).
  let signatureLivrables = "";
  let ouvrirCatalogue = null;
  function majLivrables(etat) {
    const liste = livrables(etat, projetCourant());
    const cats = ouvrirCatalogue ? (etat.fonctionnalites || []).filter((f) => f?.catalogue === true) : [];
    const signature = JSON.stringify([liste, cats.map((f) => [f.id, f.nom])]);
    if (signature === signatureLivrables) return;
    signatureLivrables = signature;
    zoneLivrable.replaceChildren();
    zoneLivrable.hidden = liste.length + cats.length === 0;
    const lien = (l, classe, texte) => {
      const a = el("a", classe, texte);
      a.href = l.url;
      a.target = "_blank";
      a.rel = "noopener";
      return a;
    };
    const catalogue = (f, classe, texte) => {
      const b = el("button", classe, texte);
      b.type = "button";
      b.addEventListener("click", () => { b.closest("details")?.removeAttribute("open"); ouvrirCatalogue(f.id); });
      return b;
    };
    if (liste.length === 1 && !cats.length) {
      zoneLivrable.append(lien(liste[0], "bouton-barre", "Dernier livrable"));
    } else if (cats.length === 1 && !liste.length) {
      zoneLivrable.append(catalogue(cats[0], "bouton-barre", "Catalogue"));
    } else if (liste.length + cats.length > 1) {
      const details = el("details", "menu-livrables");
      details.append(el("summary", "bouton-barre", "Dernier livrable"));
      const ul = el("ul", "liste-partie");
      for (const l of liste) {
        const li = el("li", "");
        li.append(lien(l, "lien-tache", l.libelle + (l.date ? " · " + dateFr(l.date) : "")));
        ul.append(li);
      }
      for (const f of cats) {
        const li = el("li", "");
        li.append(catalogue(f, "lien-tache", "Catalogue · " + f.nom));
        ul.append(li);
      }
      details.append(ul);
      zoneLivrable.append(details);
    }
  }

  // Le sélecteur de projets (mode `multi`) : un choix par projet, avec sa pastille d'attente.
  let signatureProjets = "";
  function majProjets(multi, projets, id) {
    choixProjet.hidden = !multi;
    projet.hidden = multi;
    if (!multi) return;
    const signature = JSON.stringify([projets, id]);
    if (signature === signatureProjets) return;
    signatureProjets = signature;
    choixProjet.replaceChildren();
    for (const p of projets) {
      const o = el("option", "", (p.nom || p.id) + (p.attente > 0 ? ` (${p.attente})` : "") + (p.erreur ? " ⚠" : ""));
      o.value = p.id;
      o.selected = p.id === id;
      choixProjet.append(o);
    }
  }
  choixProjet.addEventListener("change", () => {
    memoriser(choixProjet.value);
    location.reload();     // la scène est reconstruite pour les services du nouveau projet
  });

  const message = el("span", "bandeau-message");
  bandeau.append(message);
  bandeau.hidden = true;

  let factory = null, erreur = null, derniere = null;

  function afficherVoyant() {
    const v = voyant(factory, erreur);
    libelle.textContent = v.libelle;
    leVoyant.dataset.ton = v.ton;
  }

  function afficherCharge() {
    const c = derniere;
    charge.title = libelleCharge(c);
    if (!c || !c.disponible) {
      remplissage.style.width = "0%";
      charge.classList.remove("depasse");
      charge.classList.add("indisponible");
      valeur.textContent = c ? "Mesure indisponible" : "—";
      trait.style.display = c && c.max ? "" : "none";
      if (c && c.max) trait.style.left = c.max + "%";
      return;
    }
    charge.classList.remove("indisponible");
    remplissage.style.width = Math.max(0, Math.min(100, c.charge)) + "%";
    trait.style.display = "";
    trait.style.left = Math.max(0, Math.min(100, c.max)) + "%";
    charge.classList.toggle("depasse", !c.feu_vert);
    valeur.textContent = `${Math.round(c.charge)} % (max ${Math.round(c.max)} %)`;
  }

  async function rafraichirCharge() {
    try {
      const r = await fetch(urlProjet("/api/charge"), {cache: "no-store"});
      if (r.ok) derniere = await r.json();
    } catch { /* on garde la dernière mesure */ }
    afficherCharge();
    return derniere;
  }

  rafraichirCharge();
  setInterval(() => { if (!document.hidden) rafraichirCharge(); }, INTERVALLE_CHARGE);
  // Le voyant dit « sans activité depuis… » : on le remet à jour même sans nouvel état.
  setInterval(afficherVoyant, 30000);
  afficherVoyant();

  return {
    // Un état utilisable : voyant et nom du projet.
    majEtat(etat) {
      factory = etat.factory || null;
      projet.textContent = etat.projet || "";
      erreur = null;
      bandeau.hidden = true;
      afficherVoyant();
      boutonListe.hidden = !listeDisponible(etat);
      majActions(etat);
      const v4 = (etat.version ?? 1) >= 4 && etat.agir === true;
      boutonNouvelle.hidden = boutonFonctions.hidden = !v4;
      majLivrables(etat);
    },
    // Le relevé est indisponible : voyant en alerte et bandeau avec le message du serveur.
    majErreur(texte) {
      erreur = texte || "Relevé indisponible.";
      message.textContent = `${erreur} La scène montrée est la dernière connue.`;
      bandeau.hidden = false;
      afficherVoyant();
    },
    boutonListe,
    boutonNouvelle,
    boutonFonctions,
    // Le panneau donne de quoi ouvrir un catalogue ; la barre l'offre alors avec les livrables.
    surCatalogue(fn) { ouvrirCatalogue = fn; signatureLivrables = ""; },
    majProjets,
    majActions,
    demander,
    dire,
    rafraichirCharge,
    charge: () => derniere,
  };
}
