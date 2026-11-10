// Le panneau d'une fonctionnalité : bandeau du parcours, discussion de cadrage, pièces du cahier des charges.
// Les fonctions pures sont testées avec node. Tout geste est une demande au projet (`ctx.barre.demander`) ;
// tout texte venu du relevé passe par textContent.

import {el} from "./dom.js";
import {dateFr, tronquer, euros} from "./texte.js";
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
    // La dernière version de chaque document ; les précédentes dans « Voir l'historique ».
    for (const v of versionsDe(g.documents)) {
      const toutes = [v.dernier, ...v.anciens].filter((x) => EST_IMAGE.test(x.chemin)).map((x) => x.chemin);
      const li = ligneDocument(ctx, v.dernier, url, toutes);
      if (v.anciens.length) li.querySelector(".document-texte").append(historique(ctx, v.anciens, url, toutes));
      ul.append(li);
    }
    bloc.append(ul);
  }
  return bloc;
}

// Une ligne de document : la vignette (une image, ouverte dans la visionneuse avec `images`) ou « Ouvrir », le titre,
// d'où il vient, son chemin.
function ligneDocument(ctx, d, url, images) {
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
    b.addEventListener("click", () => ouvrirVisionneuse(images, Math.max(0, images.indexOf(d.chemin)), url));
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
  return li;
}

// « Voir l'historique » : les versions précédentes, de la plus récente à la plus ancienne ; la visionneuse passe de
// l'une à l'autre, la dernière version en tête.
function historique(ctx, anciens, url, images) {
  const d = el("details", "historique");
  const n = anciens.length;
  d.append(el("summary", "", `Voir l'historique (${n} version${n > 1 ? "s" : ""} précédente${n > 1 ? "s" : ""})`));
  const ul = el("ul", "liste-documents");
  for (const ancien of anciens) ul.append(ligneDocument(ctx, ancien, url, images));
  d.append(ul);
  return d;
}

// --- Le vocabulaire : les mots spécialisés que les agents définissent (`glossaire` d'un message).
// Le glossaire d'une fonctionnalité : les définitions de tous ses messages ; la dernière d'un mot l'emporte.
export function glossaireDe(f) {
  const parMot = new Map();
  // Les définitions des messages, puis le glossaire gardé par la fonctionnalité (il fait foi).
  const sources = [...(Array.isArray(f?.discussion) ? f.discussion : []).map((m) => m?.glossaire), f?.glossaire];
  for (const liste of sources) {
    for (const g of Array.isArray(liste) ? liste : []) {
      if (typeof g?.mot !== "string" || !g.mot.trim() || typeof g.definition !== "string") continue;
      const cle = sansAccentsMinuscules(g.mot.trim());
      parMot.delete(cle);   // la plus récente prend la place de l'ancienne
      parMot.set(cle, {mot: g.mot.trim(), definition: g.definition});
    }
  }
  return [...parMot.values()];
}

