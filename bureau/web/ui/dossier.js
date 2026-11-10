// Le dossier d'un service : en-tête (nom, période), onglets. Tâches est toujours là ; un onglet sans donnée est masqué.
// Onglet et période choisis sont gardés le temps de la session.

import {el} from "./dom.js";
import {tronquer, ilYA, PERIODES, PERIODE_DEFAUT, libellePeriode} from "./texte.js";
import {contenuFacturation, chargerFacturation, serviceFacture, coutEnClair} from "./facturation.js";
import {challengesDuService} from "./actions.js";
import {contenuConnaissances} from "./connaissances.js";
import {contenuKpi, rappelAlertes} from "./kpi.js";
import {contenuChallenge} from "./challenge.js";

const MAX_TITRE = 90;
const STATUTS = {travail: "au travail", sans_nouvelles: "sans nouvelles", libre: "libre"};
// `challenge` : le volet « Challenger » ouvert ({service, cible, constat, taches}) ou null.
const choix = {onglet: "taches", periode: PERIODE_DEFAUT, challenge: null};

// Les onglets disponibles, dans l'ordre.
export function ongletsDisponibles(etat) {
  const d = etat?.dossier || {};
  const l = [{id: "taches", libelle: "Tâches"}];
  if (d.connaissances) l.push({id: "connaissances", libelle: "Connaissances"});
  if (d.kpi) l.push({id: "kpi", libelle: "KPI"});
  if (d.facturation) l.push({id: "facturation", libelle: "Facturation"});
  return l;
}

function contenuTaches(ctx, conteneur, service) {
  const e = ctx.etat;
  if (e.dossier?.kpi) rappelAlertes(ctx, conteneur, service, choix.periode);
  // Tous les challenges du service : on peut toujours rouvrir un challenge, même si son alerte est levée
  // ou si sa source est sortie de la période.
  const challenges = challengesDuService(e, service);
  if (challenges.length) {
    conteneur.append(el("div", "carte-sous-titre", `Challenges (${challenges.length})`));
    const lc = el("ul", "liste-cout");
    for (const {challenge: c, aDecider} of challenges) {
      const li = el("li", "source");
      const texte = el("span", "source-texte", tronquer(c.texte, 140));
      texte.append(el("span", "ligne-detail", aDecider ? `${aDecider} solution${aDecider > 1 ? "s" : ""} à décider`
        : ((c.solutions || []).length ? "tout est décidé" : "pas encore de solution")));
      const b = el("button", "bouton secondaire", "Ouvrir");
      b.type = "button";
      b.addEventListener("click", () => ctx.challenger(c.cible, c.texte, []));
      li.append(texte, b);
      lc.append(li);
    }
    conteneur.append(lc);
  }
  const ids = new Set((e.agents || []).filter((a) => a.service === service).map((a) => a.id));
  const taches = (e.taches || []).filter((t) => t.active && ids.has(t.agent));
  conteneur.append(el("div", "carte-sous-titre", `Tâches en cours (${taches.length})`));
  const liste = el("ul", "liste-taches");
  if (!taches.length) liste.append(el("li", "vide", "Aucune tâche en cours"));
  const couts = [];
  for (const t of taches) {
    const agent = (e.agents || []).find((a) => a.id === t.agent);
    const li = el("li", "");
    const b = el("button", "ligne-tache");
    b.type = "button";
    const cout = el("span", "ligne-cout-tache", "");
    b.append(el("span", "ligne-titre", tronquer(t.titre, MAX_TITRE)),
             el("span", "ligne-detail", `${agent?.prenom || "?"}${t.etape ? " · " + tronquer(t.etape, 30) : ""} · ${ilYA(t.maj)}`),
             cout);
    b.addEventListener("click", () => ctx.ouvrirTache(t.id));
    li.append(b);
    liste.append(li);
    couts.push([t.id, cout]);
  }
  conteneur.append(liste);
  if (e.dossier?.facturation && taches.length) {
    chargerFacturation(choix.periode).then((f) => {
      const s = serviceFacture(f, service);
      for (const [id, cible] of couts) {
        if (s && s.taches[id] && cible.isConnected) cible.textContent = coutEnClair(s.taches[id]);
      }
    }, () => { /* le coût manque, la liste reste */ });
  }
}

// contenuDossier(contexte, conteneur, service, onglet) — `onglet` force l'onglet ; sinon le dernier choisi.
export function contenuDossier(ctx, conteneur, service, onglet) {
  const e = ctx.etat;
  const s = (e.services || []).find((x) => x.id === service);
  if (onglet) choix.onglet = onglet;
  if (onglet || choix.challenge?.service !== service) choix.challenge = null;
  const ctxDossier = {...ctx, challenger: (cible, constat, taches) => {
    choix.challenge = {service, cible, constat, taches};
    dessiner();
  }};
  const onglets = ongletsDisponibles(e);
  if (!onglets.some((o) => o.id === choix.onglet)) choix.onglet = "taches";

  conteneur.append(el("h2", "", tronquer(s?.nom ?? service, 40)));

  const entete = el("div", "dossier-entete");
  const select = document.createElement("select");
  select.setAttribute("aria-label", "Période");
  for (const p of PERIODES) {
    const o = el("option", "", libellePeriode(p));
    o.value = p;
    select.append(o);
  }
  select.value = choix.periode;
  entete.append(select);
  conteneur.append(entete);

  const barre = el("div", "onglets");
  barre.setAttribute("role", "tablist");
  const zone = el("div", "dossier-zone");
  conteneur.append(barre, zone);

  function dessiner() {
    barre.replaceChildren();
    for (const o of onglets) {
      const b = el("button", "onglet" + (o.id === choix.onglet ? " actif" : ""), o.libelle);
      b.type = "button";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(o.id === choix.onglet));
      b.addEventListener("click", () => { choix.onglet = o.id; choix.challenge = null; dessiner(); });
      barre.append(b);
    }
    zone.replaceChildren();
    entete.hidden = !e.dossier?.facturation && !e.dossier?.connaissances && !e.dossier?.kpi;
    if (choix.challenge) {
      contenuChallenge(ctxDossier, zone, {...choix.challenge, retour: () => { choix.challenge = null; dessiner(); }});
    } else if (choix.onglet === "facturation") contenuFacturation(ctxDossier, zone, service, choix.periode);
    else if (choix.onglet === "kpi") contenuKpi(ctxDossier, zone, service, choix.periode);
    else if (choix.onglet === "connaissances") contenuConnaissances(ctxDossier, zone, service, choix.periode);
    else contenuTaches(ctxDossier, zone, service);
  }
  select.addEventListener("change", () => { choix.periode = select.value; dessiner(); });
  dessiner();

  const agents = (e.agents || []).filter((a) => a.service === service);
  conteneur.append(el("div", "carte-sous-titre", `Agents (${agents.length})`));
  const liste = el("ul", "liste-agents");
  if (!agents.length) liste.append(el("li", "vide", "Personne au bureau"));
  for (const a of agents) {
    const li = el("li", "");
    const puce = el("span", "puce");
    puce.style.background = a.couleur || "#999";
    li.append(puce, el("span", "nom", a.prenom + (a.lieu === "cloud" ? " ☁" : "")),
              el("span", "detail", `${a.modele || "?"} · ${STATUTS[a.statut] || a.statut || "—"}`));
    liste.append(li);
  }
  conteneur.append(liste);
}
