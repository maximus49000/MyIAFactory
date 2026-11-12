// « Nouveau projet… » en deux fenêtres : (1) les informations générales, validées ; (2) l'échange avec le chef, tour par
// tour, jusqu'à une proposition de workflow que l'utilisateur valide ou fait corriger. Rien n'est créé avant la
// validation finale : le serveur garde un brouillon. Un tour du chef dure 30 à 60 s : la page relit le brouillon tant
// qu'il est « en cours ». Les fonctions pures sont testées avec node ; tout texte passe par textContent.
// Utilisable au téléphone : une seule colonne, des boutons larges, des champs en 16 px (voir style.css).

import {el} from "./dom.js";
import {blocOutil} from "./outils.js";
import {verifierCreation, motsInterdits} from "./verifs.js";

export const DELAI_RELECTURE_MS = 2500;
const plein = (t) => typeof t === "string" && t.trim() !== "";

// --- Les corps des requêtes.

// Le message à dire avant d'envoyer la première fenêtre, ou null : dossier, nom, et la description (obligatoire).
export function verifierInfos(champs) {
  const message = verifierCreation(champs);
  if (message) return message;
  if (!plein(champs?.description)) return "La description est obligatoire : décrivez le projet, c'est la base de l'échange avec le chef.";
  return null;
}

export function corpsInfos(champs, id) {
  const corps = {parent: champs.parent.trim(), nom: champs.nom.trim(), mots_interdits: motsInterdits(champs.mots),
                 facturation: champs.facturation === true, github: champs.github === true,
                 description: champs.description.trim()};
  if (plein(id)) corps.id = id;
  return corps;
}

// Les réponses aux questions ouvertes (`valeurs` : id de question -> texte), ou null s'il en manque une.
export function corpsTour(id, questions, valeurs) {
  if (!Array.isArray(questions) || questions.length === 0) return null;
  const reponses = [];
  for (const q of questions) {
    const texte = String(valeurs?.[q.id] ?? "").trim();
    if (!texte) return null;
    reponses.push({question: q.id, texte});
  }
  return {id, reponses};
}

export function corpsCorrection(id, texte) {
  return plein(texte) ? {id, correction: texte.trim()} : null;
}

export function corpsProposerMaintenant(id) {
  return {id, proposer_maintenant: true};
}

// Un bouton de choix remplit le champ de sa question (sans modifier l'objet reçu).
export function choisir(valeurs, question, choix) {
  return {...valeurs, [question]: choix};
}

export function corpsValidation(id, {fable = [], installer = false, genreDescription} = {}) {
  const corps = {id, fable: [...fable], installer: installer === true};
  if (plein(genreDescription)) corps.genre_description = genreDescription.trim();
  return corps;
}

// --- Ce que la page montre.

const euros = (v) => v.toFixed(2).replace(".", ",");
const milliers = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

// « Coût de l'échange : 0,03 € » ; les tokens seuls si un prix manque ; « » quand rien n'a été dépensé.
export function texteCout(cout) {
  if (!cout) return "";
  if (typeof cout.euros === "number") {
    return "Coût de l'échange : " + (cout.euros > 0 && cout.euros < 0.005 ? "moins de 0,01 €" : euros(cout.euros) + " €");
  }
  if (cout.tokens > 0) return `Coût de l'échange : ${milliers(cout.tokens)} tokens (prix inconnu)`;
  return "";
}

export function texteAttente(secondes) {
  return secondes >= 1 ? `Le chef réfléchit… ${Math.floor(secondes)} s (30 à 60 s en général)` : "Le chef réfléchit…";
}

