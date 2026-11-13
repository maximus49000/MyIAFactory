// Onglet « Facturation » d'un dossier de service. Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {euros, tokens, tronquer, libellePeriode, dateFr} from "./texte.js";
import {challengeDe} from "./actions.js";
import {urlProjet} from "./projets.js";
import {enAttenteCible} from "./challenge.js";
import {etiquettePart, marquerPart, avecPart} from "./abonnement.js";
import {etiquetteCO2, marquerTitreCO2, ligneEquivalences} from "./empreinte.js";

const MAX_TITRE = 90;
const MAX_DISCUSSIONS = 200;  // au-delà, la liste dit combien elle n'en montre pas

// Le service dans la facturation ; null si absent (le relevé ne l'a pas compté).
export function serviceFacture(f, id) {
  return f && f.services && f.services[id] ? f.services[id] : null;
}

// Les tâches d'un service, de la plus chère à la moins chère. La clé « » veut dire « hors tâche » ;
// dans les étapes, « sans étape ». Un titre inconnu est remplacé par l'identifiant.
export function lignesTaches(s, taches) {
  const titres = new Map((taches || []).map((t) => [t.id, t.titre]));
  return Object.entries(s?.taches || {})
    .map(([id, t]) => ({
      id, total: t.total, sansPrix: t.sans_prix || 0, reparti: t.reparti === true, ...avec(t.co2),
      titre: id === "" ? "Hors tâche" : (titres.get(id) || id),
      etapes: Object.entries(t.etapes || {})
        .map(([nom, total]) => ({nom: nom === "" ? "Sans étape" : nom, total, ...avec(t.etapes_co2?.[nom])}))
        .sort((a, b) => b.total - a.total),
    }))
    .sort((a, b) => b.total - a.total);
}

// `{co2}` quand le serveur a une empreinte estimée pour la ligne, rien sinon (jamais de zéro à la place d'un inconnu).
const avec = (co2) => (co2 ? {co2} : {});

export const MARQUE_LOT = "estimé (part d'un lot)";

// Le coût d'une tâche : « estimé (part d'un lot) » quand sa part a été répartie entre les tâches d'un lot.
export function coutDeTache(t) {
  const c = avecPart(coutEnClair({total: t.total, sans_prix: t.sansPrix}), etiquetteCO2(t.co2));
  return t.reparti ? `${c} · ${MARQUE_LOT}` : c;
}

// Un coût en clair qui ne passe jamais pour complet : `sans_prix` (nombre ou liste) dit que des usages
// à prix inconnu n'y sont pas comptés.
export function coutEnClair(x) {
  const manque = Array.isArray(x?.sans_prix) ? x.sans_prix.length > 0 : (x?.sans_prix || 0) > 0;
  if (!manque) return euros(x?.total ?? 0);
  return x.total > 0 ? `${euros(x.total)} + prix inconnu` : "prix inconnu";
}

// Les discussions (usages) d'un service, la plus récente d'abord : le niveau le plus fin de la facturation.
export function lignesDiscussions(s, etat) {
  const prenoms = new Map((etat?.agents || []).map((a) => [a.id, a.prenom]));
  const titres = new Map((etat?.taches || []).map((t) => [t.id, t.titre]));
  return [...(s?.usages || [])]
    .sort((a, b) => String(b.t).localeCompare(String(a.t)) || String(a.id).localeCompare(String(b.id)))
    .map((u) => ({
      id: u.id, t: u.t,
      agent: prenoms.get(u.agent) || u.agent || "—",
      tache: u.tache ? (titres.get(u.tache) || u.tache) : "Hors tâche",
      modele: u.modele, etape: u.etape || "Sans étape",
      tokens: Object.values(u.tokens || {}).reduce((n, v) => n + (typeof v === "number" ? v : 0), 0),
      cout: typeof u.cout === "number" ? u.cout : null, ...avec(u.co2),
      prixDu: u.prix_du ?? null, ancien: u.ancien === true,
      ...(typeof u.reparti === "string" ? {reparti: u.reparti} : {}),
    }));
}

// Le total général du projet et la part « direction / hors service » (qui n'a pas de dossier).
export function totalProjet(f) {
  return {total: f?.total ?? 0, direction: f?.direction?.total ?? 0, orchestration: f?.orchestration?.total ?? 0,
          sansPrix: (f?.sans_prix || []).length > 0,
          ...avec(f?.co2), ...(f?.direction?.co2 ? {co2Direction: f.direction.co2} : {}),
          ...(f?.orchestration?.co2 ? {co2Orchestration: f.orchestration.co2} : {})};
}

