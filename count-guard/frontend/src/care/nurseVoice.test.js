import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { doneBody, itemsToRows, rowForm, rowSession, voiceTarget } from "./drafts.js";
import { unclearLines } from "./orders.js";
import { LEAVE_OUT, NOT_PLACED, leftOutOf, notPlacedLine, pendingUnplaced, placeSentence } from "./dischargeDraft.js";

const read = (f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8");
const OBS = { id: "t1", kind: "obs", title: "BP every 1 h", mode: "tick", proof: "none", status: "open" };
const SAID = "BP one hundred twenty over eighty, pulse seventy two";
// What /dictate/task answers for SAID (backend test_dictation_fill.py::test_task_voice_values_in_words).
const PROPOSAL = { candidates: [OBS], values: { sbp: 120, dbp: 80, hr: 72 }, transcript: SAID, heard_by: "muse-voice-transcribe", source: "rules", calls: [] };

test("K6: spoken BP and pulse land in the row's own form in one step: 120/80/72", () => {
  assert.equal(voiceTarget(OBS), "form");
  const session = rowSession(PROPOSAL, OBS);
  assert.deepEqual(rowForm(session.proposal.values), { sbp: "120", dbp: "80", hr: "72" });
  const out = doneBody({ task: OBS, via: session.via, transcript: session.transcript, form: rowForm({ sbp: 120, dbp: 80, hr: 72 }),
    heardBy: session.heardBy, proposed: session.proposal.values });
  assert.deepEqual(out.body.values, { sbp: 120, dbp: 80, hr: 72 });
  assert.deepEqual(out.body.proposed_values, { sbp: 120, dbp: 80, hr: 72 });
  assert.equal(out.body.via, "voice");
});

test("rowForm keeps observation numbers only", () => {
  assert.deepEqual(rowForm({ sbp: 120, note: "x", hr: null, temp: 37.5 }), { sbp: "120", temp: "37.5" });
  assert.deepEqual(rowForm(undefined), {});
});

test("Confirm task is for photo proofs only; a tick task waits on its own button", () => {
  assert.equal(voiceTarget({ kind: "dose", proof: "photo" }), "proof");
  assert.equal(voiceTarget({ kind: "dose", proof: "none" }), "row");
  assert.equal(voiceTarget({ kind: "obs", proof: "photo" }), "form");
});

test("the row mic sends as soon as it is heard and fills the row's ObsForm (no Confirm task card)", () => {
  const src = read("NurseTasks.jsx");
  assert.match(src, /<Dictate[\s\S]*?autoSend[\s\S]*?\/>/);
  assert.match(src, /<ObsForm key=\{`\$\{task\.id\}:\$\{filled\}`\}[^>]*initial=\{said \? rowForm\(said\.proposal\.values\) : \{\}\}/);
  assert.match(src, /voiceTarget\(task\) === "proof"\) onSession/);
  assert.match(src, /<ModelStep|Dictate/); // the step lines stay in the row's Dictate (Task 2)
  const dictate = read("Dictate.jsx");
  assert.match(dictate, /if \(autoSend && result\.text\?\.trim\(\)\) sendSaid\(/);
});

test("words not understood are shown, never a row, never signed", () => {
  const draft = { items: [{ kind: "dose", text: "Paracetamol 1 g", name: "paracetamol" }], unclear: [{ kind: "unclear", heard: "Insert urinary catheter" }] };
  assert.deepEqual(unclearLines(draft), ['Not understood — not added: "Insert urinary catheter"']);
  assert.equal(itemsToRows([...draft.items, ...draft.unclear]).length, 1);
  assert.deepEqual(unclearLines({ items: [] }), []);
  assert.match(read("OrderForm.jsx"), /unclearLines\(draft\)/);
});

test("an unplaced discharge sentence is placed where the doctor chooses", () => {
  assert.equal(NOT_PLACED, "Not placed — choose a section");
  assert.equal(placeSentence("Diagnosis: Hernia.", "Follow-up", "Day 7."), "Diagnosis: Hernia.\nFollow-up: Day 7.");
  assert.equal(placeSentence("Diagnosis: Hernia.", "Diagnosis", "Right side."), "Diagnosis: Hernia. Right side.");
  assert.equal(placeSentence("", "Medicines", "Paracetamol."), "Medicines: Paracetamol.");
  assert.match(read("DoctorActions.jsx"), /<UnplacedSentences sentences=\{pending\}/);
});

test("a theatre line with no drug name shows the refusal in its own step line", () => {
  const src = read("TheatreDrugs.jsx");
  assert.match(src, /"\/theatre\/drug", own\(o\)\)/);
  assert.match(src, /sendCapability=\{DRUG_LINE\}/);
});

test("Sign discharge waits until each unplaced sentence is placed or left out; left-out ones go with the signing", () => {
  const unplaced = ["The family visited.", "Seen by physio."];
  assert.deepEqual(pendingUnplaced(unplaced, {}).map((p) => p.text), unplaced);
  const settled = { 0: LEAVE_OUT };
  assert.deepEqual(pendingUnplaced(unplaced, settled), [{ index: 1, text: "Seen by physio." }]);
  assert.equal(notPlacedLine(1), "1 sentence not placed");
  assert.equal(notPlacedLine(2), "2 sentences not placed");
  assert.deepEqual(leftOutOf(unplaced, { ...settled, 1: "Course on the ward" }), ["The family visited."]);
  const src = read("DoctorActions.jsx");
  assert.match(src, /Boolean\(shut\.sign\) \|\| pending\.length > 0\} onClick=\{signDischarge\}/);
  assert.match(src, /left_out: leftOut/);
  assert.match(src, /setSummaryDraftId\(draft\.id\);\s*setSettled\(\{\}\)/); // a new draft starts fresh
  assert.match(read("UnplacedSentences.jsx"), /<option value=\{LEAVE_OUT\}>/);
  assert.doesNotMatch(read("UnplacedSentences.jsx"), /useState/); // the choice lives beside the summary, not in this list
});

test("a sentence said twice is two separate choices, and left out twice is kept twice", () => {
  const unplaced = ["Seen by physio.", "Seen by physio."];
  assert.deepEqual(pendingUnplaced(unplaced, { 0: "Course on the ward" }), [{ index: 1, text: "Seen by physio." }]);
  assert.deepEqual(leftOutOf(unplaced, { 0: LEAVE_OUT, 1: LEAVE_OUT }), ["Seen by physio.", "Seen by physio."]);
  assert.match(read("UnplacedSentences.jsx"), /key=\{`\$\{index\}:\$\{text\}`\}/);
  assert.match(read("DoctorActions.jsx"), /\[index\]: choice/);
});
