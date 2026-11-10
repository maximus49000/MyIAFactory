// Onglet « Connaissances » d'un dossier de service : les connaissances de tous ses agents, groupées par agent,
// ce qui circule entre agents (« partagée », « appris du retour de … »), et qui n'a rien reçu sur la période.
// Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {dateFr, libellePeriode, tronquer} from "./texte.js";
import {challengeDe} from "./actions.js";
import {enAttenteCible} from "./challenge.js";

const JOUR_MS = 24 * 3600 * 1000;
const DUREES = {"7j": 7 * JOUR_MS, "30j": 30 * JOUR_MS};

// Vrai si la date (texte ISO) tombe dans la période ; une date illisible n'y tombe jamais.
export function dansLaPeriode(date, periode, maintenant = new Date()) {
  if (typeof date !== "string" || !date) return false;
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return false;
  if (periode === "aujourdhui") return d.toDateString() === maintenant.toDateString();
  return d.getTime() >= maintenant.getTime() - (DUREES[periode] ?? DUREES["7j"]);
}

// Date à laquelle une connaissance partagée a été reçue : la sienne, sinon celle du retour le plus récent.
function dateRecue(c) {
  if (c.date) return c.date;
  const retours = (c.appris_de || []).map((a) => a.retour).filter((x) => typeof x === "string" && x);
  return retours.sort().at(-1) || null;
}

// Agents présents du service qui n'ont reçu aucune connaissance d'un autre agent (de tout le projet) sur la période.
export function agentsSansApport(savoir, service, periode, maintenant = new Date()) {
  return (savoir || []).filter((s) => s.service === service && s.present
    && !(s.connaissances || []).some((c) => c.partagee && dansLaPeriode(dateRecue(c), periode, maintenant)));
}

// « appris du retour de Hugo (service QA) sur « Export CSV » » : une ligne par source.
export function provenances(c, service, nomsServices = {}) {
  return (c.appris_de || []).map((a) => {
    let t = `appris du retour de ${a.prenom || a.agent}`;
    if (a.service && a.service !== service) t += ` (service ${nomsServices[a.service] || a.service})`;
    const tache = a.titre || a.tache;
    if (tache) t += ` sur « ${tache} »`;
    return t;
  });
}

function carteConnaissance(ctx, c, service, noms, prenom) {
  const e = ctx.etat;
  const li = el("li", "connaissance");
  li.append(el("div", "connaissance-texte", c.texte));
  const meta = el("div", "lecon-meta");
  const bouts = [];
  if (c.date) bouts.push(dateFr(c.date) || c.date);
  if (c.lecon) bouts.push("leçon validée");
  const origine = c.origine ? (e.challenges || []).find((x) => x.id === c.origine) : null;
  if (origine) bouts.push(`issue du challenge « ${tronquer(origine.texte, 60)} »`);
  else if (c.origine) bouts.push(`origine : ${tronquer(c.origine, 60)}`);
  meta.textContent = bouts.join(" · ");
  if (bouts.length) li.append(meta);
  const marques = el("div", "marques");
  if (c.partagee) marques.append(el("span", "marque partagee", "partagée"));
  if (c.probleme_revenu) marques.append(el("span", "marque revenu", "problème revenu"));
  if (marques.childNodes.length) li.append(marques);
  for (const p of provenances(c, service, noms)) li.append(el("div", "provenance", p));
  const cible = {type: "connaissance", id: c.id};
  const existe = challengeDe(e, cible);
  const b = el("button", "bouton secondaire petit",
    existe ? "Voir le challenge" : (enAttenteCible(cible) ? "Demande envoyée" : "Challenger"));
  b.type = "button";
  b.disabled = !existe && enAttenteCible(cible);  // ne renvoie rien tant que le relevé ne le montre pas
  b.addEventListener("click", () => ctx.challenger(cible, `Connaissance de ${prenom} : « ${c.texte} »`, []));
  li.append(b);
  return li;
}

// contenuConnaissances(contexte, conteneur, service, periode) — `ctx.challenger(cible, constat, taches)` ouvre le volet.
export function contenuConnaissances(ctx, conteneur, service, periode) {
  const e = ctx.etat;
  const noms = Object.fromEntries((e.services || []).map((s) => [s.id, s.nom]));
  const siens = (e.savoir || []).filter((s) => s.service === service);
  const total = siens.reduce((n, s) => n + (s.connaissances || []).length, 0);
  conteneur.append(el("div", "carte-sous-titre", `Connaissances du service (${total})`));
  if (!total) conteneur.append(el("p", "vide", "Aucune connaissance pour ce service."));
  for (const s of siens) {
    if (!(s.connaissances || []).length) continue;
    conteneur.append(el("h4", "agent-savoir", s.prenom + (s.present ? "" : " · parti du bureau")));
    const ul = el("ul", "liste-partie");
    for (const c of s.connaissances) ul.append(carteConnaissance(ctx, c, service, noms, s.prenom));
    conteneur.append(ul);
  }
  const sans = agentsSansApport(e.savoir, service, periode);
  conteneur.append(el("div", "carte-sous-titre", `Rien reçu des autres agents · ${libellePeriode(periode)}`));
  conteneur.append(el("p", sans.length ? "avertissement" : "note", sans.length
    ? `${sans.map((s) => s.prenom).join(", ")} : aucune connaissance reçue d'un autre agent sur la période (n'apprend peut-être pas).`
    : "Chaque agent présent a reçu au moins une connaissance d'un autre agent sur la période."));
}
