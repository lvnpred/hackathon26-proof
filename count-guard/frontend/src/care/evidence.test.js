import test from "node:test";
import assert from "node:assert/strict";
import {
  PALETTE, boxLabel, boxesAt, capturedLine, chipText, colourFor, countSeries, evidenceView, explain, explainRegions, modeWord, plural,
  regionLabel, seenCell,
} from "./evidence.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const o = (id, label, score, kept = true) => ({ id, label, bbox: [0.1, 0.1, 0.1, 0.1], score, kept });
const F = [{ t: 0, index: 0, objects: [] }, { t: 0.5, index: 1, objects: [o("1", "towel clip", 0.9), o("2", "towel clip", 0.3, false)] }, { t: 1, index: 2, objects: [o("1", "towel clip", 0.9), o("3", "towel clip", 0.8)] }];

test("boxesAt and countSeries", () => {
  assert.deepEqual(boxesAt(F, 0.5, false).map((b) => b.id), ["1"]);
  assert.deepEqual(boxesAt(F, 0.5, true).map((b) => b.id), ["1", "2"]);
  assert.deepEqual(boxesAt(F, 7, false), []);
  assert.deepEqual(boxesAt(null, 0, false), []);
  assert.deepEqual(countSeries(F, "towel clip"), [{ t: 0, n: 0 }, { t: 0.5, n: 1 }, { t: 1, n: 2 }]);
});

test("boxesAt finds a photo frame by index when t is null", () => {
  const photos = [{ t: null, index: 0, objects: [o("1", "scissors", 0.9)] }, { t: null, index: 1, objects: [o("2", "scissors", 0.8)] }];
  assert.deepEqual(boxesAt(photos, 1, false).map((b) => b.id), ["2"]);
});

test("boxLabel", () => {
  assert.equal(boxLabel(o("1", "towel clip", 0.9)), "towel clip 1 0.90");
  assert.equal(boxLabel({ id: "4", label: "tray", score: null }), "tray 4");
});

test("explain: short concept, best frame, ignored", () => {
  const rows = [{ concept: "scissors", planned: 3, seen: 3, at_s: 0.5 }, { concept: "towel clip", planned: 4, seen: 3, at_s: 1 }];
  assert.deepEqual(explain(rows, F, 0.45, "video"), ["Saw 3 of 4 towel clips.", "The best frame was 1 s.", "1 detection under confidence 0.45 was ignored."]);
  assert.deepEqual(explain([{ concept: "scissors", planned: 3, seen: 3, at_s: 0.5 }], [{ t: 0.5, index: 1, objects: [o("1", "scissors", 0.9)] }], 0.45, "photos"), ["Saw every planned item: 3 of 3."]);
});

test("explain: nothing found is a sentence, not an error", () => {
  assert.deepEqual(explain([{ concept: "scissors", planned: 3, seen: 0, at_s: null }], [], 0.45, "video"), ["Nothing found above confidence 0.45."]);
  assert.deepEqual(explain([{ concept: "scissors", planned: 3, seen: 0, at_s: null }], [{ t: 0, index: 0, objects: [o("1", "scissors", 0.2, false)] }], 0.45, "video"), ["Nothing found above confidence 0.45.", "1 detection under confidence 0.45 was ignored."]);
  assert.deepEqual(explain([], [{ t: 0, index: 0, objects: [o("1", "a", 0.1, false), o("2", "a", 0.1, false)] }], 0.45, "video"), ["Nothing found above confidence 0.45.", "2 detections under confidence 0.45 were ignored."]);
});

test("plural", () => {
  assert.equal(plural("towel clip", 4), "towel clips");
  assert.equal(plural("towel clip", 1), "towel clip");
  assert.equal(plural("scissors", 3), "scissors");
});

test("regionLabel and explainRegions", () => {
  assert.equal(regionLabel({ label: "SBP", value: "88" }), "SBP 88");
  assert.equal(regionLabel({ label: "HR", value: null }), "HR not read");
  assert.equal(regionLabel({ label: null, value: null }), "not read");
  assert.equal(regionLabel({ label: "blister strip", value: null }), "blister strip");
  assert.deepEqual(explainRegions([{ bbox: [0, 0, 1, 1], label: "SBP", value: "88" }, { bbox: [0, 0, 1, 1], label: null, value: null }, { bbox: null, label: "HR", value: "80" }]),
    ["Read 2 values from 2 regions.", "1 region had no value read.", "1 value was read with no box."]);
  assert.deepEqual(explainRegions([{ bbox: [0, 0, 1, 1], label: "SBP", value: "88" }, { bbox: [0, 0, 1, 1], label: "DBP", value: null }, { bbox: [0, 0, 1, 1], label: null, value: null }]),
    ["Read 1 values from 3 regions.", "2 regions had no value read."]);
});

