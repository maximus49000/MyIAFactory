// Le premier lancement : une question discrète, puis (« Voir ») une fenêtre factice de l'application Claude, sombre,
// dont les lettres se décrochent et tombent avant que la fenêtre ne tombe à son tour et laisse le bureau. Chargé à
// la demande, seulement quand le serveur dit que le lancement n'a jamais été proposé. Tout est retiré à la fin.
// Le contenu est inventé (aucune vraie conversation) et rien n'est cliquable dans la fenêtre.

import {DUREES, phase, departs, tomber, signeDeCode, texteTape} from "../logique/lancement.js";

const REPONSE = "Je l'ouvre. Ton monde va se construire sous tes yeux.";
const FONDU_MS = 300;

// Icônes en traits simples (24 × 24).
const TRAITS = {
  menu: "M4 6h16M4 12h16M4 18h16", panneau: "M4 5h16v14H4zM9 5v14", gauche: "M15 6l-6 6 6 6", droite: "M9 6l6 6-6 6",
  plus: "M12 5v14M5 12h14", loupe: "M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14M16 16l4 4", dossier: "M4 6h6l2 2h8v10H4z",
  pinceau: "M4 20l4-1 10-10-3-3L5 16zM14 7l3 3", points: "M5 12h.01M12 12h.01M19 12h.01", bas: "M6 9l6 6 6-6",
  liste: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01", terminal: "M5 7l5 5-5 5M12 17h7",
  globe: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18", micro: "M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3M6 11a6 6 0 0 0 12 0M12 17v3",
};
const icone = (nom) => `<svg class="lancement-icone" viewBox="0 0 24 24" aria-hidden="true"><path d="${TRAITS[nom]}"/></svg>`;

const GROUPES = [
  ["Mon atelier", [["Installer MyIAFactory", "actif"], ["Idées de jeu de cartes", "point"], ["Préparer la démo du vendredi", "point"],
                   ["Relire le site vitrine", "point"]]],
  ["Brouillons", [["Notes du lundi", ""], ["Tests de la page d'accueil", ""], ["Plan du prochain sprint", ""]]],
];

function htmlFenetre() {
  const menu = [["plus", "Créer"], ["loupe", "Rechercher"], ["dossier", "Artéfacts"], ["pinceau", "Personnalisation"], ["points", "Plus"]]
    .map(([i, t]) => `<div class="lancement-entree">${icone(i)}<span>${t}</span></div>`).join("");
  const groupes = GROUPES.map(([titre, lignes]) => `<div class="lancement-groupe"><span>${titre}</span>${icone("bas")}</div>` +
    lignes.map(([t, genre]) => `<div class="lancement-titre ${genre === "actif" ? "lancement-actif" : ""}"><span>${t}</span>` +
      `${genre === "point" ? '<i class="lancement-pastille"></i>' : ""}</div>`).join("")).join("");
  return `
    <div class="lancement-barre">
      <div class="lancement-outils">${icone("menu")}${icone("panneau")}${icone("gauche")}${icone("droite")}</div>
      <div class="lancement-nom">Installer MyIAFactory sur mon projet ${icone("bas")}</div>
      <div class="lancement-outils lancement-outils-droite">${icone("liste")}${icone("terminal")}${icone("globe")}${icone("dossier")}</div>
    </div>
    <nav class="lancement-cote">${menu}<div class="lancement-separe"></div>${groupes}</nav>
    <section class="lancement-discussion">
      <div class="lancement-fil">
        <div class="lancement-bulle">Installe MyIAFactory sur mon projet et prépare l'équipe.</div>
        <div class="lancement-reponse">
          <p><b>C'est fait.</b> Voici ce qui est en place :</p>
          <p><b>L'équipe :</b> un directeur, trois agents et un kanban pour suivre chaque tâche.</p>
          <p><b>Le bureau :</b> une vue en 3D où l'on voit chacun travailler, sur l'ordinateur comme sur le téléphone.</p>
          <p><b>Les coûts :</b> suivis au jour le jour, avec un plafond que tu choisis.</p>
        </div>
        <div class="lancement-bulle">Ouvre le bureau.</div>
        <div class="lancement-reflexion">Réflexion</div>
        <div class="lancement-reponse lancement-tape"></div>
      </div>
      <div class="lancement-saisie">${icone("plus")}<span>Répondre…</span>${icone("micro")}</div>
    </section>
    <aside class="lancement-droite">
      <div><span>Environnement ›</span><span>MyIAFactory</span></div>
      <div><span>Contexte ›</span><span>9 % <i class="lancement-jauge"></i></span></div>
      <div><span>Connecteurs ›</span><span>Connectés : 1</span></div>
    </aside>`;
}

