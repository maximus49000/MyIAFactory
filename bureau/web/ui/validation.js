// La fenêtre de validation (conception 2026-11-12-fenetre-de-validation-design.md) : ouverte depuis « Ouvrir la
// validation » au bureau de direction, elle dit ce qu'il y a à valider (objectif, « À valider »), donne de quoi le
// vérifier (livrables à télécharger, lien d'accès du site qui tourne, images agrandissables), le compte rendu de
// l'élément, puis un point à vérifier par ligne avec deux bulles « OK » / « À revoir » et un champ libre. Un seul envoi :
// tous OK → validé ; au moins un « À revoir » → renvoyé à l'étape précédente avec les points refusés.
// Fenêtre modale : Fermer / Échap / clic hors fenêtre, focus piégé puis rendu au bouton, plein écran sous 700 px.
// Les fonctions pures sont testées avec node ; tout texte venu du relevé passe par textContent.

import {el} from "./dom.js";
import {dateFr} from "./texte.js";
import {avecProjet, projetCourant} from "./projets.js";
import {reessayerImage} from "./reessai.js";

export const POINT_PAR_DEFAUT = "L'élément correspond à l'objectif";   // une décision posée avant la fenêtre
export const MAX_POINTS = 8;
export const MAX_POINT = 160;
export const MAX_TEXTE = 3500;
// Les extensions servies par /api/telecharger (le même ensemble que `TELECHARGEABLES` de bureau/releve.py, vérifié par
// un test) ; les images se montrent en plus.
export const EXTENSIONS_TELECHARGEABLES = [".apk", ".aab", ".zip", ".7z", ".gz", ".tgz", ".tar", ".pdf", ".exe", ".msi",
  ".msix", ".appx", ".ipa", ".dmg", ".deb", ".appimage", ".pck", ".glb", ".png", ".jpg", ".jpeg", ".mp4", ".webm", ".mp3",
  ".ogg", ".wav", ".epub", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".html"];
const IMAGES = [".png", ".jpg", ".jpeg"];
const HOTES_LOCAUX = ["127.0.0.1", "localhost", "[::1]", "::1"];

const plein = (t) => typeof t === "string" && t.trim() !== "";

export function extension(chemin) {
  const nom = String(chemin || "").split(/[\\/]/).pop();
  const i = nom.lastIndexOf(".");
  return i > 0 ? nom.slice(i).toLowerCase() : "";
}
export const estImage = (chemin) => IMAGES.includes(extension(chemin));
export const estTelechargeable = (chemin) => EXTENSIONS_TELECHARGEABLES.includes(extension(chemin)) && !estImage(chemin);

// L'en-tête d'un élément à valider : « Objectif : … » (ce qu'il devait produire) puis « À valider : … » ; une ligne
// absente (décision d'avant) n'est pas montrée.
export function enteteValidation(d) {
  const lignes = [];
  if (plein(d?.objectif)) lignes.push({libelle: "Objectif", texte: d.objectif.trim()});
  if (plein(d?.a_valider)) lignes.push({libelle: "À valider", texte: d.a_valider.trim()});
  return lignes;
}

// Ce que dit chaque demande de validation, en trois blocs : « Ce qui doit marcher », « Pas encore attendu à ce stade »
// (vide : tout est attendu), « À conclure ». Une décision posée sans ces champs n'a que « Ce qui doit marcher : l'élément
// correspond à son objectif » : rien n'est inventé.
export const DOIT_MARCHER_PAR_DEFAUT = "L'élément correspond à son objectif";
export function consignesDeValidation(d) {
  if (!plein(d?.doit_marcher)) return [{cle: "doit_marcher", libelle: "Ce qui doit marcher", texte: DOIT_MARCHER_PAR_DEFAUT}];
  const blocs = [{cle: "doit_marcher", libelle: "Ce qui doit marcher", texte: d.doit_marcher.trim()}];
  if (typeof d.pas_encore === "string") {
    blocs.push({cle: "pas_encore", libelle: "Pas encore attendu à ce stade",
                texte: d.pas_encore.trim() || "Tout est attendu à ce stade."});
  }
  if (plein(d.conclusion)) blocs.push({cle: "conclusion", libelle: "À conclure", texte: d.conclusion.trim()});
  return blocs;
}