function sansAccentsMinuscules(t) {
  return String(t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

// Le texte en morceaux : simples, ou un mot du glossaire avec sa définition. Sans casse ni accents, mot entier
// (le pluriel en -s ou -x compte), le terme le plus long d'abord, sans chevauchement. Le texte reste du texte.
export function decouperTermes(texte, glossaire) {
  texte = String(texte ?? "");
  const termes = (glossaire || []).map((g) => ({cle: sansAccentsMinuscules(g.mot).trim(), definition: g.definition}))
    .filter((g) => g.cle).sort((a, b) => b.cle.length - a.cle.length);
  if (!termes.length || !texte) return [{texte}];
  // Le texte normalisé, et pour chacun de ses caractères la position du caractère d'origine.
  let plat = "";
  const origine = [];
  [...texte].reduce((pos, c) => {
    const n = sansAccentsMinuscules(c);
    for (const x of n) { plat += x; origine.push(pos); }
    return pos + c.length;
  }, 0);
  const lettre = (c) => c !== undefined && /[\p{L}\p{N}]/u.test(c);
  const pris = new Array(plat.length).fill(false);
  const trouves = [];
  for (const t of termes) {
    let i = plat.indexOf(t.cle);
    while (i >= 0) {
      let fin = i + t.cle.length;
      if (plat[fin] === "s" || plat[fin] === "x") fin += lettre(plat[fin + 1]) ? 0 : 1;   // un pluriel
      if (!lettre(plat[i - 1]) && !lettre(plat[fin]) && !pris.slice(i, fin).some(Boolean)) {
        pris.fill(true, i, fin);
        trouves.push({debut: origine[i], fin: fin < origine.length ? origine[fin] : texte.length, definition: t.definition});
      }
      i = plat.indexOf(t.cle, i + 1);
    }
  }
  trouves.sort((a, b) => a.debut - b.debut);
  const sortie = [];
  let pos = 0;
  for (const x of trouves) {
    if (x.debut > pos) sortie.push({texte: texte.slice(pos, x.debut)});
    sortie.push({texte: texte.slice(x.debut, x.fin), definition: x.definition});
    pos = x.fin;
  }
  if (pos < texte.length) sortie.push({texte: texte.slice(pos)});
  return sortie;
}

// Les questions à choix qui attendent l'utilisateur : celles du dernier message, s'il vient d'un agent.
export function questionsEnAttente(f) {
  const d = Array.isArray(f?.discussion) ? f.discussion : [];
  const m = d[d.length - 1];
  return m && m.auteur !== "utilisateur" && Array.isArray(m.questions) && m.questions.length
    ? {message: m.id, questions: m.questions} : null;
}

// La réponse envoyée : chaque question avec le choix fait (ou « passée »), puis le texte libre. Chaque question doit
// avoir une réponse ou être passée, et passer une question demande de dire pourquoi dans le texte.
// `reponses` : {rang: {choix: [..], autre?: "texte"} | {passee: true}} ; `autre` présent = « Autre » choisi (à préciser).
// Rend {texte} ou {erreur}.
export function reponseComposee(questions, reponses, libre) {
  const texteLibre = String(libre ?? "").trim();
  const lignes = [];
  let passee = false;
  for (const [k, q] of (questions || []).entries()) {
    const r = reponses?.[k];
    if (r?.passee) { lignes.push(`${q.texte} → (passée)`); passee = true; continue; }
    if (typeof r?.autre === "string" && !r.autre.trim()) return {erreur: `Précisez « Autre » pour « ${q.texte} ».`};
    const valeurs = [...(r?.choix || []), ...(typeof r?.autre === "string" ? ["Autre : " + r.autre.trim()] : [])];
    if (!valeurs.length) return {erreur: `Répondez à « ${q.texte} » (ou passez-la).`};
    lignes.push(`${q.texte} → ${valeurs.join(", ")}`);
  }
  if (passee && !texteLibre) return {erreur: "Vous passez une question : dites pourquoi dans le message."};
  if (!lignes.length && !texteLibre) return {erreur: "Écrivez un message."};
  return {texte: [lignes.join("\n"), texteLibre].filter(Boolean).join("\n\n")};
}

// Les boutons des questions à choix, au-dessus de la zone de saisie. `etat` : les réponses en cours (gardées dans
// le brouillon, elles survivent aux rafraîchissements) ; `changer()` après chaque clic.
function blocQuestions(attente, etat, changer) {
  const bloc = el("div", "questions");
  attente.questions.forEach((q, k) => {
    const r = etat[k] || (etat[k] = {choix: []});
    const div = el("div", "question" + (r.passee ? " passee" : ""));
    div.append(el("div", "question-texte", q.texte + (q.multiple ? " (plusieurs choix possibles)" : "")));
    const rangee = el("div", "question-choix");
    for (const c of q.choix) {
      const b = el("button", "choix", c);
      b.type = "button";
      b.setAttribute("aria-pressed", String(!r.passee && r.choix.includes(c)));
      b.addEventListener("click", () => {
        r.passee = false;
        if (q.multiple) r.choix = r.choix.includes(c) ? r.choix.filter((x) => x !== c) : [...r.choix, c];
        else { r.choix = r.choix[0] === c ? [] : [c]; delete r.autre; }   // un seul choix : « Autre » se ferme
        changer();
      });
      rangee.append(b);
    }
    // « Autre » : un champ dessous pour la valeur que l'on veut mettre.
    const autre = el("button", "choix", "Autre");
    autre.type = "button";
    autre.setAttribute("aria-pressed", String(!r.passee && typeof r.autre === "string"));
    autre.addEventListener("click", () => {
      r.passee = false;
      if (typeof r.autre === "string") delete r.autre;
      else { r.autre = ""; if (!q.multiple) r.choix = []; }
      changer(true);
    });
    rangee.append(autre);
    const passer = el("button", "choix passer", r.passee ? "Passée" : "Passer");
    passer.type = "button";
    passer.setAttribute("aria-pressed", String(!!r.passee));
    passer.addEventListener("click", () => { r.passee = !r.passee; if (r.passee) { r.choix = []; delete r.autre; } changer(); });
    rangee.append(passer);
    div.append(rangee);
    if (!r.passee && typeof r.autre === "string") {
      const champ = document.createElement("input");
      champ.type = "text";
      champ.className = "choix-autre";
      champ.maxLength = 300;
      champ.placeholder = "Votre réponse…";
      champ.value = r.autre;
      champ.dataset.question = String(k);
      champ.addEventListener("input", () => { r.autre = champ.value; changer(false, false); });
      div.append(champ);
    }
    bloc.append(div);
  });
  return bloc;
}

// --- Les tâches de la fonctionnalité : réalisées (dans une colonne terminée, ou inactives), et à venir (les autres, puis les
// éléments de sa file, dans l'ordre). Les tâches sans post-it (le chef qui orchestre) n'y sont pas.
export function tachesDeFonctionnalite(etat, f) {
  const colonnes = new Map((etat?.colonnes || []).map((c) => [c.id, c]));
  const prenoms = new Map((etat?.agents || []).map((a) => [a.id, a.prenom]));
  const realisees = [], aVenir = [];
  for (const t of etat?.taches || []) {
    if (t.fonctionnalite !== f?.id || t.postit === false) continue;
    const c = colonnes.get(t.colonne);
    const ligne = {id: t.id, titre: t.titre, colonne: c?.nom || t.colonne, prenom: t.agent ? prenoms.get(t.agent) || t.agent : null,
                   maj: t.maj || null, active: t.active === true, bloquee: t.bloquee || null};
    (c?.terminee || t.active === false ? realisees : aVenir).push(ligne);   // inactive : finie, même hors de « Fait »
  }
  const recent = (a, b) => String(b.maj || "").localeCompare(String(a.maj || ""));
  realisees.sort(recent);
  aVenir.sort(recent);
  const prefixe = `${f?.id}/`;
  for (const q of [...(etat?.file?.visibles || []), ...(etat?.file?.suite || [])]) {
    if (typeof q.id === "string" && q.id.startsWith(prefixe)) aVenir.push({id: q.id, titre: q.titre, file: true});
  }
  return {realisees, aVenir};
}

function partieTaches(ctx, f) {
  const {realisees, aVenir} = tachesDeFonctionnalite(ctx.etat, f);
  const bloc = el("details", "taches-fonctionnalite");
  bloc.open = true;
  bloc.append(el("summary", "", `Tâches (${realisees.length} réalisée${realisees.length > 1 ? "s" : ""}, ${aVenir.length} à venir)`));
  const liste = (titre, taches, vide) => {
    bloc.append(el("h4", "", titre));
    const ul = el("ul", "liste-taches-fonctionnalite");
    if (!taches.length) ul.append(el("li", "vide", vide));
    for (const t of taches) {
      const li = el("li", t.file ? "en-file" : "");
      if (t.file) li.append(el("span", "", t.titre), el("span", "note", " · en file"));
      else {
        const b = el("button", "lien-tache", t.titre);
        b.type = "button";
        b.addEventListener("click", () => ctx.ouvrirTache(t.id));
        li.append(b);
        const meta = [t.colonne, t.prenom, t.maj ? dateFr(t.maj) : null, t.bloquee ? "bloquée" : null].filter(Boolean).join(" · ");
        if (meta) li.append(el("div", "note", meta));
      }
      ul.append(li);
    }
    bloc.append(ul);
  };
  liste("À venir", aVenir, "Rien à venir pour l'instant");
  liste("Réalisées", realisees, "Aucune tâche réalisée pour l'instant");
  return bloc;
}

// --- Les versions d'un document : un document qui en remplace un autre (`remplace` = son chemin), ou qui a le même
// titre et le même élément, en est une nouvelle version. Rend [{dernier, anciens}] : la dernière version d'abord, les
// plus récentes en tête, l'historique du plus récent au plus ancien.
export function versionsDe(documents) {
  const liste = (Array.isArray(documents) ? documents : []).filter((d) => d && typeof d.chemin === "string");
  const parent = liste.map((_, i) => i);
  const racine = (i) => (parent[i] === i ? i : (parent[i] = racine(parent[i])));
  const unir = (i, j) => { parent[racine(i)] = racine(j); };
  const parIdentite = new Map(), parChemin = new Map();
  liste.forEach((d, i) => {
    const cle = `${d.element || ""}\u0000${d.titre || d.chemin}`;
    if (parIdentite.has(cle)) unir(i, parIdentite.get(cle)); else parIdentite.set(cle, i);
    parChemin.set(d.chemin, i);
  });
  liste.forEach((d, i) => { if (typeof d.remplace === "string" && parChemin.has(d.remplace)) unir(i, parChemin.get(d.remplace)); });
  const groupes = new Map();
  liste.forEach((d, i) => {
    const r = racine(i);
    if (!groupes.has(r)) groupes.set(r, []);
    groupes.get(r).push(d);
  });
  const date = (d) => String(d.date || "");
  return [...groupes.values()].map((g) => {
    const tries = [...g].sort((a, b) => date(b).localeCompare(date(a)));
    return {dernier: tries[0], anciens: tries.slice(1)};
  }).sort((a, b) => date(b.dernier).localeCompare(date(a.dernier)));
}

// --- Les livrables : les fichiers finaux de chaque élément validé (documents marqués `livrable`).
export function livrablesParElement(f) {
  const groupes = new Map();
  for (const d of Array.isArray(f?.documents) ? f.documents : []) {
    if (d?.livrable !== true) continue;
    const cle = typeof d.element === "string" && d.element ? d.element : null;
    if (!groupes.has(cle)) groupes.set(cle, {element: cle, documents: []});
    groupes.get(cle).documents.push(d);
  }
  const recent = (g) => g.documents.reduce((m, d) => (String(d.date || "") > m ? String(d.date || "") : m), "");
  return [...groupes.values()].map((g) => ({...g, documents: [...g.documents]
      .sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))}))
    .sort((a, b) => (a.element === null) - (b.element === null) || recent(b).localeCompare(recent(a)));
}

