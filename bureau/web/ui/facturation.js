// Onglet « Facturation » d'un dossier de service. Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {euros, tokens, tronquer, libellePeriode, dateFr} from "./texte.js";

const MAX_TITRE = 90;

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
      id, total: t.total,
      titre: id === "" ? "Hors tâche" : (titres.get(id) || id),
      etapes: Object.entries(t.etapes || {}).map(([nom, total]) => ({nom: nom === "" ? "Sans étape" : nom, total}))
        .sort((a, b) => b.total - a.total),
    }))
    .sort((a, b) => b.total - a.total);
}

export function lignesModeles(s) {
  return Object.entries(s?.modeles || {}).map(([nom, total]) => ({nom, total})).sort((a, b) => b.total - a.total);
}

// Récupère la facturation de la période ; lève une erreur lisible en cas d'échec.
export async function chargerFacturation(periode) {
  let r;
  try {
    r = await fetch(`/api/facturation?periode=${encodeURIComponent(periode)}`,
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

// Dessine la facturation du service. `donnees` vient de chargerFacturation.
export function dessinerFacturation(conteneur, donnees, service, periode, etat) {
  conteneur.replaceChildren();
  if (!donnees || donnees.disponible === false) {
    conteneur.append(el("p", "note", "La facturation n'est pas disponible : le relevé ne donne pas d'usage."));
    return;
  }
  const s = serviceFacture(donnees, service);
  const total = el("div", "cout-total", euros(s ? s.total : 0));
  if (donnees.prix_du) total.title = `Prix du ${dateFr(donnees.prix_du) || donnees.prix_du}`;
  conteneur.append(el("div", "carte-sous-titre", `Coût estimé · ${libellePeriode(periode)}`), total);
  conteneur.append(el("p", "note", "Estimation d'après les tokens et les prix des modèles, jamais une facture."));
  for (const m of [donnees.message, donnees.avertissement]) {
    if (m) conteneur.append(el("p", "avertissement", m));
  }
  if ((donnees.sans_prix || []).length) {
    const bloc = el("div", "avertissement");
    bloc.append(el("strong", "", "Prix inconnu, exclu des euros : "));
    bloc.append(document.createTextNode(donnees.sans_prix
      .map((x) => `${x.modele} (${tokens(x.tokens)} tokens)`).join(", ")));
    conteneur.append(bloc);
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
      li.append(rangee(tronquer(t.titre, MAX_TITRE), euros(t.total), "gras"));
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
  }
  const sources = (donnees.sources || []).filter((x) => x.service === service);
  if (sources.length) {
    conteneur.append(el("div", "carte-sous-titre", "Sources d'amélioration"));
    const ls = el("ul", "liste-cout");
    for (const x of sources) {
      const li = el("li", "source");
      li.append(el("span", "source-texte", x.texte));
      const b = el("button", "bouton secondaire", "Challenger");
      b.type = "button";
      b.disabled = true;     // le geste arrive avec la tâche 9
      b.title = "Bientôt disponible";
      li.append(b);
      ls.append(li);
    }
    conteneur.append(ls);
  }
  conteneur.append(el("div", "carte-sous-titre", "Gestion du bureau"));
  conteneur.append(rangee("Coût du bureau lui-même", euros(donnees.gestion ?? 0)));
  if (donnees.maj) conteneur.append(el("p", "note", `Prix mis à jour le ${dateFr(donnees.maj) || donnees.maj}.`));
}

// contenuFacturation(contexte, conteneur, service, periode)
export function contenuFacturation(ctx, conteneur, service, periode) {
  conteneur.append(el("p", "note", "Chargement…"));
  chargerFacturation(periode).then(
    (d) => { if (conteneur.isConnected) dessinerFacturation(conteneur, d, service, periode, ctx.etat); },
    (err) => { if (conteneur.isConnected) conteneur.replaceChildren(el("p", "avertissement", err.message)); },
  );
}
