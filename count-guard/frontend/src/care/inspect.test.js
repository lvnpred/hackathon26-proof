import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { AI_BY, AI_NOTE, eventIdLines, historyLine, NOT_RECORDED, draftSources, ruleCards, FIELD_LABEL, REGION_FIELD, diffLine, fieldDiffs, segments, TABS, focusRegion, inspectEpisode, modelRows, regionFieldLine, whyRegions, readInspect, recordLine, resolveMoment, stepFrame, tabsFor } from "./inspect.js";
import { canInspect } from "./moments.js";

const src = (f) => fs.readFileSync(new URL(f, import.meta.url), "utf8");

test("readInspect rejects bad ids", () => {
  assert.deepEqual(readInspect(new URLSearchParams("inspect=dayplan:abc&focus=amlodipine")), { momentId: "dayplan:abc", episodeId: null, focus: "amlodipine" });
  assert.deepEqual(readInspect(new URLSearchParams("inspect=a&episode=ep-1")), { momentId: "a", episodeId: "ep-1", focus: null });
  for (const bad of ["inspect=%3Cscript%3E", `inspect=${"a".repeat(81)}`, "", "inspect="]) assert.equal(readInspect(new URLSearchParams(bad)), null);
  assert.equal(readInspect(new URLSearchParams("inspect=a&focus=%3Cb%3E")).focus, null);
});

test("a patient sees two tabs", () => {
  assert.deepEqual(tabsFor("patient"), ["why", "evidence"]);
  assert.deepEqual(tabsFor("staff"), ["why", "evidence", "history", "model"]);
  assert.deepEqual(TABS.map(([, label]) => label), ["Why", "Evidence", "History", "Model"]);
  assert.equal(TABS.length, 4);
});

test("modelRows", () => {
  assert.deepEqual(modelRows([{ model: "sam", model_id: "sam-3.1", source: "prepared", ms: null }, { model: "spark", model_id: "m", source: "muse-spark-1.3", ms: 120 }], false),
    [{ name: "sam", id: "sam-3.1", mode: "prepared", ms: "—" }, { name: "spark", id: "m", mode: "muse-spark-1.3", ms: "120 ms" }]);
  assert.equal(modelRows([{ model: "sam", model_id: "x", source: "prepared", ms: 1 }], true)[0].mode, "Sample");
  assert.deepEqual(modelRows(null, false), []);
});

test("recordLine", () => {
  const w = { type: "tray.checked", when: "09:20", by: "Nurse Asha (synthetic)", plain: "Tray checked, 14 of 15." };
  assert.equal(recordLine(w, "staff"), "09:20 · Nurse Asha · Tray checked, 14 of 15.");
  assert.equal(recordLine(w, "patient"), "09:20 · Tray checked, 14 of 15.");
  assert.doesNotMatch(recordLine(w, "staff"), /\b[a-z]+\.[a-z_]+\b/);
  assert.doesNotMatch(recordLine(w, "patient"), /\b[a-z]+\.[a-z_]+\b/);
});

test("stepFrame clamps", () => {
  assert.equal(stepFrame(0, -1, 5), 0);
  assert.equal(stepFrame(4, 1, 5), 4);
  assert.equal(stepFrame(2, 1, 5), 3);
});

test("a patient lens never resolves a staff-only moment", () => {
  const moments = [{ id: "a", patient_finding: null }, { id: "b", patient_finding: "x", written: [{ event_id: "w" }] }];
  assert.equal(resolveMoment(moments, "a", "patient"), null);
  assert.equal(resolveMoment(moments, "a", "staff").id, "a");
  assert.equal(resolveMoment(moments, "w", "patient").id, "b");
  assert.equal(resolveMoment(moments, "zzz", "staff"), null);
  assert.equal(resolveMoment(undefined, "a", "staff"), null);
});

test("an exact moment id wins over a staff-only moment that lists it as a follow-up", () => {
  const moments = [{ id: "v", patient_finding: null, written: [{ event_id: "s" }] }, { id: "s", patient_finding: "x" }];
  assert.equal(resolveMoment(moments, "s", "patient").id, "s");
  assert.equal(resolveMoment(moments, "s", "staff").id, "s");
});

test("Inspector renders inside .app without a portal or dialog role", () => {
  const s = src("./Inspector.jsx");
  assert.match(s, /aria-label="Inspector"/);
  assert.match(s, /Nothing to inspect with that id\./);
  assert.doesNotMatch(s, /createPortal/);
  assert.doesNotMatch(s, /role="dialog"/);
  assert.match(s, /replace: true/);
  assert.match(s, /export const KIND_VIEWS/);
  assert.match(src("./CareShell.jsx"), /from "\.\/Inspector\.jsx"/);
});

