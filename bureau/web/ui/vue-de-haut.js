// La vue de haut d'un catalogue : les éléments qui ont une position, sur un <canvas>.
// Une couleur par état, un clic mène à la fiche, molette (ou boutons) pour zoomer, glisser pour se déplacer.
// `cadrage` est pur et testé avec node ; le reste ne sert qu'au navigateur.
// Repère : x vers la droite, y vers le haut (le nord en haut) ; à l'écran : (x·e + dx, dy − y·e).

import {el} from "./dom.js";

const MARGE = 14;

function bornes(elements, traces) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const prendre = (x, y) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  };
  for (const e of elements || []) if (e?.position) prendre(e.position.x, e.position.y);
  for (const t of traces || []) for (const p of t?.points || []) if (Array.isArray(p)) prendre(p[0], p[1]);
  return minX === Infinity ? null : {minX, minY, maxX, maxY};
}

// L'échelle et le décalage qui font tenir tous les points (et les traces) dans le cadre, centrés.
export function cadrage(elements, traces, largeur, hauteur) {
  const b = bornes(elements, traces);
  if (!b) return {echelle: 1, dx: largeur / 2, dy: hauteur / 2};
  const utileX = Math.max(1, largeur - 2 * MARGE), utileY = Math.max(1, hauteur - 2 * MARGE);
  const ex = b.maxX > b.minX ? utileX / (b.maxX - b.minX) : Infinity;
  const ey = b.maxY > b.minY ? utileY / (b.maxY - b.minY) : Infinity;
  let echelle = Math.min(ex, ey);
  if (!Number.isFinite(echelle) || echelle <= 0) echelle = 1;
  const cx = (b.minX + b.maxX) / 2, cy = (b.minY + b.maxY) / 2;
  return {echelle, dx: largeur / 2 - cx * echelle, dy: hauteur / 2 + cy * echelle};
}

