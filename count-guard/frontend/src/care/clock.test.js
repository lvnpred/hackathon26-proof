import test from "node:test";
import assert from "node:assert/strict";
import { H, M, label, skipTargets } from "./clock.js";

test("label matches the backend clock", () => {
  assert.equal(label(0), "Day 0 09:00");
  assert.equal(label(10 * H), "Day 0 19:00");
  assert.equal(label(33 * H + 30 * M), "Day 1 18:30");
  assert.equal(label(48 * H), "Day 2 09:00");
});

const withTasks = (...tasks) => ({ id: "e1", view: { tasks } });
const task = (id, status, due_ms) => ({ id, status, due_ms });

test("skipTargets offers +15 min, +1 h and the next due time", () => {
  const patients = [
    withTasks(task("t1", "open", 30 * H), task("t2", "open", 28 * H)),
    withTasks(task("t3", "open", 27 * H), task("t4", "done", 26 * H + 5 * M)),
  ];
  const got = skipTargets(26 * H, patients);
  assert.deepEqual(got, [
    { id: "plus15", label: "+15 min", atMs: 26 * H + 15 * M },
    { id: "plus60", label: "+1 h", atMs: 27 * H },
    { id: "next-due", label: "Next due", atMs: 27 * H },
  ]);
});

test("Next due ignores past, done, running and untimed tasks and is omitted when none", () => {
  const patients = [withTasks(task("a", "open", 25 * H), task("b", "running", 30 * H), task("c", "open", null), task("d", "open", 26 * H))];
  assert.deepEqual(skipTargets(26 * H, patients).map((t) => t.id), ["plus15", "plus60"]);
  assert.deepEqual(skipTargets(0, [{ id: "e", view: {} }]).map((t) => t.id), ["plus15", "plus60"]);
});