test("regionFieldLine names the form field each value filled", () => {
  assert.equal(regionFieldLine({ label: "SBP", value: "88" }, "monitor"), "SBP 88 \u2192 Obs \u00b7 systolic");
  assert.equal(regionFieldLine({ label: "HR", value: null }, "monitor"), "HR not read");
  assert.equal(regionFieldLine({ label: "Amlodipine 10 mg", value: null }, "strip"), "Amlodipine 10 mg \u2192 Dose \u00b7 medicine");
  assert.equal(regionFieldLine({ label: null }, "strip"), "not read");
  assert.equal(regionFieldLine({ label: "Amlodipine 10 mg" }, "medicines"), "Amlodipine 10 mg \u2192 Medicines from home");
  assert.equal(REGION_FIELD.monitor.DBP, "Obs \u00b7 diastolic");
});

test("focusRegion reads a digit string or a region object", () => {
  assert.equal(focusRegion("1"), 1);
  assert.equal(focusRegion({ region: 2 }), 2);
  assert.equal(focusRegion("amlodipine"), null);
  assert.equal(focusRegion(null), null);
});

test("a patient inspects only their own episode, whatever ?episode= says", () => {
  assert.equal(inspectEpisode({ lens: "patient", param: "ep-other", chartId: null, own: "ep-mine" }), "ep-mine");
  assert.equal(inspectEpisode({ lens: "staff", param: "ep-2", chartId: "ep-1", own: null }), "ep-2");
  assert.equal(inspectEpisode({ lens: "staff", param: null, chartId: "ep-1", own: null }), "ep-1");
});

