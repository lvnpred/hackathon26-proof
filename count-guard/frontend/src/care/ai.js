import { displayName, shortName } from "./names.js";

// The three spec pipelines, one array of steps each.
export const PIPELINES = [
  ["Voice", "Draft orders", "Nurse tasks"],
  ["Photo", "SAM regions", "Spark reads", "Check against orders"],
  ["Video", "SAM per-frame tracking", "Count", "Mismatch flag"],
];

export const callsText = (n) => (n === 0 ? "No calls yet in this run" : n === 1 ? "1 call" : `${n} calls`);

export const latencyText = (ms) => (ms === null || ms === undefined ? "Prepared · timing shown when live" : `${(ms / 1000).toFixed(1)} s median`);

// The calls and timing line of one card; with no calls there is no timing to talk about.
export const cardLine = (model) => (model.calls === 0 ? callsText(0) : `${callsText(model.calls)} · ${latencyText(model.median_ms)}`);

export const modelsPill = (live) => (live ? "Models: live" : "Models: prepared (no key)");

export const STAFF_ONLY = "AI activity is a staff view. Switch to Doctor or Nurse.";
export const canSeeAi = (role) => role !== "patient";

export const modeLabel = (mode) => ({ live: "Live", prepared: "Prepared", failed: "Failed" })[mode] || mode;

// "Day 0 09:24" -> "09:24".
export const recentText = (row) => `${row.when.slice(-5)} ${row.name} · ${displayName(row.patient)} · ${displayName(row.what)}`;

// The four cards before any summary exists (a ward with no patients still shows its models).
export const EMPTY_MODELS = [
  { key: "voice", name: "Muse Voice", role: "Writes down what staff say: orders, discharges, answers and task updates." },
  { key: "spark", name: "Muse Spark 1.3", role: "Reads photos and drafts orders and answers from the record." },
  { key: "sam", name: "SAM 3.1", role: "Finds and counts instruments, swabs and photo regions." },
  { key: "spark-open", name: "Muse Spark Open", role: "Explains a count discrepancy on the camera screen; ward questions come later." },
].map((m) => ({ ...m, mode: "prepared", calls: 0, median_ms: null, last: null }));

export const BAD_ANSWER = "The server sent an answer this page cannot read. Try again.";

// Shape guards for the two answers this page reads (a proxy or error page can return 200 with other content).
export const isSummary = (x) => Boolean(x) && Array.isArray(x.models) && Array.isArray(x.recent);
export const isTry = (x) => Boolean(x) && typeof x.mode === "string" && (typeof x.text === "string" || (Boolean(x.evidence) && typeof x.evidence === "object"));

// Pipeline buttons filter the activity list by moment kind; the key is the first word of a PIPELINES entry.
export const PIPELINE_KIND = { Voice: "voice", Photo: "photo_read", Video: "visual" };

// Every roster moment except record rows, newest first, with its patient and chart.
export function activityRows(patients) {
  const rows = [];
  for (const p of patients || []) {
    for (const moment of p.view?.ai_moments || []) {
      if (moment.kind !== "record") rows.push({ episodeId: p.id, patient: shortName(p.name), moment });
    }
  }
  return rows.sort((a, b) => b.moment.at_ms - a.moment.at_ms);
}

export function storyCounts(rows) {
  const kinds = rows.map((r) => r.moment);
  const n = (kind) => kinds.filter((m) => m.kind === kind).length;
  const flags = kinds.filter((m) => m.kind === "rule");
  return {
    transcribed: n("voice"),
    photos: n("photo_read"),
    videos: n("visual"),
    flags: flags.length,
    decided: flags.filter((m) => m.status === "recorded").length,
  };
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function storyLine(c) {
  const parts = [
    [c.transcribed, "transcribed", "note"],
    [c.photos, "read", "photo"],
    [c.videos, "counted", "video"],
    [c.flags, "raised", "flag"],
  ].filter(([n]) => n > 0).map(([n, verb, noun]) => `${verb} ${plural(n, noun)}`);
  if (parts.length === 0) return "";
  const list = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  let line = `Today the AI ${list}`;
  if (c.flags > 0) line += `; staff decided ${c.flags === 1 && c.decided === 1 ? "it" : c.decided === c.flags ? `all ${c.flags}` : `${c.decided} of ${c.flags}`}`;
  return `${line}.`;
}

export const emptyLine = (name) => `Nothing yet today. Open ${name} to follow the demo.`;