// Un retour sur le livrable d'un élément : comme « Demander à modifier » du catalogue s'il y en a un (l'élément est
// vérifié par le bureau), sinon un message de la discussion qui nomme l'élément.
export function demandeRetourLivrable(f, element, texte) {
  return f?.catalogue === true && element
    ? {type: "retour_element", fonctionnalite: f.id, element, texte}
    : {type: "message", fonctionnalite: f.id, texte: `Retour sur le livrable de « ${element || "la fonctionnalité"} » : ${texte}`};
}

// La partie « Livrables » du panneau : par élément, ses fichiers finaux et « Demander une modification ».
function partieLivrables(ctx, f) {
  const groupes = livrablesParElement(f);
  const bloc = el("details", "livrables");
  bloc.open = groupes.length > 0;
  bloc.append(el("summary", "", `Livrables (${groupes.length} élément${groupes.length > 1 ? "s" : ""})`));
  if (!groupes.length) {
    bloc.append(el("p", "note", "Aucun livrable validé pour l'instant : ils apparaissent ici élément par élément."));
    return bloc;
  }
  const url = (chemin) => urlProjet(`/api/document?fonctionnalite=${encodeURIComponent(f.id)}&chemin=${encodeURIComponent(chemin)}`);
  for (const g of groupes) {
    const art = el("article", "livrable-element");
    art.append(el("h4", "", g.element ? "Élément : " + g.element : "Sans élément"));
    const versions = versionsDe(g.documents);
    const images = versions.map((v) => v.dernier.chemin).filter((c) => EST_IMAGE.test(c));
    const rangee = el("div", "livrable-fichiers");
    for (const d of versions.map((v) => v.dernier)) {
      if (EST_IMAGE.test(d.chemin)) {
        const b = el("button", "document-vignette");
        b.type = "button";
        b.title = d.titre;
        b.setAttribute("aria-label", "Voir en plein écran : " + d.titre);
        const img = document.createElement("img");
        img.loading = "lazy";
        img.src = url(d.chemin);
        img.alt = d.titre;
        b.append(img);
        b.addEventListener("click", () => ouvrirVisionneuse(images, images.indexOf(d.chemin), url));
        rangee.append(b);
      } else {
        const a = el("a", "document-lien", d.titre);
        a.href = url(d.chemin);
        a.target = "_blank";
        a.rel = "noopener";
        rangee.append(a);
      }
    }
    art.append(rangee);
    const anciens = versions.flatMap((v) => v.anciens);
    if (anciens.length) {
      const toutes = versions.flatMap((v) => [v.dernier, ...v.anciens]).filter((x) => EST_IMAGE.test(x.chemin))
        .map((x) => x.chemin);
      art.append(historique(ctx, anciens, url, toutes));
    }
    const dernier = versions[0].dernier;
    const origine = [dernier.agent ? nomAgentDe(ctx.etat, dernier.agent) : null, dernier.date ? dateFr(dernier.date) : null]
      .filter(Boolean).join(" · ");
    if (origine) art.append(el("div", "note", origine));
    if (ctx.etat.agir === true) art.append(retourLivrable(ctx, f, g.element));
    bloc.append(art);
  }
  return bloc;
}

