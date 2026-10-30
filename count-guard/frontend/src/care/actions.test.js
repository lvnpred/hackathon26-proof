import assert from "node:assert/strict";
import { test } from "node:test";
import { panelOpen, toggled } from "./actions.js";

test("panels stay closed until chosen; a draft opens its panel", () => {
  const none = new Set();
  assert.equal(panelOpen(none, "orders", { drafts: {} }), false);
  assert.equal(panelOpen(toggled(none, "photo"), "photo", {}), true);
  assert.equal(panelOpen(toggled(toggled(none, "photo"), "photo"), "photo", {}), false);
  assert.equal(panelOpen(none, "orders", { drafts: { order: { id: "d1" } } }), true);
  assert.equal(panelOpen(none, "discharge", { drafts: { discharge: { id: "d2" } } }), true);
  assert.equal(none.size, 0);
});
