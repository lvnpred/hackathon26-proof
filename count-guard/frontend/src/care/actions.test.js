import assert from "node:assert/strict";
import { test } from "node:test";
import { actionsFor, panelOpen, toggled } from "./actions.js";

test("actionsFor", () => {
  assert.deepEqual(actionsFor("clinic").map(([, l]) => l), ["Dictate orders", "Reference photo"]);
  assert.deepEqual(actionsFor("ward").map(([, l]) => l), ["Dictate orders", "Wound photo", "Dictate discharge"]);
  assert.deepEqual(actionsFor("theatre"), []);
  assert.deepEqual(actionsFor("admitting"), []);
});

test("panels stay closed until chosen; a draft opens its panel", () => {
  const none = new Set();
  assert.equal(panelOpen(none, "orders", { drafts: {} }), false);
  assert.equal(panelOpen(toggled(none, "photo"), "photo", {}), true);
  assert.equal(panelOpen(toggled(toggled(none, "photo"), "photo"), "photo", {}), false);
  assert.equal(panelOpen(none, "orders", { drafts: { order: { id: "d1" } } }), true);
  assert.equal(panelOpen(none, "discharge", { drafts: { discharge: { id: "d2" } } }), true);
  assert.equal(none.size, 0);
});
