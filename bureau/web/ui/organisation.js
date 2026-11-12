// Une décision « organisation » au bureau du Directeur : soit le workflow proposé pour une demande (étapes, agents
// recrutés avec leur modèle, services, coût, environnement du poste, case Fable par agent), soit une évolution de
// l'organisation du projet (services ajoutés, colonnes qui changent, agents, coût). Les boutons envoient une demande,
// jamais un changement direct. Tout texte venu du projet passe par textContent.

import {el} from "./dom.js";
import {euros, tokens} from "./texte.js";

const liste = (v) => (Array.isArray(v) ? v : []);
const plein = (t) => typeof t === "string" && t.trim() !== "";

// Le coût estimé d'un changement : « 20 k à 60 k tokens, ≈ 0,40 € à ≈ 1,20 € » ; « prix inconnu » sans euros.
export function libelleCout(cout) {
  const t = liste(cout?.tokens);
  const jetons = t.length === 2 ? `${tokens(t[0])} à ${tokens(t[1])} tokens` : "tokens inconnus";
  const e = liste(cout?.euros);
  return `${jetons}, ${e.length === 2 ? `${euros(e[0])} à ${euros(e[1])}` : "prix inconnu"}`;
}

// Les colonnes que le projet avait avant : celles de son workflow principal (une colonne d'un workflow de
// fonctionnalité n'est jamais « retirée » par une évolution du principal).
const duPrincipal = (c) => !c?.workflow || c.workflow === "principal";

// Ce que la décision change, par rapport à l'organisation actuelle (`etat.services` et `etat.colonnes`).
// Un workflow de fonctionnalité n'enlève rien : ses étapes (`<fonctionnalité>-<étape>`) s'ajoutent toutes.
export function resumeOrganisation(decision, etat) {
  const o = decision?.organisation || {};
  const servicesActuels = new Set(liste(etat?.services).map((s) => s?.id));
  const colonnes = new Map(liste(etat?.colonnes).map((c) => [c?.id, c]));
  const flux = liste(o.flux);
  const nouvelles = flux.filter((e) => !colonnes.has(e?.id)).map((e) => ({id: e.id, nom: e.nom, etat: "ajoutée"}));
  let changees = [], retirees = [];
  if (!o.workflow) {
    changees = flux.filter((e) => colonnes.has(e?.id) && (colonnes.get(e.id).nom !== e.nom))
      .map((e) => ({id: e.id, nom: e.nom, etat: "renommée"}));
    const gardees = new Set(flux.map((e) => e?.id));
    retirees = liste(etat?.colonnes).filter((c) => !c?.terminee && c?.id !== "cadrage" && duPrincipal(c) && !gardees.has(c?.id))
      .map((c) => ({id: c.id, nom: c.nom, etat: "retirée"}));
  }
  return {
    services: liste(o.services).filter((s) => !servicesActuels.has(s?.id)).map((s) => ({id: s.id, nom: s.nom})),
    colonnes: [...nouvelles, ...changees, ...retirees],
    agents: liste(o.agents).map((a) => ({cle: a.cle, prenom: a.prenom || null, role: a.role, modele: a.modele, lieu: a.lieu})),
    cout: libelleCout(o.cout),
  };
}

// Le workflow proposé en clair : ses étapes dans l'ordre (nom, rôle, service), son livrable, son genre.
export function resumeWorkflow(decision, etat) {
  const o = decision?.organisation || {};
  if (!o.workflow) return null;
  const services = new Map([...liste(etat?.services), ...liste(o.services)].map((s) => [s?.id, s?.nom]));
  return {
    genre: o.workflow.genre || null,
    genreNouveau: plein(o.workflow.genre_nouveau?.description) ? o.workflow.genre_nouveau.description : null,
    livrable: plein(o.livrable) ? o.livrable : null,
    etapes: liste(o.flux).map((e, i) => e?.validation === true
      ? {rang: i + 1, nom: e.nom, role: null, service: null, validation: true}   // le Directeur valide : ni rôle ni service
      : {rang: i + 1, nom: e.nom, role: e.role, service: services.get(e.service) || e.service || null}),
  };
}

// Les agents nouveaux de la proposition, avec le pourquoi de leur modèle ; la case Fable n'existe que pour ceux
// dont le moteur a dit `fable_suggere` (le Directeur reste seul à l'accorder, agent par agent).
export function agentsOrganisation(decision) {
  return liste(decision?.organisation?.agents).map((a) => ({
    cle: a.cle,
    nom: a.prenom || a.cle,
    ligne: [a.prenom || a.cle, a.role, a.modele, a.lieu].filter(Boolean).join(" · "),
    justification: plein(a.justification) ? a.justification : null,
    fableSuggere: a.fable_suggere === true,
  }));
}

