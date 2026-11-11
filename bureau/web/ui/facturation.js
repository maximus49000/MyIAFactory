// Onglet « Facturation » d'un dossier de service. Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {euros, tokens, tronquer, libellePeriode, dateFr} from "./texte.js";
import {challengeDe} from "./actions.js";
import {urlProjet} from "./projets.js";
import {enAttenteCible} from "./challenge.js";

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
      id, total: t.total, sansPrix: t.sans_prix || 0, reparti: t.reparti === true,
      titre: id === "" ? "Hors tâche" : (titres.get(id) || id),
      etapes: Object.entries(t.etapes || {}).map(([nom, total]) => ({nom: nom === "" ? "Sans étape" : nom, total}))
        .sort((a, b) => b.total - a.total),
    }))
    .sort((a, b) => b.total - a.total);
}

export const MARQUE_LOT = "estimé (part d'un lot)";

// Le coût d'une tâche : « estimé (part d'un lot) » quand sa part a été répartie entre les tâches d'un lot.
export function coutDeTache(t) {
  const c = coutEnClair({total: t.total, sans_prix: t.sansPrix});
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
      cout: typeof u.cout === "number" ? u.cout : null,
      prixDu: u.prix_du ?? null, ancien: u.ancien === true,
      ...(typeof u.reparti === "string" ? {reparti: u.reparti} : {}),
    }));
}

// Le total général du projet et la part « direction / hors service » (qui n'a pas de dossier).
export function totalProjet(f) {
  return {total: f?.total ?? 0, direction: f?.direction?.total ?? 0, sansPrix: (f?.sans_prix || []).length > 0};
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
  return Object.entries(s?.modeles || {}).map(([nom, total]) => ({nom, total})).sort((a, b) => b.total - a.total);
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

function rangee(nom, valeur, classe = "") {
  const l = el("div", "ligne-cout " + classe);
  l.append(el("span", "cout-nom", nom), el("span", "cout-val", valeur));
  return l;
}

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
      li.append(rangee(tronquer(t.titre, MAX_TITRE), coutDeTache(t), "gras"));
      for (const e of t.etapes) li.append(rangee("↳ " + e.nom, euros(e.total), "etape"));
      liste.append(li);
    }
    conteneur.append(liste);
    conteneur.append(el("div", "carte-sous-titre", "Par modèle"));
    const modeles = lignesModeles(s);
    const lm = el("ul", "liste-cout");
    if (!modeles.length) lm.append(el("li", "vide", "Aucun modèle compté"));
    for (const m of modeles) {
      const li = el("li", "");
      li.append(rangee(m.nom, euros(m.total)));
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
                              `${tokens(d.tokens)} tokens` + (d.reparti ? ` · ${MARQUE_LOT}` : ""), "etape"));
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
  conteneur.append(rangee("Total, tous services", coutEnClair({total: projet.total, sans_prix: projet.sansPrix ? 1 : 0}), "gras"));
  conteneur.append(rangee("↳ dont direction / hors service",
                          coutEnClair(donnees.direction || {total: 0}), "etape"));
  conteneur.append(rangee("↳ dont gestion du bureau lui-même", euros(donnees.gestion ?? 0), "etape"));
  if (donnees.maj) conteneur.append(el("p", "note", `Prix mis à jour le ${dateFr(donnees.maj) || donnees.maj}`));
}

// contenuFacturation(contexte, conteneur, service, periode)
export function contenuFacturation(ctx, conteneur, service, periode) {
  conteneur.append(el("p", "note", "Chargement…"));
  chargerFacturation(periode).then(
    (d) => { if (conteneur.isConnected) dessinerFacturation(conteneur, d, service, periode, ctx.etat, ctx.challenger); },
    (err) => { if (conteneur.isConnected) conteneur.replaceChildren(el("p", "avertissement", err.message)); },
  );
}
