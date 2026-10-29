import test from "node:test";
import assert from "node:assert/strict";
import { BEATS } from "./beats.mjs";
import { STEPS } from "./steps.mjs";

test("every beat has exactly one step", () => {
  assert.deepEqual(Object.keys(STEPS).sort(), BEATS.map((b) => b.id).sort());
});