// Le rectangle visible d'un élément : l'intersection des ancêtres qui coupent ce qui dépasse, jusqu'à `racine`.
function zoneVisible(el, racine) {
  let z = {l: 0, t: 0, r: window.innerWidth, b: window.innerHeight};
  for (let e = el; e && e !== racine.parentElement; e = e.parentElement) {
    if (getComputedStyle(e).overflow === "visible") continue;
    const b = e.getBoundingClientRect();
    z = {l: Math.max(z.l, b.left), t: Math.max(z.t, b.top), r: Math.min(z.r, b.right), b: Math.min(z.b, b.bottom)};
  }
  return z;
}

// Chaque caractère visible de la fenêtre, avec sa place, sa police et sa couleur : ni le texte coupé par un
// débordement, ni celui que la zone de saisie recouvre.
function releverLettres(racine) {
  const lettres = [];
  const marche = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT);
  const saisie = racine.querySelector(".lancement-saisie");
  const dessus = saisie ? saisie.getBoundingClientRect() : null;
  for (let n = marche.nextNode(); n; n = marche.nextNode()) {
    const cs = getComputedStyle(n.parentElement);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    const z = zoneVisible(n.parentElement, racine);
    const sousLaSaisie = dessus && !saisie.contains(n);
    const police = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    for (let i = 0; i < n.length; i++) {
      const c = n.data[i];
      if (!c.trim()) continue;
      const r = document.createRange();
      r.setStart(n, i);
      r.setEnd(n, i + 1);
      const b = r.getBoundingClientRect();
      const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
      if (!b.width || cx < z.l || cx > z.r || cy < z.t || cy > z.b) continue;
      if (sousLaSaisie && cx >= dessus.left && cx <= dessus.right && cy >= dessus.top && cy <= dessus.bottom) continue;
      lettres.push({c, x: b.left, y: b.top, v: 0, police, couleur: cs.color});
    }
  }
  lettres.sort((a, b) => (a.police < b.police ? -1 : a.police > b.police ? 1 : 0));   // moins de changements de police
  return lettres;
}

