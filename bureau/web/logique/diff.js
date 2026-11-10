// Ce qui a changé sur le tableau entre deux états servis par le bureau.
// Fonctions pures : ni DOM, ni three.js.

export function etatUtilisable(etat) {
  return Boolean(etat) && !etat.erreur;
}

// -> [{tache, de, vers, porteur}] pour chaque post-it apparu ou changé de colonne.
// Porteur : l'agent qui tenait la tâche avant le changement s'il est encore là,
// sinon le chef d'atelier. Une tâche qui apparaît est posée par le chef.
export function changements(avant, apres) {
  if (!avant || !apres) return [];
  const chef = (apres.agents || []).find((a) => a.chef);
  const idChef = chef ? chef.id : null;
  const presents = new Set((apres.agents || []).map((a) => a.id));
  const anciennes = new Map();
  for (const t of avant.taches || []) if (t.postit !== false) anciennes.set(t.id, t);

  const liste = [];
  for (const t of apres.taches || []) {
    if (t.postit === false) continue;
    const ancienne = anciennes.get(t.id);
    if (!ancienne) {
      liste.push({tache: t.id, de: null, vers: t.colonne, porteur: idChef});
    } else if (ancienne.colonne !== t.colonne) {
      const porteur = ancienne.agent && presents.has(ancienne.agent) ? ancienne.agent : idChef;
      liste.push({tache: t.id, de: ancienne.colonne, vers: t.colonne, porteur});
    }
  }
  return liste;
}
