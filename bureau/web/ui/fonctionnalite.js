// Le panneau d'une fonctionnalité : bandeau du parcours, discussion de cadrage, pièces du cahier des charges.
// Les fonctions pures sont testées avec node. Tout geste est une demande au projet (`ctx.barre.demander`) ;
// tout texte venu du relevé passe par textContent.

import {el} from "./dom.js";
import {dateFr, tronquer} from "./texte.js";
import {lienSur} from "./actions.js";
import {urlProjet} from "./projets.js";

export const MAX_TEXTE = 3500;
const MAX_IMAGES = 4;
const MAX_OCTETS = 5 * 1024 * 1024;
const MAX_NOM = 80;

export const ETAPES_PARCOURS = [
  {id: "cadrage", libelle: "Cadrage"},
  {id: "cahier", libelle: "Cahier des charges"},
  {id: "decoupage", libelle: "Découpage"},
  {id: "prototype", libelle: "Prototype"},
  {id: "methode", libelle: "Méthode"},
  {id: "serie", libelle: "Série"},
];

// Le bandeau du parcours : les étapes d'avant la courante sont faites ; `terminee` : toutes faites.
export function bandeau(etape) {
  const rang = etape === "terminee" ? ETAPES_PARCOURS.length : ETAPES_PARCOURS.findIndex((e) => e.id === etape);
  return ETAPES_PARCOURS.map((e, i) => ({libelle: e.libelle, courante: rang >= 0 && i === rang, faite: rang >= 0 && i < rang}));
}

// --- Les demandes (champs exacts de la spec, §8.2).
const plein = (t) => typeof t === "string" && t.trim() !== "";

export function demandeNouvelle(texte, images) {
  const d = {type: "fonctionnalite", texte};
  if (images && images.length) d.images = images;
  return d;
}

export function demandeMessage(fonc, texte, images) {
  const d = {type: "message", fonctionnalite: fonc, texte};
  if (images && images.length) d.images = images;
  return d;
}

export function demandeCahier(fonc, verdict, texte) {
  const d = {type: "cahier", fonctionnalite: fonc, verdict};
  if (plein(texte)) d.texte = texte;
  return d;
}

export function demandeMethode(fonc, verdict, texte) {
  const d = {type: "methode", fonctionnalite: fonc, verdict};
  if (plein(texte)) d.texte = texte;
  return d;
}

// --- Les images jointes : mêmes règles que le serveur (4 au plus, 5 Mo, PNG ou JPEG, nom simple).
const TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"};

export function verifierPieces(fichiers) {
  const liste = Array.from(fichiers || []);
  if (liste.length > MAX_IMAGES) return `${MAX_IMAGES} images au plus par message.`;
  for (const f of liste) {
    const nom = String(f?.name ?? "");
    const point = nom.lastIndexOf(".");
    const attendu = point >= 0 ? TYPES[nom.slice(point).toLowerCase()] : undefined;
    if (!attendu || (f.type !== "image/png" && f.type !== "image/jpeg")) return `« ${tronquer(nom, 40)} » doit être une image PNG ou JPEG.`;
    if (f.type !== attendu) return `Le type de « ${tronquer(nom, 40)} » ne correspond pas à son extension.`;
    if (!(f.size <= MAX_OCTETS)) return `« ${tronquer(nom, 40)} » dépasse 5 Mo.`;
    if (nom.length > MAX_NOM || /[\/\\:\u0000-\u001f]/.test(nom) || nom.includes("..")) return `Le nom de « ${tronquer(nom, 40)} » n'est pas valide.`;
  }
  return null;
}

// Un fichier choisi → {nom, type, donnees} (base64), prêt à joindre à une demande.
export async function lireImage(fichier) {
  const octets = new Uint8Array(await fichier.arrayBuffer());
  let binaire = "";
  for (let i = 0; i < octets.length; i += 0x8000) binaire += String.fromCharCode(...octets.subarray(i, i + 0x8000));
  return {nom: fichier.name, type: fichier.type, donnees: btoa(binaire)};
}

