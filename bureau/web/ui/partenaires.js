// L'espace partenaire : les services qui produisent ce que Claude ne génère pas (voix, images, vidéo, 3D, traduction…).
// Ils sont facultatifs. Le bureau ne fait qu'afficher le champ `partenaires` du relevé et déposer des demandes
// (règles, actualiser, mettre à jour les offres) : il n'agit jamais lui-même et ne connaît aucune valeur de clé.
// Tout texte venu du serveur passe par textContent ; seuls les liens https:// sont rendus.

import {el} from "./dom.js";
import {dateFr} from "./texte.js";

export const MAX_REGLE = 500;
const LIBELLES_CONNEXION = {connecte: "connecté", declare: "déclaré, à vérifier", non_connecte: "non connecté"};
const LIBELLES_STATUT = {ferme: "fermé", sans_api: "sans API", restreint: "accès restreint"};
const LIBELLES_CATEGORIE = {
  "voix-audio": "Voix et audio", "images": "Images et graphisme", "video-3d-avatars": "Vidéo, 3D et avatars",
  "langue-web-agents": "Langue, web et agents", "medias-design": "Médias et design",
  "mise-en-ligne-equipe": "Mise en ligne et outils d'équipe",
  "hubs-mcp": "Hubs de connecteurs et annuaires MCP", "ia-texte-code": "Autres IA de texte et de code",
  "documents-donnees": "Documents, OCR et recherche vectorielle", "infrastructure": "E-mail, paiement, comptes et surveillance",
  "jeu": "Boutiques et services pour le jeu", "publication-sites": "Publication, sites et commerce",
  "agenda-messageries": "Agenda, formulaires et messageries",
};
const PERIODES = {mois: "/mois", an: "/an", usage: " à l'usage", jour: "/jour", heure: "/heure", minute: "/minute"};
const tableau = (v) => (Array.isArray(v) ? v : []);
const objet = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

// Un lien n'est rendu que s'il est en https:// (jamais javascript:, data:, http:).
export function lienHttps(url) {
  if (typeof url !== "string" || /[\s\u0000-\u001f\u007f]/.test(url)) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && u.hostname ? url : null;
  } catch {
    return null;
  }
}

export function libelleCategorie(id) {
  return LIBELLES_CATEGORIE[id] || id;
}

export function etatConnexion(donnees, id) {
  const e = objet(objet(donnees?.etat).connexions)[id];
  return LIBELLES_CONNEXION[e?.etat] ? e.etat : "non_connecte";
}

export function libelleConnexion(donnees, id) {
  return LIBELLES_CONNEXION[etatConnexion(donnees, id)];
}

// Ce qu'il reste chez un partenaire : « reste N unité », « illimité » ou « quota inconnu », toujours avec la date du
// relevé quand il y en a une. `limite` : un refus pour dépassement a été signalé.
export function quotaEnClair(donnees, carte) {
  const id = carte?.id;
  const limite = objet(objet(donnees?.etat).limites)[id] || null;
  const q = objet(objet(donnees?.etat).quotas)[id];
  let texte = "quota inconnu";
  if (q && q.illimite === true) texte = "illimité";
  else if (q && typeof q.reste === "number" && Number.isFinite(q.reste)) {
    texte = `reste ${q.reste.toLocaleString("fr-FR")}${typeof q.unite === "string" && q.unite ? " " + q.unite : ""}`;
  } else if (carte?.illimite === true) texte = "illimité";
  return {texte, date: q && q.lu_le ? dateFr(q.lu_le) : "", limite: limite ? limite : null};
}

// La popularité mesurée : « ●●●○○ » (niveau 1 à 5) et les signaux publics utilisés en info-bulle ; rien si elle n'est pas mesurée.
export function popularite(carte) {
  const p = carte?.popularite;
  if (!p || typeof p !== "object" || !Number.isInteger(p.niveau) || p.niveau < 1 || p.niveau > 5) return null;
  const base = typeof p.base === "string" ? p.base : "";
  const date = typeof p.date === "string" && p.date ? ` (mesurée le ${dateFr(p.date) || p.date})` : "";
  return {niveau: p.niveau, texte: "●".repeat(p.niveau) + "○".repeat(5 - p.niveau), info: base + date};
}