// Les partenaires dans la facturation : une ligne par partenaire (coût en euros ; le coût d'origine est en info-bulle).
// Un coût absent compte « non chiffré », jamais zéro ; un coût estimé le dit.
export function lignesPartenaires(f) {
  return Object.entries(f?.partenaires || {})
    .map(([id, p]) => {
      const origine = (Array.isArray(p?.origine) ? p.origine : [])
        .filter((o) => o && typeof o.montant === "number" && typeof o.devise === "string")
        .map((o) => `${String(o.montant).replace(".", ",")} ${o.devise}`).join(" + ");
      return {
        id, nom: typeof p?.nom === "string" && p.nom ? p.nom : id,
        total: typeof p?.total === "number" ? p.total : 0, origine,
        estime: p?.estime === true, nonChiffre: typeof p?.non_chiffre === "number" ? p.non_chiffre : 0,
        usages: typeof p?.usages === "number" ? p.usages : 0,
      };
    })
    .sort((a, b) => b.total - a.total || a.nom.localeCompare(b.nom));
}

export function coutDePartenaire(l) {
  let texte = l.total > 0 ? euros(l.total) : (l.nonChiffre > 0 ? "non chiffré" : euros(0));
  if (l.total > 0 && l.nonChiffre > 0) texte += " + non chiffré";
  if (l.estime && l.total > 0) texte += " · estimé";
  return texte;
}

export function lignesModeles(s) {
  return Object.entries(s?.modeles || {}).map(([nom, total]) => ({nom, total, ...avec(s.modeles_co2?.[nom])}))
    .sort((a, b) => b.total - a.total);
}

// Récupère la facturation de la période ; lève une erreur lisible en cas d'échec.
export async function chargerFacturation(periode) {
  let r;
  try {
    r = await fetch(urlProjet(`/api/facturation?periode=${encodeURIComponent(periode)}`),
                    {cache: "no-store", signal: AbortSignal.timeout(15000)});
  } catch {
    throw new Error("La facturation n'a pas pu être chargée (serveur injoignable ou trop lent).");
  }
  if (!r.ok) throw new Error(`La facturation n'a pas pu être chargée (${r.status}).`);
  return r.json();
}

// Une ligne « nom — valeur » ; `co2` (l'empreinte estimée de la ligne) pose l'infobulle quand la valeur la porte.
function rangee(nom, valeur, classe = "", co2 = null) {
  const l = el("div", "ligne-cout " + classe);
  l.append(el("span", "cout-nom", nom), el("span", "cout-val", valeur));
  return co2 ? marquerTitreCO2(l, co2) : l;
}

// Un montant en euros suivi de l'empreinte estimée de la ligne.
const avecCO2 = (texte, co2) => avecPart(texte, etiquetteCO2(co2));