// La nature de ce que le Directeur valide (en jeu, visuel, mécanique, autre) : son libellé, `null` si absente ou inconnue
// (une décision d'avant). Le mode opératoire (2 à 10 étapes) n'est montré que pour une validation en jeu.
export const NATURES = {en_jeu: "À essayer en jeu", visuel: "Visuel à juger", mecanique: "Mécanique à lire",
  autre: "À examiner"};
export function natureDeValidation(d) {
  return typeof d?.nature === "string" && Object.hasOwn(NATURES, d.nature) ? {cle: d.nature, libelle: NATURES[d.nature]} : null;
}
export function modeOperatoire(d) {
  const m = d?.mode_operatoire;
  const ok = d?.nature === "en_jeu" && Array.isArray(m) && m.length >= 2 && m.length <= 10
    && m.every((x) => plein(x) && x.trim().length <= 200);
  return ok ? m.map((x) => x.trim()) : [];
}

// Les points à vérifier de la décision : ceux qu'elle porte (1 à 8 phrases de 160 caractères au plus, sans doublon),
// sinon un seul : « L'élément correspond à l'objectif » (les décisions d'avant).
export function pointsDeValidation(d) {
  const p = d?.points;
  const ok = Array.isArray(p) && p.length >= 1 && p.length <= MAX_POINTS
    && p.every((x) => plein(x) && x.trim().length <= MAX_POINT) && new Set(p.map((x) => x.trim())).size === p.length;
  return ok ? p.map((x) => x.trim()) : [POINT_PAR_DEFAUT];
}

// « 12,3 Mo », « 850 Ko », « 512 octets » ; « » pour une taille inconnue.
export function tailleLisible(octets) {
  if (typeof octets !== "number" || !Number.isFinite(octets) || octets < 0) return "";
  if (octets < 1024) return `${octets} octet${octets > 1 ? "s" : ""}`;
  const [n, unite] = octets < 1024 * 1024 ? [octets / 1024, "Ko"] : octets < 1024 ** 3 ? [octets / 1024 ** 2, "Mo"]
    : [octets / 1024 ** 3, "Go"];
  return `${(n < 10 ? n.toFixed(1) : Math.round(n).toString()).replace(".", ",")} ${unite}`;
}

export const estHoteLocal = (hote) => HOTES_LOCAUX.includes(String(hote || "").toLowerCase());

// L'adresse de téléchargement d'un livrable (relative au bureau, avec le projet courant), et sa forme absolue quand la
// page connaît son origine (le téléphone, via Tailscale : l'adresse du bureau qu'il a ouverte).
export function urlTelechargement(fonctionnalite, chemin, projet = projetCourant(), origine = null) {
  const relative = avecProjet(`/api/telecharger?fonctionnalite=${encodeURIComponent(fonctionnalite)}`
    + `&chemin=${encodeURIComponent(chemin)}`, projet);
  return origine ? origine.replace(/\/$/, "") + relative : relative;
}

// Le lien d'accès d'un site qui tourne : sur l'ordinateur (page servie par 127.0.0.1/localhost), le lien direct ; au
// téléphone, une URL de l'ordinateur passe par le relais du bureau `/apercu/<projet>/<décision>/…` ; une URL d'ailleurs
// (un hébergement d'essai) reste directe. `null` si le lien est illisible ou n'est pas http(s).
export function lienAcces(d, {hotePage = "127.0.0.1", projet = projetCourant(), origine = null} = {}) {
  const a = d?.acces;
  if (!a || !plein(a.url)) return null;
  let u;
  try { u = new URL(a.url); } catch { return null; }
  if (u.protocol !== "http:" && u.protocol !== "https:") return null;
  const description = plein(a.description) ? a.description.trim() : "";
  const relaye = u.protocol === "http:" && estHoteLocal(u.hostname) && u.port !== "" && !estHoteLocal(hotePage);
  if (!relaye) return {url: u.href, description, relaye: false, cible: u.href};
  const prefixe = `/apercu/${encodeURIComponent(projet || "-")}/${encodeURIComponent(d.id)}`;
  const url = (origine ? origine.replace(/\/$/, "") : "") + prefixe + u.pathname + u.search + u.hash;
  return {url, description, relaye: true, cible: u.href};
}

