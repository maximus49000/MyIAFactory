// Un outil du poste « à installer », montré de la même façon partout (proposition de workflow, création du projet,
// décision « Environnement du poste à compléter ») : son objectif dans CE projet, le lien de téléchargement officiel
// (nouvel onglet), le mode opératoire numéroté et, si un agent peut l'installer seul, le bouton « Installer en
// autonomie ». Tout texte venu du projet passe par textContent ; un lien n'est jamais autre chose qu'une adresse https.

import {el} from "./dom.js";

const plein = (t) => typeof t === "string" && t.trim() !== "";
const liste = (v) => (Array.isArray(v) ? v : []);

// Une adresse https (jamais http, javascript:, data:…) ou null.
export function urlOfficielle(u) {
  if (!plein(u) || /\s/.test(u)) return null;
  try {
    const url = new URL(u);
    return url.protocol === "https:" && url.hostname ? url.href : null;
  } catch {
    return null;
  }
}

// Ce qu'on montre d'un outil. Un ancien relevé n'a ni objectif, ni lien, ni mode opératoire : l'objectif retombe sur
// l'étape (`pour`), le reste est vide et l'ancienne ligne `installation` sert de repli au mode opératoire.
export function detailOutil(x) {
  const etapes = liste(x?.etapes).filter(plein);
  return {
    nom: x?.outil,
    enPlace: x?.etat === "en_place",
    objectif: plein(x?.objectif) ? x.objectif : (plein(x?.pour) ? `Utilisé à l'étape « ${x.pour} ».` : null),
    lien: urlOfficielle(x?.telechargement),
    etapes,
    repli: !etapes.length && plein(x?.installation) ? x.installation : null,
    autonome: x?.autonome === true,
    enCours: x?.en_cours === true,
    raison: plein(x?.raison) ? x.raison : null,
    versionMin: plein(x?.version_min) ? x.version_min : null,
  };
}

// L'outil en lignes de texte (pour un texte brut) : objectif, lien, mode opératoire numéroté.
export function lignesOutil(x) {
  const d = detailOutil(x);
  const lignes = [];
  if (d.objectif) lignes.push("À quoi il sert : " + d.objectif);
  if (d.raison) lignes.push(d.raison);
  if (d.lien) lignes.push("Téléchargement officiel : " + d.lien);
  d.etapes.forEach((e, k) => lignes.push(`${k + 1}. ${e}`));
  if (d.repli) lignes.push(d.repli);
  return lignes;
}

// Le bloc d'un outil. `action` (facultatif) : {libelle, fabrique} ou un élément déjà prêt, ajouté si l'outil est
// autonome et pas déjà en cours d'installation. `enPlace` : une seule ligne, rien à installer.
export function blocOutil(x, {action = null} = {}) {
  const d = detailOutil(x);
  const bloc = el("div", "outil-a-installer");
  bloc.append(el("strong", "outil-nom", d.nom + (d.enPlace ? " : déjà en place" : "")));
  if (d.enPlace) {
    if (plein(x.version)) bloc.append(el("div", "lecon-meta", x.version));
    return bloc;
  }
  if (d.objectif) bloc.append(el("div", "outil-objectif", d.objectif));
  if (d.raison) bloc.append(el("div", "lecon-meta", d.raison));
  if (d.lien) {
    const a = el("a", "outil-lien", "Page de téléchargement officielle");
    a.href = d.lien;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    const ligne = el("div", "outil-ligne");
    ligne.append(a);
    bloc.append(ligne, el("div", "lecon-meta", d.lien));
  }
  if (d.etapes.length) {
    const ol = el("ol", "outil-etapes");
    for (const e of d.etapes) ol.append(el("li", "", e));
    bloc.append(el("div", "lecon-meta", "Mode opératoire (Windows) :"), ol);
  } else if (d.repli) {
    bloc.append(el("div", "lecon-meta", d.repli));
  }
  if (d.autonome && d.enCours) {
    bloc.append(el("div", "lecon-meta outil-en-cours", "Installation en autonomie en cours…"));
  } else if (d.autonome && action) {
    bloc.append(action);
  } else if (!d.autonome && (d.etapes.length || d.repli || d.lien)) {
    bloc.append(el("div", "lecon-meta", "Pas d'installation en autonomie : suivez le mode opératoire."));
  }
  return bloc;
}
