import test from "node:test";
import assert from "node:assert/strict";
import { H, M } from "./clock.js";
import { queueRows, todos, waitingPills } from "./derive.js";

const nudge = (id, to, at_ms, says = "Observations are overdue.") => ({
  id, key: "obs_overdue", kind: "obs_overdue", to, says, at_ms, when: "Day 1 13:00",
});
const view = (over = {}) => ({ rx: null, orders: null, card: null, handover: null, nudges: [], ...over });
const patient = (id, bed, v) => ({ id, bed, name: `Patient ${id}`, view: v });

test("identical nudges on two patients give two rows with their own key and bed", () => {
  const patients = [
    patient("e1", "Bed 1", view({ nudges: [nudge("n1", "nurse", 28 * H)] })),
    patient("e2", "Bed 2", view({ nudges: [nudge("n2", "nurse", 28 * H)] })),
  ];
  const rows = queueRows(patients, "nurse", 29 * H);
  assert.equal(rows.length, 2);
  assert.notEqual(rows[0].key, rows[1].key);
  assert.deepEqual(rows.map((r) => r.bed).sort(), ["Bed 1", "Bed 2"]);
  assert.equal(rows[0].kind, "nudge");
  assert.ok(rows[0].lineId);
});

test("waited text and late flag", () => {
  const patients = [patient("e1", "Bed 1", view({ nudges: [nudge("n1", "nurse", 28 * H)] }))];
  const now = 30 * H + 20 * M;
  assert.equal(queueRows(patients, "nurse", now)[0].waited, "2 h 20 min");
  assert.equal(waitingPills(patients, now)[0].late, true);
  assert.equal(queueRows(patients, "nurse", 28 * H + 5 * M)[0].waited, "5 min");
  assert.equal(waitingPills(patients, 28 * H + 5 * M)[0].late, false);
});

test("rows sort by longest waited first", () => {
  const patients = [
    patient("e1", "Bed 1", view({ nudges: [nudge("n1", "nurse", 29 * H)] })),
    patient("e2", "Bed 2", view({ nudges: [nudge("n2", "nurse", 27 * H)] })),
  ];
  assert.deepEqual(queueRows(patients, "nurse", 30 * H).map((r) => r.bed), ["Bed 2", "Bed 1"]);
});

test("doctor sees to-dos only", () => {
  const p = patient("e1", "Bed 1", view({ rx: { rows: [] }, nudges: [nudge("n1", "nurse", 28 * H)] }));
  const rows = queueRows([p], "doctor", 30 * H);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].says, "Ward orders not set");
  assert.equal(rows[0].kind, "todo");
  assert.equal(rows[0].lineId, null);
});

test("patient sees only patient nudges", () => {
  const p = patient("e1", "Bed 1", view({ nudges: [nudge("n1", "nurse", 28 * H), nudge("n2", "patient", 28 * H, "Check in is due.")] }));
  const rows = queueRows([p], "patient", 30 * H);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].lineId, "n2");
});

test("todos follow the order of the journey", () => {
  const handover = { to_nurse: "Nurse Joseph", accepted_by: null };
  const all = todos(patient("e1", "Bed 1", view({ rx: {}, orders: {}, handover })));
  assert.deepEqual(all.map((r) => r.says), ["Discharge card not signed", "Handover to Nurse Joseph not accepted"]);
  const none = todos(patient("e1", "Bed 1", view({ rx: {}, orders: {}, card: {}, handover: { ...handover, accepted_by: "Nurse Joseph" } })));
  assert.equal(none.length, 0);
});

test("waitingPills name the owner of each item", () => {
  const p = patient("e1", "Bed 1", view({ rx: {}, handover: { to_nurse: "Nurse Joseph", accepted_by: null }, nudges: [nudge("n1", "nurse", 28 * H), nudge("n2", "patient", 28 * H, "Check in is due.")] }));
  const who = waitingPills([p], 29 * H).map((x) => x.who).sort();
  assert.deepEqual(who, ["Dr. A. Rao", "Nurse", "Nurse Joseph", "Patient"]);
});

test("no produced text gives instructions", () => {
  const p = patient("e1", "Bed 1", view({ rx: {}, handover: { to_nurse: "Nurse Joseph", accepted_by: null }, nudges: [nudge("n1", "nurse", 28 * H)] }));
  const text = JSON.stringify([queueRows([p], "nurse", 30 * H), queueRows([p], "doctor", 30 * H), waitingPills([p], 30 * H)]);
  assert.doesNotMatch(text, /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i);
});

test("nurse sees an unaccepted handover as a to-do after the nudges", () => {
  const handover = { to_nurse: "Nurse Joseph", accepted_by: null };
  const p = patient("e1", "Bed 1", view({ handover, nudges: [nudge("n1", "nurse", 28 * H)] }));
  const rows = queueRows([p], "nurse", 30 * H);
  assert.deepEqual(rows.map((r) => r.kind), ["nudge", "todo"]);
  assert.equal(rows[1].says, "Handover to Nurse Joseph not accepted");
  assert.equal(rows[1].lineId, null);
  assert.equal(queueRows([p], "patient", 30 * H).length, 0);
});

test("to-dos have no waited text, are never late and sort after nudges", () => {
  const p = patient("e1", "Bed 1", view({ rx: {}, nudges: [nudge("n1", "nurse", 29 * H)] }));
  assert.equal(queueRows([p], "doctor", 40 * H)[0].waited, "");
  const pills = waitingPills([p], 40 * H);
  assert.deepEqual(pills.map((x) => [x.who, x.waited === "", x.late]), [["Nurse", false, true], ["Dr. A. Rao", true, false]]);
});

test("to-dos and pills carry the stage to open; nudges carry none", () => {
  const handover = { to_nurse: "Nurse Joseph", accepted_by: null };
  const p = (v) => patient("e1", "Bed 1", view(v));
  assert.equal(todos(p({ rx: {} }))[0].stage, "clinic");
  assert.equal(todos(p({ rx: {}, orders: {} }))[0].stage, "clinic");
  assert.equal(todos(p({ rx: {}, orders: {}, card: {}, handover }))[0].stage, "ward");
  const pills = waitingPills([p({ rx: {}, nudges: [nudge("n1", "nurse", 0)] })], H);
  assert.deepEqual(pills.map((x) => x.stage).sort(), ["clinic", null]);
  assert.equal(queueRows([p({ nudges: [nudge("n1", "nurse", 0)] })], "nurse", H)[0].stage, null);
});