// Ce qu'il y a à vérifier : les images (montrées, agrandissables), les livrables téléchargeables (nom, taille, date),
// les autres fichiers (nommés) et le lien d'accès.
export function aVerifier(d, options = {}) {
  const images = [], livrables = [], autres = [];
  for (const f of Array.isArray(d?.fichiers) ? d.fichiers : []) {
    if (!plein(f?.chemin)) continue;
    const nom = f.chemin.split(/[\\/]/).pop();
    const titre = plein(f.titre) ? f.titre : nom;
    if (estImage(f.chemin)) images.push({chemin: f.chemin, legende: titre !== nom ? titre : ""});
    else if (estTelechargeable(f.chemin)) {
      livrables.push({chemin: f.chemin, nom, titre, taille: tailleLisible(f.taille), date: plein(f.date) ? f.date : "",
                      url: urlTelechargement(d.fonctionnalite, f.chemin, options.projet ?? projetCourant(),
                                             options.origine || null)});
    } else autres.push({chemin: f.chemin, titre});
  }
  return {images, livrables, autres, acces: lienAcces(d, options)};
}

// La demande envoyée : `null` tant qu'un point n'a pas sa réponse ; sinon une réponse par point (dans l'ordre), le
// verdict qui en découle et le texte libre s'il y en a un. `choix` : point -> true (OK) | false (À revoir).
export function corpsValidation(d, choix, texte) {
  const points = pointsDeValidation(d);
  if (points.some((p) => typeof choix?.[p] !== "boolean")) return null;
  const reponses = points.map((p) => ({point: p, ok: choix[p]}));
  const corps = {type: "valider_etape", decision: d.id, verdict: reponses.every((r) => r.ok) ? "valider" : "renvoyer",
    reponses};
  const libre = String(texte ?? "").trim();
  if (libre) corps.texte = libre.slice(0, MAX_TEXTE);
  return corps;
}

// Le libellé du bouton d'envoi selon les réponses données.
export function libelleEnvoi(d, choix) {
  const points = pointsDeValidation(d);
  const manquent = points.filter((p) => typeof choix?.[p] !== "boolean").length;
  if (manquent) return `Répondez aux ${manquent} point${manquent > 1 ? "s" : ""} restant${manquent > 1 ? "s" : ""}`;
  const refuses = points.filter((p) => choix[p] === false).length;
  return refuses ? `Renvoyer : ${refuses} point${refuses > 1 ? "s" : ""} à revoir` : "Valider l'élément";
}

function origineDeLaPage() {
  try { return globalThis.location?.origin || null; } catch { return null; }
}
function hoteDeLaPage() {
  try { return globalThis.location?.hostname || "127.0.0.1"; } catch { return "127.0.0.1"; }
}

function section(titre) {
  const s = el("section", "val-partie");
  s.append(el("h3", "", titre));
  return s;
}

