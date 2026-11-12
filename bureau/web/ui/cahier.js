// La fenêtre du cahier des charges et de la méthode : « Ouvrir le cahier des charges » (ou « Ouvrir la méthode ») au bureau de
// direction ouvre cette fenêtre, qui montre le contenu en entier ; on ne valide plus sans l'avoir sous les yeux. Même
// comportement que la fenêtre de validation des éléments (ui/validation.js : plein écran au téléphone, Fermer / Échap / clic
// hors fenêtre, focus piégé, visionneuse d'images au-dessus). Une seule réponse : « Valider » ou « Demander une correction »
// (texte obligatoire) ; l'entrée disparaît dès l'envoi et ne revient qu'en cas d'erreur.
// Tout texte venu du relevé passe par textContent ou par le rendu Markdown sûr.

import {el} from "./dom.js";
import {dateFr} from "./texte.js";
import {avecProjet, projetCourant, urlProjet} from "./projets.js";
import {reessayerImage} from "./reessai.js";
import {ouvrirVisionneuse} from "./visionneuse.js";
import {creerAccuses} from "./accuse.js";
import {rendreTexte} from "./markdown.js";
import {demandeCahier, demandeMethode, vueCahier, versionsDe} from "./fonctionnalite.js";
import {estEnvoyee, marquerEnvoyee, oublierEnvoyee, ouvrirFenetre, estImage, estTelechargeable, urlTelechargement,
  tailleLisible, MAX_TEXTE} from "./validation.js";

const plein = (t) => typeof t === "string" && t.trim() !== "";
export const MODES_PARTENAIRE = {direct: "appelé directement par l'agent", inscrit: "à faire par vous, sur son site",
  aucun: "écarté : pas de partenaire pour ce besoin"};

const urlImage = (chemin) => avecProjet(`/api/image?chemin=${encodeURIComponent(chemin)}`, projetCourant());

export function fonctionnaliteDe(etat, id) {
  return (Array.isArray(etat?.fonctionnalites) ? etat.fonctionnalites : []).find((f) => f?.id === id) || null;
}

// Les partenaires décidés au cadrage, avec leur nom du catalogue quand il est dans l'état : [{id, nom, mode, libelle}].
export function partenairesDuCahier(etat, cahier) {
  const noms = new Map();
  for (const liste of Object.values(etat?.partenaires?.categories || {})) {
    for (const p of Array.isArray(liste) ? liste : []) if (p?.id) noms.set(p.id, p.nom);
  }
  return (Array.isArray(cahier?.partenaires) ? cahier.partenaires : []).filter((p) => plein(p?.id)).map((p) => (
    {id: p.id, nom: noms.get(p.id) || p.id, mode: p.mode, libelle: MODES_PARTENAIRE[p.mode] || String(p.mode || "")}));
}

// Ce que le résumé de la liste dit du cahier ou de la méthode, en une ligne.
export function resumeCahier(etat, d) {
  const f = fonctionnaliteDe(etat, d.fonctionnalite);
  if (d.genre === "valider_methode") return f?.methode ? `Méthode, version ${f.methode.version}` : "";
  const c = vueCahier(f).courant;
  if (!c) return "";
  const n = (k, un, plusieurs) => (k ? `${k} ${k > 1 ? plusieurs : un}` : null);
  return [n((c.maquette || []).length, "maquette", "maquettes"), n((c.etapes || []).length, "étape", "étapes"),
    n(partenairesDuCahier(etat, c).length, "partenaire", "partenaires")].filter(Boolean).join(" · ");
}

function section(titre) {
  const s = el("section", "val-partie");
  s.append(el("h3", "", titre));
  return s;
}

// Les maquettes légendées (agrandissables dans la visionneuse) et les étapes numérotées d'une version du cahier.
function piecesCahier(etat, c, parent) {
  const maquettes = (Array.isArray(c.maquette) ? c.maquette : []).map((m) => (typeof m === "string" ? {chemin: m, legende: ""}
    : {chemin: m?.chemin, legende: plein(m?.legende) ? m.legende : ""})).filter((m) => plein(m.chemin));
  if (maquettes.length) {
    const galerie = el("div", "val-images");
    maquettes.forEach((m, n) => {
      const fig = el("figure", "val-image");
      if (etat?.images_ok === true) {
        const b = el("button", "val-vignette");
        b.type = "button";
        b.setAttribute("aria-label", "Agrandir : " + (m.legende || m.chemin));
        const img = el("img", "");
        img.src = urlImage(m.chemin);
        img.alt = m.legende || m.chemin;
        reessayerImage(img);
        b.append(img);
        b.addEventListener("click", () => ouvrirVisionneuse(maquettes, n, urlImage, b));
        fig.append(b);
      } else fig.append(el("figcaption", "val-meta", "Image non affichable (aucune racine d'images déclarée)"));
      if (m.legende) fig.append(el("figcaption", "val-legende", m.legende));
      galerie.append(fig);
    });
    parent.append(galerie);
  }
  const textes = Array.isArray(c.etapes) ? c.etapes : [];
  if (textes.length) {
    const etapes = el("ol", "val-etapes");
    for (const t of textes) etapes.append(el("li", "", String(t)));
    parent.append(etapes);
  }
}

