// Le bandeau du haut, sur une seule ligne : l'heure, le nom du projet, le voyant de la factory, la charge de l'ordinateur,
// les boutons, et la roue crantée (menu des paramètres, barre-parametres.js) à droite.
// Plus, sous la barre, le bandeau d'erreur quand le relevé est indisponible.
// Tout texte venu du serveur passe par textContent.

import {voyant, libelleCharge, listeDisponible, dateFr, retenues} from "./texte.js";
import {boutons, envoyer, demandeLivrerMaintenant, attenteLivraison} from "./actions.js";
import {urlProjet, livrables, projetCourant, memoriser, optionsProjets, ENTREE_NOUVEAU} from "./projets.js";
import {brancherAssociation} from "./associer.js";
import {creerBandeauOrchestrateur} from "./orchestrateur.js";
import {creerConso} from "./conso.js";
import {definirAbonnement} from "./abonnement.js";
import {accuseDe, creerAccuses, majEtatAccuses, noterAccuse} from "./accuse.js";
import {brancherOptimiser} from "./optimiser.js";
import {creerHorloge, creerMenuParametres, raccourcir, resserrer, CLASSE_ETROITE} from "./barre-parametres.js";

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
  // Ce que le moteur dit retenir le travail (pause d'une installation, attente de charge), sous le voyant.
  const retenue = el("div", "barre-retenue");
  retenue.setAttribute("role", "status");
  retenue.hidden = true;
  function majRetenue(etat) {
    const lignes = retenues(etat);
    retenue.hidden = lignes.length === 0;
    retenue.replaceChildren(...lignes.map((l) => {
      const s = el("span", "retenue", l.texte);
      s.dataset.ton = l.ton;
      for (const p of l.pastilles || []) {      // « 10 prérequis », « 1 poste local occupé »… : une par famille
        const pastille = el("span", "pastille-attente", p.texte);
        pastille.dataset.genre = p.genre;
        s.append(" ", pastille);
      }
      return s;
    }));
  }

  const charge = el("div", "charge");
  const etiquette = el("span", "charge-etiquette", "Charge");
  const piste = el("div", "charge-piste");
  const remplissage = el("div", "charge-remplissage");
  const trait = el("div", "charge-trait");
  trait.title = "Charge maximum pour lancer une nouvelle étape";
  piste.append(remplissage, trait);
  // La valeur : le pourcentage, puis « (max …) » que la barre resserrée laisse tomber (style.css, `.barre-compacte`).
  const valeur = el("span", "charge-valeur");
  const valeurPourcent = el("span", "charge-pourcent", "—");
  const valeurMax = el("span", "charge-max", "");
  valeur.append(valeurPourcent, valeurMax);
  // « Optimiser la charge » : ce qui charge l'ordinateur, et l'arrêt d'un programme sur le clic de l'utilisateur.
  const boutonOptimiser = el("button", "bouton-barre bouton-optimiser", "Optimiser la charge");
  boutonOptimiser.type = "button";
  charge.append(etiquette, piste, valeur, boutonOptimiser);

  const zoneActions = el("div", "barre-actions");
  const boutonListe = el("button", "bouton-barre bouton-liste", "Toutes les tâches");
  boutonListe.type = "button";
  boutonListe.hidden = true;  // montré seulement pour un relevé qui a la vue liste (version 2)
  const boutonNouvelle = el("button", "bouton-barre", "+ Nouvelle fonctionnalité");
  const boutonCorrection = el("button", "bouton-barre", "+ Nouvelle correction");
  const boutonQuestion = el("button", "bouton-barre", "? Une question");
  const boutonFonctions = el("button", "bouton-barre", "Fonctionnalités");
  for (const b of [boutonNouvelle, boutonCorrection, boutonQuestion, boutonFonctions]) { b.type = "button"; b.hidden = true; }   // relevé v4 et `agir`
  const zoneLivrable = el("span", "barre-livrable");
  zoneLivrable.hidden = true;
  const boutonTelephone = el("button", "bouton-barre", "Associer un téléphone");
  boutonTelephone.type = "button";
  boutonTelephone.hidden = true;   // montré seulement sur l'ordinateur, quand le bureau est ouvert au téléphone
  // La consommation Claude : le rond seul (ce qui reste, en %), à toutes les largeurs ; les fenêtres 5 h / semaine sont
  // dans le panneau qu'il ouvre (conso.js), qui se relit avec lui.
  const blocAbonnement = el("div", "bloc-abonnement");
  blocAbonnement.append(creerConso());
  // Libellés courts quand la place manque (le libellé entier reste l'infobulle et le nom accessible).
  raccourcir(boutonNouvelle, "+ Nouv.");
  raccourcir(boutonCorrection, "+ Corr.");
  raccourcir(boutonQuestion, "?");
  raccourcir(boutonFonctions, "Fonct.");
  raccourcir(boutonListe, "Tâches");
  raccourcir(boutonOptimiser, "Optim.");

  // Maquette validée (2026-11-23) : l'heure à gauche, la consommation Claude (le rond seul, jamais caché), puis
  // le titre et le projet, le voyant, la retenue, la charge, les boutons ; la roue crantée seule à droite. « Associer un
  // téléphone » est une entrée de son menu (le bouton reste hors de la barre).
  const horloge = creerHorloge();
  const separateur = el("span", "barre-separateur");
  separateur.setAttribute("aria-hidden", "true");
  const liens = {ouvrirReglages: null, ouvrirServeurs: null};   // donnés par les panneaux (`brancherMenu`), créés après
  let replies = [];
  const telephone = () => document.documentElement.classList.contains("mobile");
  const menu = creerMenuParametres({
    get ouvrirReglages() { return liens.ouvrirReglages; },
    get ouvrirServeurs() { return liens.ouvrirServeurs; },
    get associerTelephone() { return boutonTelephone.hidden ? null : () => boutonTelephone.click(); },
    actions: () => replies.flatMap(entreesDe),
    // La retenue n'a plus sa place dans la barre (téléphone, barre étroite) : elle ouvre le menu, en lecture seule.
    retenue: () => (!retenue.hidden && (telephone() || entete.classList.contains(CLASSE_ETROITE))
      ? [...retenue.children].map((s) => s.textContent) : []),
  });
  entete.append(horloge.racine, separateur, blocAbonnement, titre, leVoyant, retenue, charge, zoneActions, boutonNouvelle, boutonCorrection,
                boutonQuestion, boutonFonctions, zoneLivrable, boutonListe, menu.racine);

  // Une seule ligne à toutes les largeurs : ce qui ne tient pas passe dans le menu de la roue, de droite à gauche
  // (barre-parametres.js). Sur téléphone : l'heure, le rond de consommation, le projet, le voyant et la roue.
  const pliables = () => [...zoneActions.children, boutonNouvelle, boutonCorrection, boutonQuestion, boutonFonctions, zoneLivrable,
                          boutonListe, ...(telephone() ? [boutonOptimiser] : [])];
  // Les entrées du menu pour un élément replié : lui-même, ou les liens et boutons du « Dernier livrable ».
  function entreesDe(e) {
    const cibles = e === zoneLivrable ? [...e.querySelectorAll("a, button")] : [e];
    return cibles.map((c) => ({libelle: c.dataset?.libelle || c.textContent.trim(), element: c, desactive: c.disabled === true}));
  }
  function ajuster() {
    replies = resserrer(entete, pliables(), {telephone: telephone()});
  }
  // La scène et les panneaux se placent sous la hauteur réelle de la barre ; sa largeur change : on la resserre.
  new ResizeObserver(() => {
    ajuster();
    document.documentElement.style.setProperty("--hauteur-barre", entete.offsetHeight + "px");
  }).observe(entete);

  // Message temporaire sous la barre : le résultat d'un envoi (jamais l'effet de la demande).
  const retour = el("div", "message-demande");
  retour.setAttribute("role", "status");
  retour.hidden = true;
  entete.after(retour);
  // L'accusé de réception : « Reçu, en cours de traitement… » jusqu'à ce que le relevé montre la demande traitée.
  const accuses = creerAccuses();
  retour.after(accuses.racine);
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
      if (r.ok) { const a = accuseDe(demande, dernierEtat); if (a) { noterAccuse(a); majEtatAccuses(null); } }
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
  let dernierEtat = null;
  function majLivrables(etat) {
    dernierEtat = etat;
    const liste = livrables(etat, projetCourant());
    const cats = ouvrirCatalogue ? (etat.fonctionnalites || []).filter((f) => f?.catalogue === true) : [];
    const aLivrer = attenteLivraison(etat);
    const signature = JSON.stringify([liste, cats.map((f) => [f.id, f.nom]), aLivrer, !!etat?.agir]);
    if (signature === signatureLivrables) return;
    signatureLivrables = signature;
    zoneLivrable.replaceChildren();
    zoneLivrable.hidden = liste.length + cats.length === 0 && !aLivrer;
    if (aLivrer) {       // des éléments conformes attendent la livraison groupée : la lancer sans attendre le calme
      const b = el("button", "bouton-barre bouton-livrer", `Livrer maintenant (${aLivrer.elements.length || "?"})`);
      b.type = "button";
      b.title = aLivrer.texte;
      b.disabled = !etat?.agir;
      b.addEventListener("click", () => demander(demandeLivrerMaintenant(), b));
      zoneLivrable.append(b);
    }
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

  // Le sélecteur de projets (mode `multi`) : un choix par projet, avec sa pastille d'attente, puis « Nouveau projet… ».
  let signatureProjets = "";
  let derniersProjets = {projets: [], parents: [], id: null};
  let ouvrirCreation = null;
  function majProjets(multi, projets, id, parents = []) {
    choixProjet.hidden = !multi;
    projet.hidden = multi;
    if (!multi) return;
    derniersProjets = {projets, parents, id};
    const signature = JSON.stringify([projets, id]);
    if (signature === signatureProjets) return;
    signatureProjets = signature;
    choixProjet.replaceChildren();
    for (const x of optionsProjets(projets, id)) {
      const o = el("option", "", x.libelle);
      o.value = x.value;
      o.selected = x.selected;
      choixProjet.append(o);
    }
    ajuster();   // la liste des projets a changé de largeur
  }
  choixProjet.addEventListener("change", () => {
    if (choixProjet.value === ENTREE_NOUVEAU) {   // le formulaire s'ouvre ; le projet affiché reste le même
      choixProjet.value = derniersProjets.id;
      if (ouvrirCreation) ouvrirCreation({...derniersProjets});
      return;
    }
    memoriser(choixProjet.value);
    location.reload();     // la scène est reconstruite pour les services du nouveau projet
  });

  const message = el("span", "bandeau-message");
  bandeau.append(message);
  bandeau.hidden = true;
  const orchestrateur = creerBandeauOrchestrateur(bandeau);

  let factory = null, erreur = null, derniere = null, locauxMax = null;

  function afficherVoyant() {
    const v = voyant(factory, erreur);
    libelle.textContent = v.libelle;
    leVoyant.dataset.ton = v.ton;
  }

  function afficherCharge() {
    const c = derniere;
    charge.title = libelleCharge(c, locauxMax);
    if (!c || !c.disponible) {
      remplissage.style.width = "0%";
      charge.classList.remove("depasse");
      charge.classList.add("indisponible");
      valeurPourcent.textContent = c ? "Mesure indisponible" : "—";
      valeurMax.textContent = "";
      trait.style.display = c && c.max ? "" : "none";
      if (c && c.max) trait.style.left = c.max + "%";
      return;
    }
    charge.classList.remove("indisponible");
    remplissage.style.width = Math.max(0, Math.min(100, c.charge)) + "%";
    trait.style.display = "";
    trait.style.left = Math.max(0, Math.min(100, c.max)) + "%";
    charge.classList.toggle("depasse", !c.feu_vert);
    valeurPourcent.textContent = `${Math.round(c.charge)} %`;
    valeurMax.textContent = ` (max ${Math.round(c.max)} %)`;
  }

  async function rafraichirCharge() {
    try {
      const r = await fetch(urlProjet("/api/charge"), {cache: "no-store"});
      if (r.ok) derniere = await r.json();
    } catch { /* on garde la dernière mesure */ }
    afficherCharge();
    return derniere;
  }

  brancherAssociation(boutonTelephone, dire);
  brancherOptimiser(boutonOptimiser, dire);
  rafraichirCharge();
  setInterval(() => { if (!document.hidden) rafraichirCharge(); }, INTERVALLE_CHARGE);
  // Le voyant dit « sans activité depuis… » : on le remet à jour même sans nouvel état.
  setInterval(afficherVoyant, 30000);
  setInterval(() => majEtatAccuses(null), 15000);   // « le moteur n'a pas encore traité » arrive avec l'heure
  afficherVoyant();

  return {
    // Un état utilisable : voyant et nom du projet.
    majEtat(etat) {
      majEtatAccuses(etat);
      definirAbonnement(etat.abonnement);   // la part estimée des coûts (panneaux)
      orchestrateur.maj(etat);
      factory = etat.factory || null;
      locauxMax = etat.agents_locaux_max ?? null;
      afficherCharge();
      projet.textContent = etat.projet || "";
      erreur = null;
      bandeau.hidden = true;
      afficherVoyant();
      majRetenue(etat);
      boutonListe.hidden = !listeDisponible(etat);
      majActions(etat);
      const v4 = (etat.version ?? 1) >= 4 && etat.agir === true;
      boutonNouvelle.hidden = boutonCorrection.hidden = boutonQuestion.hidden = boutonFonctions.hidden = !v4;
      majLivrables(etat);
      ajuster();   // des boutons ont pu paraître ou partir : la barre se resserre ou se desserre
    },
    // Les panneaux (créés après la barre) donnent de quoi ouvrir la page Réglages et les serveurs de travail.
    brancherMenu({ouvrirReglages, ouvrirServeurs}) {
      liens.ouvrirReglages = ouvrirReglages || null;
      liens.ouvrirServeurs = ouvrirServeurs || null;
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
    boutonCorrection,
    boutonQuestion,
    boutonFonctions,
    // Le panneau donne de quoi ouvrir un catalogue ; la barre l'offre alors avec les livrables.
    surCatalogue(fn) { ouvrirCatalogue = fn; signatureLivrables = ""; if (dernierEtat) majLivrables(dernierEtat); },
    majProjets,
    // La page donne de quoi ouvrir le formulaire « Nouveau projet » ; la liste déroulante l'offre alors en dernière entrée.
    surCreation(fn) { ouvrirCreation = fn; },
    // Ouvre ce formulaire depuis une décision (`options` : la décision, le genre choisi) ; faux s'il n'est pas disponible.
    nouveauProjet(options) {
      if (!ouvrirCreation) return false;
      ouvrirCreation({...derniersProjets, ...options});
      return true;
    },
    majActions,
    demander,
    dire,
    rafraichirCharge,
    charge: () => derniere,
  };
}
