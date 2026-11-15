// Les tâches refaites (même titre) : « Retour 1 », « Reprise 1 »… pour les distinguer.
// Plusieurs tâches au même titre (la même étape refaite pour le même élément) : la première garde son titre, les
// suivantes sont « Retour 1 », « Retour 2 »… quand elles partent d'un retour du Directeur, « Reprise 1 »… sinon.
// Rend id -> préfixe (sans entrée pour la première). Pur.
const DEBUTS_RETOUR = ["Remarque du Directeur", "Retour de l'utilisateur", "Consigne de l'utilisateur"];
const numero = (id) => Number(String(id).replace(/\D/g, "")) || 0;
export function prefixesDeRepetition(etat) {
  const parTitre = new Map();
  for (const t of etat?.taches || []) {
    if (!t?.titre || t.id === "orchestration") continue;
    if (!parTitre.has(t.titre)) parTitre.set(t.titre, []);
    parTitre.get(t.titre).push(t);
  }
  const prefixes = new Map();
  for (const liste of parTitre.values()) {
    if (liste.length < 2) continue;
    liste.sort((a, b) => numero(a.id) - numero(b.id));
    let retours = 0, reprises = 0;
    for (const t of liste.slice(1)) {
      const retour = (t.journal || []).some((j) => DEBUTS_RETOUR.some((d) => String(j?.texte || "").startsWith(d)));
      prefixes.set(t.id, retour ? `Retour ${++retours}` : `Reprise ${++reprises}`);
    }
  }
  return prefixes;
}

// Le livrable groupé : la livraison qui fabrique un seul livrable pour plusieurs éléments porte, dans son journal, la
// consigne du moteur « Un seul livrable pour tout le produit, avec les éléments : A, B. … Livraison groupée, lot : f1/e1
// f1/e2 » (voir `moteur.regles.livrer_si_calme`). Rend {noms, n} ou null. Pur.
const MARQUE_LIVRAISON_GROUPEE = "Livraison groupée, lot : ";
export function livraisonGroupee(t) {
  for (const j of t?.journal || []) {
    const texte = String(j?.texte || "");
    const k = texte.indexOf(MARQUE_LIVRAISON_GROUPEE);
    if (k < 0) continue;
    const cles = texte.slice(k + MARQUE_LIVRAISON_GROUPEE.length).trim().split(/\s+/).filter(Boolean);
    const m = texte.match(/avec les éléments : (.*?)\. Fabrique/);
    const noms = m ? m[1].split(", ").map((x) => x.trim()).filter(Boolean) : [];
    const n = Math.max(cles.length, noms.length);
    if (n > 1) return {noms, n};
  }
  return null;
}

// Le titre affiché d'une tâche : « Retour 2 – Conception … » pour une étape refaite ; « Livrable groupé (11 éléments) »
// pour la livraison d'un seul livrable pour plusieurs éléments (sinon elle porte le nom de l'élément qui la mène). Pur.
export function titreAffiche(etat, t, prefixes = prefixesDeRepetition(etat)) {
  const p = prefixes.get(t?.id);
  const groupe = livraisonGroupee(t);
  const titre = groupe ? `Livrable groupé (${groupe.n} éléments)` : t?.titre || "";
  return p ? `${p} – ${titre}` : titre;
}
