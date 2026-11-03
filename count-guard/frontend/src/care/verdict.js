// Photo proof verdicts (spec §6.6, U9): the line each check shows, and its tone. The server keeps the rule.
import { PREPARED, isPrepared } from "./source.js";

export const NO_PHOTO = "No photo";
export const NOT_CHECKED = "Not checked — model unavailable";
// The model's verdict on a photo. "Accepted" is only ever a person (clarity §4.3, provenance.js).
const WORD = { accepted: "Photo matches", not_accepted: "Photo does not match" };
const TONE = { accepted: "fine", not_accepted: "check", not_checked: "check", overridden: "done", none: "wait" };

const stateOf = (check) => check?.state || check?.verdict || "none";

// "Photo does not match — No wristband visible", with " · Prepared" when a prepared verdict stands behind it.
export function proofLabel(check) {
  const state = stateOf(check);
  if (state === "none") return NO_PHOTO;
  if (state === "overridden") return `Overridden — ${check.reason}`;
  const line = state === "not_checked" ? NOT_CHECKED : `${WORD[state]} — ${check.why}`;
  return isPrepared(check) ? `${line} · ${PREPARED}` : line;
}

// The StatusPill role of a check: fine, check (open), done (overridden) or wait (no photo yet).
export function proofTone(check) {
  return TONE[stateOf(check)] || "wait";
}

// The row of one item on the chart, else a row with no photo.
export function checkFor(view, item) {
  return (view?.photo_checks || []).find((row) => row.item === item) || { item, state: "none", open: false };
}
