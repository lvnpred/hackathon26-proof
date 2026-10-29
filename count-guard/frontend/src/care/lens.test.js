import test from "node:test";
import assert from "node:assert/strict";
import { lensFor } from "./lens.js";

test("a lens picked under another role is dropped on a role switch", () => {
  assert.equal(lensFor("doctor", { role: "nurse", lens: "everyone" }), "doctor");
});

test("a lens picked under the current role is kept", () => {
  assert.equal(lensFor("nurse", { role: "nurse", lens: "everyone" }), "everyone");
});

test("with nothing picked the lens is the role", () => {
  assert.equal(lensFor("patient", null), "patient");
});