// « Demander une modification » d'un livrable : un champ, puis l'envoi (un double clic ne crée qu'une demande).
function retourLivrable(ctx, f, element) {
  const cle = `livrable:${f.id}:${element}`;
  const zone = el("div", "livrable-retour");
  const ouvrir = el("button", "bouton secondaire petit", "Demander une modification");
  ouvrir.type = "button";
  const formulaire = el("div", "");
  formulaire.hidden = true;
  const texte = document.createElement("textarea");
  texte.rows = 3;
  texte.maxLength = MAX_TEXTE;
  texte.placeholder = "Ce qui ne va pas et ce qu'il faut changer…";   // pas de redessin du panneau pendant la frappe
  const envoyer = el("button", "bouton petit", "Envoyer le retour");
  envoyer.type = "button";
  envoyer.disabled = true;
  const etat = el("p", "note", ctx.envoyes.has(cle) ? "Retour envoyé : l'orchestrateur le reprend." : "");
  ouvrir.addEventListener("click", () => { formulaire.hidden = false; ouvrir.hidden = true; texte.focus(); });
  texte.addEventListener("input", () => { envoyer.disabled = !texte.value.trim() || ctx.envois.has(cle); });
  envoyer.addEventListener("click", async () => {
    if (ctx.envois.has(cle) || !texte.value.trim()) return;
    ctx.envois.add(cle);
    envoyer.disabled = true;
    let r;
    try { r = await ctx.barre.demander(demandeRetourLivrable(f, element, texte.value.trim()), envoyer); }
    finally { ctx.envois.delete(cle); }
    if (r?.ok) { ctx.envoyes.set(cle, true); texte.value = ""; formulaire.hidden = true; ouvrir.hidden = false;
                 etat.textContent = "Retour envoyé : l'orchestrateur le reprend."; }
    else envoyer.disabled = !texte.value.trim();
  });
  formulaire.append(texte, envoyer);
  zone.append(ouvrir, formulaire, etat);
  return zone;
}