test("mode, chip and colour", () => {
  assert.deepEqual([["sam-3.1", false], ["prepared", false], ["prepared", true], ["prepared (live call failed)", false]].map(([s, h]) => modeWord(s, h)), ["live", "prepared", "Sample", "failed"]);
  assert.equal(modeWord("rules", false), "");
  assert.equal(chipText([{ model: "spark", source: "prepared" }, { model: "sam", source: "prepared" }], true), "SAM 3.1 · Sample");
  assert.equal(chipText([{ model: "spark", source: "muse-spark-1.3" }], false), "Muse Spark 1.3 · live");
  assert.equal(chipText([], false), "");
  assert.equal(colourFor("retractor"), colourFor("retractor"));
  assert.equal(PALETTE.length, 8);
  assert.ok(PALETTE.includes(colourFor("towel clip")));
});

test("a missing sidecar falls back to the count table", () => {
  assert.deepEqual(evidenceView(null, { rows: [{ concept: "x" }] }), { fallback: true, rows: [{ concept: "x" }] });
  assert.deepEqual(evidenceView(null, null), { fallback: true, rows: [] });
  assert.equal(seenCell({ planned: 3, seen: 2 }), "2 (missing)");
  assert.equal(seenCell({ planned: 3, seen: null }), "not checked");
  assert.equal(seenCell({ planned: 3, seen: 3 }), "3");
});

test("evidenceView builds the viewer data from a sidecar", () => {
  const sidecar = {
    kind: "tray", media: "video", images: [{ url: "/p/1", t: 0.5, index: 1 }], frames: F, regions: null, min_score: 0.45,
    calls: [{ model: "sam", source: "prepared" }], raw: { sam: [] }, handmade: true,
    cited_by: [{ event_id: "e1", type: "tray.checked", when: 0, by: "Nurse Asha (synthetic)" }],
  };
  const v = evidenceView(sidecar, { rows: [{ concept: "towel clip", planned: 4, seen: 3, at_s: 1 }] });
  assert.equal(v.fallback, false);
  assert.equal(v.title, "Tray check");
  assert.equal(v.chip, "SAM 3.1 · Sample");
  assert.equal(v.sentences[0], "Saw 3 of 4 towel clips.");
  assert.deepEqual(v.raw, { sam: [] });
  assert.equal(v.cited.length, 1);
});

test("a photo sidecar explains its regions", () => {
  const sidecar = {
    kind: "monitor", media: "photos", images: [{ url: "/p/1", t: null, index: 0 }], frames: null, min_score: 0.45,
    regions: [{ bbox: [0.1, 0.1, 0.2, 0.1], label: "SBP", value: "88", row: null }], calls: [], raw: {}, handmade: false, cited_by: [],
  };
  const v = evidenceView(sidecar, null);
  assert.equal(v.title, "Monitor photo");
  assert.deepEqual(v.sentences, ["Read 1 values from 1 regions."]);
});

test("capturedLine", () => {
  assert.equal(capturedLine({ type: "tray.checked", when: 9 * 60000 - 9 * 60000 + 18 * 60000, by: "Nurse Asha (synthetic)" }), "Captured to record: tray.checked · 09:18 · Nurse Asha");
  assert.equal(capturedLine({ type: "tray.checked", when: "Day 0 09:18", by: "Nurse Asha" }), "Captured to record: tray.checked · 09:18 · Nurse Asha");
});

test("viewer copy has no advice words", () => {
  for (const s of ["Expected", "Seen", "Status", "Why:", "Raw output", "Show ignored", "Captured to record: tray.checked · 09:18 · Nurse Asha", "Nothing found above confidence 0.45.", "The best frame was 3.5 s.", "2 detections under confidence 0.45 were ignored.", "Read 3 values from 3 regions."]) assert.doesNotMatch(s, ADVICE);
});