// Trie des cartes : « catalogue » garde l'ordre reçu ; « popularite » met les plus populaires d'abord, les non mesurés à la fin.
export function trier(cartes, tri) {
  if (tri !== "popularite") return cartes;
  return cartes.map((c, i) => [c, i]).sort((a, b) => (popularite(b[0])?.niveau || 0) - (popularite(a[0])?.niveau || 0) || a[1] - b[1]).map((x) => x[0]);
}

export function lignePlan(plan) {
  if (!plan || typeof plan.nom !== "string") return "";
  const prix = plan.tarif === "gratuit" || plan.prix === 0 ? "gratuit"
    : (typeof plan.prix === "number" ? `${String(plan.prix).replace(".", ",")} ${plan.devise || ""}${PERIODES[plan.periode] || ""}`.trim()
      : (plan.periode === "usage" ? "à l'usage" : "prix non lu"));
  const quota = typeof plan.quota === "string" && plan.quota ? ` · ${plan.quota}` : "";
  return `${plan.nom} : ${prix}${quota}`;
}

const filtreOk = (carte, filtre) => {
  const f = String(filtre || "").trim().toLowerCase();
  if (!f) return true;
  return [carte.nom, carte.id, carte.sous_categorie, carte.description, libelleCategorie(carte.categorie)].some((t) => String(t || "").toLowerCase().includes(f));
};

// Les trois parties de l'espace : connectés, conseillés pour ce projet (ordre et raison des conseils), tous par catégorie.
export function parties(donnees, filtre = "", tri = "catalogue") {
  const categories = objet(donnees?.categories);
  const toutes = new Map();
  for (const [categorie, liste] of Object.entries(categories)) for (const c of tableau(liste)) toutes.set(c.id, {...c, categorie: c.categorie || categorie});
  const connectes = [...toutes.values()].filter((c) => etatConnexion(donnees, c.id) === "connecte");
  const conseilles = [];
  for (const [besoin, liste] of Object.entries(objet(donnees?.conseils))) {
    for (const x of tableau(liste)) if (toutes.has(x?.id)) conseilles.push({besoin, carte: toutes.get(x.id), raison: typeof x.raison === "string" ? x.raison : ""});
  }
  const parCategorie = Object.entries(categories).map(([id, liste]) => ({
    id, nom: libelleCategorie(id),
    cartes: trier(tableau(liste).map((c) => toutes.get(c.id)).filter((c) => filtreOk(c, filtre)), tri),
  })).filter((g) => g.cartes.length);
  return {connectes, conseilles, categories: parCategorie, total: toutes.size};
}

// Le tableau unique (essai réel) : tous les partenaires, chacun avec son état de connexion et ses conseils.
// `type` : "tous", "connectes", "conseilles" ou une catégorie. Au tri du catalogue, les connectés puis les conseillés
// viennent en tête ; au tri par popularité, l'ordre est celui de la popularité.
export function lignes(donnees, {filtre = "", type = "tous", tri = "catalogue"} = {}) {
  const p = parties(donnees, "", tri);
  const conseils = new Map();
  for (const x of p.conseilles) {
    if (!conseils.has(x.carte.id)) conseils.set(x.carte.id, []);
    conseils.get(x.carte.id).push({besoin: x.besoin, raison: x.raison});
  }
  let toutes = trier(p.categories.flatMap((g) => g.cartes), tri).map((c) => ({
    carte: c, connecte: etatConnexion(donnees, c.id) === "connecte", conseils: conseils.get(c.id) || []}));
  if (tri !== "popularite") {
    const rang = (l) => (l.connecte ? 0 : l.conseils.length ? 1 : 2);
    toutes = toutes.map((l, i) => [l, i]).sort((a, b) => rang(a[0]) - rang(b[0]) || a[1] - b[1]).map((x) => x[0]);
  }
  return toutes.filter((l) => (type === "connectes" ? l.connecte : type === "conseilles" ? l.conseils.length > 0
    : type && type !== "tous" ? l.carte.categorie === type : true) && filtreOk(l.carte, filtre));
}

const bouton = (libelle, classe, surClic) => {
  const b = el("button", classe, libelle);
  b.type = "button";
  b.addEventListener("click", surClic);
  return b;
};