// Le brouillon tel que la fenêtre 2 l'affiche : les messages, les questions qui attendent une réponse, la proposition.
export function vueEchange(b) {
  const echange = Array.isArray(b?.echange) ? b.echange : [];
  const messages = [];
  let precedentes = [];
  for (const e of echange) {
    if (e.auteur === "chef") {
      messages.push({auteur: "chef", texte: e.message || ""});
      precedentes = Array.isArray(e.questions) ? e.questions : [];
    } else if (Array.isArray(e.reponses)) {
      const texte = e.reponses.map((r) => {
        const q = precedentes.find((x) => x.id === r.question);
        return `${q ? q.texte : r.question} — ${r.texte}`;
      }).join("\n");
      messages.push({auteur: "utilisateur", texte});
    } else if (e.correction) {
      messages.push({auteur: "utilisateur", texte: e.correction});
    }
  }
  const dernier = echange[echange.length - 1];
  const ouvertes = !b?.proposition && b?.tour !== "en_cours" && dernier?.auteur === "chef" && Array.isArray(dernier.questions)
    ? dernier.questions : [];
  return {messages, questions: ouvertes, proposition: b?.proposition || null, erreur: b?.erreur || null,
          cout: texteCout(b?.cout), enCours: b?.tour === "en_cours"};
}

function ligneOutil(x) {
  if (x.etat === "en_place") return `${x.outil}${x.version ? " " + x.version : ""} : déjà en place`;
  const details = [];
  if (x.version) details.push(`version lue : ${x.version}`);
  if (x.version_min) details.push(`version demandée : ${x.version_min}`);
  if (x.raison) details.push(x.raison);
  return `${x.outil} : à installer` + (details.length ? ` (${details.join(" ; ")})` : "");
}

// La proposition du chef en lignes de texte : genre, étapes (rôle, service, raison, validations), livrable, équipe,
// poste (versions lues et demandées), coût d'un élément.
export function lignesProposition(p) {
  if (!p) return [];
  const g = p.genre || {};
  const lignes = [g.nouveau ? `Genre : « ${g.id} » (nouveau : ${g.description || ""})` : `Genre : « ${g.id} » (déjà connu)`];
  lignes.push("Étapes, de la demande au livrable :");
  const services = p.services || [];
  (p.workflow?.flux || []).forEach((e, k) => {
    const qui = e.validation ? "Validation du Directeur : vous regardez et vous décidez"
      : `${e.role}, service ${services.find((s) => s.id === e.service)?.nom || e.service}`;
    const raison = p.raisons?.[e.id];
    lignes.push(`${k + 1}. ${e.nom} (${qui})` + (raison ? ` : ${raison}` : ""));
  });
  if (p.livrable) lignes.push(`Livrable : ${String(p.livrable).replace(/\.$/, "")}.`);
  if ((p.agents || []).length) {
    lignes.push("Équipe à recruter :");
    for (const a of p.agents) lignes.push(`- ${a.prenom || a.cle}, ${a.role}, ${a.modele}` + (a.justification ? ` : ${a.justification}` : ""));
  }
  if ((p.environnement || []).length) {
    lignes.push("Poste de travail :");
    for (const x of p.environnement) lignes.push("- " + ligneOutil(x));
  }
  const c = p.cout;
  if (c && Array.isArray(c.tokens)) {
    let t = `Coût estimé d'un élément passé par ce workflow : ${milliers(c.tokens[0])} à ${milliers(c.tokens[1])} tokens`;
    t += Array.isArray(c.euros) ? `, soit ${euros(c.euros[0])} à ${euros(c.euros[1])} €.` : " (prix inconnu).";
    lignes.push(t);
  }
  return lignes;
}

// Les agents pour lesquels on peut cocher Fable : seulement ceux dont le chef l'a suggéré.
export function agentsFable(p) {
  return (p?.agents || []).filter((a) => a.fable_suggere === true);
}

// Les outils qui manquent et qu'un agent peut installer seul (les seuls que la case « installer » lui confie).
export function outilsAutonomes(p) {
  return (p?.environnement || []).filter((x) => x.etat !== "en_place" && x.autonome === true);
}

