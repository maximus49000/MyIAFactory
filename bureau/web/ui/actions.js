// Les boutons de la factory et l'envoi des demandes au projet. Pur (sans DOM), testé avec node.
// Le bureau n'agit jamais lui-même : chaque geste devient une demande remise au projet par le serveur.

import {urlProjet} from "./projets.js";

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
    const r = await fetchFn(urlProjet("/api/demande"), {
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

// Un verdict (« valider » ou « ecarter ») par solution cochée, dans l'ordre des solutions ; une solution
// non cochée reste en l'état.
export function demandesVerdicts(challenge, cochees, toutes, verdict = "valider") {
  if (verdict !== "valider" && verdict !== "ecarter") return [];
  const choisies = new Set(cochees || []);
  return (toutes || []).filter((s) => choisies.has(s.id))
    .map((s) => ({type: "verdict_solution", challenge, solution: s.id, verdict}));
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

// --- Le Directeur enrichi (relevé version 4) : décisions des fonctionnalités et du projet.

// Les décisions qui attendent le Directeur, rangées par genre ; chaque décision d'une fonctionnalité garde
// l'identifiant et le nom de sa fonctionnalité.
export function decisionsDirecteur(etat) {
  const sortie = {cahiers: [], methodes: [], revoir: [], genres: [], sessions: [], organisations: [], reponses: []};
  const rang = {valider_cahier: "cahiers", valider_methode: "methodes", methode_a_revoir: "revoir"};
  for (const f of Array.isArray(etat?.fonctionnalites) ? etat.fonctionnalites : []) {
    for (const d of f?.decisions || []) {
      if (rang[d?.genre]) sortie[rang[d.genre]].push({...d, fonctionnalite: f.id, nom: f.nom});
    }
    // La discussion attend l'utilisateur : même règle que le serveur (bureau/etat.py, attend_utilisateur).
    const discussion = Array.isArray(f?.discussion) ? f.discussion : [];
    const dernier = discussion[discussion.length - 1];
    if (["cadrage", "prototype"].includes(f?.etape) && dernier && messageAttend(dernier) && !(f.decisions || []).length) {
      sortie.reponses.push({fonctionnalite: f.id, nom: f.nom, dernier});
    }
  }
  for (const d of Array.isArray(etat?.decisions_projet) ? etat.decisions_projet : []) {
    if (d?.genre === "confirmer_genre") sortie.genres.push({...d});
    else if (d?.genre === "session_cloud") sortie.sessions.push({...d});
    else if (d?.genre === "organisation") sortie.organisations.push({...d});
  }
  return sortie;
}

// Le verdict d'une leçon ; l'étage n'est joint que s'il diffère de l'étage proposé (« projet » par défaut).
export function demandeLecon(lecon, verdict, etage) {
  const d = {type: "lecon", id: lecon.id, verdict};
  if (etage && etage !== (lecon.etage_propose || "projet")) d.etage = etage;
  return d;
}

// Challenger une leçon (version 4) : elle se discute dans une tâche avant le verdict.
export function demandeChallengeLecon(lecon, texte) {
  return {type: "challenge", cible: {type: "lecon", id: lecon.id}, texte: String(texte).trim()};
}

// Un message d'agent attend une réponse : des questions à choix, `attend: true`, ou (sans le dire) une question.
// Même règle que le serveur (bureau/etat.py, message_attend).
export function messageAttend(m) {
  if (!m || m.auteur === "utilisateur") return false;
  if (Array.isArray(m.questions) && m.questions.length) return true;
  if (typeof m.attend === "boolean") return m.attend;
  return String(m.texte || "").includes("?");
}

// « Tout valider » / « Tout invalider » : UNE demande groupée (le serveur envoie chaque verdict lui-même, même si la
// page se ferme), chaque leçon encore en attente avec l'étage choisi dans son menu (`etages` : id -> étage).
// null s'il ne reste rien à juger.
export function demandeToutes(lecons, verdict, etages) {
  const liste = (lecons || []).filter((l) => !l.verdict_demande).map((l) => {
    const d = demandeLecon(l, verdict, etages?.get(l.id));
    return d.etage ? {id: d.id, etage: d.etage} : {id: d.id};
  });
  return liste.length ? {type: "lecons", verdict, lecons: liste} : null;
}

// Le genre du projet : un genre connu, ou un nouveau (avec sa description).
export function demandeGenre(decision, genre, description) {
  const d = {type: "genre", decision, genre};
  if (plein(description)) d.description = description;
  return d;
}

export function demandeSession(decision, session) {
  return {type: "session_cloud", decision, session};
}

// « Lot L2, tâche 3 sur 4 » ; null si la tâche n'est pas dans un lot. Le nombre de tâches du lot est celui des tâches
// du relevé qui portent le même identifiant de lot (au moins le rang de celle-ci).
export function libelleLot(tache, taches) {
  const l = tache?.lot;
  if (!l || typeof l.id !== "string" || !l.id || !Number.isInteger(l.rang) || l.rang < 1) return null;
  const dansLeLot = (Array.isArray(taches) ? taches : []).filter((t) => t?.lot?.id === l.id).length;
  return `Lot ${l.id}, tâche ${l.rang} sur ${Math.max(dansLeLot, l.rang)}`;
}

// « Sonnet, monté depuis Haiku : <raison> » ; null si la tâche n'a pas été montée de modèle.
export function libelleMontee(tache) {
  const m = tache?.montee;
  if (!m || typeof m.a !== "string" || typeof m.de !== "string") return null;
  return `${m.a}, monté depuis ${m.de}` + (plein(m.raison) ? ` : ${m.raison}` : "");
}
