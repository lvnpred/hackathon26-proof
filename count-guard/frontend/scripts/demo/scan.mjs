// Constraint scan for the demo run: product text the viewer sees must read as plain words (spec §3).
// run.mjs passes the .app text without the Demo dock for every beat and fails on any violation.
const RULES = [
  [/\bRecorded\b/, "\"Recorded\" used as a status word"],
  [/\bDay \d+ \d\d:\d\d\b/, "a Day N clock time"],
  [/\b[a-z]+_[a-z_]+\b/, "snake_case text"],
  [/task\.assigned|work\.(done|opened)/, "an event name"],
];
const PATIENT_RULES = [[/Muse |SAM 3|AI \(on behalf|Acknowledged by/, "AI bookkeeping or a model name on a patient screen"]];

// scanText(innerText, role) -> one message per rule that matches, each with the matched text.
export function scanText(text, role) {
  const rules = role === "patient" ? [...RULES, ...PATIENT_RULES] : RULES;
  const out = [];
  for (const [re, why] of rules) {
    const m = String(text).match(re);
    if (m) out.push(`${why}: "${m[0]}"`);
  }
  return out;
}
