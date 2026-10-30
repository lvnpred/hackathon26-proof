import test from "node:test";
import assert from "node:assert/strict";
import { askAboutText, cropStyle, markLine, regionOfRow, stripLabel, stripMatch, stripTone } from "./brownbag.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const rows = [
  { read: "Metoprolol 25 mg", prescribed: true, flag: null, rx_strength: "25 mg" },
  { read: "Amlodipine 10 mg", prescribed: true, flag: "strength_differs", rx_strength: "5 mg" },
  { read: "Cetirizine 10 mg", prescribed: false, flag: "not_prescribed", rx_strength: "" },
];

test("strip labels and tones", () => {
  assert.deepEqual([0, 1, 2, null].map((row) => stripLabel({ row }, rows)), ["Metoprolol 25 mg ✓", "Amlodipine 10 mg · prescribed 5 mg", "Cetirizine 10 mg · not prescribed", "not read"]);
  assert.deepEqual(rows.map((r) => stripTone(stripMatch(r))), ["green", "amber", "red"]);
  assert.equal(stripTone(stripMatch(undefined)), "grey");
  assert.equal(stripLabel({ row: 7 }, rows), "not read");
});

test("cropStyle shows the box", () => {
  assert.deepEqual(cropStyle([0.1, 0.2, 0.5, 0.25], "/p"), { backgroundImage: 'url("/p")', backgroundSize: "200% 400%", backgroundPosition: "20% 26.67%" });
  assert.equal(cropStyle([0, 0, 1, 1], "/p").backgroundPosition, "0% 0%");
  assert.equal(cropStyle(null, "/p"), null);
});

test("regionOfRow finds the box of a read row", () => {
  const regions = [{ row: null, bbox: [0, 0, 1, 1] }, { row: 1, bbox: [0, 0.5, 1, 0.2] }];
  assert.equal(regionOfRow(regions, 1), regions[1]);
  assert.equal(regionOfRow(regions, 0), null);
});

test("brown-bag copy has no advice words", () => {
  for (const s of [askAboutText("Cetirizine 10 mg"), "Not on your prescription: Cetirizine 10 mg", "Morning", "Afternoon", "Night", "As needed", "As written", "Noted", "Discuss with patient", "Medicines from home", markLine({ mark: "discuss", by: "Dr. A. Rao (synthetic)" }), markLine({ mark: "noted", by: "Dr. A. Rao (synthetic)" })]) assert.doesNotMatch(s, ADVICE);
  assert.equal(markLine({ mark: "noted", by: "Dr. A. Rao (synthetic)" }), "Noted by Dr. A. Rao");
});
