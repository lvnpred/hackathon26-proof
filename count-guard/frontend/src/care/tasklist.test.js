import test from "node:test";
import assert from "node:assert/strict";
import { sortTasks, obsValues, orderLines, patientTaskStatus, orderStatus, markDone, taskStatusText, taskGroups, rowMark, orderFoldTitle } from "./tasklist.js";
import { H, M } from "./clock.js";
import { ADVICE } from "../../scripts/demo/beats.mjs";

const NOW = 10 * 60 * M;
const t = (id, over) => ({ id, status: "open", due_ms: NOW - 5 * M, ...over });

test("sortTasks orders overdue, due, running, later, done", () => {
  const tasks = [
    t("done", { status: "done" }),
    t("later", { due_ms: NOW + 60 * M }),
    t("running", { status: "running" }),
    t("due"),
    t("overdue", { due_ms: NOW - 45 * M }),
  ];
  assert.deepEqual(sortTasks(tasks, NOW).map((x) => x.id), ["overdue", "due", "running", "later", "done"]);
});

test("sortTasks puts the longest overdue first and does not mutate its input", () => {
  const tasks = [t("a", { due_ms: NOW - 40 * M }), t("b", { due_ms: NOW - 90 * M })];
  assert.deepEqual(sortTasks(tasks, NOW).map((x) => x.id), ["b", "a"]);
  assert.deepEqual(tasks.map((x) => x.id), ["a", "b"]);
});

test("obsValues keeps numbers, drops blank optional fields, rejects out-of-range", () => {
  assert.deepEqual(obsValues({ sbp: "120", dbp: "80", hr: "72", spo2: "", temp: "" }), { values: { sbp: 120, dbp: 80, hr: 72 } });
  assert.deepEqual(obsValues({ sbp: "120", dbp: "80", hr: "72", spo2: "98", temp: "36.8" }).values.temp, 36.8);
  assert.ok(obsValues({ sbp: "400", dbp: "80", hr: "72", spo2: "", temp: "" }).error);
  assert.ok(obsValues({ sbp: "", dbp: "80", hr: "72", spo2: "", temp: "" }).error);
});

import { surgeryNow } from "./tasklist.js";

test("surgeryNow reads only the current theatre stay and returns its times", () => {
  const line = (type, when) => ({ type, when });
  assert.deepEqual(surgeryNow([line("patient.state"), line("surgery.began", "Day 0 11:05")]), { began: "Day 0 11:05", ended: null });
  const both = [line("patient.state"), line("surgery.began", "Day 0 11:05"), line("surgery.ended", "Day 0 12:40")];
  assert.deepEqual(surgeryNow(both), { began: "Day 0 11:05", ended: "Day 0 12:40" });
  const second = [...both, line("patient.state"), line("patient.state")];
  assert.deepEqual(surgeryNow(second), { began: null, ended: null });
  assert.deepEqual(surgeryNow([]), { began: null, ended: null });
});

import { needsReason } from "./tasklist.js";

test("needsReason follows the server's list, so a corrected count asks for none", () => {
  assert.equal(needsReason({ needs: ["surgery ended", "reason (count open)"] }), true);
  assert.equal(needsReason({ needs: ["surgery ended"] }), false);
  assert.equal(needsReason(undefined), false);
});

test("orderLines shows each item once and an item with no task without one", () => {
  const order = { id: "o1", items: [{ text: "Paracetamol 1 g every 6 h" }, { text: "Check wound" }] };
  const tasks = [{ id: "t1", order_id: "o1", title: "Paracetamol 1 g every 6 h" }, { id: "t9", order_id: "o2", title: "Check wound" }];
  assert.deepEqual(orderLines(order, tasks).map((l) => [l.text, l.task?.id ?? null]), [["Paracetamol 1 g every 6 h", "t1"], ["Check wound", null]]);
});

test("orderLines uses each task once and appends an unmatched task", () => {
  const order = { id: "o1", items: [{ text: "Check wound" }, { text: "Check wound" }] };
  const tasks = [{ id: "a", order_id: "o1", title: "Check wound" }, { id: "b", order_id: "o1", title: "Extra" }];
  assert.deepEqual(orderLines(order, tasks).map((l) => l.task?.id ?? null), ["a", null, "b"]);
});

test("patientTaskStatus", () => {
  const at = (h, m = 0) => (h - 9) * 60 * M + m * M; // Day 0 clock
  const dose = { kind: "dose", every_h: 6, status: "open", due_ms: at(16), done: [{ at_ms: at(10) }] };
  assert.equal(patientTaskStatus(dose, "ward"), "Given 10:00 \u00b7 next due 16:00");
  assert.equal(patientTaskStatus({ ...dose, kind: "obs", due_ms: at(11) }, "ward"), "Done 10:00 \u00b7 next due 11:00");
  assert.equal(patientTaskStatus({ kind: "obs", every_h: 1, status: "open", due_ms: at(10), done: [] }, "ward"), "Due 10:00");
  assert.equal(patientTaskStatus({ ...dose, status: "closed", due_ms: null }, "home"), "Finished");
  assert.equal(patientTaskStatus({ kind: "check", every_h: null, status: "done", due_ms: null, done: [{ at_ms: at(10, 5) }] }, "ward"), "Done 10:05");
  assert.equal(patientTaskStatus({ ...dose, status: "running" }, "ward"), "Running");
  assert.equal(patientTaskStatus(dose, "theatre"), "Paused (in theatre)");
});

