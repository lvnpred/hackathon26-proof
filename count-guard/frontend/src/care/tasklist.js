import { hhmm } from "./clock.js";
import { taskDue } from "./derive.js";

const ORDER = { overdue: 0, due: 1, running: 2, later: 3, paused: 3, done: 4, closed: 5 };

// Overdue, due, running, later, done. Within a group the earliest due time comes first.
export function sortTasks(tasks, nowMs) {
  const key = (task) => task.due_ms ?? Infinity;
  return [...tasks].sort((a, b) => ORDER[taskDue(a, nowMs)] - ORDER[taskDue(b, nowMs)] || key(a) - key(b));
}

// Server bounds for an observation set; required fields first.
export const OBS_FIELDS = [
  ["sbp", "SBP", 30, 300, true],
  ["dbp", "DBP", 10, 200, true],
  ["hr", "HR", 20, 250, true],
  ["spo2", "SpO2", 50, 100, false],
  ["temp", "Temp °C", 30, 45, false],
];

// Form strings to { values } or { error }. Blank optional fields are left out.
export function obsValues(form) {
  const values = {};
  for (const [key, label, lo, hi, required] of OBS_FIELDS) {
    const raw = String(form[key] ?? "").trim();
    if (raw === "") {
      if (required) return { error: `${label} is needed.` };
      continue;
    }
    const n = Number(raw);
    if (!Number.isFinite(n) || n < lo || n > hi) return { error: `${label} must be between ${lo} and ${hi}.` };
    values[key] = n;
  }
  return { values };
}

// Surgery times for the current stay: the `when` of its began and ended lines, null when absent.
// Only lines after the latest patient.state count.
export function surgeryNow(timeline) {
  const lines = timeline || [];
  let since = 0;
  lines.forEach((line, i) => { if (line.type === "patient.state") since = i + 1; });
  const when = (type) => lines.slice(since).filter((line) => line.type === type).pop()?.when || null;
  return { began: when("surgery.began"), ended: when("surgery.ended") };
}

// The server lists what a move still needs; a reason is asked only while it appears there.
export function needsReason(move) {
  return (move?.needs || []).some((need) => need.startsWith("reason"));
}

// One line per order item, in order. An item takes the first unused task of the same order
// with the same title (null when none). A task left over is appended.
export function orderLines(order, tasks) {
  const mine = tasks.filter((task) => task.order_id === order.id);
  const used = new Set();
  const lines = (order.items || []).map((item, i) => {
    const task = mine.find((candidate) => !used.has(candidate.id) && candidate.title === item.text) || null;
    if (task) used.add(task.id);
    return { key: task ? task.id : `item-${i}`, text: item.text, task };
  });
  for (const task of mine.filter((candidate) => !used.has(candidate.id))) lines.push({ key: task.id, text: task.title, task });
  return lines;
}

// What happens to an order: its acknowledgement, or what the visit state means for it.
export function orderStatus(order, state) {
  if (order.acknowledged_by) return `Acknowledged by ${order.acknowledged_by}`;
  if (state === "clinic") return "Starts when the patient is admitted";
  if (state === "clinic_done") return "Not started: the visit was closed.";
  return "Waiting for the nurse";
}

// The patient's wording for a task: never "To do", times as HH:MM.
export function patientTaskStatus(task, state, nowMs) {
  if (task.status === "closed") return "Finished";
  if (state === "theatre" && task.status === "open") return "Paused (in theatre)";
  if (task.status === "running") return "Running";
  const done = task.done || [];
  const last = done.length ? hhmm(done[done.length - 1].at_ms) : null;
  if (task.status === "done") return last ? `Done ${last}` : "Done";
  const due = task.due_ms == null ? null : hhmm(task.due_ms);
  if (task.every_h && last) return `${task.kind === "dose" ? "Given" : "Done"} ${last}${due ? ` \u00b7 next due ${due}` : ""}`;
  if (!due) return "";
  return nowMs != null && task.due_ms < nowMs ? `Due since ${due}` : `Due ${due}`;
}
