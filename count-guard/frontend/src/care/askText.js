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
  if (heardText && currentText === heardText) return { via: "voice", heard_by: heardBy };
  return { via: "text", heard_by: "" };
}

// The patient's own words go to the doctor only; other roles see a fixed line.
export const QUESTION_HIDDEN = "Question from the patient";
export const questionText = (role, question) => (role === "doctor" ? question.text : QUESTION_HIDDEN);
