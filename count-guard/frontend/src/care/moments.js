// Pure helpers for AI moment lines (C3, C4). JSX only renders what these return.
import { MODEL_NAME, modeWord } from "./evidence.js";

export const INSPECT_ID = /^[A-Za-z0-9:_-]{1,80}$/;

const WORST = ["failed", "prepared", "live"];

// C4 (Inspector Model tab and the AI page only): model names in call order, ` → Rules` when rules built it without Spark, then the worst mode.
export function modelChip({ calls, handmade, source } = {}) {
  const list = calls || [];
  const names = list.map((c) => MODEL_NAME[c.model] || c.model);
  if (String(source || "").startsWith("rules") && !list.some((c) => c.model === "spark")) names.push("Rules");
  if (!names.length) return "";
  let mode = "";
  if (handmade) mode = "Sample";
  else {
    const modes = list.map((c) => modeWord(c.source, false)).filter(Boolean);
    mode = WORST.find((m) => modes.includes(m)) || "";
  }
  return mode ? `${names.join(" → ")} · ${mode}` : names.join(" → ");
}

export function momentFor(view, id) {
  if (!id) return null;
  return (view?.ai_moments || []).find((m) => m.id === id || m.photo_id === id || m.evidence_id === id
    || (m.written || []).some((w) => w.event_id === id)) || null;
}

export const findingFor = (moment, lens) => (lens === "patient" ? moment.patient_finding : moment.finding) || "";

// Record rows have nothing to open. The patient lens never opens a camera count (its raw output stays off the patient page).
export const canInspect = (moment, lens = "staff") => moment.kind !== "record" && !(lens === "patient" && moment.kind === "visual");

export const FILTERS = [["all", "All"], ["needs", "Needs you"], ["photos", "Photos"], ["video", "Video"], ["voice", "Voice"], ["answers", "Answers"], ["alerts", "Alerts"]];

// The Record & evidence rows for one chip. The patient lens keeps only rows that have a patient sentence.
export function filterMoments(moments, filter, role, lens = "staff") {
  const rows = (moments || []).filter((m) => lens !== "patient" || m.patient_finding != null);
  if (!filter || filter === "all") return rows;
  if (filter === "needs") return rows.filter((m) => (m.status === "open" || m.status === "flagged") && m.owner === role);
  return rows.filter((m) => m.filter === filter);
}

// The newest signed moment of one capability (moments arrive newest first).
export const lastSigned = (moments, capability) =>
  (moments || []).find((m) => m.capability === capability && m.status === "recorded") || null;

const STRIP_NUDGES = ["strip_strength_differs", "strip_not_prescribed"];

// The strips-photo moments of a chart, and the strip alerts they raised. Each list keeps the newest-first order.
export function stripMoments(view) {
  const all = view?.ai_moments || [];
  return {
    strips: all.filter((m) => m.capability === "strips"),
    nudges: all.filter((m) => m.capability === "nudge" && STRIP_NUDGES.includes(m.refs?.kind)),
  };
}

// The record-bot answer moment of one question, by the question's id.
export const botMoment = (view, questionId) =>
  (view?.ai_moments || []).find((m) => m.capability === "record_bot" && m.refs?.question_id === questionId) || null;

// The day-plan moment of a chart (its id is `dayplan:<prescription id>`), or null before a medicines photo is matched.
export const dayPlanMoment = (view) => (view?.ai_moments || []).find((m) => m.capability === "day_plan") || null;