export function lancer({pret, marquer}) {
  const voile = document.createElement("div");
  voile.className = "lancement";
  voile.setAttribute("role", "dialog");
  voile.setAttribute("aria-modal", "true");
  voile.setAttribute("aria-label", "Premier lancement");
  voile.innerHTML = `<div class="lancement-question"><button type="button" data-choix="voir">Voir le lancement</button>` +
    `<span aria-hidden="true">·</span><button type="button" data-choix="masquer">Masquer</button></div>`;
  document.body.append(voile);
  // Le bureau, dessous, ne reçoit ni clic ni clavier tant que le voile est là.
  const dessous = [...document.body.children].filter((e) => e !== voile && e.tagName !== "SCRIPT" && !e.inert);
  dessous.forEach((e) => { e.inert = true; });
  voile.querySelector("button").focus();

  let image = 0, ferme = false;
  const enleverEcoutes = [];
  const ecouter = (cible, evt, f, capture = false) => {
    cible.addEventListener(evt, f, capture);
    enleverEcoutes.push(() => cible.removeEventListener(evt, f, capture));
  };

  function fermer(fondu = true) {
    if (ferme) return;
    ferme = true;
    cancelAnimationFrame(image);
    enleverEcoutes.forEach((f) => f());
    dessous.forEach((e) => { e.inert = false; });
    if (!fondu) { voile.remove(); return; }
    voile.classList.add("lancement-fondu");
    setTimeout(() => voile.remove(), FONDU_MS);
  }

  ecouter(voile, "click", (e) => {
    const choix = e.target.closest("button")?.dataset.choix;
    if (choix === "masquer") { marquer(); fermer(); }
    else if (choix === "voir") { marquer(); jouer(); }
  });
  // Le clavier s'arrête au voile (capture) : Échap ne ferme pas aussi un panneau du bureau.
  ecouter(document, "keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Escape" && !voile.classList.contains("lancement-joue")) { e.preventDefault(); marquer(); fermer(); }
  }, true);

  function jouer() {
    const calme = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    voile.classList.add("lancement-joue");
    voile.innerHTML = `<div class="lancement-fenetre">${htmlFenetre()}</div><canvas class="lancement-chute"></canvas>`;
    const fenetre = voile.querySelector(".lancement-fenetre");
    const reflexion = voile.querySelector(".lancement-reflexion");
    const tape = voile.querySelector(".lancement-tape");
    const toile = voile.querySelector("canvas");
    const ctx = toile.getContext("2d");
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let W = 0, H = 0;
    const dimensionner = () => {
      W = window.innerWidth; H = window.innerHeight;
      toile.width = Math.round(W * dpr); toile.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.textBaseline = "top";
    };
    dimensionner();

    // Passer : un clic, un toucher ou une touche, une fois la question répondue.
    setTimeout(() => {
      if (ferme) return;
      ecouter(voile, "pointerdown", () => fermer());
      ecouter(document, "keydown", (e) => { if (!e.repeat) fermer(); }, true);   // une touche gardée enfoncée ne saute pas
    }, 0);

    const debut = performance.now();
    let instantPret = null, avant = debut, lettres = null, retards = null;
    pret.then(() => { instantPret = (performance.now() - debut) / 1000; }, () => {});

    function pas(maintenant) {
      if (ferme) return;
      const t = (maintenant - debut) / 1000, dt = Math.min(0.05, (maintenant - avant) / 1000);
      avant = maintenant;
      const p = phase(t, instantPret);
      if (p.nom === "fin") { fermer(false); return; }
      reflexion.hidden = p.nom !== "reflexion";
      if (p.nom === "reflexion") reflexion.textContent = "Réflexion" + ".".repeat(1 + Math.floor(t * 3) % 3);
      else tape.textContent = texteTape(REPONSE, p.nom === "frappe" ? p.avance : 1);

      // Le relevé (une mesure par caractère) se fait pendant la pause, avant que rien ne bouge ; la chute commence
      // avec les lettres.
      if (!calme && lettres === null && p.nom !== "reflexion" && p.nom !== "frappe") {
        tape.textContent = REPONSE;
        lettres = releverLettres(fenetre);
        retards = departs(lettres, W, H);
      }
      const enChute = lettres !== null && p.nom !== "pause";
      if (enChute && !fenetre.classList.contains("lancement-vide")) fenetre.classList.add("lancement-vide");
      if (enChute) {
        const tl = t - DUREES.reflexion - DUREES.frappe - DUREES.pause;
        ctx.clearRect(0, 0, W, H);
        let police = "";
        for (let i = 0; i < lettres.length; i++) {
          let l = lettres[i];
          if (l.y > H + 40) continue;
          const tombe = tl > retards[i];
          if (tombe) {
            l = lettres[i] = tomber(l, dt);
            if (Math.random() < 0.04) l.c = signeDeCode();
          }
          if (l.police !== police) { police = l.police; ctx.font = police; }
          ctx.fillStyle = l.couleur;
          if (tombe) { ctx.globalAlpha = 0.25; ctx.fillText(l.c, l.x, l.y - l.v * 0.04); ctx.globalAlpha = 1; }
          ctx.fillText(l.c, l.x, l.y);
        }
      }
      if (p.nom === "fenetre") {
        if (calme) fenetre.style.opacity = String(1 - p.avance);
        else {
          const y = p.avance * p.avance * H * 1.15;   // une chute accélérée qui sort de l'écran, quelle que soit sa hauteur
          fenetre.style.transform = `translateY(${y}px) rotate(${Math.min(3, y / 150)}deg)`;
        }
      }
      image = requestAnimationFrame(pas);
    }
    image = requestAnimationFrame(pas);
    ecouter(window, "resize", dimensionner);
  }
}