function lien(libelle, url) {
  const a = el("a", "lien-partenaire", libelle);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

// Les connexions d'une carte : le lien « Se connecter » (ou la commande MCP à copier) et le nom des variables.
function blocConnexions(carte, vue) {
  const bloc = el("div", "partenaire-connexions");
  for (const c of tableau(carte.connexions)) {
    if (!c || typeof c !== "object") continue;
    const u = lienHttps(c.url);
    if (c.type === "mcp" && typeof c.commande === "string" && c.commande) {
      const l = el("div", "partenaire-commande");
      l.append(el("code", "", c.commande), bouton("Copier", "bouton secondaire", async () => {
        try {
          await globalThis.navigator.clipboard.writeText(c.commande);
          vue.dire("Commande copiée.");
        } catch {
          vue.dire("La copie n'a pas pu se faire : sélectionnez la commande.");
        }
      }));
      bloc.append(el("div", "ligne-detail", "Connexion par serveur MCP :"), l);
    } else if (u) {
      const nom = {mcp: "Se connecter (serveur MCP)", api: "Se connecter (clé API)", studio: "Se connecter (studio)",
                   compte: "Se connecter (compte)"}[c.type] || "Se connecter";
      bloc.append(lien(nom, u));
    }
    const variables = tableau(c.variables).filter((v) => typeof v === "string");
    if (variables.length) bloc.append(el("div", "ligne-detail", `Variable d'environnement : ${variables.join(", ")}`));
  }
  return bloc;
}

// Les règles d'usage d'un partenaire : consulter, ajouter, modifier, supprimer (chaque geste est une demande).
function blocRegles(donnees, carte, vue) {
  const bloc = el("div", "partenaire-regles");
  bloc.append(el("div", "carte-sous-titre", "Règles d'usage"));
  const regles = tableau(objet(objet(donnees?.etat).regles)[carte.id]);
  if (!regles.length) bloc.append(el("div", "ligne-detail", "Aucune règle."));
  const demande = (operation, id, texte) => ({type: "partenaire_regle", partenaire: carte.id, operation,
                                              ...(id ? {id} : {}), ...(texte !== undefined ? {texte} : {})});
  for (const r of regles) {
    const li = el("div", "partenaire-regle");
    li.append(el("span", "partenaire-regle-texte", r.texte));
    if (vue.agir) {
      li.append(bouton("Modifier", "bouton secondaire", () => { vue.edition = `${carte.id}:${r.id}`; vue.redessiner(); }),
                bouton("Supprimer", "bouton secondaire", () => vue.envoyer(demande("supprimer", r.id))));
    }
    bloc.append(li);
    if (vue.edition === `${carte.id}:${r.id}`) bloc.append(formulaireRegle("Enregistrer", r.texte, vue,
      (texte) => vue.envoyer(demande("modifier", r.id, texte))));
  }
  if (vue.agir) bloc.append(formulaireRegle("Ajouter la règle", "", vue, (texte) => vue.envoyer(demande("ajouter", null, texte))));
  return bloc;
}

function formulaireRegle(libelle, depart, vue, envoyer) {
  const f = el("div", "partenaire-formulaire");
  const zone = el("textarea", "partenaire-saisie");
  zone.value = depart;
  zone.setAttribute("maxlength", String(MAX_REGLE));
  zone.setAttribute("rows", "2");
  zone.setAttribute("placeholder", "Une règle que les agents suivent quand ils appellent ce partenaire");
  f.append(zone, bouton(libelle, "bouton", () => {
    const texte = String(zone.value || "");
    if (!texte.trim()) { vue.dire("La règle est vide."); return; }
    if (texte.length > MAX_REGLE) { vue.dire(`La règle dépasse ${MAX_REGLE} caractères.`); return; }
    vue.edition = null;
    envoyer(texte);
  }));
  return f;
}

function carte(donnees, c, vue, conseils = []) {
  const racine = el("div", "partenaire-carte");
  const entete = el("div", "partenaire-entete");
  const ouverte = vue.ouvertes.has(c.id);
  racine.deplier = bouton(ouverte ? "▾" : "▸", "bouton secondaire partenaire-deplier", () => {
    if (vue.ouvertes.has(c.id)) vue.ouvertes.delete(c.id); else vue.ouvertes.add(c.id);
    // Seule la carte est redessinée : le panneau garde son défilement (sur le téléphone, il remontait en haut),
    // et le focus reste dans le panneau, ce qui suspend ses rafraîchissements pendant la lecture.
    const neuve = carte(donnees, c, vue, conseils);
    racine.replaceWith(neuve);
    neuve.deplier.focus({preventScroll: true});
  });
  entete.append(racine.deplier, el("strong", "partenaire-nom", c.nom), el("span", "partenaire-categorie", libelleCategorie(c.categorie)));
  racine.append(entete);
  if (typeof c.description === "string" && c.description.trim()) racine.append(el("p", "partenaire-description", c.description));
  for (const x of conseils) racine.append(el("div", "partenaire-conseil", `Conseillé : ${x.besoin}${x.raison ? " — " + x.raison : ""}`));
  const etat = etatConnexion(donnees, c.id);
  const connexion = objet(objet(donnees?.etat).connexions)[c.id];
  const lignes = el("div", "partenaire-resume");
  lignes.append(el("span", `partenaire-etat etat-${etat}`, LIBELLES_CONNEXION[etat]));
  if (LIBELLES_STATUT[c.statut]) lignes.append(el("span", "partenaire-statut", LIBELLES_STATUT[c.statut]));
  if (etat === "connecte" && typeof connexion?.abonnement === "string" && connexion.abonnement) {
    lignes.append(el("span", "partenaire-abonnement", `abonnement : ${connexion.abonnement}`));
  }
  const q = quotaEnClair(donnees, c);
  lignes.append(el("span", "partenaire-quota", q.date ? `${q.texte} (relevé du ${q.date})` : q.texte));
  if (q.limite) {
    const l = el("span", "partenaire-limite", "limite atteinte");
    if (typeof q.limite.raison === "string") l.title = q.limite.raison;
    lignes.append(l);
  }
  const pop = popularite(c);
  if (pop) {
    const s = el("span", "partenaire-popularite", `Popularité : ${pop.texte}`);
    if (pop.info) s.title = pop.info;
    lignes.append(s);
  }
  if (c.fiabilite === "tiers") lignes.append(el("span", "partenaire-prix-incertain", "prix à vérifier"));
  racine.append(lignes);
  if (!ouverte) return racine;
  const corps = el("div", "partenaire-corps");
  corps.append(el("div", "carte-sous-titre", "Plans et prix"));
  const plans = tableau(c.plans).map(lignePlan).filter(Boolean);
  if (!plans.length) corps.append(el("div", "ligne-detail", "Aucun plan relevé."));
  for (const p of plans) corps.append(el("div", "ligne-detail", p));
  if (typeof c.gratuit === "string" && c.gratuit) corps.append(el("div", "ligne-detail", `Gratuit : ${c.gratuit}`));
  const verifie = c.verifie_le ? dateFr(c.verifie_le) : "";
  corps.append(el("div", "ligne-detail", `Offres vérifiées le ${verifie || "—"} (${c.fiabilite === "officielle" ? "page officielle" : "source tierce"})`));
  if (typeof connexion?.source === "string" && connexion.source) corps.append(el("div", "ligne-detail", `Connexion : ${connexion.source}`));
  const liens = el("div", "partenaire-liens");
  const inscription = lienHttps(c.inscription);
  if (inscription) liens.append(lien("S'inscrire", inscription));
  corps.append(liens, blocConnexions(c, vue), blocRegles(donnees, c, vue));
  racine.append(corps);
  return racine;
}

// Rend l'espace partenaire. `envoyer(demande)` rend une promesse {ok, message} (voir actions.js). `vue` garde ce
// qui doit survivre à un nouveau dessin : filtre, cartes dépliées, confirmation, message.
export function creerVue(options = {}) {
  return {filtre: "", type: "tous", tri: "catalogue", ouvertes: new Set(), confirmation: false, message: "", edition: null, agir: options.agir !== false};
}

export function rendrePartenaires(donnees, envoyer, vue = creerVue()) {
  const racine = el("div", "partenaires");
  const dessiner = () => {
    racine.replaceChildren();
    const p = parties(donnees, vue.filtre);
    const etat = el("p", "reglage-message", vue.message);
    etat.setAttribute("aria-live", "polite");
    vue.dire = (m) => { vue.message = m; etat.textContent = m; };
    vue.redessiner = dessiner;
    vue.envoyer = async (demande) => {
      vue.dire("Envoi…");
      const r = await envoyer(demande);
      vue.dire(r && r.message ? r.message : (r && r.ok ? "Demande envoyée" : "Demande refusée"));
      return r;
    };
    racine.append(el("h2", "", "Partenaires"));
    racine.append(el("p", "note", "Les partenaires sont facultatifs : la factory se débrouille sans eux. "
      + "Vous vous inscrivez et vous vous connectez vous-même, sur leurs pages."));
    if (vue.agir) {
      const barre = el("div", "partenaires-actions");
      barre.append(bouton("Actualiser", "bouton secondaire", () => vue.envoyer({type: "partenaires_actualiser"})),
                   bouton("Mettre à jour les offres", "bouton secondaire", () => { vue.confirmation = true; dessiner(); }));
      racine.append(barre);
      if (vue.confirmation) racine.append(confirmationMaj(donnees, vue));
    }
    if (donnees?.maj_catalogue) racine.append(el("p", "note", `Catalogue mis à jour le ${dateFr(donnees.maj_catalogue) || donnees.maj_catalogue}.`));
    racine.append(etat);
    if (!p.connectes.length) racine.append(el("p", "note", "Aucun partenaire connecté. Ce n'est pas un problème : la factory travaille sans."));
    const filtres = el("div", "partenaires-filtres");
    const type = el("select", "partenaires-type");
    type.setAttribute("aria-label", "Type de partenaire");
    const options = [["tous", "Tous les types", p.total], ["connectes", "Connectés", p.connectes.length],
                     ["conseilles", "Conseillés", lignes(donnees, {type: "conseilles"}).length],
                     ...parties(donnees).categories.map((g) => [g.id, g.nom, g.cartes.length])];
    for (const [valeur, libelle, n] of options) {
      const o = el("option", "", `${libelle} (${n})`);
      o.value = valeur;
      type.append(o);
    }
    if (!options.some((o) => o[0] === vue.type)) vue.type = "tous";
    type.value = vue.type;
    const saisie = el("input", "partenaires-filtre");
    saisie.type = "search";
    saisie.value = vue.filtre;
    saisie.setAttribute("placeholder", "Chercher un partenaire");
    const tri = el("select", "partenaires-tri");
    tri.setAttribute("aria-label", "Trier les partenaires");
    for (const [valeur, libelle] of [["catalogue", "Tri : connectés et conseillés d'abord"], ["popularite", "Tri : popularité"]]) {
      const o = el("option", "", libelle);
      o.value = valeur;
      tri.append(o);
    }
    tri.value = vue.tri;
    const liste = el("div", "partenaires-liste");
    const remplir = () => {
      liste.replaceChildren();
      const l = lignes(donnees, {filtre: vue.filtre, type: vue.type, tri: vue.tri});
      if (!l.length) liste.append(el("p", "note", "Aucun partenaire ne correspond."));
      for (const x of l) liste.append(carte(donnees, x.carte, vue, x.conseils));
    };
    type.addEventListener("change", () => { vue.type = String(type.value || "tous"); remplir(); });
    saisie.addEventListener("input", () => { vue.filtre = String(saisie.value || ""); remplir(); });
    tri.addEventListener("change", () => { vue.tri = tri.value === "popularite" ? "popularite" : "catalogue"; remplir(); });
    remplir();
    filtres.append(type, saisie, tri);
    racine.append(filtres, liste);
  };
  dessiner();
  return racine;
}

// La fenêtre de confirmation de « Mettre à jour les offres » : le coût estimé de la recherche, puis la demande.
function confirmationMaj(donnees, vue) {
  const c = objet(donnees?.cout_maj);
  const fenetre = el("div", "partenaires-confirmation");
  fenetre.setAttribute("role", "alertdialog");
  const euros = typeof c.euros === "number" && Number.isFinite(c.euros) ? `≈ ${c.euros.toFixed(2).replace(".", ",")} €` : "coût estimé inconnu";
  fenetre.append(el("p", "", "La recherche des offres lit les sites des partenaires, par lots, sur un petit modèle, "
    + "et ne refait que les fiches à refaire. Elle consomme des tokens."));
  fenetre.append(el("p", "gras", `Coût estimé : ${euros}${typeof c.texte === "string" && c.texte ? " — " + c.texte : ""}`));
  fenetre.append(bouton("Lancer la mise à jour", "bouton", async () => {
    vue.confirmation = false;
    vue.redessiner();
    await vue.envoyer({type: "partenaires_maj", confirme: true});
  }), bouton("Annuler", "bouton secondaire", () => { vue.confirmation = false; vue.redessiner(); }));
  return fenetre;
}

// Dans le panneau : lit la vue gardée par le panneau (contexte) et dessine.
export function contenuPartenaires(ctx, conteneur, envoyer) {
  const e = ctx.etat;
  const vue = ctx.vuePartenaires || creerVue();
  vue.agir = e.agir === true;
  conteneur.append(rendrePartenaires(e.partenaires || {}, envoyer, vue));
}
