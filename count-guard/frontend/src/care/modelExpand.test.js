import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { expandParts, momentRecord, newMomentRecord, PARTS, plainValue, recordUrl, tryRecord } from "./expandModel.js";

const read = (f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8");
const MODEL_NAME = /SAM 3\.1|Spark 1\.3|Spark Open|Muse Voice|muse-|sam-3/;
const view = { episode: { id: "ep1" }, acts: [] };
const ev = (captured, returned, used, calls = []) => ({ kind: "x", captured, returned, used, calls });
const voiceCall = { model: "voice", model_id: "v", source: "muse-voice-transcribe", ms: 2100 };
const sparkCall = { model: "spark", model_id: "s", source: "muse-spark-1.3", ms: 3400 };

test("the four parts are named in order", () => {
  assert.deepEqual(PARTS.map((p) => p.title), ["Captured", "Model returned", "How the app used it", "What a person did"]);
});

test("voice: the recording plays, the transcript shows, the draft rows are what the app used", () => {
  const order = {
    id: "d1", type: "order.drafted", at_ms: 1000,
    evidence: ev({ audio_id: "a".repeat(32), transcript: "paracetamol one gram every six hours", typed: false },
      { model: "Spark 1.3", mode: "live", ms: 3400, raw: "{\"items\": []}" },
      { items: [{ kind: "dose", name: "paracetamol", amount: "1 g", every_h: 6 }], reason: "", fallback: null }, [voiceCall, sparkCall]),
  };
  const p = expandParts(order, view, "staff");
  assert.equal(p.captured.audio, `/journey/episodes/ep1/audio/${"a".repeat(32)}`);
  assert.equal(p.captured.transcript, "paracetamol one gram every six hours");
  assert.equal(p.returned.model, "Spark 1.3");
  assert.equal(p.returned.modeText, "Live");
  assert.equal(p.returned.seconds, "3.4 s");
  assert.equal(p.returned.raw, "{\"items\": []}");
  assert.deepEqual(p.returned.calls.map((c) => c.model), ["Muse Voice", "Spark 1.3"]);
  assert.deepEqual(p.used.lines, ["Paracetamol · 1 g · every 6 h"]);
  assert.equal(p.used.fallback, null);
  assert.equal(p.people.text, "Proposed by AI");
});

test("voice: a hear reply and an edited spoken answer show heard words and the confirmed words", () => {
  const heard = { text: "two tablets", heard_by: "prepared", audio_id: "b".repeat(32),
    evidence: ev({ audio_id: "b".repeat(32), transcript: "two tablets", typed: false }, { model: "Muse Voice", mode: "prepared", ms: 5, raw: "two tablets" }, { text: "two tablets" }, [voiceCall]) };
  const p = expandParts(heard, view);
  assert.equal(p.captured.transcript, "two tablets");
  assert.equal(p.returned.modeText, "Prepared (no live model)");
  const answer = { id: "q1", type: "question.answered", by: "Dr. A. Rao (synthetic)", at_ms: 60000,
    evidence: ev({ audio_id: "b".repeat(32), transcript: "two tablets", answer: "Two tablets twice a day", typed: false },
      { model: "Muse Voice", mode: "live", ms: 900, raw: "two tablets" }, { answer: "Two tablets twice a day", edited: true }, [voiceCall]) };
  const q = expandParts(answer, view);
  assert.equal(q.captured.answer, "Two tablets twice a day");
  assert.equal(q.people.kind, "changed");
  assert.equal(q.people.before, "two tablets");
  assert.equal(q.people.after, "Two tablets twice a day");
  assert.match(q.people.text, /^Changed by Dr\. A\. Rao /);
});

test("photo: the photo, the read and a person's override", () => {
  const verdict = { id: "c1", type: "check.photo", item: "wristband", photo_id: "p1",
    evidence: ev({ photo_id: "p1", item: "wristband", expect: "a wristband with a name", text: "Does the photo show a wristband?" },
      { model: "Spark 1.3", mode: "live", ms: 2100, raw: "{\"verdict\": \"not_accepted\"}" }, { verdict: "not_accepted", why: "No wristband visible" }, [sparkCall]) };
  const acts = [{ type: "check.override", ref: "wristband", by: "Nurse Meena (synthetic)", at_ms: 120000, reason: "Band on the other wrist" }];
  const p = expandParts(verdict, { ...view, acts });
  assert.equal(p.captured.photo, "/journey/episodes/ep1/photos/p1");
  assert.equal(p.captured.expect, "a wristband with a name");
  assert.equal(p.captured.sent, "Does the photo show a wristband?");
  assert.ok(p.used.lines.includes("Photo does not match — No wristband visible"));
  assert.equal(p.people.kind, "overridden");
  assert.match(p.people.text, /^Overridden by Nurse Meena /);
  assert.equal(p.people.reason, "Band on the other wrist");
});

test("video: kept frames go to the evidence view; the rows say what was seen and what is missing", () => {
  const check = { id: "v1", type: "tray.checked", evidence_id: "e9", source: "sam-3.1", calls: [{ model: "sam", source: "sam-3.1", ms: 4200 }],
    rows: [{ concept: "forceps", planned: 2, seen: 1 }], missing: ["forceps"], match: "mismatch", why: "One forceps not seen" };
  const p = expandParts(check, view);
  assert.equal(p.captured.evidenceId, "e9");
  assert.equal(p.returned.model, "SAM 3.1");
  assert.equal(p.returned.modeText, "Live");
  assert.equal(p.returned.seconds, "4.2 s");
  assert.ok(p.used.lines.includes("forceps: 1 of 2 seen"));
  assert.ok(p.used.lines.includes("Missing: forceps"));
});

test("text wording: the facts sent, a reply not usable and the template that stood in", () => {
  const handover = { id: "h1", type: "handover.drafted",
    evidence: ev({ facts: ["BP 120/80 at 09:00"], text: "Word these facts.\n1. BP 120/80 at 09:00" },
      { model: "Spark 1.3", mode: "failed", ms: 30000, raw: "Sure! Here you go" }, { text: null, lines: [{ text: "BP 120/80 at 09:00" }], fallback: "template", why: "reply added a fact" },
      [{ ...sparkCall, source: "rules (model reply not usable)" }]) };
  const acts = [{ type: "handover.accepted", ref: "h1", by: "Nurse Kavya (synthetic)", at_ms: 180000 }];
  const p = expandParts(handover, { ...view, acts });
  assert.deepEqual(p.captured.facts, ["BP 120/80 at 09:00"]);
  assert.equal(p.returned.modeText, "Spark 1.3 reply not usable — template used");
  assert.equal(p.used.fallback, "Spark 1.3 reply not usable — template used (reply added a fact)");
  assert.ok(p.used.lines.includes("1. BP 120/80 at 09:00"));
  assert.equal(p.people.kind, "accepted");
  assert.match(p.people.text, /^Accepted by Nurse Kavya /);
});

test("rules only: no model was asked, and the done words say so", () => {
  const typed = { id: "d2", type: "druglog.parsed", evidence: ev({ audio_id: null, transcript: "lignocaine two percent", typed: true },
    { model: "rules", mode: "none", ms: null, raw: null }, { heard_as: "drug", row: { generic: "lignocaine", strength: "2%", amount: 5, unit: "ml" } }) };
  const p = expandParts(typed, view);
  assert.equal(p.captured.audio, null);
  assert.equal(p.captured.typed, true);
  assert.equal(p.returned.model, null);
  assert.equal(p.returned.modeText, "No model used — rules");
  assert.ok(p.used.lines.includes("Heard as a drug: lignocaine 2% 5 ml"));
});

test("verdict: a failed check says it did not work, with no verdict claimed", () => {
  const failed = { id: "c2", type: "check.photo", item: "consent", verdict: "not_checked",
    evidence: ev({ photo_id: "p2" }, { model: "Spark 1.3", mode: "failed", ms: 60000, raw: "not json" }, { verdict: "not_checked", why: "" },
      [{ ...sparkCall, source: "unavailable" }]) };
  const p = expandParts(failed, view);
  assert.equal(p.returned.modeText, "Didn't work");
  assert.ok(p.used.lines.includes("Not checked — model unavailable"));
});

test("camera: the clip's read, the advice and the explanation's evidence", () => {
  const ran = { type: "camera.ran", source: "prepared", scenario: "demo", advice: [{ id: "a1", text: "One swab not seen back", rule: "R1", source: "prepared" }] };
  const p = expandParts(ran, view);
  assert.equal(p.captured.note, "The recorded theatre clip");
  assert.equal(p.returned.modeText, "Prepared (no live model)");
  assert.ok(p.used.lines.includes("One swab not seen back"));
  const closed = { type: "camera.closed", text: "Two swabs were found under the drape.",
    evidence: ev({ case_id: "case1" }, { model: "Spark Open", mode: "live", ms: null, raw: "Two swabs…" }, { text: "Two swabs were found under the drape.", fallback: null }, [{ model: "spark-open", source: "muse-spark-open" }]) };
  const q = expandParts(closed, view);
  assert.equal(q.returned.model, "Spark Open");
  assert.equal(q.returned.seconds, null);
  assert.ok(q.used.lines.includes("Two swabs were found under the drape."));
});

test("patient lens: plain words, no model names, no raw reply, no calls", () => {
  const records = [
    { evidence: ev({ audio_id: "c".repeat(32), transcript: "my wound is fine" }, { model: "Muse Voice", mode: "live", ms: 900, raw: "my wound is fine" }, { text: "my wound is fine" }, [voiceCall]) },
    { evidence: ev({ photo_id: "p3" }, { model: "Spark 1.3", mode: "failed", ms: 1, raw: "x" }, { text: "", fallback: "template" }, [{ ...sparkCall, source: "rules (model reply not usable)" }]) },
    { source: "sam-3.1", calls: [{ model: "sam", source: "sam-3.1", ms: 1 }], evidence_id: "e1" },
  ];
  for (const r of records) {
    const p = expandParts(r, view, "patient");
    assert.equal(p.returned.model, null);
    assert.equal(p.returned.raw, null);
    assert.deepEqual(p.returned.calls, []);
    assert.equal(p.captured.sent, null);
    assert.doesNotMatch(JSON.stringify(p), MODEL_NAME);
  }
});

test("plainValue: values read as words, never as keys with underscores", () => {
  assert.equal(plainValue({ said: "opening twenty swabs", n: 20 }), "“opening twenty swabs” · n 20");
  assert.equal(plainValue({ values: { bp_sys: 120, hr: 72 } }), "bp sys 120 · hr 72");
  assert.equal(plainValue([{ kind: "dose", name: "paracetamol", amount: "1 g" }]), "Paracetamol · 1 g");
  assert.equal(plainValue(null), "");
});

test("recordUrl reads one event's model record", () => {
  assert.equal(recordUrl("ep1", "ev9"), "/journey/episodes/ep1/events/ev9/model");
});

test("ModelExpand keeps the scan contract: the open view is data-expand=open, the toggle is not", () => {
  const src = read("ModelExpand.jsx");
  assert.match(src, /data-expand="open"/);
  assert.match(src, /data-expand="closed"/);
  for (const part of ["Captured", "Model returned", "How the app used it", "What a person did"]) assert.match(read("expandModel.js"), new RegExp(part));
  assert.match(src, /<details[^>]*>\s*<summary>Raw reply<\/summary>/, "the raw reply is folded");
  assert.match(src, /<audio\b[^>]*controls/, "the recording plays");
  assert.match(src, /EvidenceThumb|<Evidence\b/, "images and frames reuse the evidence view");
});

test("Try sample: the bundled input, the model's mode, and nothing written", () => {
  const voice = expandParts(tryRecord("voice")({ model: "voice", mode: "prepared", text: "paracetamol one gram" }), {});
  assert.equal(voice.captured.note, "The bundled sample recording");
  assert.equal(voice.returned.modeText, "Prepared (no live model)");
  assert.equal(voice.returned.model, "Muse Voice");
  assert.deepEqual(voice.used.lines, ["paracetamol one gram", "Nothing is written to any record."]);
  const open = expandParts(tryRecord("spark-open")({ model: "spark-open", mode: "Sample", text: "Two swabs…" }), {});
  assert.equal(open.returned.modeText, "Bundled sample text (no model call)");
  assert.equal(open.returned.model, null);
  // A sample's picture sidecar is not a model point's evidence: it does not fill the parts.
  const sam = expandParts(tryRecord("sam")({ model: "sam", mode: "live", evidence: { rows: [{ concept: "forceps", planned: 2, seen: 2 }], calls: [{ model: "sam", ms: 900 }] } }), {});
  assert.equal(sam.returned.model, "SAM 3.1");
  assert.ok(sam.used.lines.includes("forceps: 2 of 2 seen"));
});

test("a moment is read back by its event id; a day plan is shown as it is; a view call picks the moment it added", () => {
  assert.equal(momentRecord({ id: "abc-1", capability: "strips" }).eventId, "abc-1");
  assert.equal(momentRecord({ id: "dayplan:abc", capability: "day_plan" }).eventId, undefined);
  const before = { ai_moments: [{ id: "old", capability: "strips" }] };
  const after = { ai_moments: [{ id: "new", capability: "strips", finding: "2 strips read." }, ...before.ai_moments] };
  assert.equal(newMomentRecord(before, ["strips"])(after).eventId, "new");
  assert.equal(newMomentRecord(after, ["strips"])(after), null);
  assert.ok(expandParts(after.ai_moments[0], {}).used.lines.includes("2 strips read."));
});

// Every §4.2 point offers Expand: its step's done line (ModelStep expand) and, where the result stays on screen, a button.
const POINTS = {
  "Dictate.jsx": "voice transcription, nurse task voice, theatre drug words", "DoctorActions.jsx": "orders and discharge drafts",
  "Handover.jsx": "handover wording", "ContextCard.jsx": "context card", "VitalsStrip.jsx": "context card from a reading",
  "TheatreDrugs.jsx": "theatre drug", "AskCards.jsx": "Ask bot answer, Ask photo review, medicines photo", "AskInbox.jsx": "record bot answer",
  "HomeMedicines.jsx": "home medicines strips", "TaskProof.jsx": "monitor read", "ProofItem.jsx": "proof verdicts",
  "VideoCheck.jsx": "tray, set-up and swab clips", "TheatreChecklist.jsx": "tray again", "CameraAdvice.jsx": "camera read and explanation",
  "CountPanel.jsx": "camera count read", "ModelCards.jsx": "Try sample", "NurseTasks.jsx": "task said",
};
for (const [file, what] of Object.entries(POINTS)) {
  test(`${file} offers Expand (${what})`, () => {
    const src = read(file);
    const steps = src.split("<ModelStep ").slice(1).map((t) => t.slice(0, t.indexOf("/>")));
    assert.ok(steps.length > 0 || /<ExpandButton\b/.test(src), file);
    for (const tag of steps) assert.match(tag, /expand=\{/, `${file}: every step line can expand: ${tag}`);
  });
}

test("ModelStep opens the Expand on its done record; the runner keeps that record", () => {
  const src = read("ModelStep.jsx");
  assert.match(src, /step\.record/);
  assert.match(src, /<ModelExpand record=\{record\}/);
  assert.match(read("modelStep.js"), /record: \(result && record\(result\)\) \|\| null/);
});

// Fix round 1: what a person did, where the answer is not keyed to the result itself.
const ASHA = "Nurse Asha (synthetic)";
test("camera read: each finding a person saw or overrode", () => {
  const read = { type: "camera.ran", source: "prepared", adviceIds: ["a1", "a2", "a3"], advice: [] };
  const acts = [
    { type: "camera.ack", ref: "a1", by: ASHA, at_ms: 600000, reason: "" },
    { type: "camera.ack", ref: "a2", by: ASHA, at_ms: 660000, reason: "Found under the drape" },
  ];
  const p = expandParts(read, { ...view, acts }).people;
  assert.equal(p.text, "2 of 3 findings answered");
  assert.equal(p.lines.length, 2);
  assert.match(p.lines[0], /^Seen by Nurse Asha /);
  assert.match(p.lines[1], /^Overridden by Nurse Asha .* — Found under the drape$/);
  assert.equal(expandParts({ ...read, adviceIds: ["a1"] }, view).people.text, "0 of 1 finding answered");
  assert.equal(expandParts({ ...read, adviceIds: [] }, view).people.text, "Advice only — nothing for a person to answer");
});

test("proof or monitor photo read: the verdict override, the done act, else Confirm", () => {
  const read = { match: "ok", read: "BP 88/54", source: "prepared", taskId: "t1" };
  assert.equal(expandParts(read, view).people.text, "Confirmed when the nurse presses Confirm");
  const done = [{ type: "task.done", ref: "t1", by: ASHA, at_ms: 600000, value: { values: { sbp: 90 } }, proposed: { values: { sbp: 88 } } }];
  const p = expandParts(read, { ...view, acts: done }).people;
  assert.match(p.text, /^Changed by Nurse Asha /);
  assert.equal(p.before, "sbp 88");
  assert.equal(p.after, "sbp 90");
  const over = [...done, { type: "check.override", ref: "task:t1", by: ASHA, at_ms: 700000, reason: "Monitor glare" }];
  const q = expandParts(read, { ...view, acts: over }).people;
  assert.match(q.text, /^Overridden by Nurse Asha /);
  assert.equal(q.reason, "Monitor glare");
});

test("advice-only reads say nobody answers them", () => {
  for (const r of [{ type: "tray.checked", rows: [] }, { type: "brownbag.med_found", generic: "metformin" }, { id: "m1", capability: "strips", calls: [] }]) {
    assert.equal(expandParts(r, view).people.text, "Advice only — nothing for a person to answer");
  }
});

test("camera count read: not saved yet, then read -> saved and who saved it", () => {
  const read = { type: "count.camera", count: 9 };
  assert.equal(expandParts(read, view).people.text, "Not saved yet — the count a person saves decides");
  const saved = expandParts({ ...read, savedCount: { returned: 10, by: ASHA, at_ms: 900000 } }, view).people;
  assert.match(saved.text, /^Changed by Nurse Asha /);
  assert.deepEqual([saved.before, saved.after], ["Camera read 9", "Saved 10"]);
  assert.match(expandParts({ ...read, savedCount: { returned: 9, by: ASHA, at_ms: 900000 } }, view).people.text, /^Accepted by Nurse Asha /);
});

test("the patient lens asks for the record without the raw reply", () => {
  assert.equal(recordUrl("ep1", "ev9", "patient"), "/journey/episodes/ep1/events/ev9/model?lens=patient");
  assert.match(read("ModelExpand.jsx"), /recordUrl\(episodeId, eventId, lens\)/);
});

test("the sites pass the answers the people part reads", () => {
  assert.match(read("CameraAdvice.jsx"), /adviceIds:/);
  assert.match(read("TaskProof.jsx"), /taskId: /);
  assert.match(read("CountPanel.jsx"), /savedCount: /);
  const ask = read("AskCards.jsx");
  assert.match(ask, /function LastRead[\s\S]*?<ExpandButton[^>]*lens="patient"/);
  for (const card of ["ReviewCard", "MedicinesCard"]) assert.match(ask, new RegExp(`function ${card}[\\s\\S]*?<LastRead`));
});
