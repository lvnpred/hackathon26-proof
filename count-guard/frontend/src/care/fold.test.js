import test from "node:test";
import assert from "node:assert/strict";
import { foldsOnPhone } from "./fold.js";

test("foldsOnPhone keeps the doctor chip out for the patient", () => {
  assert.equal(foldsOnPhone("doctor", "patient"), false);
  assert.equal(foldsOnPhone("doctor", "nurse"), true);
  for (const c of ["picker", "role", "models", "banner", "clock"]) assert.equal(foldsOnPhone(c, "patient"), true);
});
