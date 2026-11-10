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
  const prenom = (etat.agents || []).find((a) => a.id === fonc.agent_cadrage)?.prenom;
  return `${prenom || "L'agent de cadrage"} est en train d'écrire…`;
}

// La fonctionnalité apparue entre deux états dont le premier message est ce texte (sinon null).
export function nouvelleApparue(avant, apres, texte) {
  const connues = new Set((avant?.fonctionnalites || []).map((f) => f.id));
  const f = (apres?.fonctionnalites || []).find((x) => !connues.has(x.id) && x.discussion?.[0]?.texte === texte);
  return f ? f.id : null;
}

// --- Le panneau.
const urlImage = (chemin) => urlProjet(`/api/image?chemin=${encodeURIComponent(chemin)}`);

function vignettes(chemins, etat) {
  const zone = el("div", "vignettes");
  for (const chemin of chemins || []) {
    const fig = el("figure", "vignette");
    if (etat.images_ok === true) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = urlImage(chemin);
      img.alt = "Image jointe";
      fig.addEventListener("click", () => fig.classList.toggle("agrandie"));
      fig.append(img);
    } else {
      fig.append(el("figcaption", "", "Image non affichable (aucune racine d'images déclarée)"));
    }
    zone.append(fig);
  }
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
function saisie(ctx, cle, envoyerDemande) {
  const brouillon = ctx.brouillons.get(cle) || {texte: "", images: []};
  ctx.brouillons.set(cle, brouillon);
  const bloc = el("section", "saisie-discussion");
  const zone = document.createElement("textarea");
  zone.rows = 3;
  zone.maxLength = MAX_TEXTE;
  zone.placeholder = "Écrire un message…";
  zone.value = brouillon.texte;
  zone.dataset.saisie = "1";
  const miniatures = el("div", "vignettes");
  const erreur = el("p", "saisie-erreur", "");
  erreur.setAttribute("aria-live", "polite");
  const envoyer = el("button", "bouton", "Envoyer");
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
  rangee.append(joindre, envoyer);
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
  contenu.append(discussion);

  const phrase = ecrit(f, e) || (locaux.length ? ecrit({attend_reponse: true, agent_cadrage: f?.agent_cadrage}, e) : null);
  if (phrase) {
    const p = el("p", "ecrit", phrase);
    p.setAttribute("aria-live", "polite");
    contenu.append(p);
  }

  let leTexte = () => "";
  if (e.agir === true) {
    const s = saisie(ctx, cle, async (texte, images, bouton) => {
      const joints = images.map(({nom, type, donnees}) => ({nom, type, donnees}));
      if (!f) ctx.nouvelle.envoi = {avant: e, texte, images};
      const r = await ctx.barre.demander(f ? demandeMessage(f.id, texte, joints) : demandeNouvelle(texte, joints), bouton);
      if (r.ok && f) ctx.envoyes.set(f.id, [...(ctx.envoyes.get(f.id) || []), {texte, images}]);
      if (!r.ok && !f) ctx.nouvelle.envoi = null;
      return r;
    });
    leTexte = s.texte;
    contenu.append(s.bloc);
  }
  if (!f) return;

  // Les pièces du cahier des charges et de la méthode.
  if (f.cahier) {
    contenu.append(el("h3", "", "Cahier des charges"));
    if ((f.cahier.maquette || []).length) contenu.append(vignettes(f.cahier.maquette, e));
    const etapes = el("ol", "etapes-cahier");
    for (const t of f.cahier.etapes || []) etapes.append(el("li", "", t));
    contenu.append(etapes);
    if (f.cahier.valide_le) contenu.append(el("p", "note", "Validé le " + dateFr(f.cahier.valide_le)));
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
    geste("Demander une correction", "bouton secondaire", () => demandeCahier(f.id, "corriger", leTexte()));
  }
  if (f.methode) {
    contenu.append(el("h3", "", `Méthode (version ${f.methode.version})`));
    if (f.methode.lien && lienSur(f.methode.lien)) contenu.append(lienExterne(f.methode.lien, "Ouvrir la méthode"));
    else if (f.methode.chemin) contenu.append(el("p", "note", f.methode.chemin));
    if (f.methode.validee_le) contenu.append(el("p", "note", "Validée le " + dateFr(f.methode.validee_le)));
  }
  if (e.agir === true && decisions.has("valider_methode")) geste("Valider la méthode", "bouton", () => demandeMethode(f.id, "valider"));
  if (f.catalogue && typeof ctx.ouvrirCatalogue === "function") {
    const b = el("button", "bouton secondaire", "Catalogue");
    b.type = "button";
    b.addEventListener("click", () => ctx.ouvrirCatalogue(f.id));
    gestes.append(b);
  }
  if (gestes.childElementCount) contenu.append(gestes);
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
