import test from "node:test";
import assert from "node:assert/strict";
import { findingPill } from "./finding.js";

const wait = { status: "open", owner: "nurse", finding_role: "wait", finding_text: "Waiting for the nurse" };

test("a waiting moment reads Needs you only for its owner", () => {
  assert.deepEqual(findingPill(wait, "nurse"), { role: "wait", text: "Needs you" });
  assert.deepEqual(findingPill(wait, "doctor"), { role: "wait", text: "Waiting for the nurse" });
});

test("danger and check keep their words for the owner", () => {
  const danger = { status: "open", owner: "nurse", finding_role: "danger", finding_text: "Below limit" };
  const check = { status: "flagged", owner: "doctor", finding_role: "check", finding_text: "Surgeon to decide" };
  assert.deepEqual(findingPill(danger, "nurse"), { role: "danger", text: "Below limit" });
  assert.deepEqual(findingPill(check, "doctor"), { role: "check", text: "Surgeon to decide" });
});

test("finished moments keep the backend words", () => {
  const done = { status: "recorded", owner: null, finding_role: "done", finding_text: "Signed 09:20" };
  assert.deepEqual(findingPill(done, "doctor"), { role: "done", text: "Signed 09:20" });
});

test("moments without finding fields (agent rows) are named too, and nothing reads Recorded", () => {
  assert.deepEqual(findingPill({ status: "undone", owner: null }, "nurse"), { role: "done", text: "Undone" });
  assert.deepEqual(findingPill({ status: "open", owner: "doctor" }, "nurse"), { role: "wait", text: "Waiting for the doctor" });
  assert.deepEqual(findingPill({ status: "open", owner: "doctor" }, "doctor"), { role: "wait", text: "Needs you" });
  assert.deepEqual(findingPill({ status: "recorded", owner: null, at_ms: 8 * 60 * 60_000 }, "nurse"), { role: "done", text: "Saved 17:00" });
  for (const status of ["recorded", "matches", "flagged", "failed", "open", "undone"]) {
    assert.notEqual(findingPill({ status, owner: null }, "nurse").text, "Recorded");
  }
});
