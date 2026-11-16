// Le vocabulaire d'une correction (une anomalie à réparer) : pas de « cadrage » ni de cahier, mais un diagnostic
// (lire le signalement, reproduire, trouver une piste), puis correctif, vérification, validation et livraison.
// Les identifiants du moteur ne changent pas (`cadrage`, `<fid>-correctif`…) : seuls les libellés montrés changent.

export const ETAPES_CORRECTION = [
  {id: "diagnostic", libelle: "Diagnostic"},
  {id: "correctif", libelle: "Correctif"},
  {id: "verification", libelle: "Vérification"},
  {id: "validation", libelle: "Validation"},
  {id: "livraison", libelle: "Livraison"},
];

export const estCorrection = (f) => f?.nature === "correction";

// L'étape d'une tâche de correction, sans préfixe : `cadrage` → diagnostic ; `flux:f2-correctif`, `validation:f2-validation`
// ou une colonne
// `f2-correctif` → correctif. `null` si ce n'est pas une étape du parcours d'une correction.
export function etapeCorrection(fid, valeur) {
  const v = String(valeur || "").replace(/^(flux|validation):/, "");
  if (v === "cadrage") return "diagnostic";
  const prefixe = fid + "-";
  if (!v.startsWith(prefixe)) return null;
  const id = v.slice(prefixe.length);
  return ETAPES_CORRECTION.some((x) => x.id === id) ? id : null;
}

// Les étapes de cette correction : la vérification n'y est que si son workflow en a une (une colonne du relevé).
export function etapesDe(f, e) {
  const avecVerification = (e?.colonnes || []).some((c) => c.id === `${f.id}-verification`);
  return ETAPES_CORRECTION.filter((x) => x.id !== "verification" || avecVerification);
}

// L'étape où en est la correction : diagnostic tant qu'elle est au cadrage ; ensuite, la plus avancée de ses tâches
// ouvertes (correctif tant qu'aucune n'est lisible).
export function etapeCourante(f, e) {
  if (f?.etape === "terminee") return "terminee";
  if (f?.etape === "cadrage" || f?.etape === "cahier") return "diagnostic";
  const ordre = ETAPES_CORRECTION.map((x) => x.id);
  let rang = -1;
  for (const t of e?.taches || []) {
    if (t.fonctionnalite !== f.id || t.colonne === "fait") continue;
    const id = etapeCorrection(f.id, t.colonne) || etapeCorrection(f.id, t.etape);
    if (id) rang = Math.max(rang, ordre.indexOf(id));
  }
  return rang >= 0 ? ordre[rang] : "correctif";
}

// Le bandeau du parcours d'une correction (même forme que celui d'une fonctionnalité).
export function bandeauCorrection(f, e) {
  const etapes = etapesDe(f, e);
  const courante = etapeCourante(f, e);
  const rang = courante === "terminee" ? etapes.length : etapes.findIndex((x) => x.id === courante);
  return etapes.map((x, i) => ({libelle: x.libelle, courante: rang >= 0 && i === rang, faite: rang >= 0 && i < rang}));
}

// Le libellé de l'étape d'une correction dans la liste des fonctionnalités.
export function libelleEtapeCorrection(f, e) {
  const courante = etapeCourante(f, e);
  if (courante === "terminee") return "Terminée";
  return ETAPES_CORRECTION.find((x) => x.id === courante)?.libelle || "";
}

// L'étape d'une tâche, en clair dans son détail : « diagnostic », « correctif »… pour une tâche de correction, sinon
// l'étape telle quelle.
export function libelleEtapeTache(e, t) {
  const f = (e?.fonctionnalites || []).find((x) => x.id === t?.fonctionnalite);
  if (estCorrection(f)) {
    const id = etapeCorrection(f.id, t.etape) || etapeCorrection(f.id, t.colonne);
    if (id) return id === "verification" ? "vérification" : id;
  }
  return t?.etape || "";
}
