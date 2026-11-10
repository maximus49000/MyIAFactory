// Les boutons de la factory et l'envoi des demandes au projet. Pur (sans DOM), testé avec node.
// Le bureau n'agit jamais lui-même : chaque geste devient une demande remise au projet par le serveur.

const SCHEMAS = ["https:", "http:", "claude:"];

// Même règle que côté serveur (releve.lien_valide) : https, http ou claude, sans espace ni caractère de contrôle.
export function lienSur(url) {
  if (typeof url !== "string" || !url) return false;
  if (/[\s\u0000-\u001f\u007f]/.test(url)) return false;
  const i = url.indexOf(":");
  if (i < 1 || i === url.length - 1) return false;
  return SCHEMAS.includes(url.slice(0, i + 1).toLowerCase());
}

// Les boutons à montrer : sans `agir`, les liens seuls ; avec, les demandes aussi. Un lien refusé n'est jamais montré.
export function boutons(etat) {
  const liste = Array.isArray(etat?.actions) ? etat.actions : [];
  const agir = etat?.agir === true;
  const sortie = [];
  for (const a of liste) {
    if (!a || typeof a.id !== "string" || typeof a.libelle !== "string") continue;
    const lien = a.lien === undefined || a.lien === null ? null : a.lien;
    if (lien !== null && !lienSur(lien)) continue;
    if (lien === null && !agir) continue;
    sortie.push({id: a.id, libelle: a.libelle, lien,
                 confirmer: typeof a.confirmer === "string" && a.confirmer ? a.confirmer : null,
                 actif: a.actif !== false});
  }
  return sortie;
}

// Dépose une demande. Rend {ok, message} ; ne lève jamais.
export async function envoyer(demande, fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/demande", {
      method: "POST",
      headers: {"X-Bureau": "1", "Content-Type": "application/json"},
      body: JSON.stringify(demande),
    });
    if (r.ok) return {ok: true, message: "Demande envoyée"};
    let erreur = "";
    try { erreur = (await r.json())?.erreur || ""; } catch { /* corps illisible */ }
    return {ok: false, message: `Demande refusée : ${erreur || "le serveur a répondu " + r.status}`};
  } catch {
    return {ok: false, message: "Demande refusée : serveur injoignable"};
  }
}
