import { taskDue } from "./derive.js";

const ORDER = { overdue: 0, due: 1, running: 2, later: 3, done: 4, closed: 5 };

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
