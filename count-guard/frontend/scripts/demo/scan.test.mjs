import test from "node:test";
import assert from "node:assert/strict";
import { scanText } from "./scan.mjs";

const hits = (t, role = "doctor") => scanText(t, role);

test("Recorded as a whole word is flagged", () => {
  assert.equal(hits("Pain 3/10 Recorded").length, 1);
  assert.deepEqual(hits("Prerecorded by Nurse Asha, From voice"), []);
});
test("Day N clock text is flagged", () => {
  assert.equal(hits("Surgery at Day 1 09:30").length, 1);
  assert.deepEqual(hits("Today 09:30 and review on day 7"), []);
});
test("snake_case is flagged", () => {
  assert.equal(hits("kind: move_ready").length, 1);
  assert.deepEqual(hits("Ward 4-West, BP 112/70, SpO2 98"), []);
});
test("event names are flagged", () => {
  assert.equal(hits("task.assigned").length, 1);
  assert.equal(hits("work.done").length, 1);
  assert.deepEqual(hits("The task was assigned; the work is done"), []);
});
test("patient-only AI text is flagged for the patient only", () => {
  for (const t of ["Muse Spark wrote this", "SAM 3.1 saw it", "AI (on behalf of Dr. Rao)", "Acknowledged by Asha"]) {
    assert.equal(hits(t, "patient").length, 1, t);
    assert.deepEqual(hits(t, "nurse"), [], t);
  }
  assert.deepEqual(hits("Your care team will see this", "patient"), []);
});