// Dessine la facturation du service. `donnees` vient de chargerFacturation ;
// `challenger(cible, constat, taches)` ouvre le volet « Challenger » (bouton grisé sans lui).
export function dessinerFacturation(conteneur, donnees, service, periode, etat, challenger) {
  conteneur.replaceChildren();
  if (!donnees || donnees.disponible === false) {
    conteneur.append(el("p", "note", "La facturation n'est pas disponible : le relevé ne donne pas d'usage."));
    return;
  }
  const s = serviceFacture(donnees, service);
  const total = el("div", "cout-total", coutEnClair(s || {total: 0}));
  if (donnees.prix_du) total.title = `Prix du ${dateFr(donnees.prix_du) || donnees.prix_du}`;
  conteneur.append(el("div", "carte-sous-titre", `Coût estimé · ${libellePeriode(periode)}`), total);
  const part = etiquettePart(s?.total);   // la part de l'abonnement ; « en cours d'étalonnage » tant que le ratio manque
  if (part) conteneur.append(marquerPart(el("div", "cout-part", part)));
  const empreinte = etiquetteCO2(s?.co2);   // l'empreinte carbone estimée du service (EcoLogits), avec le lien vers la méthode
  if (empreinte) conteneur.append(marquerPart(el("div", "cout-part cout-empreinte", empreinte)));
  conteneur.append(el("p", "note", "Estimation d'après les tokens et les prix des modèles, jamais une facture."));
  if (donnees.message) conteneur.append(el("p", "avertissement", donnees.message));
  if ((s?.sans_prix || []).length) {  // ce qui manque aux euros de CE service
    const bloc = el("div", "avertissement");
    bloc.append(el("strong", "", "Prix inconnu, exclu des euros : "));
    bloc.append(document.createTextNode(s.sans_prix
      .map((x) => `${x.modele} (${x.usages} discussion${x.usages > 1 ? "s" : ""}, ${tokens(x.tokens)} tokens)`).join(", ")));
    conteneur.append(bloc);
  }
  if ((s?.usages || []).some((u) => u.ancien)) {
    conteneur.append(el("p", "avertissement",
      "Des discussions sont antérieures au premier prix enregistré : elles sont comptées au prix du jour de l'installation."));
  }
  if (!s) {
    conteneur.append(el("p", "vide", "Aucun usage pour ce service sur la période."));
  } else {
    conteneur.append(el("div", "carte-sous-titre", "Par tâche et par étape"));
    const taches = lignesTaches(s, etat?.taches);
    const liste = el("ul", "liste-cout");
    if (!taches.length) liste.append(el("li", "vide", "Aucune tâche"));
    for (const t of taches) {
      const li = el("li", "");
      li.append(rangee(tronquer(t.titre, MAX_TITRE), coutDeTache(t), "gras", t.co2));
      for (const e of t.etapes) li.append(rangee("↳ " + e.nom, avecCO2(euros(e.total), e.co2), "etape", e.co2));
      liste.append(li);
    }
    conteneur.append(liste);
    conteneur.append(el("div", "carte-sous-titre", "Par modèle"));
    const modeles = lignesModeles(s);
    const lm = el("ul", "liste-cout");
    if (!modeles.length) lm.append(el("li", "vide", "Aucun modèle compté"));
    for (const m of modeles) {
      const li = el("li", "");
      li.append(rangee(m.nom, avecCO2(euros(m.total), m.co2), "", m.co2));
      lm.append(li);
    }
    conteneur.append(lm);
    const discussions = lignesDiscussions(s, etat);
    conteneur.append(el("div", "carte-sous-titre", `Par discussion (${discussions.length})`));
    const ld = el("ul", "liste-cout");
    for (const d of discussions.slice(0, MAX_DISCUSSIONS)) {
      const li = el("li", "");
      const ligne = rangee(`${dateFr(d.t)} · ${tronquer(d.agent, 30)} · ${tronquer(d.modele, 40)}`,
                           d.cout === null ? "prix inconnu" : euros(d.cout));
      if (d.cout !== null && d.prixDu) {
        ligne.title = d.ancien ? `Prix du jour de l'installation (${dateFr(d.prixDu) || d.prixDu})`
                               : `Prix du ${dateFr(d.prixDu) || d.prixDu}`;
      }
      li.append(ligne, rangee(`↳ ${tronquer(d.tache, MAX_TITRE)} · ${tronquer(d.etape, 40)}`,
                              avecCO2(`${tokens(d.tokens)} tokens`, d.co2) + (d.reparti ? ` · ${MARQUE_LOT}` : ""),
                              "etape", d.co2));
      ld.append(li);
    }
    if (discussions.length > MAX_DISCUSSIONS) {
      ld.append(el("li", "vide", `… et ${discussions.length - MAX_DISCUSSIONS} discussions plus anciennes`));
    }
    conteneur.append(ld);
  }
  const sources = (donnees.sources || []).filter((x) => x.service === service);
  if (sources.length) {
    conteneur.append(el("div", "carte-sous-titre", "Sources d'amélioration"));
    const ls = el("ul", "liste-cout");
    for (const x of sources) {
      const li = el("li", "source");
      li.append(el("span", "source-texte", x.texte));
      const cible = {type: "source", id: x.id};
      const existe = challengeDe(etat, cible);
      const attente = !existe && enAttenteCible(cible);
      const b = el("button", "bouton secondaire",
        existe ? "Voir le challenge" : (attente ? "Demande envoyée" : "Challenger"));
      b.type = "button";
      if (challenger && !attente) b.addEventListener("click", () => challenger(cible, x.texte, x.tache ? [x.tache] : []));
      else b.disabled = true;
      li.append(b);
      ls.append(li);
    }
    conteneur.append(ls);
  }
  const partenaires = lignesPartenaires(donnees);
  if (partenaires.length) {
    conteneur.append(el("div", "carte-sous-titre", "Partenaires"));
    const lp = el("ul", "liste-cout");
    for (const l of partenaires) {
      const li = el("li", "");
      const r = rangee(tronquer(l.nom, 40), coutDePartenaire(l));
      if (l.origine) r.title = `Coût d'origine : ${l.origine}`;
      li.append(r);
      lp.append(li);
    }
    conteneur.append(lp);
  }
  const projet = totalProjet(donnees);
  conteneur.append(el("div", "carte-sous-titre", "Tout le projet"));
  conteneur.append(rangee("Total, tous services",
                          avecCO2(coutEnClair({total: projet.total, sans_prix: projet.sansPrix ? 1 : 0}), projet.co2), "gras", projet.co2));
  conteneur.append(rangee("↳ dont direction / hors service",
                          avecCO2(coutEnClair(donnees.direction || {total: 0}), projet.co2Direction), "etape", projet.co2Direction));
  conteneur.append(rangee("↳ dont orchestration (les décisions du moteur)",
                          avecCO2(coutEnClair(donnees.orchestration || {total: 0}), projet.co2Orchestration), "etape",
                          projet.co2Orchestration));
  const noteEmpreinte = projet.co2 ? marquerPart(el("p", "note", `Empreinte carbone estimée : ${etiquetteCO2(projet.co2)}`)) : null;
  if (noteEmpreinte) conteneur.append(noteEmpreinte);
  const equivalences = ligneEquivalences(projet.co2);   // « Équivaut à ≈ … » pour tout le projet
  if (equivalences) conteneur.append(equivalences);
  conteneur.append(rangee("↳ dont gestion du bureau lui-même", euros(donnees.gestion ?? 0), "etape"));
  if (donnees.maj) conteneur.append(el("p", "note", `Prix mis à jour le ${dateFr(donnees.maj) || donnees.maj}`));
}

