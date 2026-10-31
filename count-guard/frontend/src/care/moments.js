// Pure helpers for AI moment lines (C3, C4). JSX only renders what these return.
import { MODEL_NAME, modeWord } from "./evidence.js";

export const INSPECT_ID = /^[A-Za-z0-9:_-]{1,80}$/;

const WHO = { doctor: "the doctor", nurse: "the nurse", patient: "the patient" };
const WORST = ["failed", "prepared", "live"];

// C3: the label depends on who is looking.
export function statusLabel(moment, role) {
  const { status, owner } = moment;
  if ((status === "open" || status === "flagged") && owner && owner === role) return { text: "Needs you", tone: "blue" };
  if (status === "flagged") return { text: "Flagged", tone: "amber" };
  if (status === "open") return { text: owner ? `Waiting for ${WHO[owner]}` : "Open", tone: "grey" };
  if (status === "matches") return { text: "Matches", tone: "green" };
  if (status === "recorded") return { text: "Recorded", tone: "green" };
  return { text: "Failed", tone: "grey" };
}

// C4: model names in call order, ` → Rules` when rules built it without Spark, then the worst mode.
export function chipFor({ calls, handmade, source } = {}) {
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

// A voice result that has no event yet.
export const heardChip = (heardBy) => chipFor({ calls: [{ model: "voice", source: heardBy }] });

export function draftChip(heardBy, source) {
  const calls = [];
  if (heardBy && heardBy !== "typed") calls.push({ model: "voice", source: heardBy });
  if (source === "muse-spark-1.3" || source === "rules (model reply not usable)") calls.push({ model: "spark", source });
  return chipFor({ calls, source });
}

export function momentFor(view, id) {
  if (!id) return null;
  return (view?.ai_moments || []).find((m) => m.id === id || m.photo_id === id || m.evidence_id === id
    || (m.written || []).some((w) => w.event_id === id)) || null;
}

export const findingFor = (moment, lens) => (lens === "patient" ? moment.patient_finding : moment.finding) || "";

export const canInspect = (moment) => moment.kind !== "record";
