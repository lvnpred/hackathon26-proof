import test from "node:test";
import assert from "node:assert/strict";
import {
  ASK_DOCTOR, NOT_FOUND, PHOTO_CLOSED, PHOTO_STATES, answerByLine, botQuestions, doctorQuestions,
  latestMedicines, latestReview, medicineLine, photoAskOpen, questionProblem, doctorOpenItems,
} from "./askText.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const view = {
  ask: {
    questions: [
      { id: "q1", to: "bot", text: "a" }, { id: "q2", to: "doctor", text: "b" },
      { id: "q3", to: "bot", text: "c" }, { id: "q4", to: "doctor", text: "d" },
    ],
    reviews: [{ id: "r1" }, { id: "r2" }],
    medicines: [{ id: "m1" }, { id: "m2" }],
  },
};

test("photoAskOpen is true only once the visit is closed or the patient is home", () => {
  for (const state of ["clinic_done", "home"]) assert.equal(photoAskOpen(state), true);
  for (const state of ["clinic", "ward", "theatre", "discharge", "", undefined]) assert.equal(photoAskOpen(state), false);
  assert.deepEqual(PHOTO_STATES, ["clinic_done", "home"]);
});

test("botQuestions and doctorQuestions filter by recipient, newest first", () => {
  assert.deepEqual(botQuestions(view).map((q) => q.id), ["q3", "q1"]);
  assert.deepEqual(doctorQuestions(view).map((q) => q.id), ["q4", "q2"]);
  assert.deepEqual(botQuestions({}), []);
});

test("latestReview and latestMedicines pick the newest, or null", () => {
  assert.equal(latestReview(view).id, "r2");
  assert.equal(latestMedicines(view).id, "m2");
  assert.equal(latestReview({}), null);
  assert.equal(latestMedicines({ ask: {} }), null);
});

test("answerByLine names the bot with its source label, and the doctor with how it was given", () => {
  assert.equal(answerByLine({ by: "Record bot", source: "rules", via: "" }), "Record bot · Rules (no model)");
  assert.equal(answerByLine({ by: "Record bot", source: "muse-spark-1.3" }), "Record bot · Muse Spark");
  assert.equal(answerByLine({ by: "Dr. A. Rao (synthetic)", source: "doctor", via: "voice" }), "Dr. A. Rao (synthetic), by voice");
  assert.equal(answerByLine({ by: "Dr. A. Rao (synthetic)", source: "doctor", via: "text" }), "Dr. A. Rao (synthetic), typed");
});

test("answerByLine reads a bot answer with an empty source as the bot, not the doctor", () => {
  assert.equal(answerByLine({ by: "Record bot", source: "", via: "" }), "Record bot · Not read");
});

test("medicineLine shows the schedule, and the whole why for any flagged row", () => {
  assert.equal(medicineLine({ prescribed: true, flag: null, medicine: "Amlodipine", schedule: "1 tablet, morning", why: "x" }), "Amlodipine: 1 tablet, morning");
  assert.equal(medicineLine({ prescribed: false, flag: "not_prescribed", why: "Pan 40 mg is not on your prescription." }), "Pan 40 mg is not on your prescription.");
  const differs = { prescribed: true, flag: "strength_differs", medicine: "Amlodipine", schedule: "s", why: "The strip reads Amlodipine 10 mg. The prescription says Amlodipine." };
  assert.equal(medicineLine(differs), differs.why);
});

test("questionProblem checks the text bounds", () => {
  assert.equal(questionProblem("Is my stitch fine?"), "");
  assert.equal(questionProblem("   "), "Type a question.");
  assert.equal(questionProblem(""), "Type a question.");
  assert.equal(questionProblem("x".repeat(300)), "");
  assert.equal(questionProblem("x".repeat(301)), "Keep the question under 300 characters.");
});

test("no fixed text or helper output reads as advice", () => {
  const texts = [
    NOT_FOUND, ASK_DOCTOR, PHOTO_CLOSED, questionProblem(""), questionProblem("x".repeat(301)),
    answerByLine({ by: "Record bot", source: "rules" }), answerByLine({ by: "Dr. Rao", source: "doctor", via: "voice" }),
    answerByLine({ by: "Dr. Rao", source: "doctor", via: "text" }),
  ];
  assert.equal(NOT_FOUND, "I can't find that in your record.");
  for (const text of texts) assert.doesNotMatch(text, ADVICE);
});

test("answerHow: voice only for unchanged heard text", async () => {
  const { answerHow, questionText } = await import("./askText.js");
  assert.deepEqual(answerHow("Come in", "Come in", "prepared"), { via: "voice", heard_by: "prepared" });
  assert.deepEqual(answerHow("Come in", "Come in today", "prepared"), { via: "text", heard_by: "" });
  assert.deepEqual(answerHow("", "Come in", ""), { via: "text", heard_by: "" });
  assert.equal(questionText("doctor", { text: "Can I take two?" }), "Can I take two?");
  assert.equal(questionText("nurse", { text: "Can I take two?" }), "Question from the patient");
});

import { sourceLabel } from "./drafts.js";
import { NOTE_HIDDEN, answerSourceLine, noteText, nudgeLabel, NUDGE_LABEL } from "./askText.js";
import { readFileSync } from "node:fs";

test("answerSourceLine names the voice source for a doctor answer and never the raw word", () => {
  assert.equal(answerSourceLine({ source: "doctor", via: "voice", heard_by: "gemini" }), sourceLabel("gemini"));
  assert.equal(answerSourceLine({ source: "doctor", via: "text", heard_by: "" }), "");
  assert.equal(answerSourceLine({ source: "doctor", via: "voice", heard_by: "" }), "");
  assert.equal(answerSourceLine({ source: "record" }), sourceLabel("record"));
});

test("noteText shows the patient's note to the doctor only", () => {
  assert.equal(noteText("doctor", { note: "itchy" }), "itchy");
  for (const role of ["nurse", "patient", ""]) assert.equal(noteText(role, { note: "itchy" }), NOTE_HIDDEN);
  assert.equal(noteText("doctor", { note: "" }), "");
  assert.equal(noteText("nurse", { note: "" }), "");
  assert.equal(NOTE_HIDDEN, "A note from the patient");
});

test("nudgeLabel covers every kind the server raises, in plain words", () => {
  const src = readFileSync(new URL("../../../backend/app/journey/nudges.py", import.meta.url), "utf8");
  const kinds = [...src.matchAll(/_nudge\(f"[^"]*", "([a-z_]+)"/g)].map((m) => m[1]);
  assert.ok(kinds.length >= 10);
  for (const kind of kinds) {
    const text = nudgeLabel(kind);
    assert.ok(NUDGE_LABEL[kind], kind);
    assert.ok(!text.includes("_") && !ADVICE.test(text), text);
  }
  assert.equal(nudgeLabel("brand_new"), "Nudge");
});

test("doctorOpenItems counts what waits on the doctor", () => {
  const v = { ask: { questions: [{ to: "doctor", answer: null }, { to: "bot", answer: null }, { to: "doctor", answer: {} }],
    reviews: [{ answer: null }] }, nudges: [{ to: "doctor" }, { to: "nurse" }] };
  assert.equal(doctorOpenItems(v), 3);
  assert.equal(doctorOpenItems({}), 0);
});
