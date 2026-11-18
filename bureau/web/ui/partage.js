// « Partager les connaissances » : un réglage de tout le bureau (pas d'un projet). Donnant-donnant : qui partage reçoit
// les leçons des autres bureaux ; qui refuse ne les reçoit pas. Le serveur (`/api/connaissances`) fait tout : clé,
// anonymisation, chiffrement, envoi ; la page ne montre que le réglage, la note, le surcoût et les leçons à relire.
// Tout texte venu du serveur passe par textContent.

import {el} from "./dom.js";

const ETAPES = {locale: "gardée(s) sur ce poste", a_anonymiser: "en cours d'anonymisation", a_relire: "à relire",
  a_envoyer: "prête(s) à partir", envoyee: "partagée(s)", ecartee: "non partagée(s)"};

export async function lireConnaissances(fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/connaissances");
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

// Une action ({action: "regler", actif?, niveau?} | {action: "valider", ids, textes?} | {action: "ecarter", ids}).
export async function demandeConnaissances(corps, fetchFn = fetch) {
  try {
    const r = await fetchFn("/api/connaissances", {
      method: "POST", headers: {"X-Bureau": "1", "Content-Type": "application/json"}, body: JSON.stringify(corps)});
    let d = null;
    try { d = await r.json(); } catch { /* corps illisible */ }
    if (r.ok) return {ok: true, vue: d, message: d?.message || "Enregistré."};
    return {ok: false, vue: d && d.actif !== undefined ? d : null,
      message: d?.message || d?.erreur || `Refusé : le serveur a répondu ${r.status}`};
  } catch {
    return {ok: false, vue: null, message: "Serveur du bureau injoignable."};
  }
}

function dollars(x) {
  const v = Number(x) || 0;
  return `${v.toFixed(v < 0.01 ? 4 : 2).replace(".", ",")} $`;
}

// Le surcoût de la relecture par Claude, à côté du niveau. Pur. Le niveau standard n'appelle pas Claude.
export function libelleSurcout(vue, niveau = vue?.niveau) {
  const s = vue?.surcout;
  if (!s || niveau === "standard") return "Aucun surcoût : pas d'appel à Claude.";
  const unite = s.estime ? `≈ ${dollars(s.par_lecon_usd)} par leçon (estimation)`
    : `${dollars(s.par_lecon_usd)} par leçon (moyenne mesurée)`;
  const total = s.relectures > 0
    ? ` · ${s.relectures} relecture${s.relectures > 1 ? "s" : ""} : ${dollars(s.cout_usd)} au total` : "";
  const avenir = s.a_venir > 0
    ? ` · ${s.a_venir} leçon${s.a_venir > 1 ? "s" : ""} à relire ≈ ${dollars(s.a_venir * s.par_lecon_usd)}` : "";
  return `Surcoût de la relecture par Claude (Haiku) : ${unite}${total}${avenir}.`;
}

// Le résumé de la file : « 3 partagée(s) · 1 à relire ». Pur.
export function resumeFile(vue) {
  const c = vue?.compte || {};
  return Object.keys(ETAPES).filter((k) => c[k] > 0).map((k) => `${c[k]} ${ETAPES[k]}`).join(" · ");
}

// La section, remplie dès que la vue arrive ; `vue` donnée par les tests, sinon lue au serveur.
export function sectionPartage(vue = null, fetchFn = fetch) {
  const section = el("section", "partie connaissances-partage");
  section.append(el("h3", "", "Partager les connaissances"));
  const corps = el("div", "");
  const message = el("p", "note", "");
  message.setAttribute("aria-live", "polite");
  section.append(corps, message);
  const remplir = (v) => {
    corps.replaceChildren();
    if (!v) { corps.append(el("p", "note", "Réglage du partage indisponible.")); return; }
    if (v.actif === null) {
      corps.append(el("p", "decisions", "Choisissez si ce bureau partage ses connaissances (réglage de tout le bureau)."));
    }
    corps.append(el("p", "note", v.note), el("p", "note", v.note_refus));
    const label = el("label", "lecons-auto-label");
    const c = document.createElement("input");
    c.type = "checkbox";
    c.checked = v.actif === true;
    label.append(c, el("span", "", " Partager les connaissances (tout le bureau)"));
    c.addEventListener("change", async () => {
      const voulu = c.checked;
      if (!voulu && !window.confirm("Désactiver le partage ? Rien ne sera plus envoyé, et vos agents ne recevront "
          + "plus les connaissances des autres bureaux.")) { c.checked = true; return; }
      c.disabled = true;
      message.textContent = voulu ? "Récupération de la clé…" : "";
      const r = await demandeConnaissances({action: "regler", actif: voulu}, fetchFn);
      message.textContent = r.message;
      remplir(r.vue || v);
    });
    corps.append(label);
    const niveau = el("label", "connaissances-niveau", "Niveau d'anonymisation : ");
    const menu = document.createElement("select");
    for (const n of v.niveaux || []) {
      const o = el("option", "", n.libelle);
      o.value = n.id;
      o.selected = n.id === v.niveau;
      menu.append(o);
    }
    const surcout = el("p", "note connaissances-surcout", libelleSurcout(v));
    menu.addEventListener("change", async () => {
      surcout.textContent = libelleSurcout(v, menu.value);
      const r = await demandeConnaissances({action: "regler", niveau: menu.value}, fetchFn);
      message.textContent = r.message;
      if (r.vue) remplir(r.vue);
    });
    niveau.append(menu);
    corps.append(niveau, surcout);
    const resume = resumeFile(v);
    if (resume) corps.append(el("p", "note", `Leçons : ${resume}.`));
    const items = (v.a_relire || []).map((x) => carteARelire(x, fetchFn, message, remplir));
    if (items.length) {
      corps.append(el("p", "decisions", `${items.length} leçon(s) à relire : voici le texte exact qui partira, `
        + "anonymisé puis chiffré. Corrigez-le si besoin, puis validez ou écartez."));
      const ul = el("ul", "lecons");
      ul.append(...items);
      corps.append(ul);
    }
  };
  if (vue) remplir(vue);
  else lireConnaissances(fetchFn).then(remplir);
  return section;
}

function carteARelire(x, fetchFn, message, remplir) {
  const li = el("li", "lecon");
  li.append(el("div", "lecon-meta", [x.etage === "genre" ? `genre ${x.genre}` : "skill", x.projet && `de ${x.projet}`,
    x.date].filter(Boolean).join(" · ")));
  li.append(el("div", "lecon-texte", x.titre_partage || ""));
  const zone = document.createElement("textarea");
  zone.className = "connaissances-texte";
  zone.value = x.texte_partage || "";
  zone.rows = 4;
  li.append(zone);
  if (x.raison) li.append(el("p", "note", x.raison));
  if (x.remplacements?.length) li.append(el("p", "note", `Effacé par le filtre : ${x.remplacements.join(", ")}.`));
  const rangee = el("div", "lecon-boutons");
  const bouton = (libelle, classe, corps) => {
    const b = el("button", classe, libelle);
    b.type = "button";
    b.addEventListener("click", async () => {
      rangee.querySelectorAll("button").forEach((y) => { y.disabled = true; });
      const r = await demandeConnaissances(corps(), fetchFn);
      message.textContent = r.message;
      if (r.vue) remplir(r.vue);
      else rangee.querySelectorAll("button").forEach((y) => { y.disabled = false; });
    });
    rangee.append(b);
  };
  bouton("Valider l'envoi", "bouton", () => ({action: "valider", ids: [x.id], textes: {[x.id]: zone.value}}));
  bouton("Ne pas partager", "bouton secondaire", () => ({action: "ecarter", ids: [x.id]}));
  li.append(rangee);
  return li;
}