test("patientTaskStatus says Due since once a never-done task is past due", () => {
  const at = (h, m = 0) => (h - 9) * 60 * M + m * M;
  const task = { kind: "obs", every_h: 1, status: "open", due_ms: at(9, 18), done: [] };
  assert.equal(patientTaskStatus(task, "ward", at(10, 40)), "Due since 09:18");
  assert.equal(patientTaskStatus(task, "ward", at(9, 0)), "Due 09:18");
  assert.equal(patientTaskStatus(task, "ward"), "Due 09:18");
});

test("patientTaskStatus words pass the no-advice scan", () => {
  const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
  const at = (h) => (h - 9) * 60 * M;
  const dose = { kind: "dose", every_h: 6, status: "open", due_ms: at(16), done: [{ at_ms: at(10) }] };
  const cases = [dose, { ...dose, status: "closed" }, { ...dose, status: "running" }, { ...dose, kind: "obs" }, { ...dose, done: [], due_ms: at(9) }, { ...dose, status: "done" }];
  for (const task of cases) for (const state of ["ward", "theatre", "home"]) assert.doesNotMatch(patientTaskStatus(task, state, at(12)), ADVICE);
});

test("orderStatus says what happens to a clinic order", () => {
  const o = { acknowledged_by: null };
  assert.equal(orderStatus(o, "clinic"), "Starts when the patient is admitted");
  assert.equal(orderStatus(o, "clinic_done"), "Not started: the visit was closed");
  assert.equal(orderStatus(o, "clinic", true), "Starts when you are admitted");
  assert.equal(orderStatus(o, "ward"), "Waiting for the nurse");
  assert.equal(orderStatus({ acknowledged_by: "Nurse Meena" }, "clinic_done"), "Acknowledged by Nurse Meena");
});

test("markDone: due work is primary, later work is early", () => {
  assert.deepEqual(markDone("overdue"), { label: "Mark done", primary: true });
  assert.deepEqual(markDone("due"), { label: "Mark done", primary: true });
  assert.deepEqual(markDone("later"), { label: "Mark done early", primary: false });
});

const k = (o) => ({ id: "t", title: "BP", kind: "obs", status: "open", due_ms: 60 * M, ...o });
test("taskStatusText words", () => {
  assert.equal(taskStatusText(k({}), 60 * M + 34 * M, "ward"), "34 min late");
  assert.equal(taskStatusText(k({}), 60 * M + 94 * M, "ward"), "1 h 34 min late");
  assert.equal(taskStatusText(k({}), 60 * M + 5 * M, "ward"), "due now");
  assert.equal(taskStatusText(k({ due_ms: 6 * H + 10 * M }), 0, "ward"), "next at 15:10");
  assert.equal(taskStatusText(k({ due_ms: null }), 0, "ward"), "no set time");
  assert.equal(taskStatusText(k({}), 0, "theatre"), "paused while in theatre");
  assert.equal(taskStatusText(k({ status: "running" }), 0, "ward"), "running");
});
test("taskGroups splits due now from later and drops done", () => {
  const g = taskGroups([k({ id: "a" }), k({ id: "b", due_ms: 9 * H }), k({ id: "c", status: "done" }), k({ id: "d", status: "running" })], 61 * M, "ward");
  assert.deepEqual(g.now.map((r) => r.task.id), ["a", "d"]);
  assert.deepEqual(g.later.map((r) => r.task.id), ["b"]);
  assert.deepEqual(taskGroups([], 0, "ward"), { now: [], later: [] });
  assert.deepEqual(taskGroups([k({})], 0, "theatre").later.map((r) => r.status), ["paused while in theatre"]);
});
test("rowMark labels", () => {
  assert.deepEqual(rowMark(k({}), "due"), { label: "Save readings", primary: true });
  assert.deepEqual(rowMark(k({ kind: "dose" }), "later"), { label: "Given early", primary: false });
  assert.deepEqual(rowMark(k({ kind: "task" }), "later"), { label: "Mark done early", primary: false });
  assert.deepEqual(rowMark(k({ kind: "dose" }), "overdue"), { label: "Mark done", primary: true });
});
test("orderFoldTitle", () => {
  assert.equal(orderFoldTitle({ by: "Dr. A. Rao (synthetic)", at_ms: 2 * M, acknowledged_by: "Nurse Meena" }), "Signed orders \u00b7 Dr. A. Rao 09:02 \u00b7 acknowledged");
  assert.equal(orderFoldTitle({ by: "D", at_ms: 0, acknowledged_by: null }), "Signed orders \u00b7 D 09:00 \u00b7 not acknowledged yet");
});
test("M2 copy has no advice words", () => {
  for (const s of ["Given early", "Save readings", "due now", "paused while in theatre", "Due now", "Later today", "Signed orders"]) assert.doesNotMatch(s, ADVICE);
});
