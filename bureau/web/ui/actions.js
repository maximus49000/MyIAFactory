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

// --- Challenger : les demandes, construites ici (pures) et envoyées par le volet.

const plein = (t) => typeof t === "string" && t.trim() !== "";

export function demandeChallenge(cible, texte, solution) {
  const d = {type: "challenge", cible: {type: cible.type, id: cible.id}};
  if (plein(texte)) d.texte = texte;
  if (plein(solution)) d.solution = solution;
  return d;
}

export function demandeSolution(challenge, texte) {
  return {type: "solution", challenge, texte};
}

// Un verdict « valider » par solution cochée, dans l'ordre des solutions ; une solution non cochée reste en l'état.
export function demandesVerdicts(challenge, cochees, toutes) {
  const choisies = new Set(cochees || []);
  return (toutes || []).filter((s) => choisies.has(s.id))
    .map((s) => ({type: "verdict_solution", challenge, solution: s.id, verdict: "valider"}));
}

// Le challenge du relevé ouvert sur cette cible, ou null.
export function challengeDe(etat, cible) {
  const liste = Array.isArray(etat?.challenges) ? etat.challenges : [];
  return liste.find((c) => c?.cible?.type === cible.type && c?.cible?.id === cible.id) || null;
}

// Les challenges qui concernent un service, avec le nombre de solutions encore à décider. Un challenge
// doit rester atteignable même quand sa cible n'est plus affichée (alerte levée, source sortie de la période).
// Cibles : `kpi:<service>:…`, `source:<service>:…`, ou une connaissance d'un agent du service.
export function challengesDuService(etat, service) {
  const liste = Array.isArray(etat?.challenges) ? etat.challenges : [];
  const autres = (etat?.services || []).map((s) => s.id).filter((id) => id !== service && id.startsWith(service + ":"));
  const siennes = new Set((etat?.savoir || []).filter((s) => s.service === service)
    .flatMap((s) => (s.connaissances || []).map((c) => c.id)));
  const duService = (c) => {
    const id = c?.cible?.id;
    if (typeof id !== "string") return false;
    if (c.cible.type === "connaissance") return siennes.has(id);
    return ["kpi", "source"].some((genre) => c.cible.type === genre && id.startsWith(`${genre}:${service}:`)
      && !autres.some((a) => id.startsWith(`${genre}:${a}:`)));  // « dev:web » n'est pas « dev »
  };
  return liste.filter(duService).map((c) => ({
    challenge: c,
    aDecider: (c.solutions || []).filter((s) => !DECIDEES.includes(String(s?.etat || "").toLowerCase())).length,
  }));
}

export const DECIDEES = ["validée", "écartée"];

// Après un envoi en plusieurs demandes : ce qui est parti, ce qui ne l'est pas (rien n'est annulé).
export function resumeEnvoi(resultats) {
  const ok = resultats.filter((r) => r.ok).map((r) => r.nom);
  const non = resultats.filter((r) => !r.ok).map((r) => `${r.nom} (${r.message})`);
  if (!non.length) return ok.length ? `Demandes envoyées : ${ok.join(", ")}.` : "";
  return (ok.length ? `Envoyées : ${ok.join(", ")}. ` : "") + `Non envoyées : ${non.join(", ")}.`;
}
