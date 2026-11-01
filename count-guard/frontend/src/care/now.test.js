import assert from "node:assert/strict";
import { test } from "node:test";
import { H, M } from "./clock.js";
import { movedAlertId, nextUp, pickNow, pickNowAcross } from "./now.js";

const NURSE = { role: "nurse", name: "Nurse Meena" };
const DOCTOR = { role: "doctor", name: "Dr. A. Rao" };
const PATIENT = { role: "patient", name: "R. Kumar" };
const NOW = 30 * H;

const view = (extra = {}) => ({
  state: "ward", order_list: [], tasks: [], nudges: [], ai_moments: [],
  now_next: { now: "N.", next: "The doctor sends the patient to theatre.", next_mine: "Send the patient to theatre.", you_next: "The doctor sends you to theatre or signs your discharge.", next_role: "doctor" },
  ...extra,
});
const task = (id, due_ms) => ({ id, title: `Task ${id}`, status: "open", due_ms });
const nudge = (id, kind, at_ms, to = "nurse", says = "Systolic BP 82 is below the limit of 90 set by Dr. A. Rao.") => ({ id, kind, at_ms, to, says, says_staff: says });

test("danger beats late beats due", () => {
  const v = view({
    tasks: [task("t1", NOW - 2 * H), task("t2", NOW - 5 * M)],
    nudges: [nudge("n1", "obs_past_limit", NOW - M)],
  });
  const pick = pickNow(v, NURSE, NOW);
  assert.deepEqual([pick.now.rank, pick.now.title], [1, "Systolic BP 82"]);
  assert.deepEqual(pick.now.pill, { role: "danger", text: "Below limit" });
  assert.deepEqual(pick.next.map((i) => i.rank), [3, 4]);
  assert.equal(pick.rest, 0);
});

test("late tasks go oldest first and the rest folds after two", () => {
  const v = view({ tasks: [task("a", NOW - 2 * H), task("b", NOW - 4 * H), task("c", NOW - 3 * H), task("d", NOW - H)] });
  const pick = pickNow(v, NURSE, NOW);
  assert.equal(pick.now.title, "Task b");
  assert.deepEqual(pick.next.map((i) => i.title), ["Task c", "Task a"]);
  assert.equal(pick.rest, 1);
  assert.equal(pick.more[0].title, "Task d");
});

test("a step waiting on the viewer is blocked, with the role's own words and buttons", () => {
  const v = view({ now_next: { ...view().now_next, next_role: "nurse", next_mine: "Acknowledge the orders." } });
  const pick = pickNow(v, NURSE, NOW);
  assert.deepEqual([pick.now.rank, pick.now.title, pick.now.pill.text], [2, "Acknowledge the orders.", "Needs you"]);
  assert.deepEqual(pick.now.action, { kind: "step", keys: ["ack"] });
});

test("an unsaved swab count blocks the nurse in theatre", () => {
  const v = view({ state: "theatre", count: { opened: 14, opened_at_ms: NOW - H }, now_next: { ...view().now_next, next_role: "doctor" } });
  const pick = pickNow(v, NURSE, NOW);
  assert.deepEqual([pick.now.rank, pick.now.kind, pick.now.title], [2, "count", "Swab count not saved"]);
  const saved = { opened: 14, closed_opened: 14, returned: 14, closed_by: "Nurse Asha (synthetic)" };
  assert.equal(pickNow({ ...v, count: saved }, NURSE, NOW).now.kind, "nothing");
});

test("review is for staff only, and only inside the undo window", () => {
  const ops = { handling: [{ work_id: "w1", summary: "Reminder sent", status: "done", at_ms: NOW - M, undo_until_ms: NOW + 5 * M }, { work_id: "w2", summary: "Old", status: "done", at_ms: 0, undo_until_ms: M }] };
  const v = view({ ops });
  assert.deepEqual([pickNow(v, NURSE, NOW).now.rank, pickNow(v, NURSE, NOW).now.title], [5, "Reminder sent"]);
  assert.equal(pickNow(v, PATIENT, NOW).now.rank, 6);
});

