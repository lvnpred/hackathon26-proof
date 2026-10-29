import test from "node:test";
import assert from "node:assert/strict";
import { H, M, STAGES, label, stageOf, jumpTargets, plusHour } from "./clock.js";

test("label matches the backend clock", () => {
  assert.equal(label(0), "Day 0 09:00");
  assert.equal(label(10 * H), "Day 0 19:00");
  assert.equal(label(33 * H + 30 * M), "Day 1 18:30");
  assert.equal(label(48 * H), "Day 2 09:00");
});

test("stageOf follows the stage times", () => {
  assert.equal(stageOf(0), "clinic");
  assert.equal(stageOf(24 * H - 1), "clinic");
  assert.equal(stageOf(24 * H), "theatre");
  assert.equal(stageOf(26 * H - 1), "theatre");
  assert.equal(stageOf(26 * H), "ward");
  assert.equal(stageOf(48 * H - 1), "ward");
  assert.equal(stageOf(48 * H), "home");
});

test("jumpTargets enables only times after now", () => {
  const enabled = Object.fromEntries(jumpTargets(26 * H).map((t) => [t.label, t.enabled]));
  assert.deepEqual(enabled, {
    Clinic: false,
    "Strips (evening)": false,
    Admission: false,
    Theatre: false,
    Ward: false,
    "Ward 18:30 check": true,
    Home: true,
  });
});

test("STAGES and plusHour", () => {
  assert.deepEqual(STAGES.map((s) => s.atMs), [0, 10 * H, 22 * H, 24 * H, 26 * H, 33 * H + 30 * M, 48 * H]);
  assert.equal(plusHour(26 * H), 27 * H);
});
