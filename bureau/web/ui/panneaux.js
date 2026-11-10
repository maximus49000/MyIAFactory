// Cartes (survol d'un agent, clic sur un post-it) et panneau de droite (service, direction).
// Lecture seule, sauf le réglage de la charge maximum. Tout texte venu du serveur passe par textContent.

import {CSS2DObject} from "three/addons/renderers/CSS2DRenderer.js";
import {tronquer, ilYA} from "./texte.js";

const STATUTS = {travail: "au travail", sans_nouvelles: "sans nouvelles", libre: "libre"};
const MAX_TITRE = 90;

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

function ligne(cle, valeur) {
  const l = el("div", "ligne");
  l.append(el("span", "cle", cle), el("span", "val", valeur));
  return l;
}

// opts : {conteneur, carte, panneau, sc, plan, etat: () => état courant, barre}
export function creerPanneaux({conteneur, carte, panneau, sc, plan, etat, barre}) {
  let epingle = null;          // {type, id} de la carte épinglée par un clic
  let panneauOuvert = null;    // {type, id}
  let signaturePanneau = "";   // ce que le panneau ouvert montre, pour savoir quand le redessiner

  const signature = (type, id, e) => JSON.stringify(type === "service"
    ? (e.agents || []).filter((a) => a.service === id).map((a) => [a.id, a.prenom, a.modele, a.statut, a.lieu, a.couleur])
    : e.decisions || 0);

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
    c.append(ligne("Modèle", a.modele || "?"));
    c.append(ligne("Lieu", a.lieu === "cloud" ? "cloud ☁" : "local"));
    c.append(ligne("Statut", STATUTS[a.statut] || a.statut || "—"));
    const titres = (a.taches || []).map((id) => (e.taches || []).find((t) => t.id === id)).filter(Boolean);
    const liste = el("ul", "carte-taches");
    if (titres.length === 0) liste.append(el("li", "vide", "Aucune tâche en cours"));
    for (const t of titres) liste.append(el("li", "", tronquer(t.titre, MAX_TITRE)));
    c.append(el("div", "carte-sous-titre", "Tâches en cours"), liste);
    return c;
  }

  function cartePostit(t, e) {
    const c = el("div", "carte-contenu");
    c.append(el("div", "carte-titre", tronquer(t.titre, MAX_TITRE)));
    const col = (e.colonnes || []).find((x) => x.id === t.colonne);
    c.append(ligne("Colonne", col ? tronquer(col.nom, 30) : "—"));
    const ag = (e.agents || []).find((x) => x.id === t.agent);
    c.append(ligne("Agent", ag ? ag.prenom : "personne"));
    c.append(ligne("Étape", t.etape ? tronquer(t.etape, MAX_TITRE) : "—"));
    c.append(ligne("Mise à jour", ilYA(t.maj)));
    return c;
  }

  function contenuCarte(choix) {
    const e = etat();
    if (!e || !choix) return null;
    if (choix.type === "agent") {
      const a = (e.agents || []).find((x) => x.id === choix.id);
      return a ? carteAgent(a, e) : null;
    }
    if (choix.type === "postit") {
      const t = (e.taches || []).find((x) => x.id === choix.id);
      if (t) return cartePostit(t, e);
      const q = (e.file?.visibles || []).find((x) => x.id === choix.id);
      if (q) {
        const c = el("div", "carte-contenu");
        c.append(el("div", "carte-titre", tronquer(q.titre, MAX_TITRE)), ligne("File d'attente", "pas encore commencée"));
        return c;
      }
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
    document.body.classList.remove("panneau-ouvert");
  }

  function ouvrirPanneau(type, id) {
    const e = etat();
    if (!e) return;
    panneauOuvert = {type, id};
    signaturePanneau = signature(type, id, e);
    const contenu = el("div", "panneau-contenu");
    const fermer = el("button", "panneau-fermer", "×");
    fermer.type = "button";
    fermer.setAttribute("aria-label", "Fermer");
    fermer.addEventListener("click", fermerPanneau);

    let avecReglage = false;
    if (type === "service") {
      const s = (e.services || []).find((x) => x.id === id);
      if (!s) { fermerPanneau(); return; }
      contenu.append(el("h2", "", tronquer(s.nom, 40)));
      const agents = (e.agents || []).filter((a) => a.service === id);
      contenu.append(el("div", "carte-sous-titre", `Agents (${agents.length})`));
      const liste = el("ul", "liste-agents");
      if (agents.length === 0) liste.append(el("li", "vide", "Personne au bureau"));
      for (const a of agents) {
        const li = el("li", "");
        const pastilleCouleur = el("span", "puce");
        pastilleCouleur.style.background = a.couleur || "#999";
        const nom = el("span", "nom", a.prenom + (a.lieu === "cloud" ? " ☁" : ""));
        const detail = el("span", "detail", `${a.modele || "?"} · ${STATUTS[a.statut] || a.statut}`);
        li.append(pastilleCouleur, nom, detail);
        liste.append(li);
      }
      contenu.append(liste);
      contenu.append(el("p", "note", "Les documents de ce service arriveront avec le projet 2."));
      avecReglage = id === "facturation";
    } else {
      contenu.append(el("h2", "", "Direction"));
      const n = e.decisions || 0;
      contenu.append(el("p", "decisions", n === 0 ? "Aucune décision n'attend le Directeur."
        : n === 1 ? "1 décision attend le Directeur." : `${n} décisions attendent le Directeur.`));
      contenu.append(el("p", "note", "La liste détaillée des décisions arrivera avec le projet 2."));
      avecReglage = !(e.services || []).some((s) => s.id === "facturation");
    }
    if (avecReglage) contenu.append(blocReglage());

    panneau.replaceChildren(fermer, contenu);
    panneau.hidden = false;
    document.body.classList.add("panneau-ouvert");
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
        const r = await fetch("/api/reglages", {
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
        const r = await fetch("/api/conseil", {cache: "no-store"});
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

  // --- Souris.
  let attente = null;
  conteneur.addEventListener("pointermove", (ev) => {
    if (attente) return;
    attente = requestAnimationFrame(() => {
      attente = null;
      const choix = sc.pointer(ev);
      const cliquable = ["agent", "postit", "service", "direction"].includes(choix.type);
      conteneur.style.cursor = cliquable ? "pointer" : "";
      if (epingle) return;
      if (choix.type === "agent") montrerCarte(choix, ev.clientX, ev.clientY);
      else cacherCarte();
    });
  });
  conteneur.addEventListener("pointerleave", () => { if (!epingle) cacherCarte(); });

  conteneur.addEventListener("click", (ev) => {
    const choix = sc.pointer(ev);
    epingle = null;
    if (choix.type === "agent" || choix.type === "postit") {
      epingle = {type: choix.type, id: choix.id};
      montrerCarte(choix, ev.clientX, ev.clientY);
      return;
    }
    cacherCarte();
    if (choix.type === "service" || choix.type === "direction") ouvrirPanneau(choix.type, choix.id);
    else fermerPanneau();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    epingle = null;
    cacherCarte();
    fermerPanneau();
  });

  return {
    // À chaque nouvel état : pastille, carte épinglée et panneau ouvert tenus à jour (sauf pendant la saisie du réglage).
    maj(e) {
      const n = e.decisions || 0;
      pastille.textContent = String(n);
      pastille.title = n === 1 ? "1 décision attend le Directeur" : `${n} décisions attendent le Directeur`;
      pastilleEtiquette.visible = n > 0;
      if (epingle) {
        const c = contenuCarte(epingle);
        if (c) carte.replaceChildren(c); else { epingle = null; cacherCarte(); }
      }
      if (panneauOuvert && !panneau.contains(document.activeElement)) {
        if (panneauOuvert.type === "service" && !(e.services || []).some((s) => s.id === panneauOuvert.id)) fermerPanneau();
        else if (signature(panneauOuvert.type, panneauOuvert.id, e) !== signaturePanneau) ouvrirPanneau(panneauOuvert.type, panneauOuvert.id);
      }
    },
  };
}
