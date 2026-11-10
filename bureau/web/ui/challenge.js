// Le volet « Challenger » : ce qui s'est passé, les solutions proposées (le Directeur, le service, l'utilisateur),
// « Ma solution » et « Valider la sélection ». Chaque geste est une demande au projet ; son effet n'apparaît
// qu'au relevé suivant (en attendant : « Demande envoyée »). Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";
import {tronquer} from "./texte.js";
import {challengeDe, demandeChallenge, demandeSolution, demandesVerdicts, resumeEnvoi} from "./actions.js";

const MAX_TEXTE = 3500;
const AUTEURS = {directeur: "le Directeur", service: "le service", utilisateur: "vous"};
const DECIDEES = ["validée", "écartée"];

// Mémoire de la session (survit aux redessins du panneau) :
const enAttente = new Map();   // clé -> repère : la demande est partie, le relevé ne la montre pas encore
const brouillons = new Map();  // clé -> texte en cours d'écriture
const resumes = new Map();     // challenge -> résumé du dernier envoi de verdicts

const cleCible = (cible) => `c:${cible.type}:${cible.id}`;

function zoneTexte(cle, etiquette) {
  const zone = document.createElement("textarea");
  zone.className = "zone-retour";
  zone.maxLength = MAX_TEXTE;
  zone.rows = 3;
  zone.placeholder = etiquette;
  zone.setAttribute("aria-label", etiquette);
  zone.value = brouillons.get(cle) || "";
  zone.addEventListener("input", () => brouillons.set(cle, zone.value));
  return zone;
}

