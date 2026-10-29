import test from "node:test";
import assert from "node:assert/strict";
import { sortTasks, obsValues } from "./tasklist.js";
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
