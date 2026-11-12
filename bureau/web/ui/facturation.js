// Onglet « Facturation » d'un dossier de service. Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {euros, tokens, tronquer, libellePeriode, dateFr} from "./texte.js";
import {challengeDe} from "./actions.js";
import {urlProjet} from "./projets.js";
import {enAttenteCible} from "./challenge.js";
import {etiquettePart, marquerPart, avecPart} from "./abonnement.js";
import {etiquetteCO2, marquerTitreCO2} from "./empreinte.js";

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
  const notes = [];
  if (cloud > 0 && !recrutes.cloud) notes.push("Aucun agent cloud recruté : les places cloud resteront vides.");
  notes.push("Chaque place est tenue par un agent recruté : pour plusieurs tâches d'un même rôle en même temps, " +
             "il faut plusieurs agents de ce rôle. Une place locale attend que la charge de l'ordinateur le permette ; " +
             "une place cloud non. Les tâches qui mènent à une validation passent d'abord ; rien ne démarre après une " +
             "validation qui vous attend.");
  const attente = etat?.attente_validation?.texte;
  return {locaux, cloud, recrutes, notes, attente: typeof attente === "string" && attente.trim() ? attente : null};
}

// La partie « Parallélisme du projet », en bas de l'onglet : deux nombres et « Enregistrer » (si l'on peut agir).
export function partieParallelisme(ctx) {
  const r = resumeParallelisme(ctx.etat);
  const bloc = el("div", "parallelisme");
  bloc.append(el("div", "carte-sous-titre", "Parallélisme du projet"));
  bloc.append(el("p", "note", `Agents recrutés : ${r.recrutes.locaux} locaux, ${r.recrutes.cloud} cloud.`));
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