// Le contenu de la fenêtre (sans le fond ni le clavier) : testé avec un faux DOM. `fermer()` est appelée après un envoi
// accepté. Rend `{boite, fermer: bouton}`.
export function contenuValidation(ctx, d, {fermer = () => {}, hotePage = hoteDeLaPage(), origine = origineDeLaPage()} = {}) {
  const boite = el("div", "val-boite");
  boite.setAttribute("role", "dialog");
  boite.setAttribute("aria-modal", "true");
  boite.setAttribute("aria-labelledby", "val-titre");
  const tete = el("div", "val-tete");
  const titre = el("h2", "val-titre", `Validation : ${d.element?.nom || d.element?.id || "élément"}`);
  titre.id = "val-titre";
  const bFermer = el("button", "val-fermer", "×");
  bFermer.type = "button";
  bFermer.setAttribute("aria-label", "Fermer");
  bFermer.addEventListener("click", () => fermer());
  tete.append(titre, bFermer);
  boite.append(tete);

  // 1. Ce qu'il y a à valider.
  const s1 = section("Ce que vous validez");
  for (const x of enteteValidation(d)) {
    const ligne = el("p", "val-entete");
    ligne.append(el("strong", "", `${x.libelle} : `), el("span", "", x.texte));
    s1.append(ligne);
  }
  if (!enteteValidation(d).length && plein(d.texte)) s1.append(el("p", "val-entete", d.texte));
  const nature = natureDeValidation(d);
  if (nature) s1.append(el("p", "val-nature val-nature-" + nature.cle, nature.libelle));
  for (const b of consignesDeValidation(d)) {
    const bloc = el("div", "val-consigne val-consigne-" + b.cle);
    bloc.append(el("h4", "", b.libelle), el("p", "", b.texte));
    s1.append(bloc);
  }
  boite.append(s1);

  // 2. De quoi vérifier.
  const v = aVerifier(d, {hotePage, origine});
  const s2 = section("À vérifier");
  for (const l of v.livrables) {
    const ligne = el("div", "val-livrable");
    const texte = el("div", "val-livrable-texte");
    texte.append(el("strong", "", l.titre), el("span", "val-meta", [l.nom, l.taille, l.date ? dateFr(l.date) : ""]
      .filter(Boolean).join(" · ")));
    const a = el("a", "bouton val-telecharger", "Télécharger");
    a.href = l.url;
    a.setAttribute("download", l.nom);
    ligne.append(texte, a);
    s2.append(ligne);
  }
  const etapes = modeOperatoire(d);
  if (etapes.length) {
    const mode = el("div", "val-mode");
    mode.append(el("h4", "", "Mode opératoire"));
    const liste = el("ol", "val-mode-etapes");
    for (const e of etapes) liste.append(el("li", "", e));
    mode.append(liste);
    s2.append(mode);
  }
  if (v.acces) {
    const ligne = el("div", "val-acces");
    const texte = el("div", "val-livrable-texte");
    texte.append(el("strong", "", v.acces.description || "Le site qui tourne"),
                 el("span", "val-meta", v.acces.relaye ? `${v.acces.cible}, ouvert à travers le bureau` : v.acces.cible));
    const a = el("a", "bouton val-ouvrir", "Ouvrir");
    a.href = v.acces.url;
    a.target = "_blank";
    a.rel = "noopener";
    ligne.append(texte, a);
    s2.append(ligne);
  }
  if (v.images.length) {
    const galerie = el("div", "val-images");
    for (const im of v.images) {
      const fig = el("figure", "val-image");
      const b = el("button", "val-vignette");
      b.type = "button";
      b.setAttribute("aria-label", "Agrandir : " + (im.legende || im.chemin));
      const img = el("img", "");
      img.src = avecProjet(`/api/image?chemin=${encodeURIComponent(im.chemin)}`, projetCourant());
      img.alt = im.legende || im.chemin;
      reessayerImage(img);
      b.append(img);
      b.addEventListener("click", () => {
        fig.classList?.toggle("agrandie");
        b.setAttribute("aria-label", (fig.classList?.contains("agrandie") ? "Réduire : " : "Agrandir : ")
          + (im.legende || im.chemin));
      });
      fig.append(b);
      if (im.legende) fig.append(el("figcaption", "val-legende", im.legende));
      galerie.append(fig);
    }
    s2.append(galerie);
  }
  for (const f of v.autres) s2.append(el("p", "val-meta", `${f.titre} : ${f.chemin}`));
  if (!v.livrables.length && !v.acces && !v.images.length) {
    s2.append(el("p", "val-meta", "Rien à télécharger ni à ouvrir pour cet élément (posé avant la fenêtre de "
      + "validation) : jugez-le sur son compte rendu, ou renvoyez-le en demandant de quoi le vérifier."));
  }
  boite.append(s2);

  // 3. Le compte rendu de l'élément.
  if (plein(d.compte_rendu)) {
    const s3 = section("Compte rendu");
    s3.append(el("p", "val-compte-rendu", d.compte_rendu));
    boite.append(s3);
  }

  // 4. Les points à vérifier, 5. le champ libre, puis l'envoi.
  const points = pointsDeValidation(d);
  const choix = {};
  const s4 = section("Points à vérifier");
  const agir = ctx.etat?.agir === true;
  const envoi = el("button", "bouton val-envoyer", libelleEnvoi(d, choix));
  envoi.type = "button";
  const libre = el("textarea", "val-libre");
  const erreur = el("p", "saisie-erreur", "");
  const maj = () => {
    envoi.textContent = libelleEnvoi(d, choix);
    envoi.disabled = corpsValidation(d, choix, "") === null;
    envoi.className = "bouton val-envoyer" + (points.some((p) => choix[p] === false) ? " secondaire" : "");
  };
  points.forEach((p, i) => {
    const groupe = el("fieldset", "val-point");
    groupe.append(el("legend", "", p));
    const bulles = el("div", "val-bulles");
    for (const [ok, libelle] of [[true, "OK"], [false, "À revoir"]]) {
      const etiquette = el("label", "val-bulle " + (ok ? "ok" : "a-revoir"));
      const radio = el("input", "");
      radio.type = "radio";
      radio.name = `val-point-${i}`;
      radio.value = ok ? "ok" : "a_revoir";
      radio.disabled = !agir;
      radio.addEventListener("change", () => { choix[p] = ok; erreur.textContent = ""; maj(); });
      etiquette.append(radio, el("span", "", libelle));
      bulles.append(etiquette);
    }
    groupe.append(bulles);
    s4.append(groupe);
  });
  boite.append(s4);
  if (!agir) {
    boite.append(el("p", "val-meta", "Ce bureau ne peut pas agir sur le projet : la validation se lit seulement."));
    return {boite, fermer: bFermer, choix};
  }
  const s5 = section("Autre chose à signaler (facultatif)");
  libre.rows = 3;
  libre.maxLength = MAX_TEXTE;
  libre.placeholder = "Ce qui sort des points ci-dessus : l'agent suivant le lira.";
  libre.setAttribute("aria-label", "Autre chose à signaler");
  s5.append(libre);
  boite.append(s5);
  envoi.addEventListener("click", async () => {
    const corps = corpsValidation(d, choix, libre.value);
    if (!corps) { erreur.textContent = "Choisissez OK ou À revoir pour chaque point."; return; }
    envoi.disabled = true;
    const r = await ctx.barre.demander(corps, envoi);
    if (r?.ok) fermer();
    else { envoi.disabled = false; erreur.textContent = r?.message || "La demande n'est pas partie."; }
  });
  maj();
  const pied = el("div", "val-pied");
  pied.append(erreur, envoi);
  boite.append(pied);
  return {boite, fermer: bFermer, choix};
}

