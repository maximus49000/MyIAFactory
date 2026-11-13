// Le bureau du Directeur (leçons à valider, retours sans réponse, tâches bloquées) et le panneau d'un agent.
// Chaque fonction remplit `contenu` ; un verdict est une demande au projet, jamais un changement direct.

import {el, ligne} from "./dom.js";
import {tronquer, dateFr, listeDisponible, phrasesDirectionV1} from "./texte.js";
import {prenomAgent} from "./detail.js";
import {demandeLecon, demandeToutes, demandeChallengeLecon} from "./actions.js";
import {contenuDecisionsV4} from "./decisions.js";
import {blocPoint, listeEchanges, TACHE_DU_CHEF} from "./point.js";
import {blocRetour} from "./detail.js";

const ETAGES = [["projet", "Projet"], ["genre", "Genre"], ["skill", "Skill"]];

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

function carteLecon(ctx, l, etages) {
  const e = ctx.etat;
  const c = el("li", "lecon");
  c.append(el("div", "lecon-texte", l.texte));
  const meta = el("div", "lecon-meta");
  meta.append(el("span", "", prenomAgent(e, l.agent) === "personne" ? l.agent : prenomAgent(e, l.agent)));
  const titre = l.tache ? titreTache(e, l.tache) : null;
  if (titre) { meta.append(document.createTextNode(" · "), lienTache(ctx, l.tache, titre)); }
  if (l.date) meta.append(document.createTextNode(" · " + dateFr(l.date)));
  c.append(meta);
  let etage = null;
  if ((e.version ?? 1) >= 4) {
    // Le texte général est celui qui est validé mot pour mot quand l'étage est Genre ou Skill.
    if (l.texte_general) c.append(el("div", "lecon-general", "Texte général (validé tel quel) : " + l.texte_general));
    const propose = l.etage_propose || "projet";
    c.append(el("div", "lecon-meta", "Étage proposé : " + (ETAGES.find(([id]) => id === propose)?.[1] || "Projet")));
    etage = el("select", "lecon-etage");
    etage.setAttribute("aria-label", "Étage de la leçon");
    for (const [id, libelle] of ETAGES) {
      const o = new Option(libelle, id);
      o.disabled = id !== "projet" && !l.texte_general;   // sans texte général, la leçon reste celle du projet
      etage.append(o);
    }
    etage.value = propose;
    if (etage.selectedOptions[0]?.disabled) etage.value = "projet";
    if (etages) etages.set(l.id, etage);   // « Tout valider » relit l'étage choisi au moment du clic
    c.append(etage);
  }
  if (l.challenge_tache) {   // la discussion ouverte sur cette leçon
    const lien = lienTache(ctx, l.challenge_tache, "Challengée : ouvrir la discussion");
    c.append(lien);
  }
  if (l.refus) c.append(el("div", "bloquee-raison", "Pas écrite dans la mémoire : " + l.refus));   // la raison du dernier refus
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
        const r = await ctx.barre.demander(demandeLecon(l, verdict, etage ? etage.value : undefined));
        if (!r.ok) valider.disabled = invalider.disabled = false;  // refus : on peut réessayer
      });
      rangee.append(bouton);
    }
    const [boutonChallenge, zoneChallenge] = (e.version ?? 1) >= 4 && !l.challenge_tache ? challenger(ctx, l) : [];
    if (boutonChallenge) rangee.append(boutonChallenge);
    c.append(rangee);
    if (zoneChallenge) c.append(zoneChallenge);
  }
  return c;
}

