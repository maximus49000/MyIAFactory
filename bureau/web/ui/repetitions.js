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

// Le titre affiché d'une tâche : « Retour 2 – Conception … » pour une étape refaite. Pur.
export function titreAffiche(etat, t, prefixes = prefixesDeRepetition(etat)) {
  const p = prefixes.get(t?.id);
  return p ? `${p} – ${t.titre}` : t?.titre || "";
}
