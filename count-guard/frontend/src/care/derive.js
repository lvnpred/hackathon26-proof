import { H, M } from "./clock.js";

// What each role is waiting on, derived from the journey views. No advice text lives here.
const DOCTOR = "Dr. A. Rao";
const ROLE_NAME = { nurse: "Nurse", patient: "Patient", doctor: DOCTOR };

// "2 h 20 min", "2 h", "5 min".
function waitedText(ms) {
  const total = Math.max(0, Math.floor(ms / M));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function base(patient) {
  return { episodeId: patient.id, bed: patient.bed, name: patient.name };
}

// The view carries no time for a to-do, so it has no waited text and sorts after every nudge.
export function todos(patient) {
  const { view } = patient;
  const make = (says, owner, role, stage) => ({
    ...base(patient),
    key: `${patient.id}:todo:${says}`,
    kind: "todo",
    says,
    waited: "",
    lineId: null,
    action: null,
    owner,
    role,
    stage,
    waitedMs: -1,
  });
  const rows = [];
  if (view.rx && !view.orders) rows.push(make("Ward orders not set", DOCTOR, "doctor", "clinic"));
  if (view.orders && !view.card) rows.push(make("Discharge card not signed", DOCTOR, "doctor", "clinic"));
  if (view.handover && !view.handover.accepted_by) {
    rows.push(make(`Handover to ${view.handover.to_nurse} not accepted`, view.handover.to_nurse, "nurse", "ward"));
  }
  return rows;
}

function nudgeRows(patient, nowMs) {
  return (patient.view.nudges || []).map((nudge) => ({
    ...base(patient),
    key: `${patient.id}:nudge:${nudge.id}`,
    kind: "nudge",
    says: nudge.says,
    waited: waitedText(nowMs - nudge.at_ms),
    lineId: nudge.id,
    stage: null,
    action: null,
    to: nudge.to,
    waitedMs: nowMs - nudge.at_ms,
  }));
}

function strip({ waitedMs, to, owner, role, ...row }) {
  return row;
}

export function queueRows(patients, role, nowMs) {
  // Doctor: to-dos only. Nurse: nudges plus the nurse's to-dos. Patient: nudges only.
  const rows = patients.flatMap((patient) => [
    ...(role === "doctor" ? [] : nudgeRows(patient, nowMs).filter((row) => row.to === role)),
    ...todos(patient).filter((row) => row.role === role),
  ]);
  return rows.sort((a, b) => b.waitedMs - a.waitedMs).map(strip);
}

export function waitingPills(patients, nowMs) {
  const pills = patients.flatMap((patient) => [
    ...nudgeRows(patient, nowMs).map((row) => ({ row, who: ROLE_NAME[row.to] || row.to, what: row.says })),
    ...todos(patient).map((row) => ({ row, who: row.owner, what: row.says })),
  ]);
  return pills
    .sort((a, b) => b.row.waitedMs - a.row.waitedMs)
    .map(({ row, who, what }) => ({
      key: row.key,
      who,
      what,
      waited: row.waited,
      late: row.waitedMs >= H,
      episodeId: row.episodeId,
      lineId: row.lineId,
      stage: row.stage,
    }));
}
