import assert from "node:assert/strict";
import { test } from "node:test";
import { cardActions, doctorBlocks, foldLines, foldOpensFor, journeySteps, lensLines, nextCard, quietActions } from "./journey.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const S = (steps) => steps.map((s) => s.status);

test("returned from theatre: Theatre is done while on the ward", () => {
  assert.deepEqual(S(journeySteps("ward", ["clinic", "admitting", "ward", "theatre", "ward"])), ["done", "done", "current", "done", "later", "later"]);
  assert.deepEqual(S(journeySteps("ward", ["clinic", "admitting", "ward"])), ["done", "done", "current", "later", "later", "later"]);
});
test("closed visit: Clinic is current and reads Visit closed", () => {
  const steps = journeySteps("clinic_done", ["clinic", "clinic_done"]);
  assert.deepEqual(steps[0], { key: "clinic", label: "Visit closed", status: "current", detail: "Clinic visit closed" });
  assert.deepEqual(S(steps).slice(1), ["later", "later", "later", "later", "later"]);
});
test("home without theatre: Theatre is skipped, not done", () => {
  assert.deepEqual(S(journeySteps("home", ["clinic", "admitting", "ward", "discharging", "home"])), ["done", "done", "done", "skipped", "done", "current"]);
});
const view = (state, next_role, extra = {}) => ({ state, order_list: [], now_next: { now: "N.", next: "X.", you_now: "YN.", you_next: "YX.", next_role }, ...extra });
test("my step: eyebrow for you, actions from the state", () => {
  const c = nextCard(view("ward", "doctor"), "doctor");
  assert.equal(c.eyebrow, "Now · for you");
  assert.deepEqual(c.actions, ["theatre", "discharge"]);
  assert.equal(c.last, "Last: N.");
});
test("someone else's step: no buttons, the eyebrow names the owner", () => {
  const c = nextCard(view("ward", "doctor"), "nurse");
  assert.equal(c.eyebrow, "Now · Doctor");
  assert.deepEqual(c.actions, []);
});
test("no owner: plain eyebrow, nothing waiting", () => {
  const c = nextCard(view("clinic_done", null), "doctor");
  assert.equal(c.eyebrow, "Now");
  assert.deepEqual(c.actions, []);
});
test("nurse acknowledges fresh orders first", () => {
  const fresh = { order_list: [{ acknowledged_by: null }] };
  assert.deepEqual(cardActions("admitting", "nurse", fresh), ["ack", "admission"]);
  assert.deepEqual(cardActions("admitting", "nurse", { order_list: [] }), ["admission"]);
});
test("quiet actions belong to the doctor", () => {
  assert.deepEqual(quietActions("ward", "nurse"), []);
  assert.deepEqual(quietActions("clinic", "doctor").map(([, l]) => l), ["Dictate orders", "Reference photo"]);
  assert.deepEqual(quietActions("ward", "doctor").map(([, l]) => l), ["Dictate orders", "Wound photo"]);
  assert.deepEqual(quietActions("admitting", "doctor").map(([id]) => id), ["orders"]);
  assert.deepEqual(quietActions("theatre", "doctor"), []);
});
test("history folds to the last 3 lines; a deep link opens it", () => {
  const lines = ["a", "b", "c", "d", "e"].map((id) => ({ id }));
  assert.deepEqual(foldLines(lines, false), { lines: lines.slice(2), more: 2 });
  assert.deepEqual(foldLines(lines, true), { lines, more: 0 });
  assert.equal(foldLines(lines.slice(0, 2), false).more, 0);
  assert.equal(foldOpensFor(lines, "a"), true);
  assert.equal(foldOpensFor(lines, "e"), false);
  assert.equal(foldOpensFor(lines, null), false);
});
test("lensLines filters by lens, keeps a nudge for the role", () => {
  const lines = [{ id: "1", type: "count.open" }, { id: "2", type: "rx.sign" }, { id: "3", type: "other.x" }];
  assert.deepEqual(lensLines(lines, [], "nurse", "nurse", null).map((l) => l.id), ["1"]);
  assert.deepEqual(lensLines(lines, [{ id: "3", to: "nurse" }], "nurse", "nurse", null).map((l) => l.id), ["1", "3"]);
});
test("new copy has no advice words", () => {
  for (const s of ["Now · for you", "Now · Nurse", "Visit closed", "Show full history (5)"]) assert.doesNotMatch(s, ADVICE);
});

test("doctorBlocks keeps the ward actions reachable when the nurse owns the step", () => {
  const mine = { mine: true, actions: ["theatre", "discharge"] };
  const theirs = { mine: false, actions: [] };
  assert.deepEqual(doctorBlocks("ward", mine), { inside: ["theatre", "discharge"], below: [] });
  assert.deepEqual(doctorBlocks("ward", theirs), { inside: [], below: ["theatre", "discharge"] });
  assert.deepEqual(doctorBlocks("clinic", theirs), { inside: [], below: [] });
});

test("the owner reads the owner's sentence, others the staff one", () => {
  const v = view("ward", "doctor");
  v.now_next.next_mine = "Send the patient to theatre or sign the discharge.";
  assert.equal(nextCard(v, "doctor").text, "Send the patient to theatre or sign the discharge.");
  assert.equal(nextCard(v, "nurse").text, "X.");
});
test("the current step skips a detail that repeats its label", () => {
  const home = journeySteps("home", ["clinic", "home"]).find((s) => s.status === "current");
  assert.equal(home.label, "Home");
  assert.equal(home.detail, "");
  assert.equal(journeySteps("ward", ["ward"]).find((s) => s.status === "current").detail, "On the ward");
});