// contenuChallenge(contexte, conteneur, {cible, constat, taches, retour})
export function contenuChallenge(ctx, conteneur, volet) {
  const e = ctx.etat;
  const {cible} = volet;
  const redessiner = () => { if (conteneur.isConnected) { conteneur.replaceChildren(); contenuChallenge(ctx, conteneur, volet); } };

  const retour = el("button", "lien-tache", "← Retour");
  retour.type = "button";
  retour.addEventListener("click", volet.retour);
  conteneur.append(retour, el("h3", "", "Challenger"));

  const ch = challengeDe(e, cible);
  conteneur.append(el("div", "carte-sous-titre", "Ce qui s'est passé"));
  conteneur.append(el("p", "constat", ch?.texte || volet.constat || "—"));
  if (ch?.texte && volet.constat && ch.texte !== volet.constat) conteneur.append(el("p", "note", volet.constat));
  const taches = (volet.taches || []).map((id) => (e.taches || []).find((t) => t.id === id)).filter(Boolean);
  for (const t of taches) {
    const b = el("button", "lien-tache", tronquer(t.titre, 90));
    b.type = "button";
    b.addEventListener("click", () => ctx.ouvrirTache(t.id));
    conteneur.append(b);
  }

  const cle = cleCible(cible);
  if (!ch) {
    if (enAttente.has(cle)) {
      conteneur.append(el("p", "envoye", "Demande envoyée : le challenge apparaîtra au prochain relevé."));
      return;
    }
    if (!e.agir) {
      conteneur.append(el("p", "note", "Lecture seule : aucune commande d'actions n'est déclarée."));
      return;
    }
    conteneur.append(el("p", "note", "Le challenge demande au Directeur et au service de proposer des solutions. "
      + "Vous pouvez écrire la vôtre dès maintenant."));
    const zone = zoneTexte(cle, "Ma solution (facultatif)");
    const ouvrir = el("button", "bouton", "Ouvrir le challenge");
    ouvrir.type = "button";
    ouvrir.addEventListener("click", async () => {
      ouvrir.disabled = true;  // tout de suite : un double clic n'envoie qu'une demande
      const r = await ctx.barre.demander(demandeChallenge(cible, undefined, zone.value));
      if (r.ok) { enAttente.set(cle, true); brouillons.delete(cle); redessiner(); } else ouvrir.disabled = false;
    });
    conteneur.append(zone, ouvrir);
    return;
  }
  enAttente.delete(cle);

  const solutions = Array.isArray(ch.solutions) ? ch.solutions : [];
  conteneur.append(el("div", "carte-sous-titre", `Solutions proposées (${solutions.length})`));
  const ul = el("ul", "liste-partie");
  if (!solutions.length) ul.append(el("li", "vide", "Aucune solution pour l'instant : le Directeur et le service répondent au relevé suivant."));
  const cases = [];
  for (const s of solutions) {
    const cleV = `v:${ch.id}:${s.id}`;
    if (enAttente.has(cleV) && enAttente.get(cleV) !== (s.etat ?? null)) enAttente.delete(cleV);
    const li = el("li", "solution");
    const decidee = DECIDEES.includes(String(s.etat || "").toLowerCase());
    const attente = enAttente.has(cleV);
    if (e.agir && !decidee && !attente) {
      const c = document.createElement("input");
      c.type = "checkbox";
      c.setAttribute("aria-label", "Choisir cette solution");
      cases.push([c, s]);
      li.append(c);
    }
    const corps = el("div", "solution-corps");
    corps.append(el("div", "solution-texte", s.texte));
    const meta = [`proposée par ${AUTEURS[s.auteur] || s.auteur}`];
    if (s.etat) meta.push(s.etat);
    corps.append(el("div", "lecon-meta", meta.join(" · ")));
    if (attente) corps.append(el("div", "envoye", "Verdict envoyé"));
    li.append(corps);
    ul.append(li);
  }
  conteneur.append(ul);

  if (!e.agir) {
    conteneur.append(el("p", "note", "Lecture seule : aucune commande d'actions n'est déclarée."));
    return;
  }
  if (cases.length) {
    const valider = el("button", "bouton", "Valider la sélection");
    valider.type = "button";
    valider.disabled = true;
    for (const [c] of cases) c.addEventListener("change", () => { valider.disabled = !cases.some(([x]) => x.checked); });
    valider.addEventListener("click", async () => {
      valider.disabled = true;
      for (const [c] of cases) c.disabled = true;
      const cochees = cases.filter(([c]) => c.checked).map(([, s]) => s.id);
      const resultats = [];
      for (const d of demandesVerdicts(ch.id, cochees, solutions)) {  // l'une après l'autre
        const s = solutions.find((x) => x.id === d.solution);
        const r = await ctx.barre.demander(d);
        if (r.ok) enAttente.set(`v:${ch.id}:${s.id}`, s.etat ?? null);
        resultats.push({nom: `« ${tronquer(s.texte, 40)} »`, ok: r.ok, message: r.message});
      }
      resumes.set(ch.id, resumeEnvoi(resultats));
      redessiner();
    });
    conteneur.append(valider);
  }
  if (resumes.get(ch.id)) conteneur.append(el("p", "note", resumes.get(ch.id)));

  const cleS = `s:${ch.id}`;
  if (enAttente.has(cleS) && enAttente.get(cleS) !== solutions.length) enAttente.delete(cleS);
  conteneur.append(el("div", "carte-sous-titre", "Ma solution"));
  if (enAttente.has(cleS)) {
    conteneur.append(el("p", "envoye", "Demande envoyée : votre solution apparaîtra au prochain relevé."));
    return;
  }
  const zone = zoneTexte(cleS, "Écrire ma solution");
  const proposer = el("button", "bouton secondaire", "Proposer");
  proposer.type = "button";
  proposer.disabled = !zone.value.trim();
  zone.addEventListener("input", () => { proposer.disabled = !zone.value.trim(); });
  proposer.addEventListener("click", async () => {
    proposer.disabled = true;
    const r = await ctx.barre.demander(demandeSolution(ch.id, zone.value));
    if (r.ok) { enAttente.set(cleS, solutions.length); brouillons.delete(cleS); redessiner(); } else proposer.disabled = false;
  });
  conteneur.append(zone, proposer);
}
