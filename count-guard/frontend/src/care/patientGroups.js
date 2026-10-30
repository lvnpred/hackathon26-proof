import { hhmm } from "./clock.js";
import { nudgeLabel } from "./askText.js";
import { STATE_LABEL, rowsFor } from "./derive.js";
import { displayName } from "./names.js";

const REASON = { question: "Question", review: "Healing photo", clinic: "See in clinic", "no-orders": "No orders signed" };
const TASK_WORD = { obs: "obs", dose: "dose" };

const lower = (s) => s.charAt(0).toLowerCase() + s.slice(1);

// "Question + healing photo": the distinct reasons behind a patient's doctor rows, in row order.
export function reasonText(rows) {
  const parts = rows.map((row) => {
    const kind = row.key.split(":")[1];
    return kind === "nudge" ? nudgeLabel(row.nudgeKind) : REASON[kind] || kind;
  });
  return [...new Set(parts)].map((part, i) => (i ? lower(part) : part)).join(" + ");
}

// What happens next when nothing waits on the doctor: the nurse's next timed task, else the NEXT sentence.
export function nextForOthers(patient, nowMs) {
  const timed = (patient.view.tasks || []).filter((t) => t.status === "open" && t.due_ms != null).sort((a, b) => a.due_ms - b.due_ms)[0];
  if (timed) return `Nurse ${TASK_WORD[timed.kind] || "task"} due ${hhmm(timed.due_ms)}`;
  return displayName(patient.view.now_next?.next);
}

export function patientGroups(patients, nowMs) {
  const waiting = [];
  const quiet = [];
  for (const patient of patients) {
    const rows = rowsFor(patient, "doctor", nowMs);
    const out = { episodeId: patient.id, bed: patient.bed, name: displayName(patient.name), state: STATE_LABEL[patient.view.state] || patient.view.state, reason: "", waited: "", next: "" };
    if (!rows.length) {
      quiet.push({ ...out, next: nextForOthers(patient, nowMs) });
      continue;
    }
    const longest = rows.reduce((a, b) => (b.waitedMs > a.waitedMs ? b : a));
    waiting.push({ ...out, reason: reasonText(rows), waited: longest.waited, waitedMs: longest.waitedMs });
  }
  waiting.sort((a, b) => b.waitedMs - a.waitedMs);
  quiet.sort((a, b) => String(a.bed).localeCompare(String(b.bed), undefined, { numeric: true }));
  return { waiting: waiting.map(({ waitedMs, ...row }) => row), quiet };
}

export const statusWord = (status) => ({ available: "Available", busy: "Busy", in_theatre: "In theatre" })[status?.status] || "Status";