// Les places du projet (le parallélisme) : bornes de la factory, vérifiées de nouveau par le serveur et l'outil.
export const BORNES_PLACES = {locaux: [1, 16], cloud: [0, 16]};

// La demande « parallelisme » ; null si une valeur sort des bornes ou n'est pas un entier.
export function demandeParallelisme(locaux, cloud) {
  const n = (v) => (typeof v === "string" && /^\s*\d+\s*$/.test(v) ? Number(v) : v);
  const l = n(locaux), c = n(cloud);
  const dans = (v, [bas, haut]) => Number.isInteger(v) && v >= bas && v <= haut;
  if (!dans(l, BORNES_PLACES.locaux) || !dans(c, BORNES_PLACES.cloud)) return null;
  return {type: "parallelisme", agents_locaux_max: l, agents_cloud_max: c};
}

// Ce que dit la partie « Parallélisme du projet » : les réglages, les agents recrutés de chaque lieu, et ce qui retient.
export function resumeParallelisme(etat) {
  const agents = (etat?.agents || []).filter((a) => !a.fixe && !a.chef && a.id !== "chef" && a.id !== "directeur");
  const recrutes = {locaux: agents.filter((a) => a.lieu !== "cloud").length, cloud: agents.filter((a) => a.lieu === "cloud").length};
  const locaux = Number.isInteger(etat?.agents_locaux_max) ? etat.agents_locaux_max : 2;
  const cloud = Number.isInteger(etat?.agents_cloud_max) ? etat.agents_cloud_max : 0;
  // Un projet d'agents polyvalents : l'équipe est exactement les places, rien ne se recrute par rôle.
  const polyvalent = etat?.recrutement?.polyvalent === true;
  const notes = [];
  if (polyvalent) {
    notes.push("Chaque place est un agent polyvalent. Il prend n'importe quelle tâche prête, en spécialiste de son " +
               "métier. Monter une place ajoute un agent ; en baisser une retire un agent libre (un agent au travail " +
               "finit d'abord sa tâche). Une place locale attend que la charge de l'ordinateur le permette ; une place " +
               "cloud non. Les tâches qui mènent à une validation passent d'abord ; rien ne démarre après une " +
               "validation qui vous attend.");
  } else {
    if (cloud > 0 && !recrutes.cloud) notes.push("Aucun agent cloud recruté : les places cloud resteront vides " +
                                                  "(recrutez-en ci-dessous).");
    notes.push("Chaque place est tenue par un agent recruté : pour plusieurs tâches d'un même rôle en même temps, " +
               "il faut plusieurs agents de ce rôle. Une place locale attend que la charge de l'ordinateur le permette ; " +
               "une place cloud non. Les tâches qui mènent à une validation passent d'abord ; rien ne démarre après une " +
               "validation qui vous attend.");
  }
  const attente = etat?.attente_validation?.texte;
  return {locaux, cloud, recrutes, notes, polyvalent, attente: typeof attente === "string" && attente.trim() ? attente : null};
}