test("Inspector seeds focus from the URL and resets per moment", () => {
  const body = src("Inspector.jsx");
  assert.match(body, /useState\(initialFocus\)/);
  assert.match(body, /<Body key=\{moment\.id\} initialFocus=\{urlFocus\}/);
  assert.match(body, /inspectEpisode\(/);
});

test("the Model tab shows raw output through RawOutput", () => {
  assert.match(src("Inspector.jsx"), /<RawOutput moment=\{moment\}/);
  assert.match(src("Inspector.jsx"), /visual: \{ Input: VisualInput, Found: VisualFound \}/);
});

test("VideoCheck shows source words, not the source label", () => {
  assert.doesNotMatch(src("VideoCheck.jsx"), /sourceLabel\(/);
  assert.doesNotMatch(src("TaskProof.jsx"), /sourceLabel\(photo/);
  assert.doesNotMatch(src("MyCare.jsx"), /sourceLabel\(/);
});

test("whyRegions counts values for a monitor and labels for strips", () => {
  const monitor = [{ label: "SBP", value: "88", bbox: [0, 0, 1, 1] }, { label: "HR", value: null, bbox: [0, 0, 1, 1] }];
  assert.equal(whyRegions("monitor", monitor).join(" "), "Read 1 values from 2 regions. 1 region had no value read.");
  const strip = [{ label: "Amlodipine 10 mg", value: null, bbox: [0, 0, 1, 1] }];
  assert.deepEqual(whyRegions("strip", strip), ["Read 1 strip from 1 region."]);
  const meds = [{ label: "A", value: null }, { label: "B", value: null }, { label: null, value: null }];
  assert.deepEqual(whyRegions("medicines", meds), ["Read 2 strips from 3 regions.", "1 region had no strip read."]);
  for (const line of [...whyRegions("strip", strip), ...whyRegions("medicines", meds)]) assert.doesNotMatch(line, /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i);
});

test("segments reassemble the text, including overlap and out-of-range marks", () => {
  const t = "Paracetamol 1 g every 6 hours";
  const cases = [
    [{ start: 0, end: 11, item: 0, field: "name" }, { start: 12, end: 15, item: 0, field: "amount" }],
    [{ start: 0, end: 11 }, { start: 5, end: 14 }, { start: 12, end: 15 }],
    [{ start: -3, end: 4 }, { start: 20, end: 99 }, { start: 9, end: 9 }],
    [],
  ];
  for (const marks of cases) assert.equal(segments(t, marks).map((s) => s.text).join(""), t);
  assert.deepEqual(segments(t, cases[1]).filter((s) => s.mark).map((s) => s.text), ["Paracetamol", "1 g"]);
  assert.equal(segments(t, cases[2]).every((s) => !s.mark), true);
});

test("fieldDiffs: an amount edit, an added row, a removed row", () => {
  const dose = { kind: "dose", text: "Paracetamol 1 g", name: "paracetamol", amount: "1 g", every_h: 6, proof: "photo" };
  const obs = { kind: "obs", text: "BP", every_h: 1, proof: "none", limits: { sbp_min: 90 } };
  assert.deepEqual(fieldDiffs([dose], [dose]), []);
  const edit = fieldDiffs([dose], [{ ...dose, amount: "500 mg" }]);
  assert.deepEqual(edit, [{ item: 0, field: "amount", drafted: "1 g", signed: "500 mg" }]);
  assert.equal(diffLine(edit[0]), "Amount: 1 g → 500 mg");
  const added = fieldDiffs([dose], [dose, obs]);
  assert.equal(diffLine(added[0]), "Added at signing: BP · every 1 h · alert if systolic < 90");
  const removed = fieldDiffs([dose, obs], [dose]);
  assert.equal(diffLine(removed[0]), "Removed at signing: BP · every 1 h · alert if systolic < 90");
  const limit = fieldDiffs([obs], [{ ...obs, limits: {} }]);
  assert.equal(diffLine(limit[0]), "Systolic min: 90 → none");
  assert.equal(FIELD_LABEL.every_h, "Every");
});

test("voice kind is registered and its copy passes ADVICE", () => {
  assert.match(src("./Inspector.jsx"), /voice: \{ Input: VoiceInput, Found: VoiceFound \}/);
  const jsx = src("./InspectVoice.jsx");
  assert.match(jsx, /No word links for this draft\./);
  assert.match(jsx, /className=\{`mark/);
  assert.doesNotMatch(jsx, /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i);
});

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const line = (id, type) => ({ id, type, when: "09:20", by: "Dr. A. Rao (synthetic)", plain: "Amlodipine 5 mg ordered." });

test("ruleCards: both sides, a missing fact, and a patient lens with no event code", () => {
  const both = ruleCards({ intent: line("a", "rx.ordered"), fact: line("b", "dose.logged") }, "staff");
  assert.deepEqual(both.map((c) => c.heading), ["Ordered / prescribed", "What was read"]);
  assert.match(both[0].line, /^09:20 · /);
  const none = ruleCards({ intent: line("a", "rx.ordered"), fact: null }, "staff");
  assert.equal(none[1].line, NOT_RECORDED);
  assert.equal(none[1].line, "Not recorded");
  const patient = ruleCards({ intent: line("a", "rx.ordered"), fact: line("b", "dose.logged") }, "patient");
  for (const c of patient) assert.doesNotMatch(c.line, /\b[a-z]+\.[a-z_]+\b/);
});

test("draftSources dedupes cited lines in order", () => {
  const refs = { lines: [{ text: "x", evidence: [line("a"), line("b")] }, { text: "y", evidence: [line("a")] }] };
  assert.deepEqual(draftSources(refs).map((l) => l.id), ["a", "b"]);
  assert.deepEqual(draftSources(undefined), []);
});

test("InspectText is registered and its copy is not advice", () => {
  assert.match(src("./Inspector.jsx"), /answer: \{ Input: AnswerInput, Found: AnswerFound \}/);
  assert.match(src("./Inspector.jsx"), /draft: \{ Input: DraftInput, Found: DraftFound \}/);
  const s = src("./InspectText.jsx");
  assert.match(s, /No input: this check compares two records\./);
  for (const text of ["No input: this check compares two records.", "No record lines were cited.", "Not recorded", "Ordered / prescribed", "Recorded / read", "Rule: The strength read from a strip is compared with the prescription row for the same medicine."]) {
    assert.doesNotMatch(text, ADVICE);
  }
});

test("the patient lens opens no camera count: no Inspect, no resolve", () => {
  const visual = { id: "v", kind: "visual", patient_finding: "The tray was checked by camera before your surgery.", evidence_id: "e" };
  assert.equal(canInspect(visual, "patient"), false);
  assert.equal(canInspect(visual, "staff"), true);
  assert.equal(canInspect({ kind: "photo_read" }, "patient"), true);
  assert.equal(resolveMoment([visual], "v", "patient"), null);
  assert.equal(resolveMoment([visual], "e", "patient"), null);
  assert.equal(resolveMoment([visual], "v", "staff").id, "v");
  assert.match(src("./AiMoment.jsx"), /canInspect\(moment, lens\)/);
});

test("the visual Found view in the patient lens has no raw output, no chart links and no staff flag sentence", () => {
  const s = src("./InspectVisual.jsx");
  assert.match(s, /linkLines=\{staff\}/);
  assert.match(s, /const staff = lens !== "patient"/);
  assert.match(s, /\{staff && <p className="small">.*checkLabel\(check\)/);
  // Raw output and the event-code lines only render when linkLines is true.
  const ev = src("./Evidence.jsx");
  assert.match(ev, /\{linkLines && <details><summary>Raw output/);
  assert.match(ev, /\{linkLines && view\.cited\.map/);
});

test("lit marks and chips use theme tokens and an explicit text colour", () => {
  const css = src("./care.css");
  for (const rule of [/\.inspector-found \.mark \{[^}]*\}/, /\.mark\.lit[^{]*\{[^}]*\}/, /\.plan-item\.lit \{[^}]*\}/]) {
    const block = css.match(rule)[0];
    assert.doesNotMatch(block, /#[0-9a-f]{3,8}\b/i);
    assert.match(block, /color: var\(--(ink|on-sun)\)/);
  }
});

test("historyLine reads as a plain audit trail", () => {
  const ai = { type: "work.done", event_id: "e1", when: "09:20", by: AI_BY, plain: `${AI_BY}: Assigned 2 tasks to Nurse Asha.` };
  const nurse = { type: "obs.recorded", event_id: "e2", when: "09:25", by: "Nurse Asha (synthetic)", plain: "Nurse Asha logged BP 88/60." };
  const bare = { type: "tray.checked", event_id: "e3", when: "Yesterday 09:30", by: "Nurse Asha (synthetic)", plain: "Tray check by photos: all seen." };
  assert.equal(historyLine(ai), "09:20 · AI: Assigned 2 tasks to Nurse Asha.");
  assert.equal(historyLine(nurse), "09:25 · Nurse Asha logged BP 88/60.");
  assert.equal(historyLine(bare), "Yesterday 09:30 · Nurse Asha · Tray check by photos: all seen.");
  for (const w of [ai, nurse, bare]) {
    const line = historyLine(w);
    assert.doesNotMatch(line, /task\.assigned|work\.done|\b[a-z]+\.[a-z_]+\b/);
    assert.equal(line.split(AI_BY).length - 1, 0);
  }
  const rx = { type: "rx.ordered", event_id: "e4", when: "09:10", by: "Dr. A. Rao (synthetic)", plain: "Prescription from Dr. A. Rao (synthetic): 2 medicines (voice)." };
  assert.equal(historyLine(rx), "09:10 · Prescription from Dr. A. Rao: 2 medicines (voice).");
  const nudge = { type: "nudge.raised", event_id: "e5", when: "09:40", by: "Nurse Meena (synthetic)", plain: "Nudge to Nurse Meena: Obs are overdue." };
  assert.equal(historyLine(nudge), "09:40 · Nudge to Nurse Meena: Obs are overdue.");
  assert.equal(historyLine({ ...nudge, by: "Ward system" }), "09:40 · Ward system · Nudge to Nurse Meena: Obs are overdue.");
  assert.equal(AI_NOTE, "AI = AI admin acting for Ward 4");
  assert.equal(eventIdLines([ai, nurse]), "work.done:e1\nobs.recorded:e2");
});

test("the Inspector opens on Why, keeps Undo in the header and handles a failed copy", () => {
  const s = src("./Inspector.jsx");
  assert.match(s, /useState\("why"\)/);
  assert.match(s, /<AgentUndo moment=\{moment\}/);
  assert.match(s, /Copy event IDs/);
  assert.match(s, /Could not copy/);
  assert.doesNotMatch(s, /<span className="chip">\{modelChip\(moment\)\}<\/span>\s*<StatusPill/);
  assert.match(src("./InspectAgent.jsx"), /"How it chose"/);
  assert.match(src("./InspectAgent.jsx"), /A fixed rule, not a model/);
});

test("record and history lines use the dock clock when the row carries ms", async () => {
  const { historyLine, recordLine } = await import("./inspect.js");
  const H = 3600000;
  const w = { at_ms: 13 * H, when: "22:00", by: "Nurse Asha", plain: "Nurse Asha logged BP.", type: "obs.recorded" };
  assert.equal(historyLine(w, 13 * H), "22:00 · Nurse Asha logged BP.");
  assert.equal(historyLine(w, 37 * H), "Yesterday 22:00 · Nurse Asha logged BP.");
  assert.equal(recordLine(w, "patient", 37 * H), "Yesterday 22:00 · Nurse Asha logged BP.");
  assert.equal(historyLine({ ...w, at_ms: undefined, when: "Yesterday 22:00" }, 37 * H), "Yesterday 22:00 · Nurse Asha logged BP.");
});

test("every product screen formats times from ms with the dock clock, not the server's when", async () => {
  const { readFileSync } = await import("node:fs");
  const src = (f) => readFileSync(new URL(`./${f}`, import.meta.url), "utf8");
  assert.match(src("AlertBanner.jsx"), /stamp\(nudge, nowMs\)/);
  assert.match(src("Timeline.jsx"), /stamp\(item, nowMs\)/);
  assert.match(src("InspectAgent.jsx"), /stamp\(i, nowMs\)/);
  assert.doesNotMatch(src("AlertBanner.jsx"), /nudge\.when/);
  assert.doesNotMatch(src("Timeline.jsx"), /item\.when/);
});
