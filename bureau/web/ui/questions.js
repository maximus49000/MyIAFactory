// Le panneau « Questions » : poser une question sur le projet, lire les réponses (d'après les documents, puis d'après
// le code), relancer un fil, ouvrir une correction ou une fonctionnalité préremplie. Tout geste est une demande au
// projet (`ctx.barre.demander`) ; tout texte venu du relevé passe par textContent ou le rendu markdown.
// Les fonctions pures sont testées avec node.

import {el} from "./dom.js";
import {rendreTexte} from "./markdown.js";
import {saisie, MAX_TEXTE} from "./fonctionnalite.js";

export const NIVEAUX = {documents: "D'après les documents", code: "D'après le code"};
export const INFO_LECTURE = "Un agent lit le code du projet (lecture seule) puis répond. Son coût est compté à la facturation, " +
  "ligne « dont questions ».";

// La demande d'une question : `fil` pour un suivi, `fonctionnalite` pour « À propos de ».
export function demandeQuestion(texte, {fil = null, fonctionnalite = null} = {}) {
  const d = {type: "question", texte};
  if (fil) d.fil = fil;
  else if (fonctionnalite) d.fonctionnalite = fonctionnalite;
  return d;
}

export const demandeApprofondir = (fil) => ({type: "question_approfondir", fil});

// Les fils du plus récent au plus ancien (le relevé les donne du plus ancien au plus récent).
export function filsAffiches(etat) {
  return Array.isArray(etat?.questions) ? [...etat.questions].reverse() : [];
}

// Ce que le fil montre sous sa dernière réponse : {attente, approfondir, suggestion, suivi}.
export function gestesDuFil(q) {
  const messages = Array.isArray(q?.messages) ? q.messages : [];
  const dernier = messages[messages.length - 1];
  const attente = q?.etat === "en_lecture" ? "Lecture du code en cours…"
    : q?.etat === "en_cours" ? "Reçu, en cours de traitement…" : null;
  const repondue = q?.etat === "repondue" && dernier?.auteur === "factory";
  const s = repondue ? dernier.suggestion : null;
  return {attente, approfondir: repondue && dernier.niveau === "documents",
          suggestion: s && (s.nature === "correction" || s.nature === "fonctionnalite") && typeof s.texte === "string" ? s : null,
          suivi: repondue};
}

export function contenuQuestions(ctx, contenu) {
  const e = ctx.etat;
  contenu.append(el("h2", "", "Questions sur le projet"));
  contenu.append(el("p", "note", "Posez une question sur le projet et son fonctionnement : la réponse vient d'abord des documents, " +
    "puis du code si besoin."));
  if (e.agir === true) contenu.append(blocSaisie(ctx, null));
  const fils = filsAffiches(e);
  if (!fils.length) contenu.append(el("p", "note", "Aucune question pour l'instant."));
  for (const q of fils) contenu.append(blocFil(ctx, q));
}

// Le champ de saisie : une question neuve (avec « À propos de ») ou le suivi d'un fil.
function blocSaisie(ctx, q) {
  const bloc = el("div", "question-saisie");
  const cle = "q:" + (q ? q.id : "nouvelle");
  let apropos = null;
  if (!q) {
    apropos = el("select", "question-apropos");
    apropos.setAttribute("aria-label", "À propos de");
    apropos.append(new Option("À propos de : tout le projet", ""));
    for (const f of ctx.etat.fonctionnalites || []) apropos.append(new Option(f.nom, f.id));
    apropos.value = ctx.questions?.apropos || "";
    apropos.addEventListener("change", () => { if (ctx.questions) ctx.questions.apropos = apropos.value; });
    bloc.append(apropos);
  }
  const s = saisie(ctx, cle, async (texte, fichiers, bouton) => {
    const r = await ctx.barre.demander(demandeQuestion(texte, {fil: q?.id, fonctionnalite: apropos?.value}), bouton);
    return r;
  }, {libelle: "Envoyer", joindre: false,
      invite: q ? "Question de suivi…" : "Votre question sur le projet…"});
  bloc.append(s.bloc);
  return bloc;
}

function blocFil(ctx, q) {
  const bloc = el("section", "question-fil");
  for (const m of q.messages || []) {
    const p = el("div", "question-message " + (m.auteur === "factory" ? "factory" : "utilisateur"));
    if (m.auteur === "factory") {
      if (NIVEAUX[m.niveau]) p.append(el("span", "question-niveau", NIVEAUX[m.niveau]));
      p.append(rendreTexte("question-texte", m.texte));
      if (Array.isArray(m.fichiers_lus) && m.fichiers_lus.length) {
        p.append(el("p", "note", "Fichiers lus : " + m.fichiers_lus.join(", ")));
      }
    } else {
      p.textContent = m.texte;
    }
    bloc.append(p);
  }
  const g = gestesDuFil(q);
  if (g.attente) {
    const p = el("p", "ecrit actif", g.attente);
    p.setAttribute("aria-live", "polite");
    bloc.append(p);
  }
  if (g.suivi && ctx.etat.agir === true) {
    const actions = el("div", "question-actions");
    const geste = (libelle, classe, fn, titre) => {
      const b = el("button", classe, libelle);
      b.type = "button";
      if (titre) b.title = titre;
      b.addEventListener("click", () => fn(b));
      actions.append(b);
    };
    if (g.approfondir) geste("Chercher dans le code", "bouton", (b) => ctx.barre.demander(demandeApprofondir(q.id), b), INFO_LECTURE);
    if (g.suggestion) {
      const s = g.suggestion;
      geste(s.nature === "correction" ? "Ouvrir une correction" : "Ouvrir une fonctionnalité", "bouton",
            () => ctx.ouvrirNouvelle(s.nature, s.texte.slice(0, MAX_TEXTE), s.concerne || null));
    }
    const suite = el("div", "question-suite");
    suite.hidden = !ctx.brouillons.get("q:" + q.id)?.texte;     // un brouillon en cours reste visible au redessin
    geste("Poser une question de suivi", "bouton secondaire", () => { suite.hidden = !suite.hidden; });
    suite.append(blocSaisie(ctx, q));
    bloc.append(actions, suite);
  }
  return bloc;
}
