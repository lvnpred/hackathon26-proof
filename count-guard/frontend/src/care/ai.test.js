import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { EMPTY_MODELS, PIPELINES, STAFF_ONLY, canSeeAi, cardLine, callsText, modelsPill, isSummary, isTry, latencyText, modeLabel, recentText } from "./ai.js";
import { chipText } from "./evidence.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("card words", () => {
  assert.deepEqual([0, 1, 6].map(callsText), ["No calls yet in this run", "1 call", "6 calls"]);
  assert.deepEqual([null, 2400].map(latencyText), ["Prepared · timing shown when live", "2.4 s median"]);
  assert.equal(modeLabel("failed"), "Failed");
  assert.equal(modeLabel("Sample"), "Sample");
  assert.equal(recentText({ when: "Day 0 09:24", name: "SAM 3.1", patient: "R. Kumar (synthetic)", what: "Tray check by video: x" }), "09:24 SAM 3.1 · R. Kumar · Tray check by video: x");
});

test("the three pipelines", () => {
  assert.deepEqual(PIPELINES[1], ["Photo", "SAM regions", "Spark reads", "Check against orders"]);
  assert.equal(PIPELINES.length, 3);
});

test("dashboard copy has no advice words", () => {
  for (const s of [...PIPELINES.flat(), "AI at work", "Try sample", "Recent AI events", "Which Muse models run this ward, and what they just did.", "No model results yet. Run a flow and they appear here.", "Models: live", "Models: prepared (no key)", STAFF_ONLY]) assert.doesNotMatch(s, ADVICE);
});

test("shape guards refuse a page that is not the answer", () => {
  assert.equal(isSummary({ detail: "<html>" }), false);
  assert.equal(isSummary(null), false);
  assert.equal(isSummary({ models: [], recent: [] }), true);
  assert.equal(isTry({ detail: "x" }), false);
  assert.equal(isTry({ mode: "Sample", text: "a" }), true);
  assert.equal(isTry({ mode: "prepared", evidence: {} }), true);
  assert.equal(EMPTY_MODELS.length, 4);
  assert.ok(EMPTY_MODELS.every((m) => m.calls === 0 && m.last === null));
});

test("an evidence chip names the model of its card", () => {
  const calls = [{ model: "sam", source: "prepared" }, { model: "spark", source: "prepared" }];
  assert.equal(chipText(calls, true), "SAM 3.1 · Sample");
  assert.equal(chipText(calls, true, "spark"), "Muse Spark 1.3 · Sample");
  assert.equal(chipText(calls, false, "voice"), "SAM 3.1 · prepared");
});

test("the dev proxy forwards every /journey path the frontend calls", () => {
  const config = fs.readFileSync(new URL("../../vite.config.js", import.meta.url), "utf8");
  const dir = new URL("../", import.meta.url);
  const used = new Set();
  for (const name of fs.readdirSync(dir)) {
    if (!/\.(jsx?|mjs)$/.test(name) || name.endsWith(".test.js")) continue;
    for (const m of fs.readFileSync(new URL(name, dir), "utf8").matchAll(/["'`](\/journey\/[a-z-]+)/g)) used.add(m[1]);
  }
  for (const m of fs.readFileSync(new URL("../journey.js", import.meta.url), "utf8").matchAll(/["'`](\/journey\/[a-z-]+)/g)) used.add(m[1]);
  for (const path of used) assert.ok(config.includes(`"${path}"`), `${path} is not proxied in vite.config.js`);
});

test("the recent line drops the synthetic tag from the event text", () => {
  assert.equal(recentText({ when: "Day 0 09:10", name: "Muse Voice", patient: "R. Kumar", what: "Dr. A. Rao (synthetic) dictated 2 orders." }), "09:10 Muse Voice · R. Kumar · Dr. A. Rao dictated 2 orders.");
});

test("a card says nothing about timing until it has calls", () => {
  assert.equal(cardLine({ calls: 0, median_ms: null }), "No calls yet in this run");
  assert.equal(cardLine({ calls: 2, median_ms: null }), "2 calls · Prepared · timing shown when live");
  assert.equal(cardLine({ calls: 1, median_ms: 1200 }), "1 call · 1.2 s median");
});

test("the models pill reads live or prepared (no key)", () => {
  assert.equal(modelsPill(true), "Models: live");
  assert.equal(modelsPill(false), "Models: prepared (no key)");
});

test("AI at work is a staff view: the patient sees a note, no data and no dock link", () => {
  assert.equal(canSeeAi("doctor"), true);
  assert.equal(canSeeAi("nurse"), true);
  assert.equal(canSeeAi("patient"), false);
  assert.equal(STAFF_ONLY, "AI at work is a staff view. Switch to Doctor or Nurse.");
  const page = fs.readFileSync(new URL("./AiDashboard.jsx", import.meta.url), "utf8");
  assert.match(page, /canSeeAi\(ward\.role\)/);
  assert.match(page, /STAFF_ONLY/);
  const dock = fs.readFileSync(new URL("./DemoDock.jsx", import.meta.url), "utf8");
  assert.match(dock, /canSeeAi\(ward\.role\) && <Link to="\/ai">/);
});

test("the pipelines are chips with arrows and fit 390 px", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.pipelines li \{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/);
  assert.match(css, /\.step-chip/);
  const page = fs.readFileSync(new URL("./AiDashboard.jsx", import.meta.url), "utf8");
  assert.match(page, /step-chip/);
});
