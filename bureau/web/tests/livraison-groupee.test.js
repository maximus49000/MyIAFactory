import {test} from "node:test";
import assert from "node:assert/strict";
import {livraisonGroupee, titreAffiche} from "../ui/repetitions.js";

// Essai réel : la livraison d'un seul apk pour onze éléments portait le titre et l'objectif de l'élément meneur.
const groupee = {id: "t272", titre: "Livraison de l'apk signé : Livraison de l'APK release signé", journal: [
  {t: "x", texte: "Un seul livrable pour tout le produit, avec les éléments : Écran Intérieur du frigo, Détail d'une "
    + "clayette, Livraison de l'APK release signé. Fabrique-le depuis le dépôt à jour. Livraison groupée, lot : "
    + "f4/e2 f4/e3 f4/e12"}]};

test("une livraison groupée est dite comme telle", () => {
  assert.deepEqual(livraisonGroupee(groupee),
    {noms: ["Écran Intérieur du frigo", "Détail d'une clayette", "Livraison de l'APK release signé"], n: 3});
  assert.equal(titreAffiche({taches: [groupee]}, groupee), "Livrable groupé (3 éléments)");
});

test("une livraison d'un seul élément garde son titre", () => {
  const seule = {id: "t1", titre: "Livraison : e1", journal: [{texte: "Un seul livrable pour tout le produit, avec "
    + "les éléments : Logique. Fabrique-le depuis le dépôt à jour. Livraison groupée, lot : f4/e1"}]};
  assert.equal(livraisonGroupee(seule), null);
  assert.equal(titreAffiche({taches: [seule]}, seule), "Livraison : e1");
  assert.equal(livraisonGroupee({id: "t2", titre: "x"}), null);
});