// La ligne sous la discussion : l'agent écrit (l'orchestrateur tourne), ou on attend l'orchestrateur.
export function ecrit(fonc, etat) {
  if (!fonc || fonc.attend_reponse !== true) return null;
  if (etat?.orchestrateur_actif !== true) return "En attente de l'orchestrateur";
  // Celui qui travaille sur la fonctionnalité : l'agent de sa tâche active la plus récente, sinon le dernier agent
  // qui a parlé dans la discussion, sinon l'agent de cadrage.
  const actives = (etat.taches || []).filter((t) => t.fonctionnalite === fonc.id && t.active && t.agent)
    .sort((a, b) => String(b.maj || "").localeCompare(String(a.maj || "")));
  const dernier = [...(fonc.discussion || [])].reverse().find((m) => m.auteur && m.auteur !== "utilisateur");
  const qui = actives[0]?.agent || dernier?.auteur || fonc.agent_cadrage;
  const prenom = (etat.agents || []).find((a) => a.id === qui)?.prenom;
  return `${prenom || "L'agent de cadrage"} est en train d'écrire…`;
}

// La fonctionnalité apparue entre deux états dont le premier message est ce texte (sinon null).
export function nouvelleApparue(avant, apres, texte) {
  const connues = new Set((avant?.fonctionnalites || []).map((f) => f.id));
  const f = (apres?.fonctionnalites || []).find((x) => !connues.has(x.id) && x.discussion?.[0]?.texte === texte);
  return f ? f.id : null;
}

// Ce que le panneau montre : quand le cahier des charges attend le verdict de l'utilisateur, la discussion est repliée
// pour laisser lire le cahier ; « Demander une correction » la rouvre, et « Envoyer » envoie alors la correction.
export function presentation(f, agir, enCorrection) {
  const cahierAValider = agir === true && (f?.decisions || []).some((d) => d.genre === "valider_cahier");
  return {discussionOuverte: !cahierAValider || enCorrection === true,
          envoiCorrection: cahierAValider && enCorrection === true};
}

// --- Le panneau.
const urlImage = (chemin) => urlProjet(`/api/image?chemin=${encodeURIComponent(chemin)}`);

// Les documents de la fonctionnalité, rangés par étape : celles du parcours dans l'ordre, puis les colonnes du flux
// (une tâche range ses captures sous sa colonne), puis « Autres » ; dans chaque groupe, les plus récents d'abord.
export function documentsParEtape(f, colonnes) {
  const groupes = new Map();
  const libelle = (etape) => ETAPES_PARCOURS.find((x) => x.id === etape)?.libelle
    || (colonnes || []).find((c) => c.id === etape)?.nom || "Autres";
  const rang = (etape) => {
    const i = ETAPES_PARCOURS.findIndex((x) => x.id === etape);
    if (i >= 0) return i;
    const j = (colonnes || []).findIndex((c) => c.id === etape);
    return j >= 0 ? 100 + j : 1000;
  };
  for (const d of Array.isArray(f?.documents) ? f.documents : []) {
    const cle = libelle(d.etape);
    if (!groupes.has(cle)) groupes.set(cle, {libelle: cle, rang: rang(d.etape), documents: []});
    groupes.get(cle).documents.push(d);
  }
  return [...groupes.values()].sort((a, b) => a.rang - b.rang).map(({libelle, documents}) => ({
    libelle, documents: documents.map((d, i) => [d, i])
      .sort(([a, i], [b, j]) => String(b.date || "").localeCompare(String(a.date || "")) || i - j).map(([d]) => d),
  }));
}

const EST_IMAGE = /\.(png|jpe?g)$/i;

// La partie « Documents » du panneau : chaque document avec son origine ; une image s'ouvre dans la visionneuse.
function partieDocuments(ctx, f) {
  const groupes = documentsParEtape(f, ctx.etat.colonnes);
  const n = (f.documents || []).length;
  const bloc = el("details", "documents");
  bloc.append(el("summary", "", `Documents (${n})`));
  if (!n) { bloc.append(el("p", "note", "Aucun document pour l'instant.")); return bloc; }
  const url = (chemin) => urlProjet(`/api/document?fonctionnalite=${encodeURIComponent(f.id)}&chemin=${encodeURIComponent(chemin)}`);
  for (const g of groupes) {
    bloc.append(el("h4", "", g.libelle));
    const ul = el("ul", "liste-documents");
    const images = g.documents.filter((d) => EST_IMAGE.test(d.chemin)).map((d) => d.chemin);
    for (const d of g.documents) {
      const li = el("li", "document");
      if (EST_IMAGE.test(d.chemin)) {
        const b = el("button", "document-vignette");
        b.type = "button";
        b.setAttribute("aria-label", "Voir en plein écran : " + d.titre);
        const img = document.createElement("img");
        img.loading = "lazy";
        img.src = url(d.chemin);
        img.alt = d.titre;
        b.append(img);
        b.addEventListener("click", () => ouvrirVisionneuse(images, images.indexOf(d.chemin), url));
        li.append(b);
      } else {
        const a = el("a", "document-lien", "Ouvrir");
        a.href = url(d.chemin);
        a.target = "_blank";
        a.rel = "noopener";
        li.append(a);
      }
      const texte = el("div", "document-texte");
      texte.append(el("strong", "", d.titre));
      const origine = [d.agent ? (d.agent === "utilisateur" ? "Vous" : nomAgentDe(ctx.etat, d.agent)) : null,
        d.tache ? "tâche " + d.tache : null, d.element ? "élément " + d.element : null, d.sous_tache || null,
        d.date ? dateFr(d.date) : null].filter(Boolean).join(" · ");
      if (origine) texte.append(el("div", "note", origine));
      texte.append(el("div", "document-chemin", d.chemin));
      li.append(texte);
      ul.append(li);
    }
    bloc.append(ul);
  }
  return bloc;
}