// L'environnement du poste : chaque outil « déjà en place » (version) ou « à installer » (comment).
export function lignesEnvironnement(decision) {
  return liste(decision?.organisation?.environnement).filter((x) => x && plein(x.outil)).map((x) => {
    const enPlace = x.etat === "en_place";
    // la version lue et la version demandée côte à côte (elles disent déjà ce que dit la « raison » du moteur)
    const lue = plein(x.version) ? x.version : null;
    const demandee = plein(x.version_min) ? x.version_min : null;
    const versions = lue && demandee ? `version lue : ${lue} · version demandée : ${demandee}`
      : (demandee && !enPlace && !plein(x.raison) ? `version demandée : ${demandee}` : null);
    const raison = lue && demandee ? null : x.raison;
    const details = enPlace ? [raison, versions || x.version, x.chemin] : [raison, versions, x.installation];
    return {outil: x.outil, enPlace, pour: plein(x.pour) ? x.pour : null, lue, demandee,
            libelle: `${x.outil} : ${enPlace ? "déjà en place" : "à installer"}`,
            detail: details.filter(plein).join(" · ") || null,
            refuse: liste(x.refuses).length > 0};
  });
}

// `fable` : les clés des agents cochés (avec « accepter » seulement) ; `texte` : ce qu'il faut changer (« refuser »).
export function demandeOrganisation(decision, verdict, {texte, fable} = {}) {
  const d = {type: "organisation", decision, verdict};
  if (verdict === "refuser" && plein(texte)) d.texte = texte.trim();
  if (verdict === "accepter" && liste(fable).length) d.fable = [...fable];
  return d;
}

function liste_(titre, lignes) {
  const bloc = el("div", "organisation-bloc");
  bloc.append(el("strong", "", titre));
  const ul = el("ul", "organisation-liste");
  for (const t of lignes) {   // un texte, ou [texte, précision]
    const [texte, precision] = Array.isArray(t) ? t : [t];
    const item = el("li", "", texte);
    if (precision) item.append(el("div", "lecon-meta", precision));
    ul.append(item);
  }
  bloc.append(ul);
  return bloc;
}

function blocWorkflow(w) {
  const bloc = liste_("Workflow proposé", w.etapes.map((e) => `${e.rang}. ${e.nom}` + (e.validation ? " (validation du Directeur)"
    : e.role ? ` (${[e.role, e.service].filter(Boolean).join(", ")})` : "")));
  if (w.livrable) bloc.append(el("div", "lecon-meta", "Livrable : " + w.livrable));
  if (w.genre) bloc.append(el("div", "lecon-meta", "Genre : " + w.genre + (w.genreNouveau ? " (nouveau : " + w.genreNouveau + ")" : "")));
  return bloc;
}

// Une case par agent dont Fable est suggéré ; rend {bloc, cochees()} (`cochees()` : les clés cochées).
function casesFable(agents) {
  const suggeres = agents.filter((a) => a.fableSuggere);
  const cases = new Map();
  const bloc = el("div", "organisation-bloc");
  if (!suggeres.length) return {bloc: null, cochees: () => []};
  bloc.append(el("strong", "", "Fable : à vous de l'accorder"));
  for (const a of suggeres) {
    const etiquette = el("label", "organisation-fable");
    const c = document.createElement("input");
    c.type = "checkbox";
    cases.set(a.cle, c);
    etiquette.append(c, el("span", "", ` ${a.nom} : utiliser Fable (plus capable, plus cher)`));
    bloc.append(etiquette);
  }
  return {bloc, cochees: () => suggeres.filter((a) => cases.get(a.cle).checked).map((a) => a.cle)};
}

// `bouton(libelle, classe, fabrique, avant)` fabrique un bouton qui envoie la demande (voir decisions.js).
export function rendreOrganisation(ctx, d, bouton) {
  const r = resumeOrganisation(d, ctx.etat);
  const w = resumeWorkflow(d, ctx.etat);
  const agents = agentsOrganisation(d);
  const li = el("li", "decision-organisation");
  li.append(el("div", "decision-texte", d.texte));
  if (w) li.append(blocWorkflow(w));
  if (r.services.length) li.append(liste_("Services ajoutés", r.services.map((s) => s.nom)));
  if (!w && r.colonnes.length) li.append(liste_("Colonnes qui changent", r.colonnes.map((c) => `${c.nom} (${c.etat})`)));
  if (agents.length) {
    li.append(liste_(w ? "Agents recrutés" : "Agents", agents.map((a) => [a.ligne, a.justification])));
  }
  const environnement = lignesEnvironnement(d);
  if (environnement.length) {
    li.append(liste_("Environnement du poste", environnement.map((x) => [x.libelle, x.detail])));
  }
  li.append(el("div", "lecon-meta", "Coût estimé : " + r.cout));
  const fable = casesFable(agents);
  if (fable.bloc) li.append(fable.bloc);
  if (ctx.etat.agir) {
    const precision = document.createElement("textarea");
    precision.rows = 2;
    precision.maxLength = 3500;
    precision.placeholder = "Ce qu'il faut changer (pour « Refuser »)";
    precision.setAttribute("aria-label", "Ce qu'il faut changer");
    const rangee = el("div", "lecon-boutons");
    rangee.append(bouton("Accepter", "bouton", () => demandeOrganisation(d.id, "accepter", {fable: fable.cochees()})),
                  bouton("Refuser", "bouton secondaire", () => demandeOrganisation(d.id, "refuser", {texte: precision.value})));
    if (w) rangee.append(bouton("Abandonner la demande", "bouton secondaire", () => demandeOrganisation(d.id, "abandonner")));
    li.append(precision, rangee);
  }
  return li;
}
