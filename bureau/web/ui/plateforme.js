// La carte « Serveur » : où en est la mise en place du serveur (lecture, système, accès, durcissement, Docker, images, licence)
// et le bouton pour la mener ou la reprendre. Le bureau ne fait qu'afficher le relevé `GET /api/plateforme` (lu au cache) et
// demander l'installation `POST /api/plateforme/installer`. Tout texte venu du serveur passe par textContent ; les liens
// http(s) d'un « geste » sont construits avec le DOM, jamais avec du HTML.

import {el} from "./dom.js";

const LIBELLES_STATUT = {fait: "fait ✓", a_faire: "à faire", bloque: "bloqué", en_cours: "en cours …"};
const INTERVALLE_MS = 3000;
const RELEVES_SANS_TRAVAIL = 3;   // relevés sans étape « en cours » avant de cesser de guetter une installation lancée
const tableau = (v) => (Array.isArray(v) ? v : []);
const texte = (v) => (typeof v === "string" ? v : "");

export const AVERTISSEMENT = "Réinstaller efface le disque du serveur. Sans votre accord ci-dessous, le serveur n'est jamais "
  + "réinstallé : seules les étapes sûres sont faites ou reprises.";
export const LIBELLE_ACCORD = "J'autorise l'effacement du serveur";
export const LIBELLE_BOUTON = "Mettre en place / reprendre";

// Demande la mise en place. `accord_reinstallation` n'est vrai que si `accord === true`. Ne lève jamais : {ok, message, occupe}.
export async function demanderInstallation(accord, fetchFn = globalThis.fetch) {
  try {
    const r = await fetchFn("/api/plateforme/installer", {
      method: "POST", headers: {"X-Bureau": "1", "Content-Type": "application/json"},
      body: JSON.stringify({accord_reinstallation: accord === true})});
    let d = {};
    try { d = await r.json(); } catch { /* corps illisible */ }
    if (r.status === 409) return {ok: false, occupe: true, message: texte(d?.erreur) || "Une installation est déjà en cours."};
    if (!r.ok) return {ok: false, message: texte(d?.erreur) || `Le serveur a répondu ${r.status}.`};
    return {ok: true, message: "Installation lancée. L'état se met à jour tout seul."};
  } catch {
    return {ok: false, message: "Installation impossible à lancer : le bureau est injoignable."};
  }
}

// Lit l'état de la plateforme. Rend l'objet reçu, ou null si le serveur est injoignable ou répond mal.
export async function lirePlateforme(fetchFn = globalThis.fetch) {
  try {
    const r = await fetchFn("/api/plateforme");
    if (!r.ok) return null;
    const d = await r.json();
    return d && typeof d === "object" && !Array.isArray(d) ? d : null;
  } catch {
    return null;
  }
}

// Un texte où les adresses http(s) deviennent des liens (construits avec le DOM) ; le reste reste du texte.
export function texteAvecLiens(brut, classe = "") {
  const racine = el("span", classe);
  const motif = /https?:\/\/[^\s<>"']+/g;
  let fin = 0;
  const m = [...String(brut).matchAll(motif)];
  for (const x of m) {
    const adresse = x[0].replace(/[.,;:!?)\]]+$/, "");
    let valide = false;
    try { valide = ["http:", "https:"].includes(new URL(adresse).protocol); } catch { valide = false; }
    if (!valide) continue;
    if (x.index > fin) racine.append(el("span", "", String(brut).slice(fin, x.index)));
    const a = el("a", "serveur-lien", adresse);
    a.href = adresse;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    racine.append(a);
    fin = x.index + adresse.length;
  }
  if (fin < String(brut).length) racine.append(el("span", "", String(brut).slice(fin)));
  return racine;
}

function ligneEtape(e) {
  const statut = LIBELLES_STATUT[e?.statut] ? e.statut : "a_faire";
  const l = el("div", `serveur-etape serveur-${statut}`);
  const tete = el("div", "serveur-etape-tete");
  tete.append(el("strong", "serveur-libelle", texte(e?.libelle) || texte(e?.id)),
              el("span", `serveur-badge badge-${statut}`, LIBELLES_STATUT[statut]));
  l.append(tete);
  if (texte(e?.detail)) l.append(el("div", "ligne-detail serveur-detail", e.detail));
  if (texte(e?.geste)) {
    const g = el("div", "serveur-geste");
    g.append(el("div", "carte-sous-titre", "À faire de votre côté"), texteAvecLiens(e.geste, "serveur-geste-texte"));
    l.append(g);
  }
  return l;
}

function verdict(etat) {
  const etapes = tableau(etat?.etapes);
  if (etat?.pret === true) return "Prêt";
  if (etat?.pret_sans_unity === true && etapes.find((e) => e?.id === "licence")?.statut !== "fait") return "Prêt, sans Unity";
  return "";
}

