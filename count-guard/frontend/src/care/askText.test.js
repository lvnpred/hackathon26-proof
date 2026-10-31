import test from "node:test";
import assert from "node:assert/strict";
import {
  ASK_DOCTOR, NOT_FOUND, answerHow, PHOTO_CLOSED, PHOTO_STATES, answerByLine, botQuestions, doctorQuestions,
  latestMedicines, latestReview, medicineLine, photoAskOpen, questionProblem, doctorOpenItems,
  inboxItems, inboxGroups, checkinLine, inboxHeader, photoDay, sendVerb,
} from "./askText.js";
import { H, M } from "./clock.js";

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
  assert.equal(answerByLine({ by: "Record bot", source: "rules", via: "" }), "Record bot");
  assert.equal(answerByLine({ by: "Record bot", source: "muse-spark-1.3" }), "Record bot");
  assert.equal(answerByLine({ by: "Dr. A. Rao (synthetic)", source: "doctor", via: "voice" }), "Dr. A. Rao (synthetic), by voice");
  assert.equal(answerByLine({ by: "Dr. A. Rao (synthetic)", source: "doctor", via: "text" }), "Dr. A. Rao (synthetic), typed");
});

test("answerByLine({source: rules}) is Record bot", () => {
  assert.equal(answerByLine({ source: "rules" }), "Record bot");
});

test("answerByLine reads a bot answer with an empty source as the bot, not the doctor", () => {
  assert.equal(answerByLine({ by: "Record bot", source: "", via: "" }), "Record bot");
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

import { NOTE_HIDDEN, answerSourceLine, noteText, nudgeLabel, NUDGE_LABEL } from "./askText.js";
import { readFileSync } from "node:fs";

test("answerSourceLine names the voice source for a doctor answer and never the raw word", () => {
  assert.equal(answerSourceLine({ source: "doctor", via: "voice", heard_by: "prepared" }), "Muse Voice · prepared");
  assert.equal(answerSourceLine({ source: "doctor", via: "text", heard_by: "" }), "");
  assert.equal(answerSourceLine({ source: "doctor", via: "voice", heard_by: "" }), "");
  assert.equal(answerSourceLine({ source: "rules" }), "Rules");
  assert.equal(answerSourceLine({ source: "muse-spark-1.3" }), "Muse Spark 1.3 · live");
  assert.equal(answerSourceLine({ source: "record" }), "");
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

const v = { ask: {
  questions: [{ id: "q2", to: "doctor", at_ms: 20 * M, answer: null }, { id: "q1", to: "doctor", at_ms: 10 * M, answer: null }, { id: "b", to: "bot", at_ms: 0, answer: null }, { id: "q0", to: "doctor", at_ms: 0, answer: { text: "ok" } }],
  reviews: [{ id: "r1", at_ms: 15 * M, answer: null }] } };
test("inboxItems: open oldest first, then answered; every role sees both", () => {
  assert.deepEqual(inboxItems(v, "doctor", 30 * M).map((i) => i.id), ["q1", "r1", "q2", "q0"]);
  assert.equal(inboxItems(v, "doctor", 30 * M)[0].waited, "20 min");
  assert.deepEqual(inboxItems(v, "nurse", 30 * M).map((i) => i.id), ["q1", "r1", "q2", "q0"]);
  assert.deepEqual(inboxGroups(inboxItems(v, "doctor", 30 * M)).answered.map((i) => i.id), ["q0"]);
  assert.deepEqual(inboxGroups(inboxItems(v, "doctor", 30 * M)).open.map((i) => i.id), ["q1", "r1", "q2"]);
  assert.equal(checkinLine({ day: 3, feels: "Better", signs: [], seen: [] }), "Day 3 check-in: Better; no listed signs \u00b7 not seen yet");
  assert.equal(checkinLine({ day: 4, feels: "Same", signs: ["Redness", "Fever"], seen: [{ by: "Nurse Meena (synthetic)" }] }), "Day 4 check-in: Same; Redness, Fever \u00b7 Seen by Nurse Meena");
  assert.deepEqual(inboxItems({}, "doctor", 0), []);
});
test("header, verb and photo day", () => {
  const items = inboxItems(v, "doctor", 30 * M);
  assert.equal(inboxHeader("R. Kumar, 58 M (synthetic)", items), "From R. Kumar \u00b7 3 waiting");
  assert.equal(inboxHeader("R. Kumar, 58 M", []), "From R. Kumar");
  assert.equal(sendVerb("R. Kumar, 58 M (synthetic)"), "Send to R. Kumar");
  assert.equal(photoDay(3 * 24 * H + 5 * M), "Thu 5 Nov");
});
test("inbox copy has no advice words", () => {
  for (const s of ["Type or say your answer", "+ add a note", "After surgery", "From R. Kumar \u00b7 2 waiting"]) assert.doesNotMatch(s, ADVICE);
});

test("answerHow compares trimmed text", () => {
  assert.deepEqual(answerHow(" the bp is fine \n", "the bp is fine", "Dr. A. Rao (synthetic)"), { via: "voice", heard_by: "Dr. A. Rao (synthetic)" });
  assert.deepEqual(answerHow("the bp is fine", "the bp is fine today", "x"), { via: "text", heard_by: "" });
});

test("inboxItems adds answered bot questions, never open, and the header count is unchanged", () => {
  const withBot = { ask: { questions: [
    { id: "b1", to: "bot", at_ms: 5 * M, answer: { text: "From the record." } },
    { id: "b2", to: "bot", at_ms: 6 * M, answer: null },
    { id: "q1", to: "doctor", at_ms: 10 * M, answer: null },
  ], reviews: [] } };
  const items = inboxItems(withBot, "nurse", 30 * M);
  assert.deepEqual(items.map((i) => [i.kind, i.id, i.open]), [["question", "q1", true], ["bot", "b1", false]]);
  assert.equal(inboxHeader("R. Kumar, 58 M (synthetic)", items), "From R. Kumar \u00b7 1 waiting");
  assert.deepEqual(inboxGroups(items).answered.map((i) => i.kind), ["bot"]);
  assert.doesNotMatch("Answered by record bot", ADVICE);
});
