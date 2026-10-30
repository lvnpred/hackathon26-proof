import test from "node:test";
import assert from "node:assert/strict";
import { H, M } from "./clock.js";
import { queueRows, todos, waitingPills, taskDue, dueLabel, STATE_LABEL } from "./derive.js";

const nudge = (id, to, at_ms, says = "Observations are overdue.") => ({
  id, key: "obs_overdue", kind: "obs_overdue", to, says, at_ms, when: "Day 1 13:00",
});
const order = (id, at_ms, acknowledged_by = null) => ({ id, by: "Dr. A. Rao", items: [], at_ms, acknowledged_by });
const view = (over = {}) => ({ state: "ward", order_list: [order("o0", 0, "Nurse")], tasks: [], handover: null, nudges: [], ...over });
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
  assert.equal(waitingPills(patients, now)[0].name, "Patient e1");
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

test("doctor sees clinic patients, ward patients without orders, and past-limit nudges", () => {
  const limit = { ...nudge("n9", "nurse", 28 * H, "Observations are past the limit."), kind: "obs_past_limit" };
  const patients = [
    patient("e1", "Bed 1", view({ state: "clinic", order_list: [] })),
    patient("e2", "Bed 2", view({ state: "ward", order_list: [] })),
    patient("e3", "Bed 3", view({ state: "ward", nudges: [nudge("n1", "nurse", 28 * H), limit] })),
  ];
  const rows = queueRows(patients, "doctor", 30 * H);
  assert.deepEqual(rows.map((r) => [r.bed, r.says]).sort(), [
    ["Bed 1", "See in clinic"],
    ["Bed 2", "No orders signed"],
    ["Bed 3", "Observations are past the limit."],
  ]);
  assert.equal(rows.find((r) => r.bed === "Bed 3").lineId, "n9");
  assert.equal(rows.find((r) => r.bed === "Bed 1").state, "clinic");
});

test("patient queue is empty; patient nudges still show as pills", () => {
  const p = patient("e1", "Bed 1", view({ nudges: [nudge("n2", "patient", 28 * H, "Check in is due.")] }));
  assert.deepEqual(queueRows([p], "patient", 30 * H), []);
  assert.deepEqual(waitingPills([p], 30 * H).map((x) => x.who), ["Patient"]);
});

test("the handover to-do shows until it is accepted", () => {
  const handover = { to_nurse: "Nurse Joseph", accepted_by: null };
  assert.deepEqual(todos(patient("e1", "Bed 1", view({ handover }))).map((r) => r.says), ["Handover to Nurse Joseph not accepted"]);
  assert.equal(todos(patient("e1", "Bed 1", view({ handover: { ...handover, accepted_by: "Nurse Joseph" } }))).length, 0);
});

test("STATE_LABEL names all seven states", () => {
  assert.deepEqual(Object.keys(STATE_LABEL), ["clinic", "clinic_done", "admitting", "ward", "theatre", "discharging", "home"]);
  assert.equal(STATE_LABEL.discharging, "Being discharged");
});

const T = 40 * H;
const task = (over = {}) => ({
  id: "t1", order_id: "o1", title: "Obs", kind: "obs", mode: "tick", proof: "", every_h: null,
  status: "open", due_ms: T, done: [], began_ms: null, ...over,
});

test("taskDue boundaries", () => {
  assert.equal(taskDue(task(), T - 1), "later");
  assert.equal(taskDue(task(), T), "due");
  assert.equal(taskDue(task(), T + 30 * M), "due");
  assert.equal(taskDue(task(), T + 30 * M + 1), "overdue");
  assert.equal(taskDue(task({ status: "running" }), T + 5 * H), "running");
  assert.equal(taskDue(task({ status: "done" }), T + 5 * H), "done");
  assert.equal(taskDue(task({ due_ms: null }), T), "later");
});