// Les outils qui manquent, tous (l'utilisateur les installe à la main avec le lien et le mode opératoire).
export function outilsManquants(p) {
  return (p?.environnement || []).filter((x) => x && x.etat !== "en_place");
}

// « Installer en autonomie » n'a de sens que si un outil autonome manque et qu'un agent peut l'installer.
export function installationPossible(p) {
  return Boolean(p?.installateur) && outilsAutonomes(p).length > 0;
}

// La fenêtre d'après une réponse à « Valider et créer » : un refus qui touche aux informations ramène à la fenêtre 1
// avec son message, l'échange gardé ; tout autre refus reste sur place ; un succès termine.
export function suiteValidation(etat, reponse) {
  if (reponse?.ok) return {...etat, ecran: "fini", message: reponse.message || ""};
  if (reponse?.retour === "infos") return {...etat, ecran: "infos", message: reponse.message || ""};
  return {...etat, message: reponse?.message || "La création a échoué."};
}

export function lignesBrouillons(liste) {
  return (Array.isArray(liste) ? liste : []).map((b) => {
    const morceaux = [b.etat === "proposition" ? "proposition prête" : "questions du chef"];
    if (b.tours > 0) morceaux.push(b.tours === 1 ? "1 tour" : `${b.tours} tours`);
    if (b.tour === "en_cours") morceaux.push("le chef réfléchit (en cours)");
    if (b.tour === "interrompu") morceaux.push("tour interrompu");
    if (typeof b.euros === "number") morceaux.push(euros(b.euros) + " €");
    return {id: b.id, titre: plein(b.nom) ? b.nom : "Projet sans nom", detail: morceaux.join(" · ")};
  });
}

export function texteAbandonnes(abandonnes) {
  return typeof abandonnes?.euros === "number" && abandonnes.euros > 0 ? `Échanges abandonnés : ${euros(abandonnes.euros)} €` : "";
}

// Depuis une décision « cette demande n'est pas du genre du projet », le formulaire actuel (projet vide) reste.
export function utiliseLeFormulaireActuel(options) {
  return Boolean(options?.decision);
}

// --- Le serveur.

export async function envoyer(chemin, corps, fetchFn = fetch) {
  try {
    const r = await fetchFn(chemin, {method: "POST", headers: {"X-Bureau": "1", "Content-Type": "application/json"},
                                    body: JSON.stringify(corps)});
    let j = null;
    try { j = await r.json(); } catch { /* corps illisible */ }
    if (r.ok) return {ok: true, ...(j || {})};
    return {ok: false, status: r.status, message: j?.erreur || `Le serveur a répondu ${r.status}.`, retour: j?.retour};
  } catch {
    return {ok: false, message: "Le serveur du bureau est injoignable."};
  }
}

export async function lire(chemin, fetchFn = fetch) {
  try {
    const r = await fetchFn(chemin);
    let j = null;
    try { j = await r.json(); } catch { /* corps illisible */ }
    if (r.ok) return {ok: true, ...(j || {})};
    return {ok: false, status: r.status, message: j?.erreur || `Le serveur a répondu ${r.status}.`};
  } catch {
    return {ok: false, message: "Le serveur du bureau est injoignable."};
  }
}

// --- Les fenêtres.

function champ(libelle, controle, aide) {
  const l = el("label", "creation-champ");
  l.append(el("span", "creation-libelle", libelle), controle);
  if (aide) l.append(el("span", "lecon-meta", aide));
  return l;
}

function saisie(type, valeur, extra = {}) {
  const i = document.createElement("input");
  i.type = type;
  if (type === "checkbox") i.checked = valeur === true; else i.value = valeur || "";
  for (const [k, v] of Object.entries(extra)) i[k] = v;
  return i;
}

function bouton(texte, secondaire, type = "button") {
  const b = el("button", "bouton" + (secondaire ? " secondaire" : ""), texte);
  b.type = type;
  return b;
}

