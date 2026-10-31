import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { canInspect, chipFor, draftChip, FILTERS, filterMoments, findingFor, heardChip, lastSigned, momentFor, statusLabel } from "./moments.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const call = (model, source) => ({ model, source });
const CHIP_VECTORS = [
  [{ calls: [call("voice", "prepared")], handmade: false, source: "rules" }, "Muse Voice → Rules · prepared"],
  [{ calls: [], handmade: false, source: "rules" }, "Rules"],
  [{ calls: [call("sam", "prepared"), call("spark", "prepared")], handmade: true, source: "prepared" }, "SAM 3.1 → Muse Spark 1.3 · Sample"],
  [{ calls: [call("voice", "muse-voice-transcribe"), call("spark", "muse-spark-1.3")], handmade: false, source: "muse-spark-1.3" }, "Muse Voice → Muse Spark 1.3 · live"],
  [{ calls: [call("voice", "prepared")], handmade: false, source: "" }, "Muse Voice · prepared"],
  [{ calls: [call("spark", "failed")], handmade: false, source: "failed" }, "Muse Spark 1.3 · failed"],
];

test("chip vectors", () => { for (const [input, want] of CHIP_VECTORS) assert.equal(chipFor(input), want); });

test("worst mode wins", () => {
  assert.equal(chipFor({ calls: [call("voice", "muse-voice-transcribe"), call("spark", "prepared")] }), "Muse Voice → Muse Spark 1.3 · prepared");
});

test("heardChip and draftChip", () => {
  assert.equal(heardChip("prepared"), "Muse Voice · prepared");
  assert.equal(draftChip("typed", "rules"), "Rules");
  assert.equal(draftChip("muse-voice-transcribe", "muse-spark-1.3"), "Muse Voice → Muse Spark 1.3 · live");
  assert.equal(draftChip("", "rules (model reply not usable)"), "Muse Spark 1.3 · failed");
});

test("status labels follow the viewer", () => {
  assert.deepEqual(statusLabel({ status: "flagged", owner: "doctor" }, "doctor"), { text: "Needs you", tone: "blue" });
  assert.deepEqual(statusLabel({ status: "flagged", owner: "doctor" }, "nurse"), { text: "Flagged", tone: "amber" });
  assert.deepEqual(statusLabel({ status: "open", owner: "nurse" }, "doctor"), { text: "Waiting for the nurse", tone: "grey" });
  assert.deepEqual(statusLabel({ status: "open", owner: "nurse" }, "nurse"), { text: "Needs you", tone: "blue" });
  assert.deepEqual(statusLabel({ status: "matches", owner: null }, "nurse"), { text: "Matches", tone: "green" });
  assert.deepEqual(statusLabel({ status: "recorded", owner: null }, "nurse"), { text: "Recorded", tone: "green" });
  assert.deepEqual(statusLabel({ status: "failed", owner: null }, "nurse"), { text: "Failed", tone: "grey" });
});

test("momentFor matches id, photo_id, evidence_id and written id", () => {
  const m = { id: "a", photo_id: "p", evidence_id: "e", written: [{ event_id: "w" }] };
  const view = { ai_moments: [{ id: "z", written: [] }, m] };
  for (const id of ["a", "p", "e", "w"]) assert.equal(momentFor(view, id), m);
  assert.equal(momentFor(view, "nope"), null);
  assert.equal(momentFor({}, "a"), null);
});

test("findingFor and canInspect", () => {
  const m = { kind: "visual", finding: "S", patient_finding: "P" };
  assert.equal(findingFor(m, "staff"), "S");
  assert.equal(findingFor(m, "patient"), "P");
  assert.equal(canInspect(m), true);
  assert.equal(canInspect({ kind: "record" }), false);
});

