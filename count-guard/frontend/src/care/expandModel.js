// The Expand view of one model result (care-app clarity §4.2), as pure parts so node --test reads them.
// expandParts(record, view, lens) -> { captured, returned, used, people }:
//   captured — what went in: the recording (playable), the transcript, the photo, the frames (evidence id), the text sent;
//   returned — the model, live / prepared / didn't work / no model, the time taken, the raw reply (staff only);
//   used     — what the app read or drafted from it, and anything that stood in for a reply it could not use;
//   people   — what a person did with it (provenance.js), with the before -> after when they changed it.
// A record is an event's model record (GET …/events/{id}/model), a call's reply (a heard recording, a sample try) or a
// view row (a camera check, a moment). It reads the record's `evidence` (Task 3) first, then its calls and source words.
// The patient lens names no model, shows no raw reply and no calls (C2).
import { newMoment, outcomeOf } from "./stepOutcome.js";
import { proofLabel } from "./verdict.js";
import { sentenceText } from "./orders.js";
import { drugLine } from "./theatreLive.js";
import { itemName } from "./evidence.js";
import { MATCH_LABEL } from "./drafts.js";
import { peopleOf, plainValue } from "./expandPeople.js";

export { plainValue };

export const PARTS = [
  { key: "captured", title: "Captured" },
  { key: "returned", title: "Model returned" },
  { key: "used", title: "How the app used it" },
  { key: "people", title: "What a person did" },
];

const NAMES = { sam: "SAM 3.1", spark: "Spark 1.3", "spark-open": "Spark Open", voice: "Muse Voice" };
const STOOD_IN = { rules: "drafted by rules", template: "template used", prepared: "prepared result used" };
const STAFF_MODE = { sample: "Bundled sample text (no model call)", live: "Live", prepared: "Prepared (no live model)", failed: "Didn't work", none: "No model used — rules", unknown: "Done" };
const PATIENT_MODE = { live: "Done", prepared: "Prepared (no live model)", failed: "Didn't work", none: "Worked out from your record", fallback: "Done", unknown: "Done" };

// A moment as an Expand record: read back by its event id (a day plan's id is not an event, so it is shown as it is).
export const momentRecord = (m) => (m ? { ...m, ...(/^[\w-]+$/.test(String(m.id)) ? { eventId: m.id } : {}) } : null);
// The run(fn, { record }) pick for a call that returns the whole view: the moment it added, of one of `caps`.
export const newMomentRecord = (before, caps) => (after) => momentRecord(newMoment(before, after, caps));

// A Try-sample reply on the AI page (POST /journey/ai/try/{model}) as an Expand record. Its `evidence` there is the
// sample's picture sidecar, not a model point's evidence, so it moves to `sample`.
const SAMPLE_INPUT = { voice: "The bundled sample recording", spark: "The bundled sample monitor photo", sam: "The bundled sample tray photo",
  "spark-open": "The bundled sample camera case" };
export const tryRecord = (key) => (out) => (out ? { type: "ai.try", model: key, mode: out.mode, text: out.text, sample: out.evidence || null } : null);

// The patient lens asks the server to leave out the raw reply, the text sent and the calls (they never reach a patient).
export const recordUrl = (episodeId, eventId, lens = "staff") =>
  `/journey/episodes/${episodeId}/events/${eventId}/model${lens === "patient" ? "?lens=patient" : ""}`;
const audioUrl = (ep, id) => (ep && id ? `/journey/episodes/${ep}/audio/${id}` : null);
const photoUrl = (ep, id) => (ep && id ? `/journey/episodes/${ep}/photos/${id}` : null);
const seconds = (ms) => (Number.isFinite(ms) ? `${(Math.round(ms / 100) / 10).toFixed(1)} s` : null);
function capturedOf(r, ev, ep, patient) {
  const c = ev?.captured || {};
  const transcript = c.transcript ?? r.transcript ?? (r.heard_by && r.heard_by !== "typed" ? r.text : undefined);
  let note = null;
  if (r.type === "ai.try") note = SAMPLE_INPUT[r.model] || "A bundled sample";
  else if (r.type === "camera.ran") note = r.scenario ? "The recorded theatre clip" : r.source === "prepared" ? "The recorded swab count" : "The theatre video";
  else if (r.type === "camera.replayed") note = "The recorded swab count";
  else if (c.case_id) note = "The camera case: every swab seen out and back";
  else if (r.media) note = r.media === "photos" ? "The photos sent" : "The video clip sent";
  return {
    audio: audioUrl(ep, c.audio_id ?? r.audio_id),
    transcript: transcript ?? null,
    answer: c.answer ?? null,
    typed: Boolean(c.typed || r.heard_by === "typed"),
    photo: r.evidence_id ? null : photoUrl(ep, c.photo_id ?? r.photo_id), // a kept sidecar shows the photo with its boxes
    evidenceId: r.evidence_id || null,
    expect: c.expect ?? null,
    facts: (c.facts || []).map((f) => (typeof f === "string" ? f : plainValue(f))),
    sent: patient ? null : c.text ?? null,
    note,
  };
}

