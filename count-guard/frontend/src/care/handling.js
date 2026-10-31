import { hhmm } from "./clock.js";
import { displayName } from "./names.js";

// Words and shapes for the AI handling strip, proposals and feed. Pure, so node can test them.
export const STAFF_BY = { doctor: "Dr. A. Rao (synthetic)", nurse: "Nurse Meena (synthetic)" };
export const OPS_SCOPE = "/ops/";

export const stripTitle = (n) => `AI is handling · ${n}`;
export const needsTitle = (n) => `Needs you · ${n}`;

export function undoLabel(untilMs, nowMs) {
  if (untilMs == null || nowMs >= untilMs) return "";
  return `Undo (${Math.ceil((untilMs - nowMs) / 60000)} min)`;
}

const toRow = (r, nowMs) => {
  const undone = r.status === "undone";
  return {
    workId: r.work_id, text: displayName(r.summary), when: hhmm(r.at_ms), level: r.level, undone,
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
  return {
    id: workId, kind: "agent", capability: "ops",
    title: displayName(proposal ? row.sentence : row.summary),
    finding: reason, patient_finding: null,
    status: proposal ? "open" : row.status === "undone" ? "undone" : "recorded",
    owner: proposal ? row.owner_role : null,
    calls: [], handmade: false, written: [], source: "rules",
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
    for (const p of proposalsFor(ops, role)) proposals.push({ episodeId: patient.id, name, p });
  }
  return { rows, proposals };
}