// Ouvre la fenêtre par-dessus le bureau. `declencheur` reprend le focus à la fermeture.
export function ouvrirValidation(ctx, d, declencheur = null) {
  document.querySelector(".val-fond")?.remove();     // une seule fenêtre à la fois
  const fond = el("div", "val-fond");
  let boite = null;
  const focalisables = () => [...boite.querySelectorAll(
    "button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled])")]
    .filter((x) => !x.hidden && x.offsetParent !== null);
  const clavier = (ev) => {
    if (ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      const grande = boite.querySelector(".val-image.agrandie");
      if (grande) { grande.classList.remove("agrandie"); return; }   // d'abord l'image agrandie
      fermerFenetre();
      return;
    }
    if (ev.key !== "Tab") return;
    const f = focalisables();
    if (!f.length) { ev.preventDefault(); return; }
    const premier = f[0], dernier = f[f.length - 1];
    if (!boite.contains(document.activeElement)) { ev.preventDefault(); premier.focus(); }
    else if (ev.shiftKey && document.activeElement === premier) { ev.preventDefault(); dernier.focus(); }
    else if (!ev.shiftKey && document.activeElement === dernier) { ev.preventDefault(); premier.focus(); }
  };
  function fermerFenetre() {
    document.removeEventListener("keydown", clavier, true);
    fond.remove();
    document.body.classList.remove("val-ouverte");
    if (declencheur && declencheur.isConnected) declencheur.focus();
  }
  const rendu = contenuValidation(ctx, d, {fermer: fermerFenetre});
  boite = rendu.boite;
  fond.append(boite);
  fond.addEventListener("mousedown", (ev) => { if (ev.target === fond) fermerFenetre(); });
  document.addEventListener("keydown", clavier, true);
  document.body.classList.add("val-ouverte");
  document.body.append(fond);
  rendu.fermer.focus();
  return fermerFenetre;
}
