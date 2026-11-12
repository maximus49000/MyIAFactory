// L'accusé de réception : dès qu'une demande est partie (décision, cahier des charges, méthode, message de discussion),
// la page dit « Reçu, en cours de traitement… » jusqu'à ce que le relevé montre qu'elle est traitée (la décision a
// disparu, le message est entré dans la discussion) ; sans effet visible au bout de 3 minutes, elle dit « Le moteur n'a
// pas encore traité votre demande » avec le motif connu. Le masquage immédiat des décisions envoyées (validation.js) ne
// change pas : l'accusé le complète à l'endroit où l'élément se trouvait. La mémoire est celle de la page (rien n'est
// gardé au rechargement : le relevé dit déjà ce qui est traité). Pur, sauf `creerAccuses` (DOM) ; testé avec node.

export const TEXTE_RECU = "Reçu, en cours de traitement…";
export const DELAI_TARDE_MS = 3 * 60 * 1000;
export const SECURITE_MS = 30 * 60 * 1000;       // un accusé jamais résolu s'efface au bout de 30 minutes
const envois = new Map();                        // clé -> {libelle, depuis, traite}
const ecouteurs = new Set();

const liste = (v) => (Array.isArray(v) ? v : []);
const plein = (t) => typeof t === "string" && t.trim() !== "";
const prevenir = () => { for (const f of [...ecouteurs]) { try { f(); } catch { /* un écouteur ne bloque pas les autres */ } } };

function decisionsDe(etat) {
  return [...liste(etat?.decisions_projet), ...liste(etat?.fonctionnalites).flatMap((f) => liste(f?.decisions))];
}

// Ce qu'il faut pour suivre une demande, ou null (pas d'accusé pour les autres gestes) : {cle, libelle, traite(etat)}.
// `etat` : l'état servi au moment de l'envoi (pour ne pas confondre l'ancienne décision et celle d'après).
export function accuseDe(demande, etat) {
  if (!demande || typeof demande !== "object") return null;
  const fonctionnalite = (e) => liste(e?.fonctionnalites).find((f) => f?.id === demande.fonctionnalite);
  if (demande.type === "message" && plein(demande.fonctionnalite)) {
    const avant = liste(fonctionnalite(etat)?.discussion).length;
    return {cle: "message:" + demande.fonctionnalite, libelle: "Votre message",
            traite: (e) => { const f = fonctionnalite(e); return !f || liste(f.discussion).length > avant; }};
  }
  if ((demande.type === "cahier" || demande.type === "methode") && plein(demande.fonctionnalite)) {
    const genre = demande.type === "cahier" ? "valider_cahier" : "valider_methode";
    const ids = new Set(liste(fonctionnalite(etat)?.decisions).filter((d) => d?.genre === genre).map((d) => d.id));
    return {cle: demande.type + ":" + demande.fonctionnalite, libelle: demande.type === "cahier" ? "Cahier des charges" : "Méthode",
            traite: (e) => {
              const f = fonctionnalite(e);
              if (!f) return true;
              const restantes = liste(f.decisions).filter((d) => d?.genre === genre);
              return ids.size ? !restantes.some((d) => ids.has(d.id)) : restantes.length === 0;
            }};
  }
  if (plein(demande.decision)) {
    const id = demande.decision;
    return {cle: "decision:" + id, libelle: "Votre réponse", traite: (e) => !decisionsDe(e).some((d) => d?.id === id)};
  }
  return null;
}

export function noterAccuse(accuse, maintenant = Date.now()) {
  if (!accuse?.cle) return;
  envois.set(accuse.cle, {libelle: accuse.libelle, depuis: maintenant, traite: accuse.traite});
  prevenir();
}
export function oublierAccuse(cle) {
  if (envois.delete(cle)) prevenir();
}
export function surAccuses(f) { ecouteurs.add(f); return () => ecouteurs.delete(f); }
export function viderAccuses() { envois.clear(); }

// Pourquoi une demande tarde : le moteur arrêté, une pause d'installation, sinon le tour en cours.
export function motifRetard(etat) {
  if (etat?.orchestrateur_present === false) return "le moteur est arrêté";
  const pause = etat?.pause_installation?.texte;
  if (plein(pause)) return pause.trim().replace(/^Pause\s*:\s*/i, "en pause : ");
  return "il termine encore son tour en cours";
}

let vu = null;     // le dernier état BRUT servi (celui des panneaux masque les décisions envoyées)

// Les accusés encore à montrer pour cet état : [{cle, libelle, phase: "recu" | "tarde", texte}]. Ceux que l'état dit
// traités (ou vieux de 30 minutes) sont retirés d'ici.
export function evaluerAccuses(etat, maintenant = Date.now()) {
  const sortie = [];
  for (const [cle, x] of [...envois]) {
    let fini = maintenant - x.depuis >= SECURITE_MS;
    if (!fini && etat) { try { fini = x.traite(etat) === true; } catch { fini = false; } }
    if (fini) { envois.delete(cle); continue; }
    const tarde = maintenant - x.depuis >= DELAI_TARDE_MS;
    sortie.push({cle, libelle: x.libelle, phase: tarde ? "tarde" : "recu",
                 texte: tarde ? `Le moteur n'a pas encore traité votre demande (${motifRetard(etat)}).` : TEXTE_RECU});
  }
  return sortie;
}

// Un état brut vient d'être servi (ou l'heure a avancé : `etat` null) : tous les blocs se redessinent.
export function majEtatAccuses(etat, maintenant = Date.now()) {
  if (etat) vu = etat;
  evaluerAccuses(vu, maintenant);
  prevenir();
}

// Le bloc à poser dans la page : une ligne par accusé (celles dont la clé commence par `prefixe`, toutes sans lui).
export function creerAccuses(prefixe = "") {
  const racine = document.createElement("div");
  racine.className = "accuses";
  racine.setAttribute("role", "status");
  racine.hidden = true;
  const maj = () => {
    if (racine.isConnected === false && racine.vuUneFois) { arreter(); return; }   // le bloc a quitté la page
    if (racine.isConnected) racine.vuUneFois = true;
    const lignes = evaluerAccuses(vu, Date.now()).filter((a) => a.cle.startsWith(prefixe));
    racine.hidden = lignes.length === 0;
    racine.textContent = "";
    racine.append(...lignes.map((a) => {
      const p = document.createElement("p");
      p.className = "accuse";
      p.setAttribute("data-phase", a.phase);
      p.textContent = `${a.libelle} : ${a.texte}`;
      return p;
    }));
  };
  const arreter = surAccuses(maj);
  maj();
  return {racine, maj};
}