test("all C7 copy passes the advice rule", () => {
  for (const s of ["Input", "What the AI found", "Record", "Model", "Inspect", "Close", "Nothing to inspect with that id.", "No model call.", "No raw output is kept for this result.", "Record & evidence", "All", "Needs you", "Photos", "Video", "Voice", "Answers", "Alerts", "Nothing here for this filter.", "AI activity", "Waiting for the doctor", "Flagged", "Matches", "Recorded", "Failed"]) assert.doesNotMatch(s, ADVICE);
});

test("AiMoment hides the arrow from the accessible name", () => {
  const src = fs.readFileSync(new URL("./AiMoment.jsx", import.meta.url), "utf8");
  assert.match(src, /aria-hidden="true">›/);
  assert.match(src, /className="ai-moment" data-moment=/);
});

const mom = (id, filter, status, owner, patient_finding = "x", capability = "tray") => ({ id, filter, status, owner, patient_finding, capability });
const ROWS = [
  mom("a", "photos", "flagged", "nurse"),
  mom("b", "video", "flagged", "doctor"),
  mom("c", "voice", "recorded", null, null, "orders"),
  mom("d", "answers", "matches", null),
  mom("e", "alerts", "open", "doctor"),
  mom("f", null, "recorded", null, null, "typed_orders"),
];
const ids = (list) => list.map((m) => m.id).join("");

test("filterMoments keeps one chip's rows", () => {
  assert.deepEqual(FILTERS.map(([key]) => key), ["all", "needs", "photos", "video", "voice", "answers", "alerts"]);
  assert.equal(ids(filterMoments(ROWS, "all", "doctor")), "abcdef");
  assert.equal(ids(filterMoments(ROWS, "photos", "doctor")), "a");
  assert.equal(ids(filterMoments(ROWS, "video", "doctor")), "b");
  assert.equal(ids(filterMoments(ROWS, "voice", "doctor")), "c");
  assert.equal(ids(filterMoments(ROWS, "answers", "doctor")), "d");
  assert.equal(ids(filterMoments(ROWS, "alerts", "doctor")), "e");
});

test("needs keeps the rows that read Needs you for this role", () => {
  assert.equal(ids(filterMoments(ROWS, "needs", "doctor")), "be");
  assert.equal(ids(filterMoments(ROWS, "needs", "nurse")), "a");
});

test("filterMoments patient lens drops rows without a patient sentence", () => {
  assert.equal(ids(filterMoments(ROWS, "all", "patient", "patient")), "abde");
});

test("lastSigned returns the newest recorded moment of the capability", () => {
  const rows = [mom("n", "voice", "open", "doctor", null, "orders"), mom("y", "voice", "recorded", null, null, "orders"), mom("z", "voice", "recorded", null, null, "orders")];
  assert.equal(lastSigned(rows, "orders").id, "y");
  assert.equal(lastSigned(rows, "discharge"), null);
  assert.equal(lastSigned(undefined, "orders"), null);
});

test("Chart and MyCare use RecordEvidence; the three cards are gone", () => {
  const read = (name) => fs.readFileSync(new URL(`./${name}`, import.meta.url), "utf8");
  assert.doesNotMatch(read("Chart.jsx"), /import .*\b(Photos|VideoChecks|OrderTasks)\b/);
  assert.match(read("Chart.jsx"), /<RecordEvidence /);
  assert.match(read("MyCare.jsx"), /<RecordEvidence [^>]*lens="patient"/);
  for (const name of ["Photos.jsx", "VideoChecks.jsx", "OrderTasks.jsx"]) assert.equal(fs.existsSync(new URL(`./${name}`, import.meta.url)), false);
});

test("RecordEvidence copy, aria-pressed chips and thumbnail", () => {
  const src = fs.readFileSync(new URL("./RecordEvidence.jsx", import.meta.url), "utf8");
  assert.match(src, /aria-label="Record and evidence"/);
  assert.match(src, /aria-pressed=\{filter === key\}/);
  assert.match(src, /Nothing here for this filter\./);
  assert.match(src, /\/journey\/episodes\/\$\{episodeId\}\/photos\/\$\{moment\.photo_id\}/);
  assert.match(src, /width=\{40\}/);
});