const nomAgentDe = (e, cle) => (e.agents || []).find((a) => a.id === cle)?.prenom || cle;

// L'image voisine dans une série de n images (on fait le tour : après la dernière, la première).
export function voisine(n, i, sens) {
  return n > 0 ? (i + sens + n) % n : 0;
}

// La visionneuse plein écran : une image à la fois, flèches gauche et droite (ou boutons), Échap pour fermer.
function ouvrirVisionneuse(chemins, depart, url = urlImage) {
  let i = depart;
  const fond = el("div", "visionneuse");
  fond.setAttribute("role", "dialog");
  fond.setAttribute("aria-modal", "true");
  fond.setAttribute("aria-label", "Images du message");
  const img = document.createElement("img");
  const compteur = el("div", "visionneuse-compteur", "");
  const fermer = el("button", "visionneuse-fermer", "×");
  const avant = el("button", "visionneuse-fleche gauche", "‹");
  const apres = el("button", "visionneuse-fleche droite", "›");
  for (const [b, nom] of [[fermer, "Fermer"], [avant, "Image précédente"], [apres, "Image suivante"]]) {
    b.type = "button";
    b.setAttribute("aria-label", nom);
  }
  const montrer = () => {
    img.src = url(chemins[i]);
    img.alt = `Image ${i + 1} sur ${chemins.length}`;
    compteur.textContent = chemins.length > 1 ? `${i + 1} / ${chemins.length}` : "";
    avant.hidden = apres.hidden = chemins.length < 2;
  };
  const aller = (sens) => { i = voisine(chemins.length, i, sens); montrer(); };
  const clavier = (ev) => {   // capturé avant le panneau : Échap ferme la visionneuse, pas le panneau
    if (ev.key === "Escape") { ev.stopPropagation(); ev.preventDefault(); clore(); }
    else if (ev.key === "ArrowLeft") { ev.stopPropagation(); aller(-1); }
    else if (ev.key === "ArrowRight") { ev.stopPropagation(); aller(1); }
  };
  const clore = () => { document.removeEventListener("keydown", clavier, true); fond.remove(); };
  fermer.addEventListener("click", clore);
  avant.addEventListener("click", () => aller(-1));
  apres.addEventListener("click", () => aller(1));
  fond.addEventListener("click", (ev) => { if (ev.target === fond) clore(); });
  document.addEventListener("keydown", clavier, true);
  fond.append(img, avant, apres, compteur, fermer);
  document.body.append(fond);
  montrer();
  fermer.focus();
}

function vignettes(chemins, etat) {
  const zone = el("div", "vignettes");
  (chemins || []).forEach((chemin, n) => {
    const fig = el("figure", "vignette");
    if (etat.images_ok === true) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = urlImage(chemin);
      img.alt = "Image jointe";
      // Au survol : agrandir dans la discussion, ou voir en plein écran (avec les autres images du message).
      const outils = el("div", "vignette-outils");
      const agrandir = el("button", "vignette-bouton", "Agrandir");
      const plein = el("button", "vignette-bouton", "Plein écran");
      for (const b of [agrandir, plein]) b.type = "button";
      agrandir.addEventListener("click", (ev) => {
        ev.stopPropagation();
        fig.classList.toggle("agrandie");
        agrandir.textContent = fig.classList.contains("agrandie") ? "Réduire" : "Agrandir";
      });
      plein.addEventListener("click", (ev) => { ev.stopPropagation(); ouvrirVisionneuse(chemins, n); });
      outils.append(agrandir, plein);
      fig.append(img, outils);
    } else {
      fig.append(el("figcaption", "", "Image non affichable (aucune racine d'images déclarée)"));
    }
    zone.append(fig);
  });
  return zone;
}