function contenuDuCahier(etat, f, boite) {
  const vue = vueCahier(f);
  const s = section("Cahier des charges");
  if (vue.courant) {
    piecesCahier(etat, vue.courant, s);
    const partenaires = partenairesDuCahier(etat, vue.courant);
    if (partenaires.length) {
      const p = el("div", "val-partenaires");
      p.append(el("h4", "", "Partenaires choisis"));
      const ul = el("ul", "");
      for (const x of partenaires) {
        const li = el("li", "");
        li.append(el("strong", "", x.nom), el("span", "", " : " + x.libelle));
        ul.append(li);
      }
      p.append(ul);
      s.append(p);
    }
  } else s.append(el("p", "val-meta", "Aucun cahier des charges à lire pour l'instant."));
  boite.append(s);
  if (vue.versions.length) {
    const histo = el("details", "val-versions");
    histo.append(el("summary", "", `Versions précédentes (${vue.versions.length})`));
    for (const c of vue.versions) {
      const bloc = el("div", "val-version");
      bloc.append(el("p", "val-meta", c.remplace_le ? "Remplacée le " + dateFr(c.remplace_le) : "En cours de correction"));
      piecesCahier(etat, c, bloc);
      histo.append(bloc);
    }
    boite.append(histo);
  }
}

// La méthode écrite (Markdown sûr, tableaux compris) puis son prototype : les images et les livrables de la fonctionnalité.
function contenuDeLaMethode(etat, f, boite) {
  const m = f?.methode;
  const s = section(m ? `Méthode (version ${m.version})` : "Méthode");
  if (m?.validee_le) s.append(el("p", "val-meta", "Validée le " + dateFr(m.validee_le)));
  const corps = el("div", "val-methode");
  s.append(corps);
  if (m && plein(m.lien) && /^https:\/\//.test(m.lien)) {
    const a = el("a", "bouton secondaire", "Ouvrir la méthode");
    a.href = m.lien;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    s.append(a);
  }
  if (m?.chemin) {
    corps.append(el("p", "val-meta", "Lecture de la méthode…"));
    (async () => {
      let texte = null;
      try {
        const r = await globalThis.fetch(urlProjet(`/api/methode?fonctionnalite=${encodeURIComponent(f.id)}`), {cache: "no-store"});
        if (r.ok) texte = await r.text();
      } catch { /* serveur injoignable */ }
      corps.replaceChildren();
      if (texte === null) corps.append(el("p", "val-meta", `Méthode illisible ici (${m.chemin}) : elle doit être en .md ou .txt, sous une racine « documents ».`));
      else corps.append(rendreTexte("val-methode-texte", texte));
    })();
  } else if (!m) corps.append(el("p", "val-meta", "Aucune méthode écrite pour l'instant."));
  boite.append(s);

  const prototype = section("Prototype");
  const docs = versionsDe(Array.isArray(f?.documents) ? f.documents : []).map((v) => v.dernier)
    .filter((d) => estImage(d.chemin) || d.livrable === true || estTelechargeable(d.chemin));
  const urlDoc = (chemin) => urlProjet(`/api/document?fonctionnalite=${encodeURIComponent(f.id)}&chemin=${encodeURIComponent(chemin)}`);
  const images = docs.filter((d) => estImage(d.chemin)).map((d) => ({chemin: d.chemin, legende: plein(d.titre) && d.titre !== d.chemin.split(/[\\/]/).pop() ? d.titre : ""}));
  if (images.length) {
    const galerie = el("div", "val-images");
    images.forEach((im, n) => {
      const fig = el("figure", "val-image");
      const b = el("button", "val-vignette");
      b.type = "button";
      b.setAttribute("aria-label", "Agrandir : " + (im.legende || im.chemin));
      const img = el("img", "");
      img.src = urlDoc(im.chemin);
      img.alt = im.legende || im.chemin;
      reessayerImage(img);
      b.append(img);
      b.addEventListener("click", () => ouvrirVisionneuse(images, n, urlDoc, b));
      fig.append(b);
      if (im.legende) fig.append(el("figcaption", "val-legende", im.legende));
      galerie.append(fig);
    });
    prototype.append(galerie);
  }
  let origine = null;
  try { origine = globalThis.location?.origin || null; } catch { /* hors navigateur */ }
  for (const d of docs.filter((x) => !estImage(x.chemin))) {
    const nom = d.chemin.split(/[\\/]/).pop();
    const ligne = el("div", "val-livrable");
    const texte = el("div", "val-livrable-texte");
    texte.append(el("strong", "", plein(d.titre) ? d.titre : nom),
                 el("span", "val-meta", [nom, tailleLisible(d.taille)].filter(Boolean).join(" · ")));
    const a = el("a", "bouton val-telecharger", "Télécharger");
    a.href = urlTelechargement(f.id, d.chemin, projetCourant(), origine);
    a.setAttribute("download", nom);
    ligne.append(texte, a);
    prototype.append(ligne);
  }
  if (!docs.length) prototype.append(el("p", "val-meta", "Aucune image ni aucun livrable du prototype pour l'instant."));
  boite.append(prototype);
}

