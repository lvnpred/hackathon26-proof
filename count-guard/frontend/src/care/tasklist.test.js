import test from "node:test";
import assert from "node:assert/strict";
import { sortTasks, obsValues, taskStatusLabel, TASK_STATUS_LABEL, orderLines, patientTaskStatus } from "./tasklist.js";
import { M } from "./clock.js";

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

test("taskStatusLabel gives plain words, and keeps an unknown word as is", () => {
  assert.equal(taskStatusLabel("open"), "To do");
  assert.equal(taskStatusLabel("running"), "Running");
  assert.equal(taskStatusLabel("done"), "Done");
  assert.equal(taskStatusLabel("closed"), "Stay ended");
  assert.equal(taskStatusLabel("paused"), "paused");
  assert.equal(TASK_STATUS_LABEL.closed, "Stay ended");
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
