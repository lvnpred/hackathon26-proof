import test from "node:test";
import assert from "node:assert/strict";
import {
  isFocusRegion, PALETTE, boxLabel, drawItems, hasIgnored, ignoredFrameNames, isDense, isFocus, labelKind, sawCount, sawRows, boxGroups, boxesAt, capturedLine, chipText, colourFor, countSeries, evidenceView, explain, explainRegions, modeWord, plural,
  regionLabel, seenCell, startImage, itemName, nudgeLabels,
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

test("startImage opens on the best frame of the first short row", () => {
  const images = [{ t: 0.5, index: 0 }, { t: 1, index: 1 }, { t: 1.5, index: 2 }];
  const rows = [{ concept: "a", planned: 2, seen: 2, at_s: 0.5 }, { concept: "b", planned: 3, seen: 2, at_s: 1.4 }];
  assert.equal(startImage(images, rows), 2);
  assert.equal(startImage(images, [{ concept: "a", planned: 2, seen: 2, at_s: 1 }]), 1);
  assert.equal(startImage(images, [{ concept: "a", planned: 2, seen: 0, at_s: null }]), 0);
  assert.equal(startImage([{ t: null, index: 0 }], rows), 0);
  assert.equal(startImage([], rows), 0);
});

test("itemName shows the tray name with the model concept beside it", () => {
  assert.equal(itemName({ concept: "scalpel handle", names: ["Knife handle"] }), "Knife handle (scalpel handle)");
  assert.equal(itemName({ concept: "needle holder", names: ["Needle holder"] }), "Needle holder");
  assert.equal(itemName({ concept: "towel clip" }), "towel clip");
});

test("nudgeLabels moves an overlapping label down and leaves clear ones", () => {
  const out = nudgeLabels([{ x: 10, y: 10, w: 60, h: 14 }, { x: 40, y: 12, w: 60, h: 14 }, { x: 200, y: 10, w: 40, h: 14 }]);
  assert.equal(out[0].y, 10);
  assert.equal(out[1].y, 24);
  assert.equal(out[2].y, 10);
});

test("countSeries tolerates a frame with no objects list", () => {
  assert.deepEqual(countSeries([{ t: 0, index: 0 }], "x"), [{ t: 0, n: 0 }]);
});

const ob = (id, label, kept = true, score = 0.9) => ({ id, label, kept, score, bbox: [0, 0, 0.1, 0.1] });

test("drawItems: ignored boxes are dashed grey, kept ones solid in the concept colour", () => {
  const items = drawItems([ob("1", "needle holder"), ob("3", "needle holder", false, 0.31)], null, null);
  assert.equal(items[0].dashed, false);
  assert.equal(items[0].colour, colourFor("needle holder"));
  assert.equal(items[1].dashed, true);
  assert.equal(items[1].colour, "#888");
  assert.equal(items[1].text, "needle holder 3 0.31");
  assert.equal(items[1].ignored, true);
});

test("drawItems: regions follow the strip tone, or grey with their label", () => {
  const regions = [{ bbox: [0, 0, 1, 1], row: 0, label: "SBP", value: 120 }];
  assert.equal(drawItems([], regions, null)[0].text, "SBP 120");
  assert.equal(drawItems([], regions, [{ read: "Cetirizine 10 mg", prescribed: false }])[0].colour, "#c62828");
});

test("isDense: any full pill wider than 1.5x its box, however many boxes", () => {
  const ok = { pill: 100, box: 80 };
  assert.equal(isDense(Array(14).fill(ok)), false);
  assert.equal(isDense([{ pill: 100, box: 80 }, { pill: 121, box: 80 }]), true);
  assert.equal(isDense([]), false);
});

test("labelKind: the inline picture always uses tags; the expanded view uses pills unless crowded", () => {
  assert.equal(labelKind(ob("1", "scissors"), { expanded: false, dense: false, focus: null }), "tag");
  assert.equal(labelKind(ob("1", "scissors"), { expanded: true, dense: false, focus: null }), "full");
  assert.equal(labelKind(ob("1", "scissors"), { expanded: true, dense: true, focus: null }), "tag");
  assert.equal(labelKind(ob("3", "scissors", false), { expanded: true, dense: true, focus: null }), "full");
  assert.equal(labelKind(ob("1", "scissors"), { expanded: true, dense: true, focus: { concept: "scissors", id: "1" } }), "full");
  assert.equal(labelKind(ob("2", "scissors"), { expanded: true, dense: true, focus: { concept: "scissors", id: "1" } }), "tag");
  assert.equal(labelKind(ob("1", "scissors"), { expanded: true, dense: true, focus: { concept: "scissors" } }), "tag");
});

test("isFocus: everything with no pick, the item's boxes for an item pick, one box for a box pick", () => {
  assert.equal(isFocus(ob("1", "swab"), null), true);
  assert.equal(isFocus(ob("1", "swab"), { concept: "swab" }), true);
  assert.equal(isFocus(ob("1", "clip"), { concept: "swab" }), false);
  assert.equal(isFocus(ob("2", "swab"), { concept: "swab", id: "1" }), false);
});

test("sawRows puts short items first with the number missing; sawCount reads 14 of 15", () => {
  const rows = sawRows([{ concept: "scissors", planned: 2, seen: 2 }, { concept: "gauze swab", planned: 15, seen: 14 }, { concept: "clip", planned: 1, seen: null }]);
  assert.deepEqual(rows.map((r) => [r.concept, r.missing]), [["gauze swab", 1], ["scissors", 0], ["clip", 0]]);
  assert.equal(rows[0].colour, colourFor("gauze swab"));
  assert.equal(sawCount(rows[0]), "14 of 15");
  assert.equal(sawCount(rows[2]), "not checked");
  assert.deepEqual(sawRows(null), []);
});

test("boxGroups groups kept boxes by item, sorted, and keeps ignored boxes apart", () => {
  const { groups, ignored } = boxGroups([ob("1", "scissors"), ob("1", "forceps"), ob("2", "scissors"), ob("3", "forceps", false)]);
  assert.deepEqual(groups.map((g) => [g.concept, g.boxes.map((b) => b.id)]), [["forceps", ["1"]], ["scissors", ["1", "2"]]]);
  assert.deepEqual(ignored.map((b) => b.id), ["3"]);
  assert.deepEqual(boxGroups(undefined), { groups: [], ignored: [] });
});

test("hasIgnored and ignoredFrameNames find the frames with an ignored box", () => {
  const frames = [
    { t: 1, index: 0, objects: [ob("1", "a")] },
    { t: 2, index: 1, objects: [ob("1", "a"), ob("3", "a", false)] },
    { t: 2.5, index: 2, objects: [ob("3", "a", false)] },
  ];
  assert.equal(hasIgnored(frames), true);
  assert.equal(hasIgnored([frames[0]]), false);
  assert.equal(hasIgnored(undefined), false);
  const images = [{ t: 1 }, { t: 2 }, { t: 2.5 }];
  assert.deepEqual(ignoredFrameNames(frames, images), [2, 2.5]);
  assert.deepEqual(ignoredFrameNames(frames, [{ index: 0 }, { index: 2 }]), [3]);
});

test("explain counts an ignored detection once however many frames it appears in", () => {
  const frames = [{ t: 0, index: 0, objects: [ob("3", "needle holder", false, 0.3)] }, { t: 1, index: 1, objects: [ob("3", "needle holder", false, 0.3)] }];
  assert.deepEqual(explain([], frames, 0.45, "video"), ["Nothing found above confidence 0.45.", "1 detection under confidence 0.45 was ignored."]);
});

test("capturedLine joins only the parts it has", () => {
  assert.equal(capturedLine({ type: "tray.checked", when: "Day 0 09:18", by: "" }), "Captured to record: tray.checked · 09:18");
  assert.equal(capturedLine({ type: "tray.checked", when: "", by: "Nurse Asha" }), "Captured to record: tray.checked · Nurse Asha");
});

test("a photo read with regions names both models in the viewer chip", () => {
  const calls = [{ model: "sam", source: "sam-3.1" }, { model: "spark", source: "muse-spark-1.3" }];
  assert.equal(chipText(calls, false, undefined, true), "SAM 3.1 + Spark 1.3 · live");
  assert.equal(chipText(calls, false, "sam", true), "SAM 3.1 · live");
  assert.equal(chipText(calls, false), "SAM 3.1 · live");
  assert.equal(evidenceView({ kind: "monitor", calls, regions: [], raw: {} }, { rows: [] }).chip, "SAM 3.1 + Spark 1.3 · live");
});

test("the viewer lists what the AI saw beside the picture and opens an expanded view", async () => {
  const fs = await import("node:fs");
  const jsx = fs.readFileSync(new URL("./Evidence.jsx", import.meta.url), "utf8");
  const big = fs.readFileSync(new URL("./EvidenceExpand.jsx", import.meta.url), "utf8");
  assert.match(jsx, /aria-label="What the AI saw"/);
  assert.match(jsx, /Expand/);
  assert.match(jsx, /\{frames && frames\.length > 1 && \(/);
  assert.doesNotMatch(jsx, /Show all labels|Show ignored/);
  assert.match(big, /role="dialog"/);
  assert.match(big, /aria-modal="true"/);
  assert.match(big, /Ignored by AI/);
  assert.match(big, /Escape/);
});

test("isFocusRegion", () => {
  assert.equal(isFocusRegion(1, { region: 1 }), true);
  assert.equal(isFocusRegion(0, { region: 1 }), false);
  assert.equal(isFocusRegion(0, null), true);
  assert.equal(isFocusRegion(0, { concept: "x" }), true);
});

test("visual Found falls back without a sidecar", () => {
  assert.equal(evidenceView(null, { rows: [] }).fallback, true);
});

test("the twin of backend visual_finding", () => {
  assert.equal(explain([{ concept: "needle holder", planned: 3, seen: 2 }], null, 0.45, "photos")[0], "Saw 2 of 3 needle holders.");
});