// La partie « Parallélisme du projet », en bas de l'onglet : deux nombres et « Enregistrer » (si l'on peut agir).
export function partieParallelisme(ctx) {
  const r = resumeParallelisme(ctx.etat);
  const bloc = el("div", "parallelisme");
  bloc.append(el("div", "carte-sous-titre", "Parallélisme du projet"));
  bloc.append(el("p", "note", `${r.polyvalent ? "Agents" : "Agents recrutés"} : ${r.recrutes.locaux} locaux, ${r.recrutes.cloud} cloud.`));
  const champ = (libelle, valeur, [bas, haut]) => {
    const label = el("label", "parallelisme-champ");
    const input = document.createElement("input");
    input.type = "number";
    input.min = String(bas);
    input.max = String(haut);
    input.step = "1";
    input.value = String(valeur);
    input.disabled = !ctx.etat?.agir;
    label.append(el("span", "", libelle), input);
    return {label, input};
  };
  const l = champ("Agents locaux en même temps", r.locaux, BORNES_PLACES.locaux);
  const c = champ("Agents cloud en même temps", r.cloud, BORNES_PLACES.cloud);
  bloc.append(l.label, c.label);
  if (r.attente) bloc.append(el("p", "avertissement", r.attente));
  for (const n of r.notes) bloc.append(el("p", "note", n));
  if (ctx.etat?.agir && ctx.barre?.demander) {
    const erreur = el("p", "saisie-erreur", "");
    const b = el("button", "bouton", "Enregistrer");
    b.type = "button";
    b.addEventListener("click", async () => {
      const d = demandeParallelisme(l.input.value, c.input.value);
      if (!d) { erreur.textContent = "Agents locaux : de 1 à 16 ; agents cloud : de 0 à 16 (nombres entiers)."; return; }
      erreur.textContent = "";
      b.disabled = true;
      const res = await ctx.barre.demander(d, b);
      if (!res?.ok) b.disabled = false;
    });
    bloc.append(erreur, b);
  }
  const rec = partieRecrutement(ctx);
  if (rec) bloc.append(rec);
  return bloc;
}

// --- Recruter des agents (conception 2026-11-12-recrutement-design.md). Le relevé publie `recrutement` ; le serveur et
// l'outil revérifient tout (rôles, modèles, dépôt GitHub, places).

export const MODELES_RECRUE = ["Haiku", "Sonnet", "Opus"];
// Le modèle de la fiche d'une recrue est son plafond (conception 2026-11-12-modele-par-tache-design.md).
export const PLAFOND_PAR_DEFAUT = "Opus";
export const REGLE_PLAFOND = "Le modèle d'un agent est son plafond : il fait tourner chaque tâche sur le modèle " +
  "qu'elle demande (celui de son étape), jamais au-dessus ; Opus par défaut, Fable avec votre accord.";

// Une ligne de l'aperçu automatique : « dev · plafond Opus · tâches en Sonnet · cloud — raison ».
export function ligneApercu(p) {
  return [p.role, `plafond ${p.modele}`, ...(p.modele_necessaire ? [`tâches en ${p.modele_necessaire}`] : []), p.lieu]
    .join(" · ") + ` — ${p.raison}`;
}
export const LIEUX_AUTO = ["mieux", "cloud", "local"];     // « Au mieux », « Cloud », « Local »
const LIBELLE_LIEU = {mieux: "Au mieux", cloud: "Cloud", local: "Local"};