test("nurse rows: new order and overdue task, overdue first", () => {
  const p = patient("e1", "Bed 1", view({
    order_list: [order("o1", T - 10 * M)],
    tasks: [task({ title: "BP check", due_ms: T - H })],
  }));
  const rows = queueRows([p], "nurse", T);
  assert.deepEqual(rows.map((r) => r.says), ["BP check \u00b7 due", "New orders from Dr. A. Rao"]);
  assert.equal(rows[1].waited, "10 min");
  assert.equal(rows[0].waited, "1 h");
  assert.equal(rows[0].kind, "task");
  assert.equal(rows[0].state, "ward");
});

test("nurse rows: due, running, admitting, discharging; later and done tasks are quiet", () => {
  const tasks = [
    task({ id: "a", title: "Dose A", due_ms: T }),
    task({ id: "b", title: "Dose B", due_ms: T + H }),
    task({ id: "c", title: "Walk", status: "running", mode: "start_end", began_ms: T - 20 * M }),
    task({ id: "d", title: "Done one", status: "done" }),
  ];
  const rows = queueRows([patient("e1", "Bed 1", view({ tasks }))], "nurse", T);
  assert.deepEqual(rows.map((r) => r.says), ["Dose A \u00b7 due", "Walk \u00b7 running"]);
  const states = queueRows([
    patient("e2", "Bed 2", view({ state: "admitting" })),
    patient("e3", "Bed 3", view({ state: "discharging" })),
  ], "nurse", T);
  assert.deepEqual(states.map((r) => r.says).sort(), ["Complete admission", "Complete discharge"]);
});

test("doctor no longer sees nurse tasks or unacknowledged orders", () => {
  const p = patient("e1", "Bed 1", view({ order_list: [order("o1", T)], tasks: [task({ due_ms: T - H })] }));
  assert.equal(queueRows([p], "doctor", T).length, 0);
});

test("waitingPills name the owner of each item", () => {
  const p = patient("e1", "Bed 1", view({ state: "clinic", order_list: [], handover: { to_nurse: "Nurse Joseph", accepted_by: null }, nudges: [nudge("n1", "nurse", 28 * H), nudge("n2", "patient", 28 * H, "Check in is due.")] }));
  const who = waitingPills([p], 29 * H).map((x) => x.who).sort();
  assert.deepEqual(who, ["Dr. A. Rao", "Nurse", "Nurse Joseph", "Patient"]);
});

test("no produced text gives instructions", () => {
  const p = patient("e1", "Bed 1", view({ state: "clinic", handover: { to_nurse: "Nurse Joseph", accepted_by: null }, tasks: [task({ due_ms: 0 })], order_list: [order("o1", 0)], nudges: [nudge("n1", "nurse", 28 * H)] }));
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
  const p = patient("e1", "Bed 1", view({ state: "clinic", nudges: [nudge("n1", "nurse", 29 * H)] }));
  assert.equal(queueRows([p], "doctor", 40 * H)[0].waited, "");
  const pills = waitingPills([p], 40 * H);
  assert.deepEqual(pills.map((x) => [x.who, x.waited === "", x.late]), [["Nurse", false, true], ["Dr. A. Rao", true, false]]);
});

test("pills and rows carry the stage to open; nudges carry none", () => {
  const handover = { to_nurse: "Nurse Joseph", accepted_by: null };
  const p = (v) => patient("e1", "Bed 1", view(v));
  assert.equal(todos(p({ handover }))[0].stage, "ward");
  const pills = waitingPills([p({ handover, nudges: [nudge("n1", "nurse", 0)] })], H);
  assert.deepEqual(pills.map((x) => String(x.stage)).sort(), ["null", "ward"]);
  assert.equal(queueRows([p({ nudges: [nudge("n1", "nurse", 0)] })], "nurse", H)[0].stage, null);
});

test("pills come from the same rows, named by role, without duplicates", () => {
  const limit = { ...nudge("n9", "nurse", 28 * H), kind: "obs_past_limit" };
  const p = patient("e1", "Bed 1", view({ state: "clinic", order_list: [], nudges: [limit] }));
  const pills = waitingPills([p], 29 * H);
  assert.deepEqual(pills.map((x) => [x.who, x.what]).sort(), [["Dr. A. Rao", "See in clinic"], ["Nurse", "Observations are overdue."]]);
});

