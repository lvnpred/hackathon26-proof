import test from "node:test";
import assert from "node:assert/strict";
import {
  OPS_SCOPE, STAFF_BY, agentMoment, agentMoments, citedLine, feedRows, handlingRows, isFeed,
  myPatientsStrip, needsTitle, proposalsFor, stripTitle, undoLabel,
} from "./handling.js";
import { aiChip, pauseLabel } from "./dock.js";
import { routedLine } from "./thread.js";
import { resolveMoment } from "./inspect.js";
import { chipFor, statusLabel } from "./moments.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const MIN = 60_000;
const row = (id, over = {}) => ({
  work_id: id, kind: "nudge", level: "act", summary: "Reminded Nurse Meena (synthetic)", at_ms: 8 * 60 * MIN,
  undo_until_ms: 10 * MIN, reason: "Obs were overdue", inputs: [{ id: "e1", label: "Obs", when: "08:00" }], status: "done", ...over,
});
const prop = (id) => ({
  work_id: id, kind: "move_ready", owner_role: "doctor", sentence: "Ready to move to the ward", draft: "d",
  cited: [{ id: "a", text: "BP steady" }, { id: "b", text: "Pain 2/10" }], at_ms: 8 * 60 * MIN, editable: true,
  reason: "Checks met", inputs: [],
});
const ops = { handling: [row("w1"), row("w2", { status: "undone", undo_until_ms: null })], proposals: [prop("p1")], open: [], routes: { q1: "Dr. A. Rao" } };

test("titles", () => {
  assert.equal(stripTitle(3), "AI is handling · 3");
  assert.equal(needsTitle(2), "Needs you · 2");
});

test("undoLabel", () => {
  assert.equal(undoLabel(600_000, 120_000), "Undo (8 min)");
  assert.equal(undoLabel(600_000, 600_000), "");
  assert.equal(undoLabel(null, 0), "");
  assert.equal(undoLabel(600_000, 570_000), "Undo (1 min)");
  assert.equal(undoLabel(600_000, 510_000), "Undo (2 min)");
  assert.equal(undoLabel(600_000, 700_000), "");
});

test("handlingRows keeps order, strips synthetic and marks undone", () => {
  const rows = handlingRows(ops, 2 * MIN);
  assert.deepEqual(rows.map((r) => r.workId), ["w1", "w2"]);
  assert.equal(rows[0].text, "Reminded Nurse Meena");
  assert.match(rows[0].when, /^\d\d:\d\d$/);
  assert.equal(rows[0].undo, "Undo (8 min)");
  assert.equal(rows[0].undone, false);
  assert.equal(rows[1].undone, true);
  assert.equal(rows[1].undo, "");
  assert.deepEqual(handlingRows(null, 0), []);
});

test("proposalsFor is role scoped, never for the patient", () => {
  assert.equal(proposalsFor(ops, "doctor").length, 1);
  assert.deepEqual(proposalsFor(ops, "nurse"), []);
  assert.deepEqual(proposalsFor(ops, "patient"), []);
});

test("citedLine", () => {
  assert.equal(citedLine([{ id: "a", text: "x" }, { id: "b", text: "y" }]), "From: x; y");
  assert.equal(citedLine([]), "");
});

test("agentMoment is a full moment (PF-3)", () => {
  const m = agentMoment(row("w1"), "ep1");
  assert.equal(m.id, "w1");
  assert.equal(m.kind, "agent");
  assert.equal(m.capability, "ops");
  assert.equal(m.patient_finding, null);
  assert.equal(m.status, "recorded");
  assert.equal(m.finding, "Obs were overdue");
  assert.equal(m.owner, null);
  assert.deepEqual([m.calls, m.handmade, m.written], [[], false, []]);
  assert.equal(m.workId, "w1");
  assert.equal(m.episodeId, "ep1");
  assert.equal(m.level, "act");
  assert.equal(m.undoUntilMs, 10 * MIN);
  assert.deepEqual(m.refs, { workId: "w1", episodeId: "ep1", reason: "Obs were overdue", inputs: m.inputs, level: "act", undoUntilMs: 10 * MIN });
  assert.equal(agentMoment(row("w2", { status: "undone" }), "ep1").status, "undone");
  const p = agentMoment(prop("p1"), "ep1");
  assert.deepEqual([p.status, p.owner, p.title], ["open", "doctor", "Ready to move to the ward"]);
});

test("agentMoments resolve for staff, never for the patient, and work with chip and status helpers", () => {
  const list = agentMoments(ops, "ep1");
  assert.deepEqual(list.map((m) => m.id), ["w1", "w2", "p1"]);
  assert.equal(resolveMoment(list, "w1", "patient"), null);
  assert.equal(resolveMoment(list, "w1", "staff").id, "w1");
  assert.equal(chipFor(list[0]), "Rules");
  assert.equal(statusLabel(list[1], "nurse").text, "Undone");
  assert.equal(statusLabel(list[0], "nurse").text, "Recorded");
  assert.equal(statusLabel(list[2], "doctor").text, "Needs you");
  assert.equal(statusLabel(list[2], "nurse").text, "Waiting for the doctor");
  assert.deepEqual(agentMoments(null, "ep1"), []);
});

test("feedRows and isFeed", () => {
  const feed = { items: [{ ...row("w1"), episode_id: "ep1", patient: "Asha K (synthetic)" }] };
  assert.equal(isFeed(feed), true);
  assert.equal(isFeed({ paused: false }), false);
  assert.equal(isFeed(null), false);
  const [r] = feedRows(feed, 2 * MIN);
  assert.deepEqual([r.workId, r.episodeId, r.patient, r.undo], ["w1", "ep1", "Asha K", "Undo (8 min)"]);
  assert.deepEqual(feedRows(null, 0), []);
});

test("myPatientsStrip", () => {
  const patients = [{ id: "ep1", name: "Asha K (synthetic)", view: { ops } }, { id: "ep2", name: "B", view: {} }];
  const s = myPatientsStrip(patients, "doctor");
  assert.equal(s.rows.length, 1);
  assert.deepEqual(s.rows[0], { episodeId: "ep1", name: "Asha K", text: "Reminded Nurse Meena" });
  assert.equal(s.proposals[0].p.work_id, "p1");
  assert.equal(s.proposals[0].episodeId, "ep1");
  assert.deepEqual(myPatientsStrip(patients, "patient"), { rows: [], proposals: [] });
});

test("dock chip, pause label, routed line, constants", () => {
  assert.equal(aiChip(null), "");
  assert.equal(aiChip(false), "AI: running");
  assert.equal(aiChip(true), "AI: paused");
  assert.equal(pauseLabel(false), "Pause AI");
  assert.equal(pauseLabel(true), "Resume AI");
  assert.equal(routedLine({ ops }, "q1"), "Your question went to Dr. A. Rao");
  assert.equal(routedLine({ ops }, "zz"), "");
  assert.equal(routedLine({}, "q1"), "");
  assert.equal(OPS_SCOPE, "/ops/");
  assert.equal(STAFF_BY.doctor, "Dr. A. Rao (synthetic)");
});

test("every C6 UI string passes the no-advice check", () => {
  const strings = [stripTitle(1), needsTitle(1), undoLabel(600_000, 0), aiChip(true), aiChip(false), pauseLabel(true), pauseLabel(false),
    routedLine({ ops }, "q1"), citedLine(prop("p").cited), "Undone"];
  for (const s of strings) assert.doesNotMatch(s, ADVICE, s);
});
