// « À faire chez <partenaire> » : l'utilisateur est inscrit chez un partenaire, sans liaison directe. L'agent n'appelle pas le
// partenaire, il prépare ce que l'utilisateur fait sur son site : le prompt prêt à copier, les réglages, le mode opératoire et
// ce qu'il doit rapporter. Le retour est une demande au projet : « Fait » (avec le résultat joint si l'utilisateur veut), ou
// « Je n'ai pas pu ». Tout texte venu du serveur passe par textContent ; seuls les liens https:// sont rendus.

import {el} from "./dom.js";
import {nomAgent} from "./detail.js";
import {lienHttps} from "./partenaires.js";
import {tailleLisible, verifierChoix} from "./pieces.js";
import {preparerFichier} from "./fonctionnalite.js";

const plein = (t) => typeof t === "string" && t.trim() !== "";
const liste = (v) => (Array.isArray(v) ? v.filter(plein) : []);
export const MAX_TEXTE_RETOUR = 3500;

// Le retour : « fait » (le texte et les fichiers rapportés, facultatifs) ou « impossible » (le texte, obligatoire).
export function demandeChezPartenaire(decision, verdict, texte, fichiers) {
  const d = {type: "faire_chez_partenaire", decision: decision.id, verdict};
  if (typeof texte === "string" && texte.trim() !== "") d.texte = texte.trim();
  if (verdict === "fait" && Array.isArray(fichiers) && fichiers.length) {
    d.fichiers = fichiers.map((f) => ({nom: f.nom, type: f.type, donnees: f.donnees}));
  }
  return d;
}

// Une génération à la fois chez un partenaire : une demande placée `apres` une autre n'est pas encore à faire tant que
// celle-ci est dans la liste.
export function attendUneAutre(decision, decisions) {
  return plein(decision?.apres) && (Array.isArray(decisions) ? decisions : []).some((x) => x?.id === decision.apres);
}

// Le nom du partenaire tel que la décision le donne (sinon son identifiant).
export const nomPartenaire = (d) => (plein(d?.nom_partenaire) ? d.nom_partenaire : String(d?.partenaire ?? "le partenaire"));

// Tout ce que l'utilisateur copie ou lit, en un texte : le prompt seul pour « Copier le prompt ».
export const promptACopier = (d) => String(d?.prompt ?? "");

async function copier(texte, ctx) {
  try {
    await globalThis.navigator.clipboard.writeText(texte);
    return "Prompt copié.";
  } catch {
    return "La copie n'a pas pu se faire : sélectionnez le prompt.";
  }
}

// `boutonDemande(libelle, classe, fabrique, avant)` : le bouton qui envoie une demande (celui de decisions.js).
export function decisionChezPartenaire(ctx, d, boutonDemande) {
  const li = el("li", "decision-chez-partenaire");
  const nom = nomPartenaire(d);
  li.append(el("div", "decision-texte", `À faire chez ${nom}`));
  li.append(el("div", "lecon-meta", [nomAgent(ctx.etat, d.agent), d.quoi && `pour : ${d.quoi}`].filter(plein).join(" · ")));
  const decisions = Array.isArray(ctx.etat?.decisions_projet) ? ctx.etat.decisions_projet : [];
  if (attendUneAutre(d, decisions)) {
    li.append(el("div", "decision-regle", `Une génération à la fois chez ${nom} : cette demande vient après la demande ${d.apres}.`));
  }
  const site = lienHttps(d.site);
  if (site) {
    const a = el("a", "lien-partenaire", `Ouvrir ${nom}`);
    a.href = site;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    li.append(a);
  }
  const prompt = String(d.prompt ?? "");
  const zone = el("textarea", "chez-prompt");
  zone.value = prompt;
  zone.readOnly = true;
  zone.rows = Math.min(10, Math.max(3, prompt.split("\n").length + 1));
  zone.setAttribute("aria-label", `Prompt à coller chez ${nom}`);
  const message = el("span", "lecon-meta", "");
  const copie = el("button", "bouton", "Copier le prompt");
  copie.type = "button";
  copie.addEventListener("click", async () => { message.textContent = await copier(promptACopier(d), ctx); });
  li.append(el("div", "lecon-meta", `Prompt (${prompt.length} caractères)`), zone, copie, message);
  const reglages = liste(d.reglages);
  if (reglages.length) {
    li.append(el("div", "lecon-meta", "Réglages à choisir chez le partenaire :"));
    const ul = el("ul", "chez-reglages");
    for (const r of reglages) ul.append(el("li", "", r));
    li.append(ul);
  }
  const elements = liste(d.elements);
  if (elements.length) li.append(el("div", "lecon-meta", `Éléments groupés dans cette génération : ${elements.join(", ")}`));
  const etapes = liste(d.mode_operatoire);
  if (etapes.length) {
    li.append(el("div", "lecon-meta", "Mode opératoire :"));
    const ol = el("ol", "chez-etapes");
    for (const e of etapes) ol.append(el("li", "", e));
    li.append(ol);
  }
  const a = d.a_rapporter && typeof d.a_rapporter === "object" ? d.a_rapporter : {};
  if (plein(a.description)) {
    li.append(el("div", "decision-texte", `À rapporter : ${a.description}` + (plein(a.nom) ? ` (nom attendu : ${a.nom})` : "")));
    li.append(el("div", "lecon-meta", "Un type de fichier que la page n'accepte pas (glb, fbx, obj…) : joignez-le dans un .zip, "
      + "ou déposez-le dans le dossier du projet et dites où dans le texte."));
  }
  if (!ctx.etat.agir || attendUneAutre(d, decisions)) return li;
  // Le retour : le résultat en pièces jointes (facultatif), un mot, puis « Fait » ou « Je n'ai pas pu ».
  const prets = [];
  const choisis = el("div", "lecon-meta", "");
  const fichier = el("input", "chez-fichiers");
  fichier.type = "file";
  fichier.multiple = true;
  fichier.setAttribute("aria-label", "Joindre le résultat");
  const rafraichir = () => {
    choisis.textContent = prets.length ? "Joints : " + prets.map((p) => `${p.nom} (${tailleLisible(p.taille)})`).join(", ") : "";
  };
  fichier.addEventListener("change", async () => {
    const files = Array.from(fichier.files || []);
    const probleme = verifierChoix(prets, files);
    if (probleme) { choisis.textContent = probleme; return; }
    try {
      for (const f of files) prets.push(await preparerFichier(f));
      rafraichir();
    } catch (e) {
      choisis.textContent = e instanceof Error ? e.message : "Un fichier n'a pas pu être lu.";
    }
  });
  const texte = el("input", "chez-texte");
  texte.type = "text";
  texte.maxLength = 500;
  texte.placeholder = "Un mot (facultatif pour « Fait », obligatoire pour « Je n'ai pas pu »)";
  texte.setAttribute("aria-label", "Votre retour");
  li.append(el("div", "lecon-meta", "Rapportez le résultat :"), fichier, choisis, texte);
  const rangee = el("div", "lecon-boutons");
  rangee.append(
    boutonDemande("Fait", "bouton", () => demandeChezPartenaire(d, "fait", texte.value, prets)),
    boutonDemande("Je n'ai pas pu", "bouton secondaire", () => demandeChezPartenaire(d, "impossible", texte.value),
      () => { if (plein(texte.value)) return true; choisis.textContent = "Dites ce qui a bloqué."; return false; }));
  li.append(rangee);
  return li;
}
