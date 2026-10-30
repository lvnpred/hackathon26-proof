import { label } from "./clock.js";
import { waitedText } from "./derive.js";
import { shortName } from "./names.js";
import { sourceLabel } from "./drafts.js";

// Same copy as the server's not-found answer.
export const NOT_FOUND = "I can't find that in your record.";
export const ASK_DOCTOR = "Ask Dr. Rao";
// The states in which a photo may go to the doctor (the server's PHOTO_STATES).
export const PHOTO_STATES = ["clinic_done", "home"];
export const PHOTO_CLOSED = "Photos for the doctor open once the visit is closed or you are home.";

export const photoAskOpen = (state) => PHOTO_STATES.includes(state);

const asked = (view, to) => ((view?.ask?.questions) || []).filter((q) => q.to === to).reverse();
const newest = (list) => (list && list.length ? list[list.length - 1] : null);

export const botQuestions = (view) => asked(view, "bot");
export const doctorQuestions = (view) => asked(view, "doctor");
export const latestReview = (view) => newest(view?.ask?.reviews);
export const latestMedicines = (view) => newest(view?.ask?.medicines);

// What waits on the doctor: unanswered questions to the doctor, unanswered reviews, nudges to the doctor.
export const doctorOpenItems = (view) =>
  doctorQuestions(view).filter((q) => !q.answer).length
  + (view?.ask?.reviews || []).filter((r) => !r.answer).length
  + (view?.nudges || []).filter((n) => n.to === "doctor").length;

// The doctor's inbox: questions to the doctor and reviews. The doctor sees all; others see answered items.
// Open items first, then answered, each oldest first (R22).
export function inboxItems(view, role, nowMs) {
  const make = (kind) => (item) => ({ kind, id: item.id, atMs: item.at_ms, open: !item.answer, waited: item.answer ? "" : waitedText(nowMs - item.at_ms) });
  const all = [
    ...((view?.ask?.questions) || []).filter((q) => q.to === "doctor").map(make("question")),
    ...((view?.ask?.reviews) || []).map(make("review")),
  ].filter((i) => role === "doctor" || !i.open);
  const byTime = (a, b) => a.atMs - b.atMs;
  return [...all.filter((i) => i.open).sort(byTime), ...all.filter((i) => !i.open).sort(byTime)];
}

export function inboxHeader(name, items) {
  const n = items.filter((i) => i.open).length;
  return n > 0 ? `From ${shortName(name)} · ${n} waiting` : `From ${shortName(name)}`;
}

// "Day 3": the demo-clock day of a photo (R23).
export const photoDay = (atMs) => label(atMs).split(" ").slice(0, 2).join(" ");
export const sendVerb = (name) => `Send to ${shortName(name)}`;

// Who answered, and how: the bot names its source; the doctor says typed or by voice.
export function answerByLine(answer) {
  if (answer.source === "doctor") return `${answer.by}, ${answer.via === "voice" ? "by voice" : "typed"}`;
  return `Record bot · ${sourceLabel(answer.source)}`;
}

// A prescribed strip reads as its schedule; any flagged strip shows its whole reason.
export function medicineLine(row) {
  if (row.flag || !row.prescribed) return row.why;
  return `${row.medicine}: ${row.schedule}`;
}

// "" when the question can be sent (the server accepts 1 to 300 characters).
export function questionProblem(text) {
  const said = (text || "").trim();
  if (!said) return "Type a question.";
  if (said.length > 300) return "Keep the question under 300 characters.";
  return "";
}

// How an answer was given: "voice" only while the text is exactly what was heard.
export function answerHow(heardText, currentText, heardBy) {
  if (heardText && (currentText || "").trim() === heardText.trim()) return { via: "voice", heard_by: heardBy };
  return { via: "text", heard_by: "" };
}

// The patient's own words go to the doctor only; other roles see a fixed line.
export const QUESTION_HIDDEN = "Question from the patient";
export const questionText = (role, question) => (role === "doctor" ? question.text : QUESTION_HIDDEN);

// The source line under a doctor's answer: only a voice answer was heard by a model.
export function answerSourceLine(answer) {
  if (answer.source === "doctor") return answer.via === "voice" && answer.heard_by ? sourceLabel(answer.heard_by) : "";
  return answer.source ? sourceLabel(answer.source) : "";
}

// The patient's note on a healing photo goes to the doctor only, like the question text.
export const NOTE_HIDDEN = "A note from the patient";
export const noteText = (role, review) => (!review.note ? "" : role === "doctor" ? review.note : NOTE_HIDDEN);

// Plain words for the nudge kinds the server raises (backend/app/journey/nudges.py).
export const NUDGE_LABEL = {
  strip_not_prescribed: "Strip not on the prescription",
  strip_strength_differs: "Strip strength differs",
  dose_not_ordered: "Dose not ordered",
  dose_logged_early: "Dose logged early",
  dose_overdue: "Dose overdue",
  obs_past_limit: "Observation past its limit",
  obs_overdue: "Observations overdue",
  count_open: "Count still open",
  help_requested: "Patient asked for help",
  warning_sign_ticked: "Warning sign ticked",
};
export const nudgeLabel = (kind) => NUDGE_LABEL[kind] || "Nudge";
