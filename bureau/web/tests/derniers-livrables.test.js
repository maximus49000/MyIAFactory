import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {derniersLivrables, varianteDe, versionDe} from "../ui/derniers-livrables.js";

const doc = (chemin, date, titre = null) => ({chemin, date, titre: titre || chemin, livrable: true});
const etat = (fonctionnalites, projet = "FM_Stats") => ({projet, fonctionnalites});

test("variante : nom sans version, sans bruit ni nom du projet", () => {
  assert.equal(varianteDe("Livrables/FM_Stats_Maitre_12.apk", "", "FM_Stats"), "maitre");
  assert.equal(varianteDe("Livrables/FM_Stats_Client_3.apk", "", "FM_Stats"), "client");
  assert.equal(varianteDe("android_app/build/app-maitre-release.apk", "", "FM_Stats"), "maitre");
  assert.equal(varianteDe("android_app/build/app-client-release.apk", "", "FM_Stats"), "client");
  assert.equal(varianteDe("a/app-release.apk", "APK release FM_Stats (onglet)", "FM_Stats"), "livrable");
});

test("variante : le titre court nomme la variante d'un fichier sans nom de variante", () => {
  assert.equal(varianteDe(".factory/livrables/FM_Stats_121.apk", "APK Maître (release) : Versement rapide", "FM_Stats"), "maitre");
  assert.equal(varianteDe(".factory/livrables/FM_Stats_121.apk", "APK release de la branche agent/t77", "FM_Stats"), "livrable");
});

test("version : le dernier nombre du nom du fichier", () => {
  assert.equal(versionDe("Livrables/FM_Stats_Maitre_12.apk"), 12);
  assert.equal(versionDe("x/app-release.apk"), null);
});

test("FM_Stats : un livrable Maître et un Client, le plus récent de chacun", () => {
  const e = etat([
    {id: "f1", documents: [doc("L/FM_Stats_Maitre_1.apk", "2026-11-25T10:00:00+01:00"), doc("L/FM_Stats_Client_1.apk", "2026-11-25T10:05:00+01:00")]},
    {id: "f2", documents: [doc("L/FM_Stats_Maitre_2.apk", "2026-11-26T09:00:00+01:00")]},
  ]);
  const l = derniersLivrables(e);
  assert.deepEqual(l.map((x) => [x.libelle, x.chemin, x.version, x.fonctionnalite]),
    [["Maitre", "L/FM_Stats_Maitre_2.apk", 2, "f2"], ["Client", "L/FM_Stats_Client_1.apk", 1, "f1"]]);
});

test("un nouveau livrable d'une variante remplace l'ancien ; les anciens ne sont pas listés", () => {
  const avant = etat([{id: "f1", documents: [doc("L/FM_Stats_Maitre_1.apk", "2026-11-25"), doc("L/FM_Stats_Client_1.apk", "2026-11-25")]}]);
  assert.equal(derniersLivrables(avant).length, 2);
  const apres = etat([{id: "f1", documents: [doc("L/FM_Stats_Maitre_1.apk", "2026-11-25"), doc("L/FM_Stats_Client_1.apk", "2026-11-25")]},
                      {id: "f2", documents: [doc("L/FM_Stats_Client_2.apk", "2026-11-27")]}]);
  const l = derniersLivrables(apres);
  assert.equal(l.length, 2);
  assert.equal(l.find((x) => x.variante === "client").chemin, "L/FM_Stats_Client_2.apk");
  assert.equal(l.find((x) => x.variante === "maitre").chemin, "L/FM_Stats_Maitre_1.apk");
});

test("l'avis de fin compte aussi, avec le lien de la release", () => {
  const e = etat([{id: "f24", documents: [doc("pieces/f24/maquette.html", "2026-11-26")],
                   fin: {date: "2026-11-26T16:11:32+01:00", livrables: [{chemin: ".factory/livrables/FM_Stats_121.apk",
                     titre: "APK Maître (release) : Versement rapide", lien: "https://github.com/x/y/releases/tag/v121"}]}},
                  {id: "f22", documents: [doc("android_app/build/app-maitre-release.apk", "2026-11-26T13:16:00+01:00", "APK Maître")]}]);
  const l = derniersLivrables(e);
  assert.equal(l.length, 1, "maquette exclue, Maître unique");
  assert.equal(l[0].chemin, ".factory/livrables/FM_Stats_121.apk");
  assert.equal(l[0].version, 121);
  assert.equal(l[0].libelle, "Maître", "l'orthographe du titre");
  assert.equal(l[0].lien, "https://github.com/x/y/releases/tag/v121");
});

test("une seule variante : une ligne ; copies précédentes ignorées ; sans livrable : liste vide", () => {
  const un = derniersLivrables(etat([{id: "f1", documents: [doc("jeu_1.zip", "2026-01-01"), doc("jeu_2.zip", "2026-02-01"),
                                                           doc(".factory/livrables-precedents/dernier.apk", "2026-03-01")]}], "Jeu"));
  assert.equal(un.length, 1);
  assert.equal(un[0].chemin, "jeu_2.zip");
  assert.equal(un[0].libelle, "Dernier livrable");
  assert.deepEqual(derniersLivrables(etat([{id: "f1", documents: [doc("pieces/m.html", "2026-01-01")]}])), []);
  assert.deepEqual(derniersLivrables(null), []);
  assert.deepEqual(derniersLivrables({}), []);
});

test("le bouton est sur la barre de chaque projet, la vue dit « Aucun livrable pour l'instant »", () => {
  const barre = readFileSync(new URL("../ui/barre.js", import.meta.url), "utf8");
  assert.match(barre, /"Derniers livrables"/);
  assert.match(barre, /boutonFonctions, boutonDerniers, zoneLivrable/);
  assert.doesNotMatch(barre, /boutonDerniers\.hidden/);
  const vue = readFileSync(new URL("../ui/derniers-livrables.js", import.meta.url), "utf8");
  assert.match(vue, /Aucun livrable pour l'instant/);
});
