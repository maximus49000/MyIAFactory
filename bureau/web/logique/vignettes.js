// Les vignettes des post-its : quelle adresse d'image pour quel post-it, et quand recharger. Pur (sans DOM ni three.js).

import {imagesUrl, imagesVisibles} from "../ui/texte.js";

// L'adresse de la première image d'une tâche, ou null (pas d'image, ou images non servies : aucune requête).
export function vignetteUrl(imagesOk, tache) {
  if (!imagesVisibles({images_ok: imagesOk}, tache)) return null;
  return imagesUrl(tache)[0]?.url ?? null;
}

// Pour chaque identifiant de post-it visible, l'adresse voulue (Map ; les post-its sans image n'y figurent pas).
// Une seule adresse par post-it : au plus une texture par post-it.
export function vignettesVoulues(imagesOk, taches, idsVisibles) {
  const voulues = new Map();
  if (!Array.isArray(taches)) return voulues;
  for (const id of idsVisibles || []) {
    if (voulues.has(id)) continue;
    const url = vignetteUrl(imagesOk, taches.find((t) => t.id === id));
    if (url) voulues.set(id, url);
  }
  return voulues;
}

// Ce qu'il faut faire pour passer de `courant` (cle -> adresse déjà demandée) à `voulu` :
// libérer les textures des post-its disparus ou dont l'image change, charger les nouvelles.
export function planVignettes(courant, voulu) {
  const liberer = [], charger = [];
  for (const [cle, url] of courant) if (voulu.get(cle) !== url) liberer.push(cle);
  for (const [cle, url] of voulu) if (courant.get(cle) !== url) charger.push({cle, url});
  return {charger, liberer};
}
