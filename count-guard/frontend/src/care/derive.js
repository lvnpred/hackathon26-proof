import { SAFETY } from "./alerts.js";
import { H, M } from "./clock.js";
import { RANK } from "./rank.js";

const OVERDUE = ["dose_overdue", "obs_overdue"];

// What each role is waiting on, derived from the journey views. No advice text lives here.
const DOCTOR = "Dr. A. Rao";
const ROLE_NAME = { nurse: "Nurse", patient: "Patient", doctor: DOCTOR };

// "2 h 20 min", "2 h", "5 min".
export function waitedText(ms) {
  const total = Math.max(0, Math.floor(ms / M));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function base(patient) {
  return { episodeId: patient.id, bed: patient.bed, name: patient.name };
}

export const STATE_LABEL = {
  clinic: "In clinic",
  clinic_done: "Clinic visit closed",
  admitting: "Being admitted",
  ward: "On the ward",
  theatre: "In theatre",
  discharging: "Being discharged",
  home: "Home",
};

const GRACE = 30 * M;

// "running" | "overdue" | "due" | "later" | "done" | "closed" | "paused". Overdue starts 30 min after the due time (v1 grace).
// An open ward task is "paused" while the patient is in theatre.
export function taskDue(task, nowMs, state) {
  if (task.status === "closed") return "closed";
  if (task.status === "done") return "done";
  if (task.status === "running") return "running";
  if (state === "theatre") return "paused";
  if (task.due_ms == null || task.due_ms > nowMs) return "later";
  return task.due_ms + GRACE < nowMs ? "overdue" : "due";
}

// The word on a task pill. Only "paused" reads differently from its key.
export const dueLabel = (due) => (due === "paused" ? "paused (in theatre)" : due);


// waitedMs -1 means the view carries no time for the row.
function row(patient, key, kind, says, extra) {
  return {
    ...base(patient),
    key: `${patient.id}:${key}`,
    kind,
    says,
    waited: "",
    lineId: null,
    action: null,
    stage: null,
    state: patient.view.state,
    waitedMs: -1,
    rank: RANK.due,
    ...extra,
  };
}

function timed(nowMs, sinceMs) {
  return { waited: waitedText(nowMs - sinceMs), waitedMs: nowMs - sinceMs };
}

// Handover is the one v1 to-do kept: the view still carries it.
export function todos(patient) {
  const { handover } = patient.view;
  if (!handover || handover.accepted_by) return [];
  const says = `Handover to ${handover.to_nurse} not accepted`;
  return [row(patient, `todo:${says}`, "todo", says, { owner: handover.to_nurse, role: "nurse", stage: "ward" })];
}

function nudgeRows(patient, nowMs) {
  return (patient.view.nudges || []).map((nudge) =>
    row(patient, `nudge:${nudge.id}`, "nudge", nudge.says, {
      ...timed(nowMs, nudge.at_ms),
      lineId: nudge.id,
      staffSays: nudge.says_staff || nudge.says,
      to: nudge.to,
      owner: ROLE_NAME[nudge.to] || nudge.to,
      role: nudge.to,
      nudgeKind: nudge.kind,
      rank: SAFETY.includes(nudge.kind) ? RANK.danger : OVERDUE.includes(nudge.kind) ? RANK.late : RANK.due,
    }),
  );
}

function doctorRows(patient, nowMs) {
  const { state, order_list: orders = [] } = patient.view;
  const rows = [];
  if (state === "clinic") rows.push(row(patient, "clinic", "state", "See in clinic", { owner: DOCTOR, role: "doctor", rank: RANK.blocked }));
  if (state === "ward" && !orders.length) {
    rows.push(row(patient, "no-orders", "state", "No orders signed", { owner: DOCTOR, role: "doctor", rank: RANK.blocked }));
  }
  const pastLimit = nudgeRows(patient, nowMs)
    .filter((r) => r.nudgeKind === "obs_past_limit")
    .map((r) => ({ ...r, role: "doctor", owner: DOCTOR }));
  return [...rows, ...askRows(patient, nowMs), ...pastLimit];
}

// Open questions to the doctor and healing photos to review. The question text stays on the chart.
function askRows(patient, nowMs) {
  const { questions = [], reviews = [] } = patient.view.ask || {};
  const open = (key, id, at_ms, says) =>
    row(patient, `${key}:${id}`, "ask", says, { ...timed(nowMs, at_ms), lineId: id, owner: DOCTOR, role: "doctor", rank: RANK.due });
  return [
    ...questions.filter((q) => q.to === "doctor" && !q.answer).map((q) => open("question", q.id, q.at_ms, "Question from the patient")),
    ...reviews.filter((r) => !r.answer).map((r) => open("review", r.id, r.at_ms, "Healing photo to review")),
  ];
}

function nurseRows(patient, nowMs) {
  const { state, order_list: orders = [], tasks = [] } = patient.view;
  const rows = [];
  // Orders signed in clinic wait for the admission; the server refuses an earlier acknowledgement.
  const ackable = ["admitting", "ward"].includes(state) ? orders : [];
  for (const order of ackable.filter((o) => !o.acknowledged_by)) {
    rows.push(row(patient, `order:${order.id}`, "order", `New orders from ${order.by}`, {
      ...timed(nowMs, order.at_ms), owner: "Nurse", role: "nurse", rank: RANK.blocked,
    }));
  }
  // Recurring tasks belong to the ward stay: none appear once the patient is discharging, home or in theatre.
  const taskStates = ["ward", "admitting"];
  for (const task of taskStates.includes(state) ? tasks : []) {
    const due = taskDue(task, nowMs);
    if (due === "overdue" || due === "due") {
      rows.push(row(patient, `task:${task.id}`, "task", `${task.title} \u00b7 due`, {
        ...timed(nowMs, task.due_ms), owner: "Nurse", role: "nurse", rank: due === "overdue" ? RANK.late : RANK.due,
      }));
    } else if (due === "running") {
      rows.push(row(patient, `task:${task.id}`, "task", `${task.title} \u00b7 running`, {
        ...(task.began_ms == null ? {} : timed(nowMs, task.began_ms)), owner: "Nurse", role: "nurse", rank: RANK.running,
      }));
    }
  }
  if (state === "admitting") rows.push(row(patient, "admitting", "state", "Complete admission", { owner: "Nurse", role: "nurse", rank: RANK.blocked }));
  if (state === "discharging") rows.push(row(patient, "discharging", "state", "Complete discharge", { owner: "Nurse", role: "nurse", rank: RANK.blocked }));
  return rows;
}

// Every row for a role. Patients get nudges only; their queue page stays empty (Today / My care).
export function rowsFor(patient, role, nowMs) {
  const nudges = nudgeRows(patient, nowMs).filter((r) => r.to === role);
  if (role === "doctor") {
    const seen = new Set();
    return [...doctorRows(patient, nowMs), ...nudges].filter((r) => !seen.has(r.key) && seen.add(r.key));
  }
  if (role === "nurse") return [...nurseRows(patient, nowMs), ...nudges, ...todos(patient)];
  return nudges;
}

function sorted(rows) {
  return rows.sort((a, b) => a.rank - b.rank || b.waitedMs - a.waitedMs);
}

function strip({ waitedMs, to, owner, role, rank, nudgeKind, ...rest }) {
  return rest;
}

export function queueRows(patients, role, nowMs) {
  if (role === "patient") return [];
  const rows = patients.flatMap((patient) => rowsFor(patient, role, nowMs));
  return sorted(rows).map(strip);
}

// `role` is the viewer: staff read a nudge's staff wording, the patient reads `says`.
export function waitingPills(patients, nowMs, role) {
  // Nurse first, so a nudge the doctor also sees keeps its own recipient.
  const seen = new Set();
  const rows = ["nurse", "patient", "doctor"]
    .flatMap((role) => patients.flatMap((patient) => rowsFor(patient, role, nowMs)))
    .filter((r) => !seen.has(r.key) && seen.add(r.key));
  const names = Object.fromEntries(patients.map((patient) => [patient.id, patient.name]));
  return sorted(rows).map((r) => ({
    key: r.key,
    name: names[r.episodeId] || "",
    who: r.owner,
    role: r.role,
    what: role === "patient" ? r.says : r.staffSays || r.says,
    waited: r.waited,
    late: r.waitedMs >= H,
    episodeId: r.episodeId,
    lineId: r.lineId,
    stage: r.stage,
    nudgeKind: r.nudgeKind,
  }));
}

// The nurse's theatre screen shows the tray result in her Tray check card, once (CL-R2).
export function trayOnNurseCard(role, state) {
  return role === "nurse" && state === "theatre";
}

// The banner's tray flag shows only while the patient is in theatre (a stale flag on the ward or
// home chart confuses), and not to the nurse, whose card already shows it (CL-R2, CL-R9).
export function showTrayFlag(role, state) {
  return state === "theatre" && !trayOnNurseCard(role, state);
}