// Le contenu de la fenêtre (sans le fond ni le clavier) : testé avec un faux DOM. `d` est la décision `valider_cahier` ou
// `valider_methode` de la fonctionnalité. Rend `{boite, fermer: bouton}`.
export function contenuCahierMethode(ctx, d, {fermer = () => {}} = {}) {
  const methode = d.genre === "valider_methode";
  const f = fonctionnaliteDe(ctx.etat, d.fonctionnalite);
  const boite = el("div", "val-boite");
  boite.setAttribute("role", "dialog");
  boite.setAttribute("aria-modal", "true");
  boite.setAttribute("aria-labelledby", "val-titre");
  const tete = el("div", "val-tete");
  const titre = el("h2", "val-titre", `${methode ? "Méthode" : "Cahier des charges"} : ${f?.nom || d.nom || d.fonctionnalite}`);
  titre.id = "val-titre";
  const bFermer = el("button", "val-fermer", "×");
  bFermer.type = "button";
  bFermer.setAttribute("aria-label", "Fermer");
  bFermer.addEventListener("click", () => fermer());
  tete.append(titre, bFermer);
  boite.append(tete);
  if (plein(d.texte)) boite.append(el("p", "val-entete", d.texte));
  if (methode) contenuDeLaMethode(ctx.etat, f, boite); else contenuDuCahier(ctx.etat, f, boite);

  const deja = estEnvoyee(d.id);
  if (ctx.etat?.agir !== true || deja) {
    boite.append(el("p", "val-meta", deja ? "Réponse envoyée : le moteur la traite, rien n'attend plus de vous ici."
      : "Ce bureau ne peut pas agir sur le projet : le contenu se lit seulement."));
    if (deja) boite.append(creerAccuses((methode ? "methode:" : "cahier:") + d.fonctionnalite).racine);   // « Reçu, en cours de traitement… »
    return {boite, fermer: bFermer};
  }
  const s = section("Votre réponse");
  const libre = el("textarea", "val-libre");
  libre.rows = 3;
  libre.maxLength = MAX_TEXTE;
  libre.placeholder = methode ? "Ce qu'il faut changer dans la méthode (obligatoire pour demander une correction)…"
    : "Ce qu'il faut corriger dans le cahier des charges (obligatoire pour demander une correction)…";
  libre.setAttribute("aria-label", "Correction demandée");
  s.append(libre);
  boite.append(s);
  const erreur = el("p", "saisie-erreur", "");
  const valider = el("button", "bouton val-envoyer", "Valider");
  const corriger = el("button", "bouton secondaire val-envoyer", "Demander une correction");
  for (const b of [valider, corriger]) b.type = "button";
  const envoyer = async (demande, bouton) => {
    valider.disabled = corriger.disabled = true;
    marquerEnvoyee(d.id);       // dès l'envoi : retirée de la liste et du compteur, même si l'état servi se rafraîchit avant la réponse
    const r = await ctx.barre.demander(demande, bouton);
    if (r?.ok) { fermer(); return; }
    if (!/déjà reçu/.test(r?.message || "")) oublierEnvoyee(d.id);    // déjà répondue : elle reste « envoyée »
    valider.disabled = corriger.disabled = false;
    erreur.textContent = r?.message || "La demande n'est pas partie.";
  };
  valider.addEventListener("click", () => {
    erreur.textContent = "";
    return envoyer(methode ? demandeMethode(d.fonctionnalite, "valider") : demandeCahier(d.fonctionnalite, "valider"), valider);
  });
  corriger.addEventListener("click", () => {
    const texte = String(libre.value || "").trim();
    if (!texte) { erreur.textContent = "Écrivez ce qu'il faut corriger avant de demander une correction."; libre.focus?.(); return; }
    erreur.textContent = "";
    return envoyer(methode ? demandeMethode(d.fonctionnalite, "revoir", texte) : demandeCahier(d.fonctionnalite, "corriger", texte), corriger);
  });
  const pied = el("div", "val-pied");
  pied.append(erreur, corriger, valider);
  boite.append(pied);
  return {boite, fermer: bFermer};
}

// Ouvre la fenêtre par-dessus le bureau ; `declencheur` reprend le focus à la fermeture.
export function ouvrirCahier(ctx, d, declencheur = null) {
  return ouvrirFenetre((fermer) => contenuCahierMethode(ctx, d, {fermer}), declencheur);
}
