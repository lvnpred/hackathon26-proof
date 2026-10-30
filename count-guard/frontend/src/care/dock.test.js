import test from "node:test";
import assert from "node:assert/strict";
import { alertsLabel, dockSummary, modelsText } from "./dock.js";
import { M } from "./clock.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("dockSummary folds the dock to one line", () => {
  assert.equal(dockSummary("nurse", 12 * M), "DEMO · Nurse · 09:12");
  assert.equal(dockSummary("doctor", 0), "DEMO · Doctor · 09:00");
});

test("modelsText and alertsLabel", () => {
  assert.equal(modelsText(false), "Synthetic data · models: offline (prepared)");
  assert.equal(modelsText(true), "Synthetic data · models: live");
  assert.equal(modelsText(null), "Synthetic data");
  assert.deepEqual([0, 1, 2].map(alertsLabel), ["", "1 alert", "2 alerts"]);
});

test("dock copy has no advice words", () => {
  for (const s of [dockSummary("patient", 0), modelsText(false), alertsLabel(2)]) assert.doesNotMatch(s, ADVICE);
});
