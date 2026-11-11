// « L'orchestrateur n'est pas lancé » (essai réel) : quand le relevé le dit absent, les gestes sont bloqués (le
// serveur met `agir` à faux) et ce bandeau propose de le lancer. Tout texte venu du serveur passe par textContent.

import {urlProjet} from "./projets.js";

export function bandeauVisible(etat) {
  return etat?.orchestrateur_absent === true;
}

// Rend {ok, message, aCopier} ; aCopier : le message à coller quand rien n'a pu démarrer (claude absent).
export async function lancerOrchestrateur(fetchFn = fetch) {
  try {
    const r = await fetchFn(urlProjet("/api/orchestrateur/lancer"), {
      method: "POST", headers: {"X-Bureau": "1", "Content-Type": "application/json"}, body: "{}"});
    let d = {};
    try { d = await r.json(); } catch { /* corps illisible */ }
    if (!r.ok) return {ok: false, message: d?.erreur || `Le serveur a répondu ${r.status}.`, aCopier: null};
    return {ok: d.ok === true, message: String(d.message || ""), aCopier: typeof d.a_copier === "string" ? d.a_copier : null};
  } catch {
    return {ok: false, message: "Lancement impossible : serveur injoignable.", aCopier: null};
  }
}

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

// Le bandeau, posé sous la barre. `maj(etat)` le montre ou le cache.
export function creerBandeauOrchestrateur(apres) {
  const bandeau = el("div", "bandeau-orchestrateur");
  bandeau.setAttribute("role", "alert");
  bandeau.hidden = true;
  const texte = el("span", "", "L'orchestrateur n'est pas lancé : les gestes attendent qu'il soit là.");
  const bouton = el("button", "bouton", "Lancer l'orchestrateur");
  bouton.type = "button";
  const retour = el("p", "bandeau-orchestrateur-retour");
  retour.hidden = true;
  const copie = el("textarea", "bandeau-orchestrateur-copie");
  copie.readOnly = true;
  copie.hidden = true;
  bouton.addEventListener("click", async () => {
    bouton.disabled = true;
    const r = await lancerOrchestrateur();
    retour.textContent = r.message;
    retour.hidden = !r.message;
    copie.hidden = !r.aCopier;
    if (r.aCopier) copie.value = r.aCopier;
    if (!r.ok) bouton.disabled = false;
  });
  bandeau.append(texte, bouton, retour, copie);
  apres.after(bandeau);
  return {
    maj(etat) {
      const visible = bandeauVisible(etat);
      if (!visible) { bouton.disabled = false; retour.hidden = true; copie.hidden = true; }
      bandeau.hidden = !visible;
    },
  };
}
