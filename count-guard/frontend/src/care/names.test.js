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

test("the By line is static text: no editable input holds the tagged name", async () => {
  const fs = await import("node:fs");
  for (const file of ["./CountPanel.jsx", "../screens/WardPanel.jsx"]) {
    const src = fs.readFileSync(new URL(file, import.meta.url), "utf8");
    assert.doesNotMatch(src, /<input value=\{by\}/, file);
    assert.match(src, /By \{displayName\(by\)\}/, file);
  }
  assert.equal(displayName("Nurse Asha (synthetic)"), "Nurse Asha");
});
