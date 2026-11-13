// Chaque module de la page se charge : une erreur de syntaxe (essai réel : « section » déclarée deux fois dans
// directeur.js) laissait la page vide, sans qu'aucun autre test ne la voie.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readdirSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {dirname, join} from "node:path";

const ici = dirname(fileURLToPath(import.meta.url));

for (const dossier of ["ui", "logique", "scene"]) {
  for (const f of readdirSync(join(ici, "..", dossier)).filter((x) => x.endsWith(".js"))) {
    test(`${dossier}/${f} est du JavaScript valide`, () => {
      const r = spawnSync(process.execPath, ["--check", join(ici, "..", dossier, f)], {encoding: "utf-8"});
      assert.equal(r.status, 0, r.stderr);
    });
  }
}