test("closed tasks and tasks of patients past the ward stay out of the queue and the strip", () => {
  const due = { id: "t1", title: "Paracetamol", status: "open", mode: "tick", due_ms: 0, done: [] };
  const closed = { ...due, id: "t2", status: "closed", due_ms: null };
  const patients = [
    patient("e1", "Bed 1", view({ state: "discharging", tasks: [closed, due] })),
    patient("e2", "Bed 2", view({ state: "home", tasks: [due] })),
    patient("e3", "Bed 3", view({ state: "ward", tasks: [closed] })),
    patient("e4", "Bed 4", view({ state: "theatre", tasks: [due] })),
    patient("e5", "Bed 5", view({ state: "ward", tasks: [due] })),
  ];
  const rows = queueRows(patients, "nurse", 2 * H).filter((r) => r.kind === "task");
  assert.deepEqual(rows.map((r) => r.bed), ["Bed 5"]);
  assert.deepEqual(waitingPills(patients, 2 * H).filter((p) => p.what.includes("Paracetamol")).map((p) => p.episodeId), ["e5"]);
  assert.equal(taskDue(closed, 2 * H), "closed");
});

const ask = (over) => ({ questions: [], reviews: [], medicines: [], ...over });
const question = (id, to, answer = null) => ({ id, to, text: "Can I take two?", by: "R. Kumar", at_ms: 28 * H, answer });
const review = (id, answer = null) => ({ id, photo: { id: "p1", url: "/p" }, note: "", by: "R. Kumar", at_ms: 29 * H, answer });

test("doctor rows: an open question and an open review, with fixed texts and no question text", () => {
  const p = patient("e1", "Bed 1", view({ state: "home", ask: ask({ questions: [question("q1", "doctor")], reviews: [review("r1")] }) }));
  const rows = queueRows([p], "doctor", 30 * H);
  assert.deepEqual(rows.map((r) => [r.key, r.says, r.lineId, r.kind]).sort(), [
    ["e1:question:q1", "Question from the patient", "q1", "ask"],
    ["e1:review:r1", "Healing photo to review", "r1", "ask"],
  ]);
  assert.doesNotMatch(JSON.stringify(rows), /take two/);
});

test("answered and bot questions give no doctor rows", () => {
  const done = { text: "ok", by: "Dr", at_ms: 29 * H, source: "doctor" };
  const p = patient("e1", "Bed 1", view({
    state: "home",
    ask: ask({ questions: [question("q1", "doctor", done), question("q2", "bot", done), question("q3", "bot")], reviews: [review("r1", { decision: "no_visit" })] }),
  }));
  assert.deepEqual(queueRows([p], "doctor", 30 * H), []);
});

test("a doctor-addressed nudge gives exactly one doctor row", () => {
  const n = { ...nudge("n9", "doctor", 28 * H, "Observations are past the limit."), kind: "obs_past_limit" };
  const rows = queueRows([patient("e1", "Bed 1", view({ nudges: [n] }))], "doctor", 30 * H);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].lineId, "n9");
});

test("the waiting strip names the doctor for a question", () => {
  const p = patient("e1", "Bed 1", view({ state: "home", ask: ask({ questions: [question("q1", "doctor")] }) }));
  const pill = waitingPills([p], 30 * H)[0];
  assert.equal(`${pill.who} → ${pill.what}`, "Dr. A. Rao → Question from the patient");
  assert.equal(pill.lineId, "q1");
});

test("ward tasks pause in theatre", () => {
  const task = { status: "open", due_ms: 0 };
  assert.equal(taskDue(task, 2 * H, "theatre"), "paused");
  assert.equal(taskDue(task, 2 * H, "ward"), "overdue");
  assert.equal(taskDue({ status: "done" }, 2 * H, "theatre"), "done");
  assert.equal(dueLabel("paused"), "paused (in theatre)");
  assert.equal(dueLabel("due"), "due");
});
