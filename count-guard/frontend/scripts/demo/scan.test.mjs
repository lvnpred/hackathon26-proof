import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ALLOWED_SELECTOR, allowedText, isStepLine, scanBeat, scanText } from "./scan.mjs";

const hits = (t, role = "doctor") => scanText(t, role);

test("Recorded as a whole word is flagged", () => {
  assert.equal(hits("Pain 3/10 Recorded").length, 1);
  assert.deepEqual(hits("Prerecorded by Nurse Asha, From voice"), []);
  assert.deepEqual(hits("Unrecorded dose"), [], "Unrecorded is not the status word");
});
test("Day N clock text is flagged", () => {
  assert.equal(hits("Surgery at Day 1 09:30").length, 1);
  assert.deepEqual(hits("Today 09:30 and review on day 7"), []);
});
test("snake_case is flagged, capitalised and with digits too", () => {
  for (const t of ["kind: move_ready", "Move_ready", "task_2_done", "work_id2", "SPO2_MAX"]) assert.equal(hits(t).length, 1, t);
  assert.deepEqual(hits("Ward 4-West, BP 112/70, SpO2 98"), []);
  assert.deepEqual(hits("Move ready. Task 2 done; work id 2. Re-check at 10:30 — e.g. Dr. Rao's note."), []);
});
test("event names are flagged", () => {
  assert.ok(hits("task.assigned").some((m) => m.includes("event name")));
  assert.ok(hits("work.done").some((m) => m.includes("event name")));
  assert.deepEqual(hits("The task was assigned; the work is done"), []);
});
test("model names are flagged for every role", () => {
  for (const t of ["Muse Spark wrote this", "SAM 3.1 saw it", "Ask Muse Spark 1.3 to word it", "Muse  Voice", "Spark 1.3 · live", "SAM\u00a03"]) {
    for (const role of ["patient", "nurse", "doctor"]) assert.equal(hits(t, role).length, 1, `${role}: ${t}`);
  }
  assert.deepEqual(hits("Let the AI word it", "nurse"), []);
  assert.deepEqual(hits("Sparkline of counts; a museum visit", "nurse"), []);
});
test("lowercase and hyphenated model ids are flagged too, ordinary prose is not", () => {
  for (const t of ["muse-spark-1.3", "model: sam-3.1", "MUSE-SPARK-OPEN", "muse_voice", "spark-1.3", "spark-open", "sam3", "sam.3.1", "Sam-3.1"]) {
    for (const role of ["patient", "nurse", "doctor"]) assert.ok(hits(t, role).some((m) => m.includes("model name")), `${role}: ${t}`);
  }
  for (const t of ["Sam is the nurse's brother", "same 3 times", "sample-1 taken", "the museum-2 exhibit", "a muse for the team", "Sparkline of counts", "spark plug", "Samuel 3 mg", "Samantha-2"]) {
    assert.deepEqual(hits(t, "nurse"), [], t);
  }
  assert.deepEqual(scanText("muse-spark-1.3", "nurse", { models: true }), [], "the AI page may name models");
});
test("dotted internal names are flagged; times, decimals, abbreviations and file names are not", () => {
  for (const t of ["Captured to record: swabs.counted · 10:26", "strip.read", "tray.checked · 09:20", "obs.recorded"]) assert.equal(hits(t).length >= 1, true, t);
  assert.deepEqual(hits("Saved to the record · 10:26 · Nurse Asha"), []);
  assert.deepEqual(hits("At 10.26, confidence 0.45, 3.5 s, Dr. A. Rao, e.g. a swab, i.e. the count. Photo tray.png"), []);
});
test("AI bookkeeping is flagged for the patient only, with any spacing", () => {
  for (const t of ["AI (on behalf of Dr. Rao)", "AI  (on\nbehalf of Dr. Rao)", "Acknowledged by Asha", "Acknowledged\tby Asha"]) {
    assert.equal(hits(t, "patient").length, 1, t);
    assert.deepEqual(hits(t, "nurse"), [], t);
  }
  assert.deepEqual(hits("Your care team will see this", "patient"), []);
});
test("the AI page beat and the Inspector Model tab may name models; nothing else may", () => {
  assert.deepEqual(scanBeat({ text: "Muse Spark 1.3 reads photos", role: "none", beat: "ai" }), []);
  assert.equal(scanBeat({ text: "Muse Spark 1.3 reads photos", role: "none", beat: "intro" }).length, 1);
  const panel = "Muse Spark 1.3 · live";
  assert.deepEqual(scanBeat({ text: `Chart ${panel} Close`, modelPanel: panel, role: "nurse", beat: "kumar-count" }), []);
  assert.equal(scanBeat({ text: `Ask Muse Spark 1.3 ${panel}`, modelPanel: panel, role: "nurse", beat: "kumar-count" }).length, 1);
});

