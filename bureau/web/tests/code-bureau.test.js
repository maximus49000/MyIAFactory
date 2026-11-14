import {test} from "node:test";
import assert from "node:assert/strict";
import {codeChange} from "../logique/diff.js";

test("la page se recharge quand le code du bureau a changé, pas sinon", () => {
  assert.equal(codeChange({code_bureau: "a"}, {code_bureau: "b"}), true);
  assert.equal(codeChange({code_bureau: "a"}, {code_bureau: "a"}), false);
  assert.equal(codeChange({}, {code_bureau: "b"}), false);          // serveur d'avant : rien à comparer
  assert.equal(codeChange({code_bureau: "a"}, {erreur: "x"}), false);
});
