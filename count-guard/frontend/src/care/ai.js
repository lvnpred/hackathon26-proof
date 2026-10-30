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
export const recentText = (row) => `${row.when.slice(-5)} ${row.name} · ${displayName(row.patient)} · ${row.what}`;
