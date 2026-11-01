import { displayName } from "./names.js";

// Pure helpers for what the models read: monitor values for the obs form, the camera swab count for
// the closing, and the line that shows a read value next to the one that was saved.
const MONITOR = [["SBP", "sbp"], ["DBP", "dbp"], ["HR", "hr"]];
const ORDER = ["returned", "sbp", "dbp", "hr"];

// Fills sbp, dbp and hr from the photo's regions, only where the form field is empty (R15).
export function prefillObs(regions, form) {
  const out = { ...(form || {}) };
  for (const [label, key] of MONITOR) {
    const region = (regions || []).find((r) => r.label === label && r.value !== null && r.value !== undefined);
    if (region && (out[key] === undefined || out[key] === null || out[key] === "")) out[key] = String(region.value);
  }
  return out;
}

export function closingBody(count, returned, detail) {
  const body = { step: "closing", returned, detail };
  return count?.camera ? { ...body, evidence_id: count.camera.evidence_id, via: "camera" } : body;
}

// "Read 118, saved 120 by Nurse Meena": only the keys that differ. "" when none differ or either side is missing.
export function correctionLine(read, saved, by) {
  if (!read || !saved) return "";
  const keys = ORDER.filter((k) => read[k] !== undefined && saved[k] !== undefined && read[k] !== saved[k]);
  if (!keys.length) return "";
  return `Read ${keys.map((k) => read[k]).join("/")}, saved ${keys.map((k) => saved[k]).join("/")} by ${displayName(by)}`;
}
