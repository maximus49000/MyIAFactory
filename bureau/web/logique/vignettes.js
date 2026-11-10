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

// Tient à jour, post-it par post-it, la vignette affichée. Indépendant de three.js : le moteur 3D est injecté.
//   charger(url, surSucces(image), surEchec())  demande l'image (asynchrone)
//   creer(cle, image) -> objet | null           fabrique et attache la vignette ; null si le post-it n'existe plus
//   retirer(cle, objet)                         détache et libère la vignette
//   jeter(image)                                libère une image qui ne servira pas (par défaut image.close())
// Une vignette est remplacée seulement à l'arrivée de la nouvelle (pas de clignotement) ; une réponse en retard
// ou pour un post-it disparu est jetée ; après un échec, la même adresse n'est retentée qu'après `delaiEssaiMs`.
export class Vignettes {
  constructor({charger, creer, retirer, jeter = (image) => image?.close?.(), maintenant = () => Date.now(),
               delaiEssaiMs = 60000}) {
    Object.assign(this, {chargerImage: charger, creer, retirer, jeter, maintenant, delaiEssaiMs});
    this.affichees = new Map();   // cle -> {url, objet}
    this.enCours = new Map();     // cle -> {url} : le chargement attendu (un jeton par essai)
    this.echecs = new Map();      // cle -> {url, t}
  }

  // `voulues` : cle -> adresse, pour les post-its visibles qui ont une image ; le reste est libéré.
  synchroniser(voulues) {
    for (const cle of new Set([...this.affichees.keys(), ...this.enCours.keys(), ...this.echecs.keys()])) {
      if (!voulues.has(cle)) this.oublier(cle);
    }
    for (const [cle, url] of voulues) this._vouloir(cle, url);
  }

  oublier(cle) {
    this.enCours.delete(cle);
    this.echecs.delete(cle);
    const a = this.affichees.get(cle);
    if (a) { this.affichees.delete(cle); this.retirer(cle, a.objet); }
  }

  _vouloir(cle, url) {
    if (this.affichees.get(cle)?.url === url) { this.enCours.delete(cle); return; }
    if (this.enCours.get(cle)?.url === url) return;
    const echec = this.echecs.get(cle);
    if (echec?.url === url && this.maintenant() - echec.t < this.delaiEssaiMs) return;
    const essai = {url};
    this.enCours.set(cle, essai);
    this.echecs.delete(cle);
    this.chargerImage(url, (image) => {
      if (this.enCours.get(cle) !== essai) { this.jeter(image); return; }
      this.enCours.delete(cle);
      const objet = this.creer(cle, image);
      if (!objet) { this.jeter(image); return; }
      const ancienne = this.affichees.get(cle);
      this.affichees.set(cle, {url, objet});
      if (ancienne) this.retirer(cle, ancienne.objet);
    }, () => {
      if (this.enCours.get(cle) !== essai) return;
      this.enCours.delete(cle);
      this.echecs.set(cle, {url, t: this.maintenant()});
    });
  }
}
