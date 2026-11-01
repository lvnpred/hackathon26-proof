// Constraint scan for the demo run: product text the viewer sees must read as plain words (spec §3).
// run.mjs passes the .app text without the Demo dock for every beat and fails on any violation.
const RULES = [
  [/\bRecorded\b/, "\"Recorded\" used as a status word"],
  [/\bDay \d+ \d\d:\d\d\b/, "a Day N clock time"],
  [/\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]*[A-Za-z0-9]\b/, "snake_case text"],
  [/task\.assigned|work\.(done|opened)/, "an event name"],
];
// Spec §3 rule 8: model names only on the AI page and in the Inspector Model tab, for every role.
const MODEL_RULE = [/\b(?:Muse|SAM)\s+\S+|\bSpark\s+\d/, "a model name outside the AI page and the Inspector Model tab"];
const PATIENT_RULES = [[/AI\s+\(on\s+behalf|Acknowledged\s+by/, "AI bookkeeping on a patient screen"]];
// The beat that films the AI page, where model names belong.
export const MODEL_BEATS = new Set(["ai"]);

// scanText(innerText, role, { models }) -> one message per rule that matches, each with the matched text.
// `models: true` allows model names (the AI page).
export function scanText(text, role, { models = false } = {}) {
  const rules = [...RULES, ...(models ? [] : [MODEL_RULE]), ...(role === "patient" ? PATIENT_RULES : [])];
  const out = [];
  for (const [re, why] of rules) {
    const m = String(text).match(re);
    if (m) out.push(`${why}: "${m[0]}"`);
  }
  return out;
}

// scanBeat: the scan for one beat. The open Inspector Model tab's text (`modelPanel`) is left out, and the AI page
// beat may name models.
export function scanBeat({ text, modelPanel = "", role, beat }) {
  const seen = modelPanel ? String(text).replace(modelPanel, "") : String(text);
  return scanText(seen, role, { models: MODEL_BEATS.has(beat) });
}
