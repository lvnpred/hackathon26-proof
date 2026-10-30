import test from "node:test";
import assert from "node:assert/strict";
import { nextForOthers, patientGroups, reasonText, statusWord } from "./patientGroups.js";
import { H, M } from "./clock.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const P = (id, bed, state, view = {}) => ({
  id,
  bed,
  name: `Patient ${bed}`,
  view: { state, order_list: [], tasks: [], nudges: [], ask: {}, now_next: { next: "Nothing next." }, ...view },
});

test("reasonText joins distinct reasons", () => {
  assert.equal(reasonText([{ key: "e4:question:q1" }, { key: "e4:question:q2" }, { key: "e4:review:r1" }]), "Question + healing photo");
  assert.equal(reasonText([{ key: "e7:nudge:n1", nudgeKind: "obs_past_limit" }]), "Observation past its limit");
  assert.equal(reasonText([{ key: "e1:clinic" }, { key: "e2:no-orders" }]), "See in clinic + no orders signed");
});

test("patientGroups splits waiting from quiet", () => {
  const kumar = P("e4", "4", "home", { ask: { questions: [{ id: "q", to: "doctor", at_ms: 0, answer: null }], reviews: [{ id: "r", at_ms: 10 * M, answer: null }] } });
  const iyer = P("e7", "7", "ward", { order_list: [{}], tasks: [{ status: "open", kind: "obs", due_ms: H }] });
  const g = patientGroups([iyer, kumar], 30 * M);
  assert.deepEqual(g.waiting.map((r) => [r.bed, r.reason, r.waited, r.state]), [["4", "Question + healing photo", "30 min", "Home"]]);
  assert.deepEqual(g.quiet.map((r) => [r.bed, r.next]), [["7", "Nurse obs due 10:00"]]);
});

test("a quiet patient with no task reads the NEXT sentence", () => {
  const das = P("e9", "9", "clinic_done", { now_next: { next: "The visit is closed. No further steps." } });
  assert.equal(nextForOthers(das, 0), "The visit is closed. No further steps.");
});

test("statusWord", () => {
  assert.equal(statusWord({ status: "available" }), "Available");
  assert.equal(statusWord({ status: "in_theatre" }), "In theatre");
  assert.equal(statusWord(null), "Status");
});

test("M5 copy has no advice words", () => {
  for (const s of ["Waiting on you · 1", "Nothing for you now · 2", "Who is waiting on you first.", "Nurse obs due 10:00"]) assert.doesNotMatch(s, ADVICE);
});