// Ce que montre la partie « Recruter » ; null si le relevé ne publie pas `recrutement` (orchestrateur d'avant).
export function resumeRecrutement(etat) {
  const rec = etat?.recrutement;
  if (!rec || typeof rec !== "object") return null;
  const depot = rec.depot || {};
  const places = {cloud: Number.isInteger(rec.places?.cloud) ? rec.places.cloud : 0,
                  locaux: Number.isInteger(rec.places?.locaux) ? rec.places.locaux : 0};
  const github = depot.github === true;
  let raisonCloud = null;
  if (!github) raisonCloud = rec.cloud_impossible || "Le projet n'est pas sur GitHub.";
  else if (!places.cloud) raisonCloud = "Aucune place cloud sans agent : augmentez « Agents cloud en même temps ».";
  return {polyvalent: rec.polyvalent === true, roles: Array.isArray(rec.roles) ? rec.roles : [], places, github, raisonCloud,
          cloudPossible: raisonCloud === null, propositions: Array.isArray(rec.propositions) ? rec.propositions : [],
          parLieu: LIEUX_AUTO.reduce((o, k) => ({...o, [k]: Array.isArray(rec.propositions_par_lieu?.[k]) ? rec.propositions_par_lieu[k]
                                                                  : (k === "mieux" && Array.isArray(rec.propositions) ? rec.propositions : [])}), {}),
          notesParLieu: LIEUX_AUTO.reduce((o, k) => ({...o, [k]: Array.isArray(rec.notes_par_lieu?.[k]) ? rec.notes_par_lieu[k] : []}), {}),
          notes: Array.isArray(rec.notes) ? rec.notes : [], url: typeof depot.url === "string" ? depot.url : null,
          creable: depot.creable === true && !github, essai: depot.essai && typeof depot.essai === "object" ? depot.essai : null};
}

// La demande « recruter » d'un agent choisi à la main ; {erreur} si le choix ne va pas (rien ne part).
export function demandeRecrutementManuel(resume, {role, modele, lieu, fable = false}) {
  if (!resume) return {erreur: "Le relevé ne permet pas encore de recruter."};
  if (!resume.roles.some((r) => r.role === role)) return {erreur: "Choisissez un rôle du workflow du projet."};
  if (modele === "Fable" ? fable !== true : !MODELES_RECRUE.includes(modele)) {
    return {erreur: modele === "Fable" ? "Fable demande votre accord : cochez « J'accorde Fable »." : "Choisissez un modèle."};
  }
  if (lieu !== "local" && lieu !== "cloud") return {erreur: "Choisissez local ou cloud."};
  if (lieu === "cloud" && !resume.cloudPossible) return {erreur: resume.raisonCloud};
  const agent = {role, modele, lieu};
  if (modele === "Fable") agent.fable = true;
  return {type: "recruter", mode: "manuel", agents: [agent]};
}

// Les propositions du lieu demandé (« mieux », « cloud » ou « local » ; elles ne dépendent pas de N).
export function propositionsDuLieu(resume, lieu = "mieux") {
  return resume?.parLieu?.[lieu] || (lieu === "mieux" ? resume?.propositions || [] : []);
}

// Les N premières propositions du lieu (« mieux » par défaut) ; si N dépasse ce qui est possible, toutes celles
// possibles ; [] si N ne va pas.
export function apercuAuto(resume, n, lieu = "mieux") {
  const v = typeof n === "string" && /^\s*\d+\s*$/.test(n) ? Number(n) : n;
  if (!resume || !Number.isInteger(v) || v < 1) return [];
  return propositionsDuLieu(resume, lieu).slice(0, v);
}

// Ce que dit la répartition quand le lieu ne permet pas N agents : combien sont possibles et pourquoi ; "" sinon.
export function limiteAuto(resume, n, lieu = "mieux") {
  const v = typeof n === "string" && /^\s*\d+\s*$/.test(n) ? Number(n) : n;
  if (!resume || !Number.isInteger(v) || v < 1) return "";
  const possibles = propositionsDuLieu(resume, lieu).length;
  if (v <= possibles) return "";
  const ou = lieu === "cloud" ? " cloud" : lieu === "local" ? " locaux" : "";
  if (lieu === "cloud" && !resume.cloudPossible && !possibles) {
    return `Aucun agent cloud possible : ${resume.raisonCloud}`;
  }
  const raisons = (resume.notesParLieu?.[lieu] || []).join(" ");
  return `${possibles ? `Seulement ${possibles} agent${possibles > 1 ? "s" : ""}${ou} possible${possibles > 1 ? "s" : ""}` :
                        `Aucun agent${ou} possible`} (${v} demandé${v > 1 ? "s" : ""}).${raisons ? " " + raisons : ""}`;
}

