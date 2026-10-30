import { displayName } from "./names.js";

// The three spec pipelines, one array of steps each.
export const PIPELINES = [
  ["Voice", "Draft orders", "Nurse tasks"],
  ["Photo", "SAM regions", "Spark reads", "Check against orders"],
  ["Video", "SAM per-frame tracking", "Count", "Mismatch flag"],
];

export const callsText = (n) => (n === 0 ? "No calls yet" : n === 1 ? "1 call" : `${n} calls`);

export const latencyText = (ms) => (ms === null || ms === undefined ? "No timing yet" : `${(ms / 1000).toFixed(1)} s median`);

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
