import { blankRow } from "./orders.js";

export const MATCH_LABEL = {
  ok: "Photo matches the task",
  mismatch: "Flagged: the photo does not match. The nurse decides.",
  none: "Photo kept, not checked",
};

export const SOURCE_LABEL = {
  "muse-spark-1.3": "Muse Spark",
  rules: "Rules (no model)",
  "rules (model reply not usable)": "Rules (model reply not usable)",
  prepared: "Prepared demo result",
  typed: "Typed",
  "muse-voice-transcribe": "Muse Voice",
};

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