test("the patient never gets late, review or task words", () => {
  const v = view({ tasks: [task("t1", NOW - 3 * H)], nudges: [nudge("n1", "dose_overdue", NOW - H, "patient", "Your tablet is overdue.")], ops: { handling: [{ work_id: "w1", summary: "x", status: "done", undo_until_ms: NOW + M }] } });
  const pick = pickNow(v, PATIENT, NOW);
  assert.equal(pick.now.rank, 4);
  assert.equal(pick.now.pill.text, "For you");
  assert.deepEqual(pick.next, []);
  assert.doesNotMatch(JSON.stringify(pick), /Late|Review|Task t1/);
});

test("nothing: the title, and the next owner action from now_next", () => {
  const pick = pickNow(view(), NURSE, NOW);
  assert.deepEqual([pick.now.rank, pick.now.title, pick.now.detail], [6, "Nothing needs you.", "Next: The doctor sends the patient to theatre."]);
  assert.deepEqual(pick.now.pill, { role: "wait", text: "Waiting for the doctor" });
  assert.deepEqual([pick.next, pick.rest], [[], 0]);
});

test("the doctor sees a past-limit alert addressed to the nurse", () => {
  const v = view({ nudges: [nudge("n1", "obs_past_limit", NOW - M)] });
  assert.equal(pickNow(v, DOCTOR, NOW).now.rank, 1);
});

test("across patients the nurse gets BP-below-limit first, then the oldest", () => {
  const patients = [
    { id: "e1", bed: "1", name: "A", view: view({ tasks: [task("t1", NOW - 6 * H)] }) },
    { id: "e2", bed: "2", name: "B", view: view({ nudges: [nudge("n1", "obs_past_limit", NOW - M)] }) },
    { id: "e3", bed: "3", name: "C", view: view({ tasks: [task("t2", NOW - 3 * H)] }) },
  ];
  const pick = pickNowAcross(patients, NURSE, NOW);
  assert.deepEqual([pick.now.patient.episodeId, pick.now.rank], ["e2", 1]);
  assert.deepEqual(pick.next.map((i) => i.patient.episodeId), ["e1", "e3"]);
  assert.equal(pickNowAcross([], NURSE, NOW).now.title, "Nothing needs you.");
});

test("NextUp: one of three lines for the patient", () => {
  assert.equal(nextUp(view({ now_next: { next_role: "patient", you_next: "Complete your check-in." } })).text, "You need to: complete your check-in.");
  const fresh = { next_role: "nurse", you_next: "The nurse acknowledges the new orders from Dr. A. Rao." };
  assert.equal(nextUp(view({ state: "ward", now_next: fresh })).text, "The nurse will acknowledge the new orders from Dr. A. Rao.");
  assert.equal(nextUp(view({ state: "ward", now_next: { next_role: "doctor", you_next: "The doctor sends you to theatre or signs your discharge." } })).text, "The doctor will send you to theatre or sign your discharge.");
  assert.equal(nextUp(view({ state: "admitting", now_next: { next_role: "nurse", you_next: "The nurse completes your admission." } })).text, "The nurse will complete your admission.");
  assert.equal(nextUp(view({ state: "home", now_next: { next_role: "doctor", you_next: "The doctor reviews your healing photo." } })).text, "The doctor will review your healing photo.");
  assert.equal(nextUp(view({ state: "home", now_next: { next_role: null, you_next: "You are home. No further steps." } })).text, "You don't need to do anything now.");
  for (const state of ["clinic", "admitting", "ward", "theatre", "discharging"]) {
    assert.doesNotMatch(nextUp(view({ state, now_next: { next_role: "nurse", you_next: "x" } })).text, /late|task/i);
  }
});

test("Now holds the winner's action: an alert is moved out of the list, a task or ask gets a focus action", () => {
  const v = view({ nudges: [nudge("n1", "obs_past_limit", NOW - M)] });
  assert.equal(movedAlertId(pickNow(v, NURSE, NOW), "nurse"), "n1");
  assert.equal(movedAlertId(pickNow(v, NURSE, NOW), "patient"), null);
  assert.equal(pickNow(view({ tasks: [task("t1", NOW - 2 * H)] }), NURSE, NOW).now.action.kind, "task");
  const ask = view({ now_next: { next_role: "nurse" }, ask: { questions: [{ to: "doctor", at_ms: NOW - H, answer: null }] } });
  assert.equal(pickNow(ask, DOCTOR, NOW).now.action.kind, "focus");
  const other = view({ nudges: [nudge("n2", "obs_past_limit", NOW - M, "nurse")] });
  assert.equal(pickNow(other, DOCTOR, NOW).now.action, null);
});
