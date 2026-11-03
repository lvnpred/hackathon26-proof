// Constraint scan for the demo run: product text the viewer sees must read as plain words (spec §3).
// run.mjs passes the .app text without the Demo dock for every beat and fails on any violation.
const RULES = [
  [/\bRecorded\b/, "\"Recorded\" used as a status word"],
  [/\bDay \d+ \d\d:\d\d\b/, "a Day N clock time"],
  [/\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]*[A-Za-z0-9]\b/, "snake_case text"],
  [/task\.assigned|work\.(done|opened)/, "an event name"],
  // A dotted internal name such as swabs.counted or strip.read; times, decimals, "Dr. A. Rao", "e.g." and file names are not.
  [/\b[a-z]{3,}\.(?!(?:png|jpe?g|mp4|webm|json|csv|pdf|txt|com|org|net|io|html?|css|js)\b)[a-z]{3,}(?:_[a-z]+)*\b/, "a dotted internal name"],
];
// Spec §3 rule 8: model names only on the AI page and in the Inspector Model tab, for every role.
// Capitalised names ("Muse Spark", "SAM 3.1") are case-sensitive; ids ("muse-spark-1.3", "sam-3.1", "spark-open") match in any case.
const MODEL_WHY = "a model name outside the AI page and the Inspector Model tab";
const MODEL_RULES = [
  [/\b(?:Muse|SAM)\s+\S+|\bSpark\s+\d/, MODEL_WHY],
  [/\bmuse[-_.](?:spark|voice|open)\S*|\bsam[-_.]?\d\S*|\bspark[-_.](?:\d|open)\S*/i, MODEL_WHY],
];
const PATIENT_RULES = [[/AI\s+\(on\s+behalf|Acknowledged\s+by/, "AI bookkeeping on a patient screen"]];
// The beat that films the AI page, where model names belong.
export const MODEL_BEATS = new Set(["ai"]);

// scanText(innerText, role, { models }) -> one message per rule that matches, each with the matched text.
// `models: true` allows model names (the AI page). `modelText` is the text the model rules read, when it differs.
export function scanText(text, role, { models = false, modelText = text } = {}) {
  const rules = [
    ...RULES.map((r) => [...r, text]),
    ...(models ? [] : MODEL_RULES.map((r) => [...r, modelText])),
    ...(role === "patient" ? PATIENT_RULES.map((r) => [...r, text]) : []),
  ];
  const out = [];
  for (const [re, why, seen] of rules) {
    const m = String(seen).match(re);
    if (m) out.push(`${why}: "${m[0]}"`);
  }
  return out;
}

// Spec §4.1 (C2): on a staff screen a model may be named only in a model step line and in an open Expand view.
// A `.model-step` counts only when its text is a step line that names a model; an Expand view counts only while
// it is open (`[data-expand="open"]`, the contract ModelStep and the Expand view keep). The step lines that name a
// model: "Checking with X… n s", "Done · live (X, t s)" and "Done · X reply not usable — rules|template|prepared result used".
const STEP_MODEL = "(?:SAM 3\\.1|Spark 1\\.3|Spark Open|Muse Voice)";
export const STEP_LINE = new RegExp(
  `^(?:✓\\s*)?(?:Checking with ${STEP_MODEL}… \\d+ s|Done · live \\(${STEP_MODEL}, \\d+(?:\\.\\d+)? s\\)` +
    `|Done · ${STEP_MODEL} reply not usable — (?:rules|template|prepared result) used)(?:\\s*Expand)?$`,
);
export const ALLOWED_SELECTOR = '.model-step, [data-expand="open"]';

export const isStepLine = (text) => STEP_LINE.test(String(text).replace(/\s+/g, " ").trim());

// One region -> true when its text may name a model: an open Expand view, or a model step showing a step line.
export function allowedRegion({ kind, text }) {
  return kind === "expand" || (kind === "step" && isStepLine(text));
}

// allowedText(text, regions) -> the text with each allowed region's text taken out once (a region is one place).
export function allowedText(text, regions = []) {
  return regions
    .filter((r) => r?.text && allowedRegion(r))
    .reduce((rest, { text: region }) => {
      const at = rest.indexOf(region);
      return at < 0 ? rest : rest.slice(0, at) + rest.slice(at + region.length);
    }, String(text));
}

// scanBeat: the scan for one beat. The open Inspector Model tab's text (`modelPanel`) is left out, and the AI page
// beat may name models. The model rules read `modelText` when given (run.mjs reads it from the page with the allowed
// regions hidden, so the cut is by DOM position), else the text minus the `allowed` regions ({ kind, text }). Every
// other rule reads the whole text. A patient screen never names a model, so it gets no allowance.
export function scanBeat({ text, modelPanel = "", modelText, allowed = [], role, beat }) {
  const cut = (t) => (modelPanel ? String(t).replace(modelPanel, "") : String(t));
  const seen = cut(text);
  let forModels = seen;
  if (role !== "patient") forModels = modelText !== undefined ? cut(modelText) : allowedText(seen, allowed);
  return scanText(seen, role, { models: MODEL_BEATS.has(beat), modelText: forModels });
}
