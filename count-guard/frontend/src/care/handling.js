import { whenText } from "./when.js";
import { displayName } from "./names.js";

// Words and shapes for the AI handling strip, proposals and feed. Pure, so node can test them.
export const STAFF_BY = { doctor: "Dr. A. Rao (synthetic)", nurse: "Nurse Meena (synthetic)" };
export const THEATRE_NURSE = "Nurse Asha (synthetic)";
export const OPS_SCOPE = "/ops/";

// Who acts for the role on this chart: the nurse in theatre is Nurse Asha, as in NurseActions; else the role's name.
export const staffBy = (role, view) => (role === "nurse" && view?.state === "theatre" ? THEATRE_NURSE : STAFF_BY[role]);

// The human action for a paused task, from its kind; the reason sentence is the fallback.
const PAUSED_ACTIONS = { ack_order: "Acknowledge order" };
const pausedText = (r) => PAUSED_ACTIONS[r.kind] || `${displayName(r.reason)} · ${r.paused_note}`;
export const PAUSED_TITLE = "Waiting for a person";
// While the agent is paused: what it would have done, each as "{reason} · Paused · not done". Staff only.
export const pausedRows = (ops, role) =>
  role === "patient" ? [] : (ops?.open || []).filter((r) => r.paused_note)
    .map((r) => ({ workId: r.work_id, text: pausedText(r) }));

export const stripTitle = (n) => `AI is handling · ${n}`;
const LEVELS = {
  L2: "The AI did this on its own, and you can undo it.",
  L1: "The AI proposed this and waited for a person to approve it.",
  L3: "The AI only told someone about this.",
};
export const levelWords = (level) => LEVELS[level] || "The AI handled this by its rules.";
// Undone rows stay listed but do not count as live.
export const liveCount = (ops) => (ops?.handling || []).filter((r) => r.status !== "undone").length;

export const adminTitle = (n) => `AI admin for this patient · ${n}`;
export const foldTitle = (done) => `AI did ${done.length} admin task${done.length === 1 ? "" : "s"} · Review`;

// Rows with a live Undo stay open; once every window has closed they fold. A row moved into the Now card is left out.
export function handlingState(ops, nowMs, role, movedWork = null) {
  const rows = handlingRows(ops, nowMs).filter((r) => r.workId !== movedWork);
  return {
    open: rows.filter((r) => r.undo), done: rows.filter((r) => !r.undo),
    paused: pausedRows(ops, role), proposals: proposalsFor(ops, role),
  };
}

export const needsTitle = (n) => `Needs you · ${n}`;

export function undoLabel(untilMs, nowMs) {
  if (untilMs == null || nowMs >= untilMs) return "";
  return `Undo · ${Math.ceil((untilMs - nowMs) / 60000)} min`;
}

const toRow = (r, nowMs) => {
  const undone = r.status === "undone";
  return {
    workId: r.work_id, text: displayName(r.summary), when: whenText(r.at_ms, nowMs), level: r.level, undone,
    undo: undone ? "" : undoLabel(r.undo_until_ms, nowMs),
  };
};

// Undone rows stay in the list, marked, so the strip can show "Undone".
export const handlingRows = (ops, nowMs) => (ops?.handling || []).map((r) => toRow(r, nowMs));

export const proposalsFor = (ops, role) =>
  role === "patient" ? [] : (ops?.proposals || []).filter((p) => p.owner_role === role);

export const citedLine = (cited) => ((cited || []).length ? `From: ${cited.map((c) => c.text).join("; ")}` : "");

// One moment the Inspector can open by id. A row is a handling row or a proposal; patient_finding stays null so a patient never sees it.
export function agentMoment(row, episodeId) {
  const proposal = row.sentence != null;
  const reason = row.reason || "";
  const inputs = row.inputs || [];
  const level = row.level ?? null;
  const undoUntilMs = row.undo_until_ms ?? null;
  const workId = row.work_id;
  const spark = row.model === "spark";
  return {
    id: workId, kind: "agent", capability: "ops", at_ms: row.at_ms,
    title: displayName(proposal ? row.sentence : row.summary),
    finding: reason, patient_finding: null,
    status: proposal ? "open" : row.status === "undone" ? "undone" : "recorded",
    owner: proposal ? row.owner_role : null,
    // The reword names the same model and mode modelChip reads elsewhere: "Spark 1.3 · live".
    calls: spark ? [{ model: "spark", source: "muse-spark-1.3" }] : [], handmade: false,
    written: row.written || [], source: spark ? "spark" : "rules",
    refs: { workId, episodeId, reason, inputs, level, undoUntilMs },
    workId, episodeId, reason, inputs, level, undoUntilMs,
  };
}

export const agentMoments = (ops, episodeId) =>
  [...(ops?.handling || []), ...(ops?.proposals || [])].map((r) => agentMoment(r, episodeId));

export const isFeed = (out) => Array.isArray(out?.items);

export const feedRows = (feed, nowMs) =>
  (feed?.items || []).map((r) => ({ ...toRow(r, nowMs), episodeId: r.episode_id, patient: displayName(r.patient) }));

// Under the status menu: the live handling rows per patient, then the role's proposals.
export function myPatientsStrip(patients, role) {
  const rows = [];
  const proposals = [];
  if (role === "patient") return { rows, proposals };
  for (const patient of patients || []) {
    const name = displayName(patient.name);
    const ops = patient.view?.ops;
    const live = (ops?.handling || []).filter((r) => r.status !== "undone");
    const newest = live.reduce((best, r) => (best == null || r.at_ms > best.at_ms ? r : best), null);
    if (newest) rows.push({ episodeId: patient.id, name, text: toRow(newest, 0).text });
    for (const p of proposalsFor(ops, role)) proposals.push({ episodeId: patient.id, name, p, view: patient.view });
  }
  return { rows, proposals };
}