const step = (text) => ({ kind: "step", text });
const expand = (text) => ({ kind: "expand", text });

test("model names may sit inside a model step line or an open Expand view on staff screens", () => {
  const line = "Checking with SAM 3.1… 3 s";
  const text = `Tray check\n${line}\nCount 12`;
  assert.deepEqual(scanBeat({ text, allowed: [step(line)], role: "nurse", beat: "tray" }), []);
  const done = "✓\nDone · live (Spark 1.3, 2.1 s)\nExpand";
  assert.deepEqual(scanBeat({ text: `Orders\n${done}`, allowed: [step(done)], role: "doctor", beat: "orders" }), []);
  const view = "Model returned: Spark 1.3 · live";
  assert.deepEqual(scanBeat({ text: `Orders\n${view}`, allowed: [expand(view)], role: "doctor", beat: "orders" }), []);
  assert.equal(scanBeat({ text, role: "nurse", beat: "tray" }).length, 1, "without the allowance it is flagged");
  assert.equal(scanBeat({ text, allowed: [step(line)], role: "patient", beat: "home" }).length, 1, "a patient screen never names a model");
  assert.equal(scanBeat({ text: "Recorded\nok", allowed: [expand("Recorded")], role: "nurse", beat: "x" }).length, 1, "other rules still read the region");
});

test("SAM 3.1 in a card line next to an allowed region is still flagged", () => {
  const line = "Checking with SAM 3.1… 3 s";
  assert.equal(scanBeat({ text: `SAM 3.1 saw it\n${line}`, allowed: [step(line)], role: "nurse", beat: "tray" }).length, 1);
  assert.equal(scanBeat({ text: `${line}\n${line}`, allowed: [step(line)], role: "nurse", beat: "tray" }).length, 1, "one region takes out one place");
});

test("a model step whose text is not a step line gets no allowance", () => {
  for (const t of ["SAM 3.1 saw three swabs", "Checking with SAM 3.1… 3 s and more", "Done · live (SAM 4, 2 s)", "Checking with Muse Spark… 3 s"]) {
    assert.equal(scanBeat({ text: `Card\n${t}`, allowed: [step(t)], role: "nurse", beat: "tray" }).length, 1, t);
  }
  for (const t of ["Checking with Muse Voice… 12 s", "Done · live (Spark Open, 4 s)", "✓ Done · live (SAM 3.1, 0.9 s) Expand"]) assert.ok(isStepLine(t), t);
});

test("modelText read by DOM position is what the model rules see", () => {
  const text = "Tray\nChecking with SAM 3.1… 3 s";
  assert.deepEqual(scanBeat({ text, modelText: "Tray\n", role: "nurse", beat: "tray" }), []);
  assert.equal(scanBeat({ text, modelText: text, role: "nurse", beat: "tray" }).length, 1);
  assert.equal(scanBeat({ text, modelText: "Tray\n", role: "patient", beat: "home" }).length, 1, "patient: no allowance");
});

test("allowedText takes out each allowed region once; empty and unallowed regions are ignored", () => {
  const line = "Checking with SAM 3.1… 3 s";
  assert.equal(allowedText(`a ${line} b ${line}`, [step(line), step(""), step("SAM 3.1")]), `a  b ${line}`);
});

test("run.mjs reads the model text with the allowed regions hidden, open Expand views only", () => {
  const src = fs.readFileSync(new URL("./run.mjs", import.meta.url), "utf8");
  assert.match(src, /ALLOWED_SELECTOR, STEP_LINE\.source/);
  assert.match(src, /setProperty\("display", "none", "important"\)/);
  assert.equal(ALLOWED_SELECTOR, '.model-step, [data-expand="open"]');
});
