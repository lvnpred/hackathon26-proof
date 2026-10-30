import test from "node:test";
import assert from "node:assert/strict";
import { PIPELINES, callsText, latencyText, modeLabel, recentText } from "./ai.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("card words", () => {
  assert.deepEqual([0, 1, 6].map(callsText), ["No calls yet", "1 call", "6 calls"]);
  assert.deepEqual([null, 2400].map(latencyText), ["No timing yet", "2.4 s median"]);
  assert.equal(modeLabel("failed"), "Failed");
  assert.equal(modeLabel("Sample"), "Sample");
  assert.equal(recentText({ when: "Day 0 09:24", name: "SAM 3.1", patient: "R. Kumar (synthetic)", what: "Tray check by video: x" }), "09:24 SAM 3.1 · R. Kumar · Tray check by video: x");
});

test("the three pipelines", () => {
  assert.deepEqual(PIPELINES[1], ["Photo", "SAM regions", "Spark reads", "Check against orders"]);
  assert.equal(PIPELINES.length, 3);
});

test("dashboard copy has no advice words", () => {
  for (const s of [...PIPELINES.flat(), "AI at work", "Try sample", "Recent AI events", "Which Muse models run this ward, and what they just did.", "No model results yet. Run a flow and they appear here.", "Live ●", "Prepared ○"]) assert.doesNotMatch(s, ADVICE);
});
