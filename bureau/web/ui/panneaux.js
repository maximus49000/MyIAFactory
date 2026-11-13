// Cartes (survol d'un agent, clic sur un post-it) et panneau de droite (service, direction).
// Lecture seule, sauf le réglage de la charge maximum. Tout texte venu du serveur passe par textContent.

import {CSS2DObject} from "three/addons/renderers/CSS2DRenderer.js";
import {tronquer, filtrer, filtreDeListe, cleTravail} from "./texte.js";
import {el, ligne} from "./dom.js";
import {urlProjet} from "./projets.js";
import {contenuTache, contenuFile, contenuAttente, contenuListe} from "./detail.js";
import {contenuDossier} from "./dossier.js";
import {contenuDirecteur, contenuAgent, resumeLecons} from "./directeur.js";
import {contenuFonctionnalite, contenuFonctionnalites, nouvelleApparue} from "./fonctionnalite.js";
import {contenuCatalogue} from "./catalogue.js";
import {ouvrirKanban} from "./kanban-plein.js";
import {contenuPartenaires, creerVue} from "./partenaires.js";
import {envoyer as envoyerDemande} from "./actions.js";
import {appliquerEnvoyees, surEnvoyees} from "./validation.js";
import {ouvrirCahier} from "./cahier.js";

const STATUTS = {travail: "au travail", sans_nouvelles: "sans nouvelles", libre: "libre"};
const MAX_TITRE = 90;