function messageDe(m, etat) {
  const li = el("li", "message");
  const utilisateur = m.auteur === "utilisateur";
  li.classList.add(utilisateur ? "message-utilisateur" : "message-agent");
  const qui = utilisateur ? "Vous" : [m.prenom || m.auteur, m.service].filter(Boolean).join(" · ");
  const tete = el("div", "message-tete");
  tete.append(el("strong", "", qui), el("span", "date", m.t ? dateFr(m.t) : ""));
  li.append(tete, el("div", "message-texte", m.texte));
  if ((m.images || []).length) li.append(vignettes(m.images, etat));
  return li;
}

function miniature(i) {
  const fig = el("figure", "vignette");
  const img = document.createElement("img");
  img.src = `data:${i.type};base64,${i.donnees}`;
  img.alt = i.nom;
  fig.append(img);
  return fig;
}

function messageLocal(envoi) {
  const li = el("li", "message message-utilisateur message-local");
  li.append(el("div", "message-tete", "Vous"), el("div", "message-texte", envoi.texte));
  if (envoi.images.length) {
    const zone = el("div", "vignettes");
    for (const i of envoi.images) zone.append(miniature(i));
    li.append(zone);
  }
  return li;
}

function lienExterne(url, texte) {
  const a = el("a", "lien-tache", texte);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

// La zone de saisie : texte, images jointes (vignettes avant envoi), envoi. Le brouillon survit aux rafraîchissements.
// `envoyerDemande(texte, images, bouton)` rend {ok}. Un envoi en cours (`ctx.envois`) grise « Envoyer », même après un redessin.
function saisie(ctx, cle, envoyerDemande, {libelle = "Envoyer", images = true, invite = "Écrire un message…"} = {}) {
  const brouillon = ctx.brouillons.get(cle) || {texte: "", images: []};
  ctx.brouillons.set(cle, brouillon);
  const bloc = el("section", "saisie-discussion");
  const zone = document.createElement("textarea");
  zone.rows = 3;
  zone.maxLength = MAX_TEXTE;
  zone.placeholder = invite;
  zone.value = brouillon.texte;
  zone.dataset.saisie = "1";
  const miniatures = el("div", "vignettes");
  const erreur = el("p", "saisie-erreur", "");
  erreur.setAttribute("aria-live", "polite");
  const envoyer = el("button", "bouton", libelle);
  envoyer.type = "button";
  const joindre = el("button", "bouton secondaire", "Joindre une image");
  joindre.type = "button";
  const fichier = document.createElement("input");
  fichier.type = "file";
  fichier.accept = "image/png,image/jpeg";
  fichier.multiple = true;
  fichier.hidden = true;

  const maj = () => { envoyer.disabled = !zone.value.trim() || ctx.envois.has(cle); };
  function dessinerMiniatures() {
    miniatures.replaceChildren();
    brouillon.images.forEach((i, n) => {
      const fig = miniature(i);
      const retirer = el("button", "vignette-retirer", "×");
      retirer.type = "button";
      retirer.setAttribute("aria-label", `Retirer ${i.nom}`);
      retirer.addEventListener("click", () => { brouillon.images.splice(n, 1); dessinerMiniatures(); });
      fig.append(retirer);
      miniatures.append(fig);
    });
  }
  zone.addEventListener("input", () => { brouillon.texte = zone.value; maj(); });
  joindre.addEventListener("click", () => fichier.click());
  fichier.addEventListener("change", async () => {
    const choisis = Array.from(fichier.files);
    fichier.value = "";
    const dejaLa = brouillon.images.map((i) => ({name: i.nom, type: i.type, size: 0}));
    const probleme = verifierPieces([...dejaLa, ...choisis]);
    if (probleme) { erreur.textContent = probleme; return; }
    erreur.textContent = "";
    try { for (const f of choisis) brouillon.images.push(await lireImage(f)); }
    catch { erreur.textContent = "Une image n'a pas pu être lue."; }
    dessinerMiniatures();
  });
  envoyer.addEventListener("click", async () => {
    if (ctx.envois.has(cle) || !zone.value.trim()) return;   // un double clic ne crée qu'une demande
    ctx.envois.add(cle);
    envoyer.disabled = true;
    const texte = zone.value, images = brouillon.images.slice();
    let r;
    try { r = await envoyerDemande(texte, images, envoyer); } finally { ctx.envois.delete(cle); }
    if (r?.ok) { brouillon.texte = ""; brouillon.images = []; ctx.rouvrir(); }
    else maj();
  });
  maj();
  dessinerMiniatures();
  const rangee = el("div", "retour-pied");
  if (images) rangee.append(joindre);
  rangee.append(envoyer);
  bloc.append(zone, miniatures, erreur, rangee, fichier);
  return {bloc, texte: () => zone.value};
}

// f : la fonctionnalité du relevé, ou null pour une discussion neuve.
export function contenuFonctionnalite(ctx, contenu, f) {
  const e = ctx.etat;
  const cle = "f:" + (f ? f.id : "nouvelle");
  contenu.append(el("h2", "", f ? f.nom : "Nouvelle fonctionnalité"));
  if (f) {
    const ol = el("ol", "parcours");
    for (const b of bandeau(f.etape)) {
      const li = el("li", "etape" + (b.courante ? " courante" : "") + (b.faite ? " faite" : ""), b.libelle);
      if (b.courante) li.setAttribute("aria-current", "step");
      ol.append(li);
    }
    contenu.append(ol);
  } else {
    contenu.append(el("p", "note", "Décrivez ce que vous voulez : l'agent de cadrage vous répondra ici."));
  }

  const vue = presentation(f, e.agir, f ? ctx.corrections.has(f.id) : false);
  const blocDiscussion = el("div", "bloc-discussion");

  // La discussion, du plus ancien au plus récent, puis les messages envoyés que le relevé n'a pas encore repris.
  const discussion = el("ul", "discussion");
  const messages = f ? f.discussion || [] : [];
  for (const m of messages) discussion.append(messageDe(m, e));
  const repris = new Set(messages.filter((m) => m.auteur === "utilisateur").map((m) => m.texte));
  const locaux = f ? (ctx.envoyes.get(f.id) || []).filter((x) => !repris.has(x.texte))
                   : (ctx.nouvelle.envoi ? [ctx.nouvelle.envoi] : []);
  if (f) ctx.envoyes.set(f.id, locaux);
  for (const x of locaux) discussion.append(messageLocal(x));
  if (!messages.length && !locaux.length) discussion.append(el("li", "vide", "Aucun message"));
  blocDiscussion.append(discussion);
  // On arrive sur le dernier message, pas en haut de la discussion.
  requestAnimationFrame(() => { discussion.scrollTop = discussion.scrollHeight; });

  const phrase = ecrit(f, e) || (locaux.length ? ecrit({attend_reponse: true, agent_cadrage: f?.agent_cadrage}, e) : null);
  if (phrase) {
    const p = el("p", "ecrit", phrase);
    p.setAttribute("aria-live", "polite");
    blocDiscussion.append(p);
  }

  if (e.agir === true) {
    const s = vue.envoiCorrection
      ? saisie(ctx, cle + ":correction", async (texte, images, bouton) => {
          const r = await ctx.barre.demander(demandeCahier(f.id, "corriger", texte), bouton);
          if (r.ok) ctx.corrections.delete(f.id);
          return r;
        }, {libelle: "Envoyer la correction", images: false, invite: "Ce qu'il faut corriger dans le cahier des charges…"})
      : saisie(ctx, cle, async (texte, images, bouton) => {
          const joints = images.map(({nom, type, donnees}) => ({nom, type, donnees}));
          if (!f) ctx.nouvelle.envoi = {avant: e, texte, images};
          const r = await ctx.barre.demander(f ? demandeMessage(f.id, texte, joints) : demandeNouvelle(texte, joints), bouton);
          if (r.ok && f) ctx.envoyes.set(f.id, [...(ctx.envoyes.get(f.id) || []), {texte, images}]);
          if (!r.ok && !f) ctx.nouvelle.envoi = null;
          return r;
        });
    blocDiscussion.append(s.bloc);
  }
  if (!f) { contenu.append(blocDiscussion); return; }

  // Les pièces du cahier des charges et de la méthode.
  const blocCahier = el("div", "bloc-cahier");
  if (f.cahier) {
    blocCahier.append(el("h3", "", "Cahier des charges"));
    if ((f.cahier.maquette || []).length) blocCahier.append(vignettes(f.cahier.maquette, e));
    const etapes = el("ol", "etapes-cahier");
    for (const t of f.cahier.etapes || []) etapes.append(el("li", "", t));
    blocCahier.append(etapes);
    if (f.cahier.valide_le) blocCahier.append(el("p", "note", "Validé le " + dateFr(f.cahier.valide_le)));
  }
  const decisions = new Set((f.decisions || []).map((d) => d.genre));
  const gestes = el("div", "gestes");
  const geste = (libelle, classe, demande) => {
    const b = el("button", classe, libelle);
    b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      const r = await ctx.barre.demander(demande(), b);
      if (!r.ok) b.disabled = false;
    });
    gestes.append(b);
  };
  if (e.agir === true && decisions.has("valider_cahier")) {
    geste("Valider le cahier des charges", "bouton", () => demandeCahier(f.id, "valider"));
    // La correction s'écrit dans la discussion, qui se rouvre ; « Envoyer la correction » l'envoie.
    const corriger = el("button", "bouton secondaire", vue.envoiCorrection ? "Annuler la correction" : "Demander une correction");
    corriger.type = "button";
    corriger.addEventListener("click", () => {
      if (ctx.corrections.has(f.id)) ctx.corrections.delete(f.id); else ctx.corrections.add(f.id);
      ctx.rouvrir();
      if (ctx.corrections.has(f.id)) requestAnimationFrame(() => document.querySelector(".panneau textarea[data-saisie]")?.focus());
    });
    gestes.append(corriger);
  }
  const blocMethode = el("div", "bloc-methode");
  if (f.methode) {
    blocMethode.append(el("h3", "", `Méthode (version ${f.methode.version})`));
    if (f.methode.lien && lienSur(f.methode.lien)) blocMethode.append(lienExterne(f.methode.lien, "Ouvrir la méthode"));
    else if (f.methode.chemin) blocMethode.append(el("p", "note", f.methode.chemin));
    if (f.methode.validee_le) blocMethode.append(el("p", "note", "Validée le " + dateFr(f.methode.validee_le)));
  }
  if (e.agir === true && decisions.has("valider_methode")) geste("Valider la méthode", "bouton", () => demandeMethode(f.id, "valider"));
  if (f.catalogue && typeof ctx.ouvrirCatalogue === "function") {
    const b = el("button", "bouton secondaire", "Catalogue");
    b.type = "button";
    b.addEventListener("click", () => ctx.ouvrirCatalogue(f.id));
    gestes.append(b);
  }
  if (vue.discussionOuverte) {
    contenu.append(blocDiscussion, blocCahier, blocMethode);
    if (gestes.childElementCount) contenu.append(gestes);
    contenu.append(partieDocuments(ctx, f));
  } else {
    const repliee = el("details", "discussion-repliee");
    repliee.append(el("summary", "", `Discussion (${messages.length} message${messages.length > 1 ? "s" : ""})`), blocDiscussion);
    contenu.append(blocCahier, blocMethode);
    if (gestes.childElementCount) contenu.append(gestes);
    contenu.append(repliee, partieDocuments(ctx, f));
  }
}

// La liste « Fonctionnalités » du projet.
export function contenuFonctionnalites(ctx, contenu) {
  contenu.append(el("h2", "", "Fonctionnalités"));
  const ul = el("ul", "liste-partie");
  const liste = ctx.etat.fonctionnalites || [];
  if (!liste.length) ul.append(el("li", "vide", "Aucune fonctionnalité"));
  for (const f of liste) {
    const li = el("li", "");
    const b = el("button", "lien-tache", f.nom);
    b.type = "button";
    b.addEventListener("click", () => ctx.ouvrirFonctionnalite(f.id));
    const etape = ETAPES_PARCOURS.find((x) => x.id === f.etape)?.libelle || (f.etape === "terminee" ? "Terminée" : f.etape);
    const n = (f.decisions || []).length;
    li.append(b, el("div", "note", etape + (n ? ` · ${n} décision${n > 1 ? "s" : ""}` : "")));
    ul.append(li);
  }
  contenu.append(ul);
  if (ctx.etat.agir === true) {
    const nouvelle = el("button", "bouton", "+ Nouvelle fonctionnalité");
    nouvelle.type = "button";
    nouvelle.addEventListener("click", () => ctx.ouvrirNouvelle());
    contenu.append(nouvelle);
  }
}