// La demande « recruter » d'une répartition automatique confirmée ; null si l'aperçu est vide.
export function demandeRecrutementAuto(apercu, lieu = "mieux") {
  if (!Array.isArray(apercu) || !apercu.length) return null;
  return {type: "recruter", mode: "auto", lieu,
          agents: apercu.map((p) => ({role: p.role, modele: p.modele, lieu: p.lieu}))};
}

// Le clic « Créer le dépôt Git » : le seul consentement à la création du dépôt GitHub privé.
export function demandeDepot() {
  return {type: "depot_git", confirme: true};
}

function choix(options, valeur) {
  const s = document.createElement("select");
  for (const [v, libelle, inactif] of options) {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = libelle;
    if (inactif) o.disabled = true;
    s.append(o);
  }
  if (valeur !== undefined) s.value = valeur;
  return s;
}

function boutonDemande(ctx, libelle, fabrique, erreur) {
  const b = el("button", "bouton", libelle);
  b.type = "button";
  b.addEventListener("click", async () => {
    const d = fabrique();
    if (!d || d.erreur) { erreur.textContent = d?.erreur || "Rien à envoyer."; return; }
    erreur.textContent = "";
    b.disabled = true;
    const res = await ctx.barre.demander(d, b);
    if (!res?.ok) b.disabled = false;
  });
  return b;
}

