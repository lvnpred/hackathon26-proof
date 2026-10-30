import test from "node:test";
import assert from "node:assert/strict";
import { opensRow } from "./rows.js";

test("opensRow ignores clicks on the row's own controls", () => {
  assert.equal(opensRow({ closest: () => null }), true);
  assert.equal(opensRow({ closest: (s) => (s.includes("button") ? {} : null) }), false);
});
