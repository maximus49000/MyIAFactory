// Le bureau du Directeur (leçons à valider, retours sans réponse, tâches bloquées) et le panneau d'un agent.
// Chaque fonction remplit `contenu` ; un verdict est une demande au projet, jamais un changement direct.

import {el, ligne} from "./dom.js";
import {tronquer, dateFr, listeDisponible, phrasesDirectionV1} from "./texte.js";
import {prenomAgent} from "./detail.js";

const MAX_TITRE = 90;

function titreTache(e, id) {
  const t = (e.taches || []).find((x) => x.id === id);
  return t ? tronquer(t.titre, MAX_TITRE) : null;
}

// Un lien qui ouvre le panneau d'une tâche.
function lienTache(ctx, id, texte) {
  const b = el("button", "lien-tache", texte);
  b.type = "button";
  b.addEventListener("click", () => ctx.ouvrirTache(id));
  return b;
}

function carteLecon(ctx, l) {
  const e = ctx.etat;
  const c = el("li", "lecon");
  c.append(el("div", "lecon-texte", l.texte));
  const meta = el("div", "lecon-meta");
  meta.append(el("span", "", prenomAgent(e, l.agent) === "personne" ? l.agent : prenomAgent(e, l.agent)));
  const titre = l.tache ? titreTache(e, l.tache) : null;
  if (titre) { meta.append(document.createTextNode(" · "), lienTache(ctx, l.tache, titre)); }
  if (l.date) meta.append(document.createTextNode(" · " + dateFr(l.date)));
  c.append(meta);
  if (l.verdict_demande) {
    c.append(el("div", "lecon-verdict", `Verdict envoyé : ${l.verdict_demande}`));
  } else if (e.agir) {
    const rangee = el("div", "lecon-boutons");
    const valider = el("button", "bouton", "Valider");
    const invalider = el("button", "bouton secondaire", "Invalider");
    for (const [bouton, verdict] of [[valider, "valider"], [invalider, "invalider"]]) {
      bouton.type = "button";
      bouton.addEventListener("click", async () => {
        valider.disabled = invalider.disabled = true;
        const r = await ctx.barre.demander({type: "lecon", id: l.id, verdict});
        if (!r.ok) valider.disabled = invalider.disabled = false;  // refus : on peut réessayer
      });
      rangee.append(bouton);
    }
    c.append(rangee);
  }
  return c;
}

function partie(titre, vide, elements) {
  const s = el("section", "partie");
  s.append(el("h3", "", titre));
  const ul = el("ul", "liste-partie");
  if (!elements.length) ul.append(el("li", "vide", vide));
  for (const x of elements) ul.append(x);
  s.append(ul);
  return s;
}

export function contenuDirecteur(ctx, contenu) {
  const e = ctx.etat;
  contenu.append(el("h2", "", "Direction"));
  if (!listeDisponible(e)) {  // relevé en version 1 : le panneau d'avant
    for (const p of phrasesDirectionV1(e)) contenu.append(el("p", p.classe, p.texte));
    return;
  }
  const n = e.decisions || 0;
  if (n > 0) {
    contenu.append(el("p", "decisions", n === 1 ? "1 décision attend le Directeur (comptée par le projet)."
      : `${n} décisions attendent le Directeur (comptées par le projet).`));
  }
  contenu.append(partie("Leçons à valider", "Aucune leçon à valider", (e.lecons || []).map((l) => carteLecon(ctx, l))));

  const retours = [];
  for (const t of e.taches || []) {
    for (const r of t.retours || []) {
      if (r.reponse && r.reponse.trim()) continue;
      const li = el("li", "");
      li.append(lienTache(ctx, t.id, tronquer(t.titre, MAX_TITRE)), el("div", "retour-texte", tronquer(r.texte, 200)));
      retours.push(li);
    }
  }
  contenu.append(partie("Retours sans réponse", "Aucun retour sans réponse", retours));

  const bloquees = [];
  for (const t of e.taches || []) {
    if (!t.bloquee || !t.bloquee.trim()) continue;
    const li = el("li", "");
    li.append(lienTache(ctx, t.id, tronquer(t.titre, MAX_TITRE)), el("div", "bloquee-raison", t.bloquee));
    bloquees.push(li);
  }
  contenu.append(partie("Tâches bloquées", "Aucune tâche bloquée", bloquees));
}

const ETATS_LECON = {"à valider": "à valider", "validée": "validée"};

// « 3 leçons (dont 1 à valider) » ; null si l'agent n'a aucune leçon.
export function resumeLecons(agent) {
  const l = agent?.lecons || [];
  if (!l.length) return null;
  const a = l.filter((x) => x.etat === "à valider").length;
  return `${l.length} leçon${l.length > 1 ? "s" : ""}` + (a ? ` (dont ${a} à valider)` : "");
}

export function contenuAgent(ctx, contenu, a, statuts) {
  const e = ctx.etat;
  contenu.append(el("h2", "", a.prenom || "?"));
  const service = a.chef ? "Chef d'atelier" : ((e.services || []).find((s) => s.id === a.service)?.nom || "—");
  contenu.append(ligne("Service", service));
  if (a.specialite) contenu.append(ligne("Spécialité", a.specialite));
  contenu.append(ligne("Modèle", a.modele || "?"));
  contenu.append(ligne("Lieu", a.lieu === "cloud" ? "cloud ☁" : "local"));
  contenu.append(ligne("Statut", statuts[a.statut] || a.statut || "—"));

  contenu.append(el("div", "carte-sous-titre", "Tâches en cours"));
  const taches = el("ul", "liste-partie");
  const siennes = (a.taches || []).map((id) => (e.taches || []).find((t) => t.id === id)).filter(Boolean);
  if (!siennes.length) taches.append(el("li", "vide", "Aucune tâche en cours"));
  for (const t of siennes) {
    const li = el("li", "");
    li.append(lienTache(ctx, t.id, tronquer(t.titre, MAX_TITRE)));
    taches.append(li);
  }
  contenu.append(taches);

  contenu.append(el("div", "carte-sous-titre", "Leçons"));
  const lecons = el("ul", "liste-partie");
  if (!(a.lecons || []).length) lecons.append(el("li", "vide", "Aucune leçon"));
  for (const l of a.lecons || []) {
    const li = el("li", "lecon");
    li.append(el("div", "lecon-texte", l.texte), el("div", "lecon-etat", ETATS_LECON[l.etat] || l.etat));
    lecons.append(li);
  }
  contenu.append(lecons);
}
