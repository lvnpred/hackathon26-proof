import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { canInspect, chipFor, draftChip, findingFor, heardChip, momentFor, statusLabel } from "./moments.js";

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
