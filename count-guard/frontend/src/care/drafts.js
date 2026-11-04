import { hhmm } from "./clock.js";
import { displayName } from "./names.js";
import { blankRow } from "./orders.js";
import { obsValues } from "./tasklist.js";
import { proposalByModel } from "./provenance.js";

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
  return items.filter((item) => item.kind !== "unclear").map((item) => { // words not understood are never a row
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
const OBS_KEYS = ["sbp", "dbp", "hr", "spo2", "temp"];

// Spoken values as the strings the row's ObsForm holds: { sbp: 120 } -> { sbp: "120" } (clarity §4.5).
export const rowForm = (values) => Object.fromEntries(Object.entries(values || {})
  .filter(([k, v]) => OBS_KEYS.includes(k) && v !== null && v !== "" && Number.isFinite(Number(v))).map(([k, v]) => [k, String(v)]));

// Where a spoken completion lands (clarity §4.5): an observation fills its own row's form; a task with photo proof
// opens Confirm task (photo proofs only); any other task waits on its own row button.
export const voiceTarget = (task) => (task.kind === "obs" ? "form" : task.proof === "photo" ? "proof" : "row");

// proposed: the heard values the AI proposed; edited/heardText: heard words the person changed (clarity §4.3).
export function doneBody({ task, via, transcript, form, photo, heardBy, proposed = null, edited = false, heardText = "" }) {
  const said = (transcript || "").trim();
  if (via === "voice" && !said) return { error: "A completion by voice needs what was said." };
  const body = { via, transcript: said, note: "" };
  if (via === "voice" && heardBy) {
    body.heard_by = heardBy;
    if (edited) Object.assign(body, { edited: true, heard_text: heardText });
  }
  if (task.kind === "obs") {
    const out = obsValues(form || {});
    if (out.error) return { error: out.error };
    body.values = out.values;
    const heard = Object.entries(proposed || {}).filter(([k, v]) => OBS_KEYS.includes(k) && Number.isFinite(Number(v)) && v !== "" && v !== null);
    if (via === "voice" && heard.length) body.proposed_values = Object.fromEntries(heard.map(([k, v]) => [k, Number(v)]));
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
    ai: proposalByModel(proposal), // "Proposed by AI" only when a model made the values (clarity §4.3)
  };
}