// La partie « Recruter » : à la main (rôle, modèle, lieu), en automatique (N agents, aperçu puis confirmation), et le
// dépôt Git (sans GitHub, pas d'agent cloud : « Créer le dépôt Git »).
export function partieRecrutement(ctx) {
  const r = resumeRecrutement(ctx.etat);
  if (!r || r.polyvalent) return null;      // un projet polyvalent : l'équipe suit les places, rien à recruter
  const agir = !!(ctx.etat?.agir && ctx.barre?.demander);
  const bloc = el("div", "recrutement");
  bloc.append(el("div", "carte-sous-titre", "Recruter des agents"));
  // Le dépôt.
  if (r.github) {
    const p = el("p", "note", "Dépôt GitHub : ");
    if (r.url) {
      const a = el("a", "", r.url);
      a.href = r.url;
      a.target = "_blank";
      a.rel = "noopener";
      p.append(a);
    } else p.append("en place");
    bloc.append(p);
  } else {
    bloc.append(el("p", "avertissement", `Agents cloud impossibles : ${r.raisonCloud}`));
    if (r.creable && agir) {
      const erreur = el("p", "saisie-erreur", "");
      bloc.append(el("p", "note", "« Créer le dépôt Git » crée un dépôt git local si besoin (premier commit), puis un " +
                                  "dépôt GitHub privé, et y pousse le projet (gh doit être installé et connecté). Les " +
                                  "clés (.env) et les fichiers propres à ce poste n'y partent pas."));
      bloc.append(boutonDemande(ctx, "Créer le dépôt Git", demandeDepot, erreur), erreur);
    }
  }
  if (r.essai && !r.github) bloc.append(el("p", r.essai.fait ? "note" : "avertissement", r.essai.texte || ""));
  if (!r.roles.length) {
    bloc.append(el("p", "note", "Le projet n'a pas encore de workflow : rien à recruter."));
    return bloc;
  }
  // À la main.
  const manuel = el("div", "recrutement-manuel");
  const role = choix(r.roles.map((x) => [x.role, `${x.nom || x.role} (${x.agents} agent${x.agents > 1 ? "s" : ""})`]));
  const modele = choix(MODELES_RECRUE.map((m) => [m, m]).concat([["Fable", "Fable (votre accord)", true]]),
                       PLAFOND_PAR_DEFAUT);
  const accord = document.createElement("input");
  accord.type = "checkbox";
  accord.addEventListener("change", () => {
    modele.querySelector('option[value="Fable"]').disabled = !accord.checked;
    if (!accord.checked && modele.value === "Fable") modele.value = "Opus";
  });
  const lieu = choix([["local", "local"], ["cloud", r.cloudPossible ? "cloud" : "cloud (impossible)", !r.cloudPossible]],
                     "local");
  const etiquetteAccord = el("label", "organisation-fable");
  etiquetteAccord.append(accord, el("span", "", " J'accorde Fable à cet agent (plus capable, plus cher)"));
  manuel.append(el("p", "note", REGLE_PLAFOND));
  for (const [libelle, champ] of [["Rôle", role], ["Plafond", modele], ["Lieu", lieu]]) {
    const label = el("label", "parallelisme-champ");
    champ.disabled = !agir;
    label.append(el("span", "", libelle), champ);
    manuel.append(label);
  }
  accord.disabled = !agir;
  manuel.append(etiquetteAccord);
  if (!r.cloudPossible) manuel.append(el("p", "note", `Cloud : ${r.raisonCloud}`));
  if (agir) {
    const erreur = el("p", "saisie-erreur", "");
    manuel.append(boutonDemande(ctx, "Recruter un agent", () => demandeRecrutementManuel(
      r, {role: role.value, modele: modele.value, lieu: lieu.value, fable: accord.checked}), erreur), erreur);
  }
  bloc.append(manuel);
  // En automatique.
  const auto = el("div", "recrutement-auto");
  auto.append(el("p", "note", "Attribution automatique : les rôles qui ont le plus de travail prêt ou en file (sans " +
                              "compter ce qu'une validation retient), le plafond Opus, et le modèle que demandent les " +
                              "tâches que chaque agent prend (conception : Opus ; code et création : Sonnet ; tests, " +
                              "livraison, rangement : Haiku ; un cran de plus après un échec ; jamais Fable), le lieu demandé " +
                              "(« Au mieux » : cloud d'abord s'il reste des places), jamais au-delà des places."));
  if (agir) {
    const label = el("label", "parallelisme-champ");
    const nombre = document.createElement("input");
    nombre.type = "number";
    nombre.min = "1";
    nombre.max = "16";
    nombre.step = "1";
    nombre.value = "1";
    label.append(el("span", "", "Nombre d'agents (1 à 16)"), nombre);
    const ou = choix(LIEUX_AUTO.map((k) => [k, LIBELLE_LIEU[k]]), "mieux");
    const labelLieu = el("label", "parallelisme-champ");
    labelLieu.append(el("span", "", "Lieu"), ou);
    const liste = el("ul", "recrutement-apercu");
    const erreur = el("p", "saisie-erreur", "");
    const infos = el("div", "recrutement-infos");
    let apercu = [];
    const confirmer = boutonDemande(ctx, "Confirmer le recrutement", () => demandeRecrutementAuto(apercu, ou.value), erreur);
    confirmer.hidden = true;
    const voir = el("button", "bouton", "Recruter N agents : voir la répartition");
    voir.type = "button";
    voir.addEventListener("click", () => {
      apercu = apercuAuto(r, nombre.value, ou.value);
      liste.replaceChildren(...apercu.map((p) => el("li", "", ligneApercu(p))));
      const limite = limiteAuto(r, nombre.value, ou.value);
      infos.replaceChildren(...(limite ? [el("p", "avertissement", limite)] : []),
                            ...(!apercu.length ? (r.notesParLieu[ou.value] || r.notes).map((n) => el("p", "note", n)) : []));
      erreur.textContent = apercu.length || limite ? "" : "Un nombre de 1 à 16.";
      confirmer.hidden = !apercu.length;
    });
    for (const k of [nombre, ou]) k.addEventListener("change", () => { confirmer.hidden = true; liste.replaceChildren(); infos.replaceChildren(); apercu = []; });
    auto.append(label, labelLieu, voir, liste, infos, confirmer, erreur);
  } else for (const n of r.notes) auto.append(el("p", "note", n));
  bloc.append(auto);
  return bloc;
}

// contenuFacturation(contexte, conteneur, service, periode)
export function contenuFacturation(ctx, conteneur, service, periode) {
  conteneur.append(el("p", "note", "Chargement…"));
  chargerFacturation(periode).then(
    (d) => {
      if (!conteneur.isConnected) return;
      dessinerFacturation(conteneur, d, service, periode, ctx.etat, ctx.challenger);
      if (ctx.etat?.version >= 4 || ctx.etat?.agents_locaux_max !== undefined) conteneur.append(partieParallelisme(ctx));
    },
    (err) => { if (conteneur.isConnected) conteneur.replaceChildren(el("p", "avertissement", err.message)); },
  );
}
