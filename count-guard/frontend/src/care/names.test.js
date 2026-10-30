import assert from "node:assert/strict";
import { test } from "node:test";
import { displayName, displayView, shortName } from "./names.js";

test("displayName and shortName strip the synthetic tag", () => {
  assert.equal(displayName("R. Kumar, 58 M (synthetic)"), "R. Kumar, 58 M");
  assert.equal(displayName("Nurse Acknowledges orders from Dr. A. Rao (synthetic)."), "Nurse Acknowledges orders from Dr. A. Rao.");
  assert.equal(displayName(null), "");
  assert.equal(shortName("R. Kumar, 58 M (synthetic)"), "R. Kumar");
});

test("displayView maps every string and keeps the rest", () => {
  const v = { by: "Dr. A. Rao (synthetic)", n: 3, ok: true, none: null, rows: [{ by: "Nurse Asha (synthetic)" }] };
  assert.deepEqual(displayView(v), { by: "Dr. A. Rao", n: 3, ok: true, none: null, rows: [{ by: "Nurse Asha" }] });
  assert.equal(v.by, "Dr. A. Rao (synthetic)");
});