// L'échelle d'un coût : les tokens consommés et les lignes produites, pour juger un prix.
export function echelle({tokens = 0, lignes = null} = {}) {
  const morceaux = [];
  if (tokens > 0) {
    const n = tokens >= 1e6 ? (tokens / 1e6).toFixed(1).replace(".", ",") + " M"
      : tokens >= 1e3 ? Math.round(tokens / 1e3) + " k" : String(tokens);
    morceaux.push(n + " tokens");
  }
  if (Number.isInteger(lignes)) morceaux.push(`${lignes} ligne${lignes > 1 ? "s" : ""}`);
  return morceaux.join(" · ");
}

// La partie « Coût » : le coût de chaque tâche de la fonctionnalité (depuis toujours), lu à l'ouverture du panneau.
function partieCouts(f) {
  const bloc = el("details", "couts");
  const titre = el("summary", "", "Coût : …");
  bloc.append(titre);
  const corps = el("div", "");
  bloc.append(corps);
  (async () => {
    let c;
    try {
      const r = await fetch(urlProjet(`/api/couts?fonctionnalite=${encodeURIComponent(f.id)}`), {cache: "no-store"});
      c = await r.json();
    } catch { titre.textContent = "Coût : indisponible"; return; }
    if (!c?.disponible) { bloc.remove(); return; }
    const incomplet = c.sans_prix ? " + prix inconnu" : "";
    titre.textContent = `Coût : ${euros(c.total)}${incomplet}` + (echelle(c) ? ` (${echelle(c)})` : "");
    if (!c.taches.length) { corps.append(el("p", "note", "Aucune consommation notée pour l'instant.")); return; }
    const ul = el("ul", "liste-couts");
    for (const t of c.taches) {
      const li = el("li", "");
      const modeles = Object.entries(t.modeles).map(([m, v]) => `${m} ${euros(v)}`).join(" · ");
      li.append(el("span", "cout-tache", t.titre), el("strong", "cout-montant", euros(t.total) + (t.sans_prix ? " + prix inconnu" : "")));
      const detail = [echelle(t), modeles].filter(Boolean).join(" · ");
      if (detail) li.append(el("div", "note", detail));
      ul.append(li);
    }
    corps.append(ul, el("p", "note", "Estimation d'après les tokens notés par l'orchestrateur (au plus bas quand seul un total est connu)."));
  })();
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

// Un texte où les mots du glossaire sont mis en valeur : autre couleur, définition au survol (ou au focus, au
// clavier et au toucher). Tout reste du texte : la définition est un attribut, montrée par le style.
// Une seule bulle de définition pour toute la page, placée près du mot et gardée dans la fenêtre (une bulle dans la
// discussion serait coupée par son défilement).
let bulle = null;
function montrerDefinition(mot) {
  if (!bulle) { bulle = el("div", "bulle-definition"); bulle.setAttribute("role", "tooltip"); document.body.append(bulle); }
  bulle.textContent = mot.dataset.definition;
  bulle.hidden = false;
  const r = mot.getBoundingClientRect(), l = bulle.offsetWidth, h = bulle.offsetHeight;
  const gauche = Math.max(8, Math.min(r.left, window.innerWidth - l - 8));
  const haut = r.bottom + 6 + h > window.innerHeight - 8 ? r.top - h - 6 : r.bottom + 6;
  bulle.style.left = gauche + "px";
  bulle.style.top = Math.max(8, haut) + "px";
}
function cacherDefinition() { if (bulle) bulle.hidden = true; }

function texteAvecTermes(classe, texte, glossaire) {
  const bloc = el("div", classe);
  for (const m of decouperTermes(texte, glossaire)) {
    if (!m.definition) { bloc.append(m.texte); continue; }
    const t = el("span", "terme", m.texte);
    t.dataset.definition = m.definition;
    t.tabIndex = 0;
    t.setAttribute("aria-label", `${m.texte} : ${m.definition}`);
    t.addEventListener("mouseenter", () => montrerDefinition(t));
    t.addEventListener("focus", () => montrerDefinition(t));
    t.addEventListener("click", () => montrerDefinition(t));   // au toucher
    t.addEventListener("mouseleave", cacherDefinition);
    t.addEventListener("blur", cacherDefinition);
    bloc.append(t);
  }
  return bloc;
}

// Tout le contenu d'un message, en texte : le texte, ses questions à choix, les chemins de ses images.
export function texteACopier(m) {
  const parties = [String(m?.texte || "")];
  const q = Array.isArray(m?.questions) ? m.questions : [];
  if (q.length) parties.push(q.map((x) => `${x.texte} (${(x.choix || []).join(" / ")})`).join("\n"));
  if ((m?.images || []).length) parties.push("Images :\n" + m.images.map((c) => "- " + c).join("\n"));
  return parties.filter(Boolean).join("\n\n");
}

// Copie dans le presse-papiers (avec un repli quand l'API n'est pas permise) ; le bouton dit « Copié ».
async function copier(texte, bouton) {
  try {
    await navigator.clipboard.writeText(texte);
  } catch {
    const zone = document.createElement("textarea");
    zone.value = texte;
    zone.style.position = "fixed";
    zone.style.opacity = "0";
    document.body.append(zone);
    zone.select();
    try { document.execCommand("copy"); } finally { zone.remove(); }
  }
  bouton.textContent = "Copié";
  setTimeout(() => { bouton.textContent = "Copier"; }, 1500);
}

function messageDe(m, etat, glossaire = []) {
  const li = el("li", "message");
  const utilisateur = m.auteur === "utilisateur";
  li.classList.add(utilisateur ? "message-utilisateur" : "message-agent");
  const qui = utilisateur ? "Vous" : [m.prenom || m.auteur, m.service].filter(Boolean).join(" · ");
  const tete = el("div", "message-tete");
  const bouton = el("button", "message-copier", "Copier");
  bouton.type = "button";
  bouton.setAttribute("aria-label", "Copier le contenu du message");
  bouton.addEventListener("click", () => copier(texteACopier(m), bouton));
  tete.append(el("strong", "", qui), el("span", "date", m.t ? dateFr(m.t) : ""), bouton);
  li.append(tete, texteAvecTermes("message-texte", m.texte, glossaire));
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
function saisie(ctx, cle, envoyerDemande, {libelle = "Envoyer", images = true, invite = "Écrire un message…",
                                         questions = null} = {}) {
  const brouillon = ctx.brouillons.get(cle) || {texte: "", images: []};
  ctx.brouillons.set(cle, brouillon);
  // Les réponses aux questions à choix du dernier message (oubliées quand un autre message en pose de nouvelles).
  if (questions && brouillon.reponsesDe !== questions.message) { brouillon.reponsesDe = questions.message; brouillon.reponses = {}; }
  const preparer = () => (questions ? reponseComposee(questions.questions, brouillon.reponses, zone.value)
                                    : (zone.value.trim() ? {texte: zone.value} : {erreur: ""}));
  const bloc = el("section", "saisie-discussion");
  const zone = document.createElement("textarea");
  zone.rows = 3;
  zone.maxLength = MAX_TEXTE;
  zone.placeholder = questions ? "Ajouter un commentaire (obligatoire si vous passez une question)…" : invite;
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

  const conseil = el("p", "note questions-conseil", "");
  const maj = () => {
    const pr = preparer();
    envoyer.disabled = Boolean(pr.erreur !== undefined) || ctx.envois.has(cle);
    conseil.textContent = questions ? (pr.erreur || "") : "";
  };
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
    const pr = preparer();
    if (ctx.envois.has(cle) || pr.erreur !== undefined) return;   // un double clic ne crée qu'une demande
    ctx.envois.add(cle);
    envoyer.disabled = true;
    const texte = pr.texte, images = brouillon.images.slice();
    let r;
    try { r = await envoyerDemande(texte, images, envoyer); } finally { ctx.envois.delete(cle); }
    if (r?.ok) { brouillon.texte = ""; brouillon.images = []; brouillon.reponses = {}; ctx.rouvrir(); }
    else maj();
  });
  maj();
  dessinerMiniatures();
  const rangee = el("div", "retour-pied");
  if (images) rangee.append(joindre);
  rangee.append(envoyer);
  if (questions) {
    const changer = (focusAutre = false, redessin = true) => {
      if (!redessin) { maj(); return; }   // frappe dans « Autre » : le champ reste, seul « Envoyer » se met à jour
      const nouveau = blocQuestions(questions, brouillon.reponses, changer);
      questionnaire.replaceWith(nouveau);
      questionnaire = nouveau;
      if (focusAutre) nouveau.querySelector("input.choix-autre:placeholder-shown")?.focus();
      maj();
    };
    let questionnaire = blocQuestions(questions, brouillon.reponses, changer);
    bloc.append(questionnaire);
  }
  bloc.append(zone, conseil, miniatures, erreur, rangee, fichier);
  maj();
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
  const glossaire = glossaireDe(f);
  for (const m of messages) discussion.append(messageDe(m, e, glossaire));
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
        }, {questions: f ? questionsEnAttente(f) : null});
    blocDiscussion.append(s.bloc);
  }
  if (!f) { contenu.append(blocDiscussion); return; }

  // Les pièces du cahier des charges et de la méthode.
  const blocCahier = el("div", "bloc-cahier");
  if (f.cahier) {
    blocCahier.append(el("h3", "", "Cahier des charges"));
    if ((f.cahier.maquette || []).length) blocCahier.append(vignettes(f.cahier.maquette, e));
    const etapes = el("ol", "etapes-cahier");
    for (const t of f.cahier.etapes || []) {
      const li = el("li", "");
      li.append(...texteAvecTermes("", t, glossaire).childNodes);
      etapes.append(li);
    }
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
    contenu.append(partieTaches(ctx, f), partieLivrables(ctx, f), partieCouts(f), partieDocuments(ctx, f));
  } else {
    const repliee = el("details", "discussion-repliee");
    repliee.append(el("summary", "", `Discussion (${messages.length} message${messages.length > 1 ? "s" : ""})`), blocDiscussion);
    contenu.append(blocCahier, blocMethode);
    if (gestes.childElementCount) contenu.append(gestes);
    contenu.append(repliee, partieTaches(ctx, f), partieLivrables(ctx, f), partieCouts(f), partieDocuments(ctx, f));
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