// La carte. `etat` : la réponse de /api/plateforme (ou null : injoignable). Options : `installer(accord)` -> {ok, message, occupe?},
// `fetchFn`, `minuterie` {attendre(f, ms) -> poignée, annuler(poignée)} et `actif()` (faux : la carte est retirée, on cesse de relire).
export function carteServeur(etat, options = {}) {
  const fetchFn = options.fetchFn || globalThis.fetch;
  const installer = options.installer || ((accord) => demanderInstallation(accord, fetchFn));
  const minuterie = options.minuterie || {attendre: (f, ms) => setTimeout(f, ms), annuler: (h) => clearTimeout(h)};
  const racine = el("section", "carte-serveur");
  racine.append(el("h2", "", "Serveur"));
  const resume = el("p", "serveur-resume");
  const message = el("p", "reglage-message serveur-message");
  message.setAttribute("aria-live", "polite");
  const erreur = el("p", "reglage-message serveur-erreur");
  erreur.setAttribute("role", "alert");
  const liste = el("div", "serveur-etapes");
  const avert = el("p", "serveur-avertissement", AVERTISSEMENT);
  avert.setAttribute("role", "note");
  const accord = el("input", "serveur-accord");
  accord.type = "checkbox";
  accord.checked = false;
  accord.id = "serveur-accord";
  const etiquette = el("label", "serveur-accord-libelle");
  etiquette.htmlFor = "serveur-accord";
  etiquette.append(accord, el("span", "", ` ${LIBELLE_ACCORD}`));
  const bouton = el("button", "bouton serveur-bouton", LIBELLE_BOUTON);
  bouton.type = "button";
  racine.append(resume, message, erreur, liste, avert, etiquette, bouton);

  let courant = etat;
  let lance = false;          // une installation vient d'être demandée : on guette son démarrage
  let sansTravail = 0;
  let poignee = null;
  let fini = false;

  // « en cours » : le fil du bureau tourne (`en_cours` du relevé) ou une étape se dit en cours.
  const enCours = () => courant?.en_cours === true || tableau(courant?.etapes).some((e) => e?.statut === "en_cours");
  const actif = () => !fini && (options.actif ? options.actif() : racine.isConnected !== false);

  function dessiner() {
    const etapes = tableau(courant?.etapes);
    liste.replaceChildren(...etapes.map(ligneEtape));
    if (!courant) {
      resume.textContent = "Le bureau ne répond pas : l'état du serveur n'a pas pu être lu.";
    } else {
      const v = verdict(courant);
      resume.textContent = v || (etapes.length ? "Le serveur n'est pas encore prêt." : "Aucun état lu pour l'instant : le serveur est à mettre en place.");
    }
    erreur.textContent = texte(courant?.erreur);
    bouton.disabled = enCours() || lance;
  }

  function planifier() {
    if (poignee !== null || !actif() || !(enCours() || lance)) return;
    poignee = minuterie.attendre(async () => {
      poignee = null;
      if (!actif()) return;
      const neuf = await lirePlateforme(fetchFn);
      if (neuf) courant = neuf;
      if (enCours()) sansTravail = 0;
      else if (lance && ++sansTravail >= RELEVES_SANS_TRAVAIL) { lance = false; sansTravail = 0; }
      dessiner();
      planifier();
    }, INTERVALLE_MS);
  }

  bouton.addEventListener("click", async () => {
    if (bouton.disabled) return;
    bouton.disabled = true;
    message.textContent = "Envoi…";
    // L'accord n'est donné que par la case cochée, et il ne sert qu'une fois : la case est décochée tout de suite,
    // avant l'envoi, quelle que soit la réponse (succès, 409 ou erreur).
    const accorde = accord.checked === true;
    accord.checked = false;
    const r = await installer(accorde);
    message.textContent = r?.message || (r?.ok ? "Installation lancée." : "Demande refusée.");
    if (r?.ok || r?.occupe) { lance = true; sansTravail = 0; }
    dessiner();
    planifier();
  });

  racine.planifier = planifier;
  racine.arreter = () => { fini = true; if (poignee !== null) { minuterie.annuler(poignee); poignee = null; } };
  dessiner();
  planifier();
  return racine;
}

// Monte la carte dans `conteneur` : lit l'état puis dessine (injoignable : la carte le dit). Rend la carte.
export async function monterCarteServeur(conteneur, options = {}) {
  const fetchFn = options.fetchFn || globalThis.fetch;
  const carte = carteServeur(await lirePlateforme(fetchFn), {...options, fetchFn});
  conteneur.append(carte);
  carte.planifier();   // la carte est maintenant dans la page : une installation en cours se suit
  return carte;
}
