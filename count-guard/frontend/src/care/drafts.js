import { hhmm } from "./clock.js";
import { displayName } from "./names.js";
import { blankRow } from "./orders.js";
import { obsValues } from "./tasklist.js";

export const MATCH_LABEL = {
  ok: "Photo matches the task",
  mismatch: "Flagged: the photo does not match. The nurse decides.",
  none: "Photo kept, not checked",
};

// True when a draft with an id we have not loaded yet has appeared (drives the prefill effects).
export function draftChanged(prevId, draft) {
  return Boolean(draft?.id) && draft.id !== prevId;
}

const text = (value) => (value === null || value === undefined ? "" : String(value));

// The inverse of orderRowsToItems: numbers become the strings a form holds.
export function itemsToRows(items) {
  return items.map((item) => {
    const row = { ...blankRow(item.kind || "other") };
    row.text = text(item.text);
    row.name = text(item.name);
    row.amount = text(item.amount);
    row.every_h = text(item.every_h);
    if (item.mode) row.mode = item.mode;
    if (item.proof) row.proof = item.proof;
    row.sbp_min = text(item.limits?.sbp_min);
    row.sbp_max = text(item.limits?.sbp_max);
    return row;
  });
}

export function sectionsToSummary(sections) {
  return sections.map((s) => `${s.heading}: ${s.text}`).join("\n");
}

// The tasks a spoken completion may mean. No candidates: offer every open task. One: no pick needed.
export function proposalChoices(proposal, tasks) {
  const candidates = proposal?.candidates || [];
  const choices = candidates.length ? candidates : tasks.filter((t) => t.status === "open" || t.status === "running");
  return { choices, pick: choices.length !== 1 };
}

export function newestPhoto(view, taskId) {
  const photos = (view?.photos || []).filter((p) => taskId === null || p.task_id === taskId);
  return photos.length ? photos[photos.length - 1] : null;
}

// The body for POST /tasks/{id}/done (without `by`), or { error }. Mirrors the server's DoneIn rules.
export function doneBody({ task, via, transcript, form, photo, heardBy }) {
  const said = (transcript || "").trim();
  if (via === "voice" && !said) return { error: "A completion by voice needs what was said." };
  const body = { via, transcript: said, note: "" };
  if (via === "voice" && heardBy) body.heard_by = heardBy;
  if (task.kind === "obs") {
    const out = obsValues(form || {});
    if (out.error) return { error: out.error };
    body.values = out.values;
  }
  if (photo) body.proof_id = photo.id;
  return { body };
}

// What a done entry shows: spoken or tapped, its photo (if still on the chart) and whether it was flagged.
export function proofOf(done, photos) {
  const photo = done.proof_id ? (photos || []).find((p) => p.id === done.proof_id) || null : null;
  return { voice: done.via === "voice", typed: done.via === "text", photo, flagged: done.match === "mismatch" };
}

// The muted line under a task row: its last completion, who did it and how, with the photo match.
export function lastDoneLine(task, photos) {
  const d = (task.done || []).slice(-1)[0];
  if (!d) return null;
  const proof = proofOf(d, photos);
  const how = proof.voice ? "by voice" : proof.typed ? "typed" : "by tap";
  return {
    text: `Last done ${hhmm(d.at_ms)} by ${displayName(d.by)}, ${how}`,
    match: d.match ? MATCH_LABEL[d.match] || MATCH_LABEL.none : null,
    flagged: proof.flagged,
    evidenceId: d.evidence_id || null,
  };
}

// A row's spoken completion is pinned to that row's task; only an observation keeps spoken values.
export function rowSession(proposal, task) {
  return {
    proposal: { candidates: [task], values: task.kind === "obs" ? proposal.values || {} : {} },
    via: proposal.heard_by === "typed" ? "text" : "voice",
    transcript: proposal.transcript || "",
    source: proposal.source,
    heardBy: proposal.heard_by,
  };
}