function outcome(r, ev) {
  if (r.type === "ai.try") {
    const calls = r.sample?.calls || [];
    const mode = r.mode === "Sample" ? "sample" : ["live", "prepared", "failed"].includes(r.mode) ? r.mode : "unknown";
    return { mode, model: mode === "sample" ? null : NAMES[r.model] || null, ms: calls[calls.length - 1]?.ms, calls };
  }
  const out = outcomeOf(ev ? { evidence: ev } : r) || { mode: "unknown" };
  const calls = ev?.calls || r.calls || [];
  const last = calls[calls.length - 1];
  const ms = ev?.returned?.ms ?? last?.ms;
  return { ...out, model: out.model || ev?.returned?.model || NAMES[last?.model] || null, ms, calls };
}

function fallbackText(out, used, patient) {
  const stood = used?.fallback || out.fallback;
  if (!stood || (out.mode !== "fallback" && out.mode !== "failed" && out.mode !== "none")) return null;
  if (patient) return "The app used its standard wording.";
  const what = STOOD_IN[stood] || `${stood} used`;
  const head = out.mode === "none" ? `No model used — ${what}` : `${out.model ? `${out.model} reply` : "Reply"} not usable — ${what}`;
  return used?.why ? `${head} (${used.why})` : head;
}

function returnedOf(r, ev, out, patient) {
  if (patient) return { model: null, modeText: PATIENT_MODE[out.mode] || "Done", seconds: null, raw: null, calls: [] };
  const fell = out.mode === "fallback" ? `${out.model ? `${out.model} reply` : "Reply"} not usable — ${STOOD_IN[out.fallback] || `${out.fallback} used`}` : null;
  const model = out.model && out.model !== "rules" ? out.model : null;
  return {
    model: out.mode === "none" ? null : model,
    modeText: fell || STAFF_MODE[out.mode] || "Done",
    seconds: seconds(out.ms),
    raw: ev?.returned?.raw ?? null,
    calls: out.calls.map((c) => ({ model: NAMES[c.model] || String(c.model || "model").replaceAll("_", " "), modeText: STAFF_MODE[outcomeOf({ calls: [c] })?.mode] || "Didn't work", seconds: seconds(c.ms) })),
  };
}

function rowLines(r) {
  const lines = r.finding ? [r.finding] : []; // a moment's one-line finding
  for (const row of r.rows || []) if (row.concept && row.planned != null) lines.push(`${itemName(row)}: ${row.seen ?? 0} of ${row.planned} seen`);
  if (r.missing?.length) lines.push(`Missing: ${r.missing.join(", ")}`);
  if (r.match && MATCH_LABEL[r.match] && !r.rows) lines.push(r.why ? `${MATCH_LABEL[r.match]} — ${r.why}` : MATCH_LABEL[r.match]);
  else if (r.why && r.rows) lines.push(r.why);
  if (r.generic || r.name_as_read) lines.push(`Read: ${[r.generic || r.name_as_read, r.strength].filter(Boolean).join(" ")}`);
  if (typeof r.read === "string" && r.read) lines.push(`Read: ${r.read}`);
  if (r.values_read) lines.push(`Read from the monitor: ${plainValue(r.values_read)}`);
  for (const a of r.advice || []) if (a.text) lines.push(a.text);
  if (r.type === "count.camera" && r.count != null) lines.push(`Camera read ${r.count} swabs back — advice only; the count a person saves decides`);
  if (r.type === "ai.try") {
    if (r.text) lines.push(r.text);
    for (const row of r.sample?.rows || []) if (row.concept && row.planned != null) lines.push(`${itemName(row)}: ${row.seen ?? 0} of ${row.planned} seen`);
    lines.push("Nothing is written to any record.");
  }
  if (r.type === "camera.ran" && !(r.advice || []).length) lines.push("The camera found nothing to check.");
  return lines;
}

function usedLines(u, r) {
  if (!u) return rowLines(r);
  const lines = [];
  for (const item of u.items || []) lines.push(sentenceText(item));
  for (const s of u.sections || []) if (s?.text) lines.push(`${s.heading}: ${s.text}`);
  if (u.verdict) lines.push(proofLabel({ verdict: u.verdict, why: u.why }));
  if (u.heard_as === "drug" && u.row) lines.push(`Heard as a drug: ${drugLine(u.row)}`);
  if (u.heard_as === "pack" && u.row) lines.push(`Heard as a pack of ${u.row.n}`);
  if (u.values) lines.push(`Values: ${plainValue(u.values)}`);
  if (typeof u.answer === "string") lines.push(`Answer sent: ${u.answer}`);
  if (typeof u.text === "string" && u.text) lines.push(u.text);
  if (typeof u.summary === "string" && u.summary) lines.push(u.summary);
  (u.lines || []).forEach((line, i) => line?.text && lines.push(`${i + 1}. ${line.text}`));
  if (typeof u.reason === "string" && u.reason) lines.push(`Reason: ${u.reason}`);
  return lines.length ? lines : rowLines(r);
}

export function expandParts(record, view, lens = "staff") {
  const r = record || {};
  const ev = r.evidence && typeof r.evidence === "object" && r.evidence.returned ? r.evidence : null; // Task 3 evidence only
  const patient = lens === "patient";
  const ep = view?.episode?.id || r.episode_id || null;
  const out = outcome(r, ev);
  return {
    captured: capturedOf(r, ev, ep, patient),
    returned: returnedOf(r, ev, out, patient),
    used: { lines: usedLines(ev?.used, r), fallback: fallbackText(out, ev?.used, patient) },
    people: peopleOf(r, ev, view),
  };
}