function zone(placeholder, rows, valeur, max) {
  const t = document.createElement("textarea");
  t.rows = rows;
  t.maxLength = max;
  t.placeholder = placeholder;
  t.value = valeur || "";
  return t;
}

// Ouvre « Nouveau projet… ». `options` : {projets, parents, id (projet affiché)}. `deps` : {apresCreation, aLire}
// (donnés par creation.js, qui sait basculer sur le nouveau projet). Rend une fonction qui ferme la fenêtre.
export function ouvrirDefinition(options = {}, deps = {}) {
  const {projets = [], parents = [], id = null} = options;
  const origine = projets.find((p) => p?.id === id) || {};
  const fond = el("div", "creation-fond");
  const fenetre = el("div", "creation creation-chef");
  fenetre.setAttribute("role", "dialog");
  fenetre.setAttribute("aria-label", "Nouveau projet");
  fond.append(fenetre);
  let etat = {ecran: "liste", brouillon: null, message: ""};
  let abandonnes = null;
  let minuteur = null;
  let ferme = false;
  let attenteDepuis = null;
  let valeurs = {};         // les réponses tapées, gardées d'un affichage à l'autre
  let correction = "";
  let descriptionGenre = null;
  let fable = new Set();
  let installer = false;
  const fermer = () => { ferme = true; clearTimeout(minuteur); fond.remove(); };

  const dire = (message) => el("p", "saisie-erreur", message || "");
  const bandeau = (message) => { const p = dire(message); p.setAttribute("role", "alert"); return p; };

  function montrer(...enfants) { fenetre.replaceChildren(...enfants); }

  // -- Les brouillons à reprendre.
  async function ecranListe() {
    const r = await lire("/api/creations");
    if (ferme) return;
    if (!r.ok) { etat = {...etat, ecran: "infos", message: r.message}; return afficher(); }
    abandonnes = r.abandonnes;
    if (!r.brouillons?.length) { etat = {ecran: "infos", brouillon: null, message: ""}; return afficher(); }
    const corps = [el("h2", "", "Nouveau projet"), el("p", "lecon-meta", "Des projets sont en cours de définition avec le chef. Reprenez-en un, ou commencez-en un nouveau.")];
    for (const l of lignesBrouillons(r.brouillons)) {
      const carte = el("div", "creation-brouillon");
      carte.append(el("strong", "", l.titre), el("span", "lecon-meta", l.detail));
      const rangee = el("div", "lecon-boutons");
      const reprendre = bouton("Reprendre");
      reprendre.addEventListener("click", () => reprendreBrouillon(l.id));
      const supprimer = bouton("Supprimer", true);
      let sur = false;
      supprimer.addEventListener("click", async () => {
        if (!sur) { sur = true; supprimer.textContent = "Confirmer la suppression"; return; }
        supprimer.disabled = true;
        const s = await envoyer("/api/creations/supprimer", {id: l.id});
        if (!s.ok) { carte.append(bandeau(s.message)); supprimer.disabled = false; return; }
        ecranListe();
      });
      rangee.append(reprendre, supprimer);
      carte.append(rangee);
      corps.push(carte);
    }
    const total = texteAbandonnes(r.abandonnes);
    if (total) corps.push(el("p", "lecon-meta", total));
    const rangee = el("div", "lecon-boutons");
    const nouveau = bouton("Nouveau projet");
    nouveau.addEventListener("click", () => { etat = {ecran: "infos", brouillon: null, message: ""}; afficher(); });
    const annuler = bouton("Annuler", true);
    annuler.addEventListener("click", fermer);
    rangee.append(nouveau, annuler);
    corps.push(rangee);
    montrer(...corps);
  }

  async function reprendreBrouillon(idBrouillon) {
    const r = await lire(`/api/creations?id=${encodeURIComponent(idBrouillon)}`);
    if (ferme) return;
    if (!r.ok) { fenetre.append(bandeau(r.message)); return; }
    etat = {ecran: r.brouillon.echange.length || r.brouillon.proposition ? "echange" : "infos", brouillon: r.brouillon, message: ""};
    afficher();
  }

  // -- La première fenêtre.
  function ecranInfos() {
    const b = etat.brouillon;
    const infos = b?.infos || {};
    const form = el("form");
    const parent = saisie("text", infos.parent ?? parents[0] ?? "", {placeholder: "Dossier où ranger le projet", maxLength: 500});
    parent.setAttribute("list", "creation-parents");
    parent.setAttribute("autocomplete", "off");
    const suggestions = document.createElement("datalist");
    suggestions.id = "creation-parents";
    for (const p of parents) suggestions.append(new Option(p, p));
    const nom = saisie("text", infos.nom || "", {placeholder: "Nom du projet (devient le nom du dossier)", maxLength: 100});
    const mots = saisie("text", (infos.mots_interdits || origine.mots_interdits || []).join(", "), {placeholder: "Séparés par des virgules"});
    const facturation = saisie("checkbox", b ? infos.facturation === true : origine.facturation === true);
    facturation.disabled = Boolean(b?.echange?.length);
    const github = saisie("checkbox", infos.github === true);
    const description = zone("Ce que fera ce projet : ce que vous voulez obtenir, pour qui, ce qui compte", 5, infos.description, 3900);
    const erreur = bandeau(etat.message);
    const valider = bouton("Valider", false, "submit");
    const annuler = bouton(b ? "Retour" : "Annuler", true);
    annuler.addEventListener("click", () => { if (b && (b.echange.length || b.proposition)) { etat = {...etat, ecran: "echange", message: ""}; afficher(); } else fermer(); });
    const cocheFacturation = el("label", "creation-case");
    cocheFacturation.append(facturation, el("span", "", " Suivre les coûts de ce projet (un objectif de facturation)"));
    const cocheGithub = el("label", "creation-case");
    cocheGithub.append(github, el("span", "", " Créer aussi un dépôt GitHub privé"));
    const rangee = el("div", "lecon-boutons");
    rangee.append(valider, annuler);
    form.append(el("h2", "", "Nouveau projet — 1. Les informations"), champ("Dossier parent", parent), suggestions,
                champ("Nom du projet", nom), champ("Mots interdits (le nom du projet est ajouté)", mots),
                champ("Description du projet", description, "Obligatoire : le chef s'en sert pour vous poser les bonnes questions."),
                cocheFacturation, cocheGithub, erreur, rangee);
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const champs = {parent: parent.value, nom: nom.value, mots: mots.value, facturation: facturation.checked,
                      github: github.checked, description: description.value};
      const message = verifierInfos(champs);
      if (message) { erreur.textContent = message; return; }
      erreur.textContent = "";
      valider.disabled = true;
      const r = await envoyer("/api/creations/infos", corpsInfos(champs, b?.id));
      if (ferme) return;
      if (!r.ok) { erreur.textContent = r.message; valider.disabled = false; return; }
      etat = {ecran: "echange", brouillon: r.brouillon, message: ""};
      afficher();
      if (!r.brouillon.echange.length && r.brouillon.tour === "libre") envoyerTour({id: r.brouillon.id});
    });
    montrer(form);
    nom.focus();
  }

  // -- La seconde fenêtre : l'échange.
  async function envoyerTour(corps) {
    const r = await envoyer("/api/creations/tour", corps);
    if (ferme) return;
    if (r.ok) etat = {...etat, brouillon: r.brouillon, message: ""};
    else etat = {...etat, message: r.message};
    afficher();
  }

  function surveiller() {
    clearTimeout(minuteur);
    if (ferme || etat.ecran !== "echange" || etat.brouillon?.tour !== "en_cours") { attenteDepuis = null; return; }
    if (attenteDepuis === null) attenteDepuis = Date.now();
    minuteur = setTimeout(async () => {
      const r = await lire(`/api/creations?id=${encodeURIComponent(etat.brouillon.id)}`);
      if (ferme) return;
      if (r.ok) etat = {...etat, brouillon: r.brouillon, message: ""};
      else etat = {...etat, message: r.message};
      afficher();
    }, DELAI_RELECTURE_MS);
  }

  function ecranEchange() {
    const b = etat.brouillon;
    const v = vueEchange(b);
    const corps = [el("h2", "", "Nouveau projet — 2. Le chef"), el("p", "lecon-meta", `${b.infos.nom} · tour ${b.tours} sur ${b.tours_max}`)];
    const flux = el("div", "creation-echange");
    for (const m of v.messages) flux.append(el("div", "creation-message " + (m.auteur === "chef" ? "chef" : "utilisateur"), m.texte));
    corps.push(flux);
    const cout = el("p", "lecon-meta creation-cout", v.cout);
    corps.push(cout);
    if (v.enCours) {
      const attente = el("p", "creation-attente", texteAttente(attenteDepuis ? (Date.now() - attenteDepuis) / 1000 : 0));
      attente.setAttribute("role", "status");
      corps.push(attente);
    }
    if (etat.message) corps.push(bandeau(etat.message));
    if (v.erreur) {
      corps.push(bandeau(v.erreur));
      const renvoyer = bouton("Renvoyer");
      renvoyer.addEventListener("click", () => { renvoyer.disabled = true; envoyerTour({id: b.id}); });
      corps.push(renvoyer);
    }
    const bas = el("div", "lecon-boutons");
    if (v.questions.length) corps.push(formulaireQuestions(b, v.questions));
    else if (v.proposition && !v.enCours) corps.push(...blocProposition(b, v.proposition));
    if (!v.enCours) {
      const infos = bouton("Modifier les informations", true);
      infos.addEventListener("click", () => { etat = {...etat, ecran: "infos", message: ""}; afficher(); });
      bas.append(infos);
    }
    const quitter = bouton("Fermer (le brouillon est gardé)", true);
    quitter.addEventListener("click", fermer);
    bas.append(quitter);
    corps.push(bas);
    montrer(...corps);
    surveiller();
  }

  function formulaireQuestions(b, questions) {
    const form = el("form", "creation-questions");
    const erreur = dire("");
    erreur.setAttribute("role", "alert");
    const champs = new Map();
    for (const q of questions) {
      const bloc = el("div", "creation-question");
      const t = zone("Votre réponse", 2, valeurs[q.id], 1900);
      t.addEventListener("input", () => { valeurs[q.id] = t.value; });
      champs.set(q.id, t);
      bloc.append(el("div", "creation-libelle", q.texte));
      if ((q.choix || []).length) {
        const choix = el("div", "creation-choix");
        for (const c of q.choix) {
          const bt = bouton(c, true);
          bt.addEventListener("click", () => { valeurs = choisir(valeurs, q.id, c); t.value = c; });
          choix.append(bt);
        }
        bloc.append(choix);
      }
      bloc.append(t);
      form.append(bloc);
    }
    const envoi = bouton("Envoyer mes réponses", false, "submit");
    const maintenant = bouton("Proposez maintenant", true);
    maintenant.addEventListener("click", () => { maintenant.disabled = envoi.disabled = true; envoyerTour(corpsProposerMaintenant(b.id)); });
    const rangee = el("div", "lecon-boutons");
    rangee.append(envoi, maintenant);
    form.append(erreur, rangee);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const corps = corpsTour(b.id, questions, valeurs);
      if (!corps) { erreur.textContent = "Répondez à chaque question (ou demandez au chef de proposer maintenant)."; return; }
      valeurs = {};
      envoi.disabled = true;
      envoyerTour(corps);
    });
    return form;
  }

  function blocProposition(b, p) {
    const sortie = [el("h3", "creation-sous-titre", "La proposition du chef")];
    sortie.push(el("p", "creation-message chef", p.message || ""));
    sortie.push(el("pre", "creation-proposition", lignesProposition(p).join("\n")));
    const manquants = outilsManquants(p);
    if (manquants.length) {
      const bloc = el("div", "creation-outils");
      bloc.append(el("strong", "", "Outils à installer sur ce poste"));
      for (const x of manquants) bloc.append(blocOutil(x));
      sortie.push(bloc);
    }
    if (p.genre?.nouveau) {
      if (descriptionGenre === null) descriptionGenre = p.genre.description || "";
      const t = zone("Description du genre", 3, descriptionGenre, 900);
      t.addEventListener("input", () => { descriptionGenre = t.value; });
      sortie.push(champ(`Description du nouveau genre « ${p.genre.id} »`, t, "Modifiable : elle sert à reconnaître ce genre dans les prochaines demandes."));
    }
    for (const a of agentsFable(p)) {
      const c = saisie("checkbox", fable.has(a.cle));
      c.addEventListener("change", () => { if (c.checked) fable.add(a.cle); else fable.delete(a.cle); });
      const l = el("label", "creation-case");
      l.append(c, el("span", "", ` Donner Fable à ${a.prenom || a.cle} (${a.role}) : le chef le suggère, c'est plus cher`));
      sortie.push(l);
    }
    if (installationPossible(p)) {
      const c = saisie("checkbox", installer);
      c.addEventListener("change", () => { installer = c.checked; });
      const l = el("label", "creation-case");
      l.append(c, el("span", "", ` Installer en autonomie : ${outilsAutonomes(p).map((x) => x.outil).join(", ")} (un agent s'en charge au premier passage du moteur ; rien d'autre n'est installé)`));
      sortie.push(l);
    }
    const erreur = dire("");
    erreur.setAttribute("role", "alert");
    const creer = bouton("Valider et créer le projet");
    creer.addEventListener("click", async () => {
      creer.disabled = true;
      const r = await envoyer("/api/creations/valider", corpsValidation(b.id, {fable: [...fable], installer, genreDescription: descriptionGenre}));
      if (ferme) return;
      etat = suiteValidation(etat, r);
      if (!r.ok) { creer.disabled = false; }
      if (etat.ecran === "fini") etat.reponse = r;
      afficher();
    });
    const aCorriger = zone("Ce qu'il faut changer (une étape à ajouter, un rôle, une validation…)", 2, correction, 1900);
    aCorriger.addEventListener("input", () => { correction = aCorriger.value; });
    const corriger = bouton("Demander une correction", true);
    corriger.addEventListener("click", () => {
      const corps = corpsCorrection(b.id, aCorriger.value);
      if (!corps) { erreur.textContent = "Dites au chef ce qu'il faut corriger."; return; }
      correction = "";
      corriger.disabled = true;
      envoyerTour(corps);
    });
    const rangee = el("div", "lecon-boutons");
    rangee.append(creer);
    sortie.push(erreur, rangee, champ("Ou demandez une correction", aCorriger), corriger);
    return sortie;
  }

  // -- La fin.
  function ecranFini() {
    const r = etat.reponse || {};
    const suite = bouton("Ouvrir le nouveau projet");
    suite.addEventListener("click", () => deps.apresCreation?.(r));
    montrer(el("h2", "", "Projet créé"), el("p", "", etat.message), suite);
  }

  function afficher() {
    if (ferme) return;
    if (etat.ecran === "infos") return ecranInfos();
    if (etat.ecran === "echange") return ecranEchange();
    if (etat.ecran === "fini") return ecranFini();
    return ecranListe();
  }

  fond.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fermer(); });
  document.body.append(fond);
  montrer(el("p", "lecon-meta", "Chargement…"));
  ecranListe();
  return fermer;
}