// « Challenger » : un champ pour dire ce qu'on conteste ; l'envoi ouvre une discussion dans une tâche.
function challenger(ctx, l) {
  const bouton = el("button", "bouton secondaire", "Challenger");
  bouton.type = "button";
  const zone = el("div", "lecon-challenge");
  zone.hidden = true;
  const texte = document.createElement("textarea");
  texte.rows = 3;
  texte.maxLength = 3500;
  texte.placeholder = "Ce que vous contestez dans cette leçon, et pourquoi…";
  const envoyer = el("button", "bouton petit", "Envoyer le challenge");
  envoyer.type = "button";
  envoyer.disabled = true;
  const note = el("p", "note", "");
  bouton.addEventListener("click", () => { zone.hidden = !zone.hidden; if (!zone.hidden) texte.focus(); });
  texte.addEventListener("input", () => { envoyer.disabled = !texte.value.trim(); });
  let enCours = false;
  envoyer.addEventListener("click", async () => {
    if (enCours || !texte.value.trim()) return;   // un double clic ne crée qu'une demande
    enCours = true;
    envoyer.disabled = true;
    const r = await ctx.barre.demander(demandeChallengeLecon(l, texte.value), envoyer);
    enCours = false;
    if (r.ok) { zone.replaceChildren(el("p", "note", "Challenge envoyé : une tâche s'ouvre pour en discuter.")); bouton.hidden = true; }
    else envoyer.disabled = !texte.value.trim();
  });
  zone.append(texte, envoyer, note);
  return [bouton, zone];
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
  if ((e.version ?? 1) >= 4) contenuDecisionsV4(ctx, contenu);
  const menus = new Map();   // id de leçon -> son menu d'étage
  const cartes = (e.lecons || []).map((l) => carteLecon(ctx, l, menus));
  const section = partie("Leçons à valider", "Aucune leçon à valider", cartes);
  const enAttente = (e.lecons || []).filter((l) => !l.verdict_demande);
  if (e.agir && enAttente.length >= 2) {
    // Tout valider ou tout invalider, chaque leçon avec l'étage montré dans son menu (même s'il a été changé).
    const rangee = el("div", "lecon-boutons tout");
    const tout = (libelle, classe, verdict, question) => {
      const b = el("button", classe, libelle);
      b.type = "button";
      b.addEventListener("click", async () => {
        if (question && !window.confirm(question)) return;
        const boutons = [...section.querySelectorAll(".lecon-boutons button")];
        boutons.forEach((x) => { x.disabled = true; });
        const etages = new Map([...menus].map(([id, menu]) => [id, menu.value]));
        const d = demandeToutes(e.lecons, verdict, etages);
        const r = d ? await ctx.barre.demander(d) : {ok: true};
        if (!r.ok) boutons.forEach((x) => { x.disabled = false; });   // refusé : on peut réessayer
      });
      rangee.append(b);
    };
    tout(`Tout valider (${enAttente.length})`, "bouton", "valider", null);
    tout(`Tout invalider (${enAttente.length})`, "bouton secondaire", "invalider",
         `Invalider les ${enAttente.length} leçons en attente ? Elles seront retirées.`);
    section.querySelector("h3").after(rangee);
  }
  contenu.append(section);

  // Validées, mais pas encore écrites dans la mémoire de la skill : le moteur les réessaie seul.
  const enEcriture = (e.lecons_en_attente || []).map((l) => {
    const li = el("li", "lecon");
    li.append(el("div", "lecon-texte", l.texte),
              el("div", "lecon-etat", "Validée, écriture en attente : le moteur réessaie seul"),
              el("div", "bloquee-raison", l.raison || "Raison inconnue"));
    return li;
  });
  if (enEcriture.length) contenu.append(partie("Leçons validées, écriture en attente", "", enEcriture));

  // Les réponses du Chef aux questions qu'on lui a posées (panneau du Chef) : lisibles ici aussi.
  const echanges = el("section", "partie");
  echanges.append(el("h3", "", "Échanges avec le Chef"), listeEchanges(e, dateFr));
  contenu.append(echanges);

  const retours = [];
  for (const t of e.taches || []) {
    if (t.id === TACHE_DU_CHEF) continue;       // montrés ci-dessus
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
  contenu.append(ligne("Plafond", a.modele || "?"));   // le modèle de la fiche : jamais dépassé
  contenu.append(ligne("Lieu", a.lieu === "cloud" ? "cloud ☁" : "local"));
  contenu.append(ligne("Statut", statuts[a.statut] || a.statut || "—"));
  if (a.chef) {
    contenu.append(blocPoint(e, ctx.ouvrirTache));      // « où en est-on ? » : la réponse immédiate
    if (e.agir) contenu.append(blocRetour(ctx, TACHE_DU_CHEF, {titre: "Demander au Chef",
                                                                 invite: "Une question au Chef (il répond d'après l'état du projet)…"}));
    contenu.append(el("div", "carte-sous-titre", "Échanges avec le Chef"), listeEchanges(e, dateFr));
  }

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
