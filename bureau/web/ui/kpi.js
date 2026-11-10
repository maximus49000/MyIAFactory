// Onglet « KPI » d'un dossier de service, et rappel des alertes en haut de l'onglet Tâches.
// Les KPI du projet sont montrés tels quels ; ceux que le bureau calcule suivent la période.
// Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {tronquer, libellePeriode} from "./texte.js";
import {challengeDe} from "./actions.js";
import {urlProjet} from "./projets.js";
import {enAttenteCible} from "./challenge.js";

const MAX_NOM = 60;

// Un nombre en clair : virgule décimale, deux décimales au plus.
export function nombreFr(n) {
  return String(Number(n.toFixed(2))).replace(".", ",");
}

// La valeur à montrer pour la période, avec son unité. Le projet peut donner `periodes` ; sans valeur
// pour la période demandée, c'est la valeur du projet qui vaut (marquée « toutes périodes »).
export function valeurKpi(kpi, periode) {
  const propres = kpi?.periodes && typeof kpi.periodes === "object" && Object.hasOwn(kpi.periodes, periode);
  const v = propres ? kpi.periodes[periode] : kpi?.valeur;
  let texte;
  if (typeof v === "number" && Number.isFinite(v)) texte = nombreFr(v);
  else if (typeof v === "string") texte = v;
  else return "—";
  return kpi.unite ? `${texte} ${kpi.unite}` : texte;
}

// « toutes périodes » quand le chiffre ne suit pas le sélecteur ; null sinon.
export function etiquettePeriode(kpi, periode) {
  const p = kpi?.periodes;
  if (!p || typeof p !== "object" || !Object.keys(p).length) return "toutes périodes";
  if (periode !== undefined && !Object.hasOwn(p, periode)) return "toutes périodes";
  return null;
}

export function kpiEnAlerte(liste) {
  return Array.isArray(liste) ? liste.filter((k) => k && k.alerte === true) : [];
}

// L'identifiant de cible d'un KPI — celui que le serveur recalcule, aussi pour un KPI du projet.
export function idCibleKpi(service, id) {
  return `kpi:${service}:${id}`;
}

export async function chargerKpi(periode) {
  let r;
  try {
    r = await fetch(urlProjet(`/api/kpi?periode=${encodeURIComponent(periode)}`),
                    {cache: "no-store", signal: AbortSignal.timeout(15000)});
  } catch {
    throw new Error("Les KPI n'ont pas pu être chargés (serveur injoignable ou trop lent).");
  }
  if (!r.ok) throw new Error(`Les KPI n'ont pas pu être chargés (${r.status}).`);
  return r.json();
}

// Le bouton « Challenger » d'un KPI : même comportement que pour une connaissance ou une source.
function boutonChallenge(k, service, etat, challenger) {
  const cible = {type: "kpi", id: idCibleKpi(service, k.id)};
  const existe = challengeDe(etat, cible);
  const attente = !existe && enAttenteCible(cible);
  const b = el("button", "bouton secondaire",
    existe ? "Voir le challenge" : (attente ? "Demande envoyée" : "Challenger"));
  b.type = "button";
  const constat = k.texte || `${k.nom} : ${valeurKpi(k, "7j")}`;
  if (challenger && !attente) b.addEventListener("click", () => challenger(cible, constat, []));
  else b.disabled = true;
  return b;
}

function carte(k, periode, service, etat, challenger) {
  const c = el("li", "carte-kpi" + (k.alerte ? " alerte" : ""));
  c.append(el("div", "kpi-nom", tronquer(k.nom, MAX_NOM)), el("div", "kpi-valeur", valeurKpi(k, periode)));
  if (k.evolution) c.append(el("div", "kpi-evolution", k.evolution));
  const etiquette = etiquettePeriode(k, periode);
  if (etiquette) c.append(el("div", "kpi-periode", etiquette));
  if (k.alerte) {
    c.append(el("div", "kpi-alerte", "Alerte" + (k.texte ? " : " + k.texte : "")));
    c.append(boutonChallenge(k, service, etat, challenger));
  }
  return c;
}

// Dessine la grille. `donnees` vient de chargerKpi.
export function dessinerKpi(conteneur, donnees, service, periode, etat, challenger) {
  conteneur.replaceChildren();
  const liste = donnees && donnees.disponible !== false ? donnees.services?.[service] : null;
  if (!liste) {
    conteneur.append(el("p", "note", "Les KPI ne sont pas disponibles : le relevé n'en donne pas."));
    return;
  }
  conteneur.append(el("div", "carte-sous-titre", `KPI · ${libellePeriode(periode)}`));
  if (!liste.length) {
    conteneur.append(el("p", "vide", "Aucun KPI pour ce service."));
    return;
  }
  const grille = el("ul", "grille-kpi");
  for (const k of liste) grille.append(carte(k, periode, service, etat, challenger));
  conteneur.append(grille);
}

// contenuKpi(contexte, conteneur, service, periode)
export function contenuKpi(ctx, conteneur, service, periode) {
  conteneur.append(el("p", "note", "Chargement…"));
  chargerKpi(periode).then(
    (d) => { if (conteneur.isConnected) dessinerKpi(conteneur, d, service, periode, ctx.etat, ctx.challenger); },
    (err) => { if (conteneur.isConnected) conteneur.replaceChildren(el("p", "avertissement", err.message)); },
  );
}

// Les alertes du service, en haut de l'onglet Tâches. Un échec laisse l'onglet comme il était.
export function rappelAlertes(ctx, conteneur, service, periode) {
  const place = el("div", "rappel-alertes");
  conteneur.append(place);
  chargerKpi(periode).then((d) => {
    const alertes = kpiEnAlerte(d?.disponible === false ? [] : d?.services?.[service]);
    if (!alertes.length || !place.isConnected) return;
    place.append(el("div", "carte-sous-titre", `Alertes (${alertes.length})`));
    const ul = el("ul", "liste-alertes");
    for (const k of alertes) {
      const li = el("li", "alerte-kpi");
      li.append(el("span", "alerte-texte", `${tronquer(k.nom, MAX_NOM)} : ${valeurKpi(k, periode)}${k.texte ? " — " + k.texte : ""}`),
                boutonChallenge(k, service, ctx.etat, ctx.challenger));
      ul.append(li);
    }
    place.append(ul);
  }, () => { /* pas de rappel */ });
}
