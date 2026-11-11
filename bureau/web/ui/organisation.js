// Une décision « organisation » au bureau du Directeur : ce qui change dans l'organisation du projet (services
// ajoutés, colonnes qui changent, agents, coût). « Accepter » et « Refuser » envoient une demande, jamais un
// changement direct. Tout texte venu du projet passe par textContent.

import {el} from "./dom.js";
import {euros, tokens} from "./texte.js";

const liste = (v) => (Array.isArray(v) ? v : []);

// Le coût estimé d'un changement : « 20 k à 60 k tokens, ≈ 0,40 € à ≈ 1,20 € » ; « prix inconnu » sans euros.
export function libelleCout(cout) {
  const t = liste(cout?.tokens);
  const jetons = t.length === 2 ? `${tokens(t[0])} à ${tokens(t[1])} tokens` : "tokens inconnus";
  const e = liste(cout?.euros);
  return `${jetons}, ${e.length === 2 ? `${euros(e[0])} à ${euros(e[1])}` : "prix inconnu"}`;
}

// Ce que la décision change, par rapport à l'organisation actuelle (`etat.services` et `etat.colonnes`).
export function resumeOrganisation(decision, etat) {
  const o = decision?.organisation || {};
  const servicesActuels = new Set(liste(etat?.services).map((s) => s?.id));
  const colonnes = new Map(liste(etat?.colonnes).map((c) => [c?.id, c]));
  const flux = liste(o.flux);
  const nouvelles = flux.filter((e) => !colonnes.has(e?.id)).map((e) => ({id: e.id, nom: e.nom, etat: "ajoutée"}));
  const changees = flux.filter((e) => colonnes.has(e?.id) && (colonnes.get(e.id).nom !== e.nom))
    .map((e) => ({id: e.id, nom: e.nom, etat: "renommée"}));
  const gardees = new Set(flux.map((e) => e?.id));
  const retirees = liste(etat?.colonnes).filter((c) => !c?.terminee && c?.id !== "cadrage" && !gardees.has(c?.id))
    .map((c) => ({id: c.id, nom: c.nom, etat: "retirée"}));
  return {
    services: liste(o.services).filter((s) => !servicesActuels.has(s?.id)).map((s) => ({id: s.id, nom: s.nom})),
    colonnes: [...nouvelles, ...changees, ...retirees],
    agents: liste(o.agents).map((a) => ({cle: a.cle, prenom: a.prenom || null, role: a.role, modele: a.modele, lieu: a.lieu})),
    cout: libelleCout(o.cout),
  };
}

export function demandeOrganisation(decision, verdict) {
  return {type: "organisation", decision, verdict};
}

function liste_(titre, lignes) {
  const bloc = el("div", "organisation-bloc");
  bloc.append(el("strong", "", titre));
  const ul = el("ul", "organisation-liste");
  for (const t of lignes) ul.append(el("li", "", t));
  bloc.append(ul);
  return bloc;
}

// `bouton(libelle, classe, fabrique)` fabrique un bouton qui envoie la demande (voir decisions.js).
export function rendreOrganisation(ctx, d, bouton) {
  const r = resumeOrganisation(d, ctx.etat);
  const li = el("li", "decision-organisation");
  li.append(el("div", "decision-texte", d.texte));
  if (r.services.length) li.append(liste_("Services ajoutés", r.services.map((s) => s.nom)));
  if (r.colonnes.length) li.append(liste_("Colonnes qui changent", r.colonnes.map((c) => `${c.nom} (${c.etat})`)));
  if (r.agents.length) {
    li.append(liste_("Agents", r.agents.map((a) => [a.prenom || a.cle, a.role, a.modele, a.lieu].join(" · "))));
  }
  li.append(el("div", "lecon-meta", "Coût estimé : " + r.cout));
  if (ctx.etat.agir) {
    const rangee = el("div", "lecon-boutons");
    rangee.append(bouton("Accepter", "bouton", () => demandeOrganisation(d.id, "accepter")),
                  bouton("Refuser", "bouton secondaire", () => demandeOrganisation(d.id, "refuser")));
    li.append(rangee);
  }
  return li;
}