// opts : {elements (avec position), traces, couleur(element) -> css, estompe(element) -> bool,
//         surChoix(element), libelle(element) -> texte, vue: objet où garder zoom et position}
export function creerVueDeHaut(opts) {
  const {traces = [], couleur, surChoix, libelle, vue} = opts;
  const elements = (opts.elements || []).filter((e) => Number.isFinite(e?.position?.x) && Number.isFinite(e?.position?.y));
  let estompe = opts.estompe || (() => false);
  const boite = el("div", "cat-carte");
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `Vue de haut : ${elements.length} éléments placés`);
  const apercu = el("div", "cat-apercu");
  apercu.hidden = true;
  boite.append(canvas, apercu);

  let largeur = 0, hauteur = 0, base = null;
  // vue.t : {echelle, dx, dy} de l'utilisateur, gardé tant que le panneau reste sur ce catalogue.
  const t = () => vue.t || base;

  function dessiner() {
    if (!largeur || !hauteur) return;
    const ctx2d = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    ctx2d.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx2d.clearRect(0, 0, largeur, hauteur);
    const {echelle, dx, dy} = t();
    const style = getComputedStyle(boite);
    ctx2d.lineJoin = "round";
    ctx2d.strokeStyle = style.getPropertyValue("--cat-ardoise").trim() || "#3a4656";
    ctx2d.globalAlpha = 0.8;
    ctx2d.lineWidth = 2.2;
    for (const tr of traces) {
      const pts = (tr?.points || []).filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]));
      if (pts.length < 2) continue;
      ctx2d.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx2d.lineTo : ctx2d.moveTo).call(ctx2d, x * echelle + dx, dy - y * echelle));
      ctx2d.stroke();
    }
    const papier = style.getPropertyValue("--cat-papier").trim() || "#fbf9f4";
    const depart = elements.length > 2000 ? 2.2 : elements.length > 500 ? 3 : 4;   // plus d'éléments, points plus fins
    const rayon = Math.min(8, depart + Math.log2(Math.max(1, echelle / (base?.echelle || echelle))));
    ctx2d.lineWidth = 1;
    ctx2d.strokeStyle = papier;
    // Les estompés d'abord, pour que les éléments filtrés restent au-dessus.
    for (const passe of [true, false]) {
      ctx2d.globalAlpha = passe ? 0.18 : 1;
      for (const e of elements) {
        if (Boolean(estompe(e)) !== passe) continue;
        const x = e.position.x * echelle + dx, y = dy - e.position.y * echelle;
        if (x < -10 || y < -10 || x > largeur + 10 || y > hauteur + 10) continue;
        ctx2d.beginPath();
        ctx2d.arc(x, y, rayon, 0, Math.PI * 2);
        ctx2d.fillStyle = couleur(e, style);
        ctx2d.fill();
        ctx2d.stroke();
      }
    }
    ctx2d.globalAlpha = 1;
  }

  function redimensionner() {
    const r = boite.getBoundingClientRect();
    const l = Math.round(r.width), h = Math.round(r.height);
    if (!l || !h || (l === largeur && h === hauteur)) return;
    const ancien = base;
    largeur = l; hauteur = h;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(l * ratio);
    canvas.height = Math.round(h * ratio);
    canvas.style.width = l + "px";
    canvas.style.height = h + "px";
    base = cadrage(elements, traces, l, h);
    if (vue.t && ancien) {   // garder le zoom de l'utilisateur, recentré sur la nouvelle taille
      vue.t = {echelle: vue.t.echelle, dx: vue.t.dx + (base.dx - ancien.dx), dy: vue.t.dy + (base.dy - ancien.dy)};
    }
    dessiner();
  }

  function zoomer(facteur, mx = largeur / 2, my = hauteur / 2) {
    const c = t();
    const min = base.echelle * 0.5, max = base.echelle * 400;
    const echelle = Math.min(max, Math.max(min, c.echelle * facteur));
    const f = echelle / c.echelle;
    vue.t = {echelle, dx: mx - (mx - c.dx) * f, dy: my - (my - c.dy) * f};
    dessiner();
  }

  function plusProche(mx, my) {
    const {echelle, dx, dy} = t();
    let meilleur = null, d2 = 10 * 10;
    for (const e of elements) {
      if (estompe(e)) continue;
      const x = e.position.x * echelle + dx - mx, y = dy - e.position.y * echelle - my;
      const d = x * x + y * y;
      if (d <= d2) { d2 = d; meilleur = e; }
    }
    return meilleur;
  }

  const local = (ev) => {
    const r = canvas.getBoundingClientRect();
    return [ev.clientX - r.left, ev.clientY - r.top];
  };
  canvas.addEventListener("wheel", (ev) => {
    if (!base) return;
    ev.preventDefault();
    const [mx, my] = local(ev);
    zoomer(Math.exp(-ev.deltaY * 0.0015), mx, my);
  }, {passive: false});

  let appui = null;   // {x, y, dx, dy, bouge}
  canvas.addEventListener("pointerdown", (ev) => {
    if (!base) return;
    const c = t();
    appui = {x: ev.clientX, y: ev.clientY, dx: c.dx, dy: c.dy, bouge: false};
    canvas.setPointerCapture(ev.pointerId);
    canvas.classList.add("glisse");
  });
  canvas.addEventListener("pointermove", (ev) => {
    if (appui) {
      const mx = ev.clientX - appui.x, my = ev.clientY - appui.y;
      if (!appui.bouge && mx * mx + my * my < 16) return;
      appui.bouge = true;
      apercu.hidden = true;
      vue.t = {echelle: t().echelle, dx: appui.dx + mx, dy: appui.dy + my};
      dessiner();
      return;
    }
    if (!base) return;
    const [x, y] = local(ev);
    const e = plusProche(x, y);
    canvas.style.cursor = e ? "pointer" : "grab";
    if (!e) { apercu.hidden = true; return; }
    apercu.textContent = libelle(e);
    apercu.hidden = false;
    apercu.style.left = Math.min(x + 12, Math.max(0, largeur - apercu.offsetWidth - 4)) + "px";
    apercu.style.top = (y + 14 + apercu.offsetHeight > hauteur ? y - apercu.offsetHeight - 10 : y + 14) + "px";
  });
  const finAppui = (ev) => {
    if (!appui) return;
    const clic = !appui.bouge;
    appui = null;
    canvas.classList.remove("glisse");
    if (clic && ev.type === "pointerup") {
      const [x, y] = local(ev);
      const e = plusProche(x, y);
      if (e) surChoix(e);
    }
  };
  canvas.addEventListener("pointerup", finAppui);
  canvas.addEventListener("pointercancel", finAppui);
  canvas.addEventListener("pointerleave", () => { apercu.hidden = true; });

  const observateur = new ResizeObserver(redimensionner);
  observateur.observe(boite);

  return {
    element: boite,
    zoomer: (f) => { if (base) zoomer(f); },
    toutVoir: () => { vue.t = null; dessiner(); },
    filtrer(fn) { estompe = fn; dessiner(); },
    detruire: () => observateur.disconnect(),
  };
}
