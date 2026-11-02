import test from "node:test";
import assert from "node:assert/strict";
import { rosterFrom, wardPollIntervalMs } from "./roster.js";

test("rosterFrom takes the server clock and sorts patients by bed number", () => {
  const got = rosterFrom({
    now_ms: 5,
    board: "b1",
    patients: [{ id: "c", bed: "10" }, { id: "a", bed: "4" }, { id: "b", bed: "9" }],
  });
  assert.equal(got.nowMs, 5);
  assert.equal(got.board, "b1");
  assert.deepEqual(got.patients.map((p) => p.id), ["a", "b", "c"]);
});

test("rosterFrom copes with an empty ward", () => {
  const got = rosterFrom({ now_ms: 0, patients: [] });
  assert.deepEqual(got, { nowMs: 0, board: "", patients: [] });
});

test("rosterFrom with one patient keeps that patient", () => {
  const got = rosterFrom({ now_ms: 5, patients: [{ id: "a", bed: "4" }] });
  assert.equal(got.nowMs, 5);
  assert.deepEqual(got.patients, [{ id: "a", bed: "4" }]);
});

test("the ward refreshes every second until the live stream lands", () => {
  assert.equal(wardPollIntervalMs(), 1000);
});
