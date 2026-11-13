// Le point de l'atelier, dans le panneau du Chef : qui fait quoi, depuis quand, sa dernière action ; ce qui attend le
// Directeur, ce qui est bloqué, ce que la charge retient. Tiré de l'état servi, sans appel d'IA : la réponse
// immédiate à « où en est-on ? ». `pointAtelier` est pur (testé avec node).

import {el} from "./dom.js";
import {auTravail, tronquer} from "./texte.js";
import {urlProjet} from "./projets.js";

const liste = (v) => (Array.isArray(v) ? v : []);
const MAX_TITRE = 90;

export function pointAtelier(etat, maintenant = new Date()) {
  const taches = liste(etat?.taches);
  const parId = new Map(taches.map((t) => [t?.id, t]));
  const agents = [];
  for (const a of liste(etat?.agents)) {
    if (a?.chef) continue;
    for (const id of liste(a?.taches)) {
      const t = parId.get(id);
      if (!t) continue;
      const travail = auTravail(t.travail, maintenant);
      agents.push({prenom: a.prenom || a.id || "?", tache: t.id, titre: tronquer(t.titre || "", MAX_TITRE),
                   cloud: a.lieu === "cloud",
                   etat: travail ? `au travail depuis ${travail.depuis}` + (travail.action ? ` · ${travail.action}` : "")
                     : t.attente ? t.attente
                     : a.statut === "sans_nouvelles" ? (a.bulle || "sans nouvelles")
                     : a.lieu === "cloud" ? "en cours dans sa session cloud" : "en cours"});
    }
  }
  const decisions = liste(etat?.decisions_projet).length
    + liste(etat?.fonctionnalites).reduce((n, f) => n + liste(f?.decisions).length, 0);
  const bloquees = taches.filter((t) => typeof t?.bloquee === "string" && t.bloquee.trim() && t.colonne !== "fait")
    .map((t) => ({tache: t.id, titre: tronquer(t.titre || "", MAX_TITRE)}));
  const retenue = typeof etat?.attente_charge?.texte === "string" ? etat.attente_charge.texte : null;
  return {agents, decisions, bloquees, retenue};
}

// Le bloc du panneau ; `ouvrirTache(id)` ouvre la tâche.
export function blocPoint(etat, ouvrirTache, maintenant = new Date()) {
  const p = pointAtelier(etat, maintenant);
  const bloc = el("div", "point-atelier");
  bloc.append(el("div", "carte-sous-titre", "Point de l'atelier"));
  const ul = el("ul", "liste-partie");
  if (!p.agents.length) ul.append(el("li", "vide", "Aucun agent au travail"));
  for (const a of p.agents) {
    const li = el("li", "");
    const lien = el("button", "lien-tache", `${a.prenom}${a.cloud ? " ☁" : ""} — ${a.titre}`);
    lien.type = "button";
    lien.addEventListener("click", () => ouvrirTache(a.tache));
    li.append(lien, el("div", "lecon-meta", a.etat));
    ul.append(li);
  }
  bloc.append(ul);
  const resume = [`${p.decisions} décision${p.decisions > 1 ? "s" : ""} attend${p.decisions > 1 ? "ent" : ""} le Directeur`];
  if (p.bloquees.length) resume.push(`${p.bloquees.length} tâche${p.bloquees.length > 1 ? "s" : ""} bloquée${p.bloquees.length > 1 ? "s" : ""}`);
  bloc.append(el("p", "lecon-meta", resume.join(" · ")));
  if (p.retenue) bloc.append(el("p", "carte-attente", p.retenue));
  return bloc;
}

// Les échanges avec le Chef : les questions envoyées sur sa tâche « Orchestration » et ses réponses, les plus récents
// d'abord. Pur.
export const TACHE_DU_CHEF = "orchestration";
export function echangesChef(etat, max = 10) {
  const t = liste(etat?.taches).find((x) => x?.id === TACHE_DU_CHEF);
  return liste(t?.retours).filter((r) => typeof r?.texte === "string" && r.texte.trim())
    .map((r) => ({t: r.t || null, question: r.texte.trim(),
                  reponse: typeof r.reponse === "string" && r.reponse.trim() ? r.reponse.trim() : null}))
    .reverse().slice(0, max);
}

// Les échanges que l'espace de direction montre encore : pas ceux marqués « Vu » (le panneau du Chef les garde). Pur.
export function echangesNonVus(etat, max = 10) {
  const vus = new Set(liste(etat?.echanges_vus));
  return echangesChef(etat, 50).filter((x) => !x.t || !vus.has(x.t)).slice(0, max);
}

// « Vu » : l'échange quitte l'espace de direction, sur tous les appareils (gardé par le bureau).
export async function marquerVu(t, fetchFn = fetch) {
  try {
    const r = await fetchFn(urlProjet("/api/echanges/vu"), {method: "POST",
      headers: {"X-Bureau": "1", "Content-Type": "application/json"}, body: JSON.stringify({t})});
    return r.ok;
  } catch { return false; }
}

// La liste des échanges. `direction` : sans ceux déjà vus, chacun avec son bouton « Vu » (réponse arrivée).
export function listeEchanges(etat, dateFr, max = 10, {direction = false, apresVu = null} = {}) {
  const ul = el("ul", "liste-partie echanges-chef");
  const echanges = direction ? echangesNonVus(etat, max) : echangesChef(etat, max);
  if (!echanges.length) ul.append(el("li", "vide", direction ? "Aucun échange à lire" : "Aucune question posée au Chef"));
  for (const x of echanges) {
    const li = el("li", "");
    li.append(el("div", "retour-texte", x.question),
              x.reponse ? el("div", "retour-reponse", x.reponse) : el("div", "retour-attente", "le Chef réfléchit…"),
              el("div", "retour-date", x.t ? dateFr(x.t) : ""));
    if (direction && x.reponse && x.t) {
      const vu = el("button", "bouton secondaire", "Vu");
      vu.type = "button";
      vu.addEventListener("click", async () => {
        vu.disabled = true;
        if (await marquerVu(x.t)) { li.remove(); if (apresVu) apresVu(); } else vu.disabled = false;
      });
      li.append(vu);
    }
    ul.append(li);
  }
  return ul;
}
