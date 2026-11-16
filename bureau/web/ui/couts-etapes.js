// Le coût d'une fonctionnalité regroupé par étape du parcours : pour chaque étape, le nombre de passages, le
// sous-total, la part du total et la durée cumulée. Une correction suit son vocabulaire (Diagnostic → Correctif →
// Vérification → Validation → Livraison) ; une fonctionnalité, ses étapes dans l'ordre où elles ont eu lieu. Pur.

import {estCorrection, etapeCorrection, ETAPES_CORRECTION} from "./parcours-correction.js";
import {minutesDeTache} from "./couts.js";

const AUTRES = {cle: "autres", libelle: "Autres"};
const FIXES = {cadrage: "Cadrage", prototype: "Prototype", relecture: "Relecture", correction: "Retours et reprises",
               retour: "Retours et reprises", demande: "Demandes", environnement: "Installation du poste",
               challenge: "Challenge"};

// L'étape d'une tâche de coût : `{cle, libelle}`.
export function etapeDuCout(t, f, e) {
  if (estCorrection(f)) {
    const id = etapeCorrection(f.id, t.etape) || etapeCorrection(f.id, t.colonne);
    const x = ETAPES_CORRECTION.find((y) => y.id === id);
    return x ? {cle: x.id, libelle: x.libelle} : AUTRES;
  }
  const etape = String(t.etape || "");
  const pas = etape.match(/^(?:flux|validation):(.+)$/)?.[1];
  if (pas) {
    const nom = (e?.colonnes || []).find((c) => c.id === pas)?.nom;
    return {cle: "pas:" + pas, libelle: nom || pas.replace(new RegExp("^" + f?.id + "-"), "")};
  }
  const cle = etape === "retour" ? "correction" : etape;
  return FIXES[cle] ? {cle, libelle: FIXES[cle]} : AUTRES;
}

// Les groupes, dans l'ordre du parcours : `[{cle, libelle, passages, total, sans_prix, minutes, inconnues, part,
// taches}]`. `taches` : les lignes de `/api/couts?fonctionnalite=…` (avec `etape`, `debut`, `fin`).
export function regrouperParEtape(taches, f, e) {
  const groupes = new Map();
  for (const t of taches || []) {
    const {cle, libelle} = etapeDuCout(t, f, e);
    if (!groupes.has(cle)) groupes.set(cle, {cle, libelle, passages: 0, total: 0, sans_prix: 0, minutes: 0, inconnues: 0,
                                             taches: []});
    const g = groupes.get(cle);
    g.passages += 1;
    g.total += typeof t.total === "number" ? t.total : 0;
    g.sans_prix += t.sans_prix || 0;
    const m = minutesDeTache({debut: t.debut, fin: t.fin, colonne: "fait"});
    if (m === null) g.inconnues += 1; else g.minutes += m;
    g.taches.push(t);
  }
  let liste = [...groupes.values()];
  if (estCorrection(f)) {        // l'ordre du parcours d'une correction, les « Autres » à la fin
    const ordre = ETAPES_CORRECTION.map((x) => x.id);
    const rang = (g) => (ordre.includes(g.cle) ? ordre.indexOf(g.cle) : ordre.length);
    liste = liste.sort((a, b) => rang(a) - rang(b));
  } else {                       // l'ordre où les étapes ont eu lieu, les « Autres » à la fin
    liste = liste.filter((g) => g.cle !== AUTRES.cle).concat(liste.filter((g) => g.cle === AUTRES.cle));
  }
  const total = liste.reduce((s, g) => s + g.total, 0);
  for (const g of liste) g.part = total > 0 ? g.total / total : 0;
  return liste;
}

// Pourquoi une tâche a été refaite, d'après son journal (celui du relevé) : « refait : rien à valider », « retour du
// Directeur »… ; null si le journal ne le dit pas.
export function raisonDuPassage(tache) {
  const textes = (tache?.journal || []).map((j) => String(j?.texte ?? j ?? ""));
  if (textes.some((x) => /Rien à valider|sans dire ce qui doit marcher|Validation sans consigne/.test(x))) {
    return "refait : rien à valider";
  }
  if (textes.some((x) => /Retour de l'utilisateur|Consigne de l'utilisateur|remarque du Directeur|Renvoy/i.test(x))) {
    return "retour du Directeur";
  }
  return null;
}

// « 12 min », « 1 h 05 » ; null sans durée connue.
export function libelleMinutes(m, inconnues = 0, passages = 1) {
  if (inconnues >= passages) return null;
  return m < 1 ? "moins d'une minute" : m < 60 ? `${Math.floor(m)} min`
    : `${Math.floor(m / 60)} h ${String(Math.floor(m % 60)).padStart(2, "0")}`;
}