// opts : {conteneur, carte, panneau, sc, plan, etat: () => état courant, barre, surFiltre: () => void}
export function creerPanneaux({conteneur, carte, panneau, sc, plan, etat: etatBrut, barre, surFiltre = () => {}}) {
  // Partout l'état affiché est l'état servi SANS les validations déjà envoyées (liste, compteur, signature).
  const etat = () => appliquerEnvoyees(etatBrut());
  let panneauOuvert = null;    // {type, id}
  let signaturePanneau = "";   // ce que le panneau ouvert montre, pour savoir quand le redessiner
  let retourListe = false;     // le panneau d'une tâche a été ouvert depuis la vue liste
  const filtreListe = {etat: null, type: null};   // etat null : pas de choix, le défaut de la vue s'applique
  const brouillons = new Map();  // tâche -> retour en cours d'écriture ; "f:<id>" -> saisie de discussion (survit aux rafraîchissements)
  const envois = new Set();      // saisies dont l'envoi est en cours (un double clic ne crée qu'une demande)
  const envoyes = new Map();     // fonctionnalité -> messages envoyés que le relevé n'a pas encore repris
  const nouvelle = {envoi: null};  // la discussion neuve : {avant, texte, images} une fois le premier message parti
  const corrections = new Set();   // fonctionnalités dont l'utilisateur écrit une correction du cahier des charges
  const catalogues = new Map();      // fonctionnalité -> {statut, cat, avertissements, erreur, lu} (lu à l'ouverture)
  const vuesCatalogue = new Map();   // fonctionnalité -> filtres, page, fiche ouverte, zoom de la vue de haut
  const retoursEnvoyes = new Map();  // fonctionnalité + élément -> retours envoyés que le catalogue n'a pas repris
  let grand = false;                 // le catalogue en plein écran (« Agrandir », Échap pour revenir)
  const vuePartenaires = creerVue();  // filtre, cartes dépliées, message : survit aux rafraîchissements

  const signature = (type, id, e) => {
    if (type === "service") {
      return JSON.stringify((e.agents || []).filter((a) => a.service === id)
        .map((a) => [a.id, a.prenom, a.modele, a.statut, a.lieu, a.couleur]).concat([e.dossier, e.agir,
        e.challenges, (e.savoir || []).filter((s) => s.service === id),
        (e.taches || []).filter((t) => t.active).map((t) => [t.id, t.titre, t.agent, t.etape])]));
    }
    if (type === "partenaires") return JSON.stringify([e.partenaires, e.agir]);
    if (type === "tache") {
      const t = (e.taches || []).find((x) => x.id === id);
      return JSON.stringify([t, cleTravail(t), e.colonnes, e.types, e.agir, e.images_ok,
        (e.agents || []).map((a) => [a.id, a.prenom]), retourListe]);
    }
    if (type === "file") return JSON.stringify([(e.file?.visibles || []).find((q) => q.id === id), e.colonnes, e.agir]);
    if (type === "attente") return JSON.stringify([e.file, e.colonnes, e.agir]);
    if (type === "fonctionnalite") {
      return JSON.stringify([(e.fonctionnalites || []).find((f) => f.id === id), e.agir, e.images_ok,
        e.orchestrateur_actif, (e.agents || []).map((a) => [a.id, a.prenom]), nouvelle.envoi?.texte, e.pause_installation?.texte,
        // Une tâche de la fonctionnalité qui bouge (un agent a fini) : le panneau se redessine et relit le coût.
        (e.taches || []).filter((t) => t.fonctionnalite === id).map((t) => [t.id, t.maj, t.colonne, t.active, t.agent, t.attente,
          cleTravail(t)])]);     // l'agent au travail : « depuis X min » suit la minute qui passe
    }
    if (type === "fonctionnalites") return JSON.stringify([e.fonctionnalites, e.agir]);
    if (type === "catalogue") {
      const f = (e.fonctionnalites || []).find((x) => x.id === id);
      return JSON.stringify([f?.nom, f?.catalogue, e.agir, e.images_ok]);
    }
    if (type === "liste") {
      return JSON.stringify([(e.taches || []).map((t) => [t.id, t.titre, t.colonne, t.agent, t.maj, t.type, t.active]),
        e.colonnes, e.types, (e.agents || []).map((a) => [a.id, a.prenom]), filtreListe]);
    }
    if (type === "agent") {
      const a = (e.agents || []).find((x) => x.id === id);
      // Le Chef : son point de l'atelier et ses échanges suivent l'état (réponse arrivée, minute qui passe…).
      const chef = a?.chef ? [e.agents, (e.taches || []).map((t) => [t.id, t.bloquee, t.attente, t.retours, cleTravail(t)]),
        e.decisions_projet, (e.fonctionnalites || []).map((f) => f.decisions), e.attente_charge] : null;
      return JSON.stringify([a, (e.taches || []).map((t) => [t.id, t.titre, t.colonne, t.agent]), e.services, e.agir,
        retourListe, chef]);
    }
    return JSON.stringify([e.decisions, e.lecons, e.lecons_en_attente, e.agir, (e.agents || []).map((a) => [a.id, a.modele, a.service, a.prenom]),
      e.version, (e.fonctionnalites || []).map((f) => [f.id, f.nom, f.decisions, f.etape, (f.discussion || []).length]), e.decisions_projet,
      (e.taches || []).map((t) => [t.id, t.titre, t.bloquee, t.retours]), e.echanges_vus]);
  };

  // Les tâches qui passent le filtre tant que la vue liste est ouverte (sinon null : rien n'est estompé).
  function filtreActif() {
    const e = etat();
    return panneauOuvert?.type === "liste" && e ? filtrer(e.taches, filtreDeListe(e, filtreListe), e.colonnes) : null;
  }

  // --- Pastille de décisions au-dessus du bureau du Directeur.
  const pastille = el("div", "pastille");
  const pastilleEtiquette = new CSS2DObject(el("div", "pastille-porte"));
  pastilleEtiquette.element.append(pastille);
  pastilleEtiquette.position.set(plan.directeur.x, 1.4, plan.directeur.z);
  pastilleEtiquette.center.set(0.5, 1);
  pastilleEtiquette.visible = false;
  sc.scene.add(pastilleEtiquette);

  // --- Cartes.
  function carteAgent(a, e) {
    const c = el("div", "carte-contenu");
    c.append(el("div", "carte-titre", a.prenom || "?"));
    const service = a.chef ? "Chef d'atelier" : ((e.services || []).find((s) => s.id === a.service)?.nom || "—");
    c.append(ligne("Service", service));
    if (a.specialite) c.append(ligne("Spécialité", a.specialite));
    c.append(ligne("Plafond", a.modele || "?"));   // le modèle de la fiche : jamais dépassé
    c.append(ligne("Lieu", a.lieu === "cloud" ? "cloud ☁" : "local"));
    c.append(ligne("Statut", STATUTS[a.statut] || a.statut || "—"));
    if (resumeLecons(a)) c.append(ligne("Leçons", resumeLecons(a)));
    const titres = (a.taches || []).map((id) => (e.taches || []).find((t) => t.id === id)).filter(Boolean);
    const liste = el("ul", "carte-taches");
    if (titres.length === 0) liste.append(el("li", "vide", "Aucune tâche en cours"));
    for (const t of titres) liste.append(el("li", "", tronquer(t.titre, MAX_TITRE)));
    c.append(el("div", "carte-sous-titre", "Tâches en cours"), liste);
    return c;
  }

  function contenuCarte(choix) {
    const e = etat();
    if (!e || !choix) return null;
    if (choix.type === "agent") {
      const a = (e.agents || []).find((x) => x.id === choix.id);
      return a ? carteAgent(a, e) : null;
    }
    return null;
  }

  function montrerCarte(choix, x, y) {
    const c = contenuCarte(choix);
    if (!c) { cacherCarte(); return; }
    carte.replaceChildren(c);
    carte.hidden = false;
    const l = carte.offsetWidth, h = carte.offsetHeight;
    const gauche = Math.min(x + 16, window.innerWidth - l - 8);
    const haut = y + 16 + h > window.innerHeight - 8 ? y - h - 12 : y + 16;
    carte.style.left = Math.max(8, gauche) + "px";
    carte.style.top = Math.max(8, haut) + "px";
  }
  function cacherCarte() { carte.hidden = true; carte.replaceChildren(); }

  // --- Panneau de droite.
  function fermerPanneau() {
    panneauOuvert = null;
    panneau.hidden = true;
    panneau.replaceChildren();
    grand = false;
    document.body.classList.remove("panneau-ouvert", "panneau-catalogue", "panneau-grand");
    surFiltre();
  }

  const contexte = () => ({
    etat: etat(), barre, brouillons, vuePartenaires, filtreListe, retourListe, envois, envoyes, nouvelle, corrections,
    rouvrir: () => { if (panneauOuvert) ouvrirPanneau(panneauOuvert.type, panneauOuvert.id); },
    ouvrirFonctionnalite: (id) => ouvrirPanneau("fonctionnalite", id),
    ouvrirCatalogue: (id) => ouvrirCatalogue(id),
    ouvrirCahier,
    estOuvert: (type, id) => panneauOuvert?.type === type && panneauOuvert.id === id,
    catalogues, vuesCatalogue, retoursEnvoyes,
    grand: () => grand,
    basculerGrand: () => { grand = !grand; if (panneauOuvert) ouvrirPanneau(panneauOuvert.type, panneauOuvert.id); },
    ouvrirNouvelle: () => ouvrirPanneau("fonctionnalite", null),
    ouvrirListe: () => ouvrirPanneau("liste", null),
    ouvrirAttente: () => ouvrirPanneau("attente", null),
    ouvrirTache: (id) => { retourListe = false; ouvrirPanneau("tache", id); },
    ouvrirTacheDepuisListe: (id) => { retourListe = true; ouvrirPanneau("tache", id); },
    changerFiltre: (changement) => { Object.assign(filtreListe, changement); ouvrirPanneau("liste", null); },
  });

  // Venir d'ailleurs (fonctionnalité, barre) ouvre la page du catalogue, pas la dernière fiche vue.
  function ouvrirCatalogue(id) {
    const v = vuesCatalogue.get(id);
    if (v) v.fiche = null;
    ouvrirPanneau("catalogue", id);
  }

  function ouvrirPanneau(type, id) {
    const e = etat();
    if (!e) return;
    if (type === "file" && (e.taches || []).some((t) => t.id === id)) type = "tache";  // la file est devenue une tâche
    if (type !== "tache") retourListe = false;
    // La saisie d'une discussion garde le curseur quand le panneau se redessine.
    const surSaisie = panneauOuvert?.type === "fonctionnalite" && document.activeElement?.dataset?.saisie === "1"
      && panneau.contains(document.activeElement);
    const debut = surSaisie ? document.activeElement.selectionStart : 0;
    // Le même panneau redessiné (relevé rafraîchi) garde son défilement : la lecture ne remonte pas en haut.
    const memeVue = !panneau.hidden && panneauOuvert?.type === type && panneauOuvert?.id === id;
    const defilement = memeVue ? panneau.scrollTop : 0;
    panneauOuvert = {type, id};
    signaturePanneau = signature(type, id, e);
    const contenu = el("div", "panneau-contenu");
    const fermer = el("button", "panneau-fermer", document.documentElement.classList.contains("mobile") ? "Fermer" : "×");
    fermer.type = "button";
    fermer.setAttribute("aria-label", "Fermer");
    fermer.addEventListener("click", fermerPanneau);

    let avecReglage = false;
    if (type === "service") {
      const s = (e.services || []).find((x) => x.id === id);
      if (!s) { fermerPanneau(); return; }
      contenuDossier(contexte(), contenu, id);
      avecReglage = id === "facturation";
    } else if (type === "tache") {
      const t = (e.taches || []).find((x) => x.id === id);
      if (!t) { fermerPanneau(); return; }
      contenuTache(contexte(), contenu, t);
    } else if (type === "file") {
      const q = (e.file?.visibles || []).find((x) => x.id === id);
      if (!q) { fermerPanneau(); return; }
      contenuFile(contexte(), contenu, q);
    } else if (type === "attente") {
      contenuAttente(contexte(), contenu);
    } else if (type === "liste") {
      contenuListe(contexte(), contenu);
    } else if (type === "fonctionnalite") {
      const f = id === null ? null : (e.fonctionnalites || []).find((x) => x.id === id);
      if (id !== null && !f) { fermerPanneau(); return; }
      contenuFonctionnalite(contexte(), contenu, f);
    } else if (type === "fonctionnalites") {
      contenuFonctionnalites(contexte(), contenu);
    } else if (type === "catalogue") {
      const f = (e.fonctionnalites || []).find((x) => x.id === id);
      if (!f || f.catalogue !== true) { fermerPanneau(); return; }
      contenuCatalogue(contexte(), contenu, f);
    } else if (type === "partenaires") {
      if (!e.partenaires) { fermerPanneau(); return; }
      contenuPartenaires(contexte(), contenu, envoyerDemande);
    } else if (type === "agent") {
      const a = (e.agents || []).find((x) => x.id === id);
      if (!a) { fermerPanneau(); return; }
      contenuAgent(contexte(), contenu, a, STATUTS);
    } else {
      contenuDirecteur(contexte(), contenu);
      avecReglage = !(e.services || []).some((s) => s.id === "facturation");
    }
    if (avecReglage) contenu.append(blocReglage());

    panneau.replaceChildren(fermer, contenu);
    if (memeVue) panneau.scrollTop = defilement;
    panneau.hidden = false;
    if (type !== "catalogue") grand = false;
    document.body.classList.add("panneau-ouvert");
    document.body.classList.toggle("panneau-catalogue", type === "catalogue");
    document.body.classList.toggle("panneau-grand", type === "catalogue" && grand);
    if (surSaisie) {
      const zone = panneau.querySelector("textarea[data-saisie]");
      if (zone) { zone.focus(); zone.setSelectionRange(debut, debut); }
    }
    surFiltre();
  }

  // --- Réglage de la charge maximum et « Me conseiller ».
  function blocReglage() {
    const bloc = el("section", "reglage");
    bloc.append(el("h3", "", "Charge maximum"));
    bloc.append(el("label", "reglage-label", "Charge maximum pour lancer une nouvelle étape"));

    const rangee = el("div", "reglage-rangee");
    const curseur = document.createElement("input");
    curseur.type = "range";
    curseur.min = "30"; curseur.max = "95"; curseur.step = "5";
    const c0 = barre.charge();
    curseur.value = String(c0 && c0.max ? Math.round(c0.max / 5) * 5 : 75);
    const valeur = el("output", "reglage-valeur", curseur.value + " %");
    const enregistrer = el("button", "bouton", "Enregistrer");
    enregistrer.type = "button";
    rangee.append(curseur, valeur, enregistrer);
    const etatMessage = el("p", "reglage-message", "");
    etatMessage.setAttribute("aria-live", "polite");

    curseur.addEventListener("input", () => { valeur.textContent = curseur.value + " %"; });

    async function enregistrerValeur(v) {
      try {
        const r = await fetch(urlProjet("/api/reglages"), {
          method: "POST",
          headers: {"Content-Type": "application/json", "X-Bureau": "1"},
          body: JSON.stringify({charge_max: v}),
        });
        if (!r.ok) {
          let m = `Refusé (${r.status}).`;
          try { m = (await r.json()).erreur || m; } catch { /* corps absent */ }
          etatMessage.textContent = m;
          return false;
        }
        etatMessage.textContent = `Enregistré : ${v} %.`;
        await barre.rafraichirCharge();
        return true;
      } catch {
        etatMessage.textContent = "Serveur du bureau injoignable.";
        return false;
      }
    }
    enregistrer.addEventListener("click", () => enregistrerValeur(Number(curseur.value)));

    const conseiller = el("button", "bouton secondaire", "Me conseiller");
    conseiller.type = "button";
    const zoneConseil = el("div", "conseil");
    zoneConseil.hidden = true;
    conseiller.addEventListener("click", async () => {
      try {
        const r = await fetch(urlProjet("/api/conseil"), {cache: "no-store"});
        const c = await r.json();
        const v = Math.max(30, Math.min(95, Math.round(c.valeur / 5) * 5));
        const phrase = el("p", "", `Je conseille ${c.valeur} %. ${c.explication}`);
        const appliquer = el("button", "bouton", "Appliquer");
        appliquer.type = "button";
        appliquer.addEventListener("click", async () => {
          curseur.value = String(v);
          valeur.textContent = v + " %";
          await enregistrerValeur(v);
        });
        zoneConseil.replaceChildren(phrase, appliquer);
        zoneConseil.hidden = false;
      } catch {
        zoneConseil.replaceChildren(el("p", "", "Le conseil n'a pas pu être calculé."));
        zoneConseil.hidden = false;
      }
    });

    bloc.append(rangee, etatMessage, conseiller, zoneConseil);
    bloc.append(el("p", "note", "Les sessions cloud ne comptent pas : seule la charge de cet ordinateur est mesurée."));
    return bloc;
  }

  // --- Boutons de la barre : « + Nouvelle fonctionnalité » et « Fonctionnalités ».
  barre.boutonNouvelle.addEventListener("click", () => { nouvelle.envoi = null; ouvrirPanneau("fonctionnalite", null); });
  barre.boutonFonctions.addEventListener("click", () => ouvrirPanneau("fonctionnalites", null));
  barre.surCatalogue((id) => ouvrirCatalogue(id));

  // --- Souris.
  let attente = null;
  conteneur.addEventListener("pointermove", (ev) => {
    if (attente || ev.pointerType === "touch") return;   // au doigt, pas de survol : un toucher est un clic
    attente = requestAnimationFrame(() => {
      attente = null;
      const choix = sc.pointer(ev);
      const cliquable = ["agent", "postit", "file", "attente", "service", "direction", "partenaires", "kanban"].includes(choix.type);
      conteneur.style.cursor = cliquable ? "pointer" : "";
      if (choix.type === "agent") montrerCarte(choix, ev.clientX, ev.clientY);
      else cacherCarte();
    });
  });
  conteneur.addEventListener("pointerleave", cacherCarte);

  conteneur.addEventListener("click", (ev) => {
    const etiquette = ev.target?.closest?.(".etiquette[data-type]");     // le prénom d'un agent, au-dessus de sa tête
    const choix = etiquette ? {type: etiquette.dataset.type, id: etiquette.dataset.id} : sc.pointer(ev);
    cacherCarte();
    if (choix.type === "agent") {
      // au travail : directement sa tâche ; libre (ou le Chef) : sa fiche, avec l'historique de ses tâches
      const a = (etat()?.agents || []).find((x) => x.id === choix.id);
      const tache = a && !a.chef && a.statut !== "libre" ? (a.taches || [])[0] : null;
      if (tache) ouvrirPanneau("tache", tache); else ouvrirPanneau("agent", choix.id);
    }
    else if (choix.type === "postit") ouvrirPanneau("tache", choix.id);
    else if (choix.type === "file") ouvrirPanneau("file", choix.id);
    else if (choix.type === "attente") ouvrirPanneau("attente", null);
    else if (choix.type === "service" || choix.type === "direction") ouvrirPanneau(choix.type, choix.id);
    else if (choix.type === "partenaires") ouvrirPanneau("partenaires", null);
    else if (choix.type === "kanban" && etat()) ouvrirKanban(etat(), (id) => { retourListe = false; ouvrirPanneau("tache", id); });
    else fermerPanneau();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    const cible = ev.target;
    if ((cible?.tagName === "INPUT" || cible?.tagName === "TEXTAREA") && cible.value) return;   // Échap dans un champ rempli : rien ne se perd
    cacherCarte();
    if (grand && panneauOuvert?.type === "catalogue") { grand = false; ouvrirPanneau("catalogue", panneauOuvert.id); return; }
    fermerPanneau();
  });

  const api = {
    // À chaque nouvel état : pastille et panneau ouvert tenus à jour (sauf pendant la saisie du réglage).
    // Ouvre la vue liste, ou la ferme si elle est déjà ouverte.
    basculerListe() {
      if (panneauOuvert?.type === "liste") fermerPanneau(); else ouvrirPanneau("liste", null);
    },
    filtre: filtreActif,
    maj(e) {
      e = appliquerEnvoyees(e);
      // Une discussion neuve : dès que le relevé montre la fonctionnalité créée, on l'ouvre.
      if (panneauOuvert?.type === "fonctionnalite" && panneauOuvert.id === null && nouvelle.envoi) {
        const id = nouvelleApparue(nouvelle.envoi.avant, e, nouvelle.envoi.texte);
        if (id) { nouvelle.envoi = null; ouvrirPanneau("fonctionnalite", id); }
      }
      const n = e.directeur ? e.directeur.total : (e.decisions || 0);
      pastille.textContent = String(n);
      pastille.title = n === 1 ? "1 décision attend le Directeur" : `${n} décisions attendent le Directeur`;
      pastilleEtiquette.visible = n > 0;
      const saisieOuverte = panneauOuvert?.type === "fonctionnalite" && panneau.contains(document.activeElement)
        && document.activeElement?.dataset?.saisie === "1";   // la saisie se redessine en gardant le curseur
      if (panneauOuvert && (saisieOuverte || !panneau.contains(document.activeElement))) {
        const {type, id} = panneauOuvert;
        if ((type === "fonctionnalite" || type === "catalogue") && id !== null
            && !(e.fonctionnalites || []).some((f) => f.id === id)) fermerPanneau();
        else if (type === "service" && !(e.services || []).some((s) => s.id === id)) fermerPanneau();
        else if (type === "partenaires" && !e.partenaires) fermerPanneau();
        else if (type === "agent" && !(e.agents || []).some((a) => a.id === id)) fermerPanneau();
        else if (type === "tache" && !(e.taches || []).some((t) => t.id === id)) fermerPanneau();
        else if (type === "file" && !(e.taches || []).some((t) => t.id === id)
                 && !(e.file?.visibles || []).some((q) => q.id === id)) fermerPanneau();
        else if (signature(panneauOuvert.type, panneauOuvert.id, e) !== signaturePanneau) ouvrirPanneau(panneauOuvert.type, panneauOuvert.id);
      }
    },
  };
  // Une validation envoyée (ou dont l'envoi a échoué) : liste et compteur redessinés tout de suite, sans attendre la relecture.
  surEnvoyees(() => { const e = etatBrut(); if (e) api.maj(e); });
  return api;
}
