import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { EMPTY_MODELS, PIPELINES, PIPELINE_KIND, STAFF_ONLY, activityRows, emptyLine, storyCounts, storyLine, canSeeAi, cardLine, callsText, modelsPill, isSummary, isTry, latencyText, modeLabel, recentText } from "./ai.js";
import { chipText } from "./evidence.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("card words", () => {
  assert.deepEqual([0, 1, 6].map(callsText), ["No calls yet in this run", "1 call", "6 calls"]);
  assert.deepEqual([null, 2400].map(latencyText), ["Prepared · timing shown when live", "2.4 s median"]);
  assert.equal(modeLabel("failed"), "Failed");
  assert.equal(modeLabel("Sample"), "Sample");
  assert.equal(recentText({ when: "Yesterday 09:24", name: "SAM 3.1", patient: "R. Kumar (synthetic)", what: "Tray check by video: x" }), "Yesterday 09:24 SAM 3.1 · R. Kumar · Tray check by video: x");
});

test("the three pipelines", () => {
  assert.deepEqual(PIPELINES[1], ["Photo", "SAM regions", "Spark reads", "Check against orders"]);
  assert.equal(PIPELINES.length, 3);
});

test("dashboard copy has no advice words", () => {
  for (const s of [...PIPELINES.flat(), "AI activity", "Try sample", "Nothing here for this filter.", emptyLine("R. Kumar"), storyLine({ transcribed: 3, photos: 4, videos: 2, flags: 3, decided: 3 }), "Models: live", "Models: prepared (no key)", STAFF_ONLY]) assert.doesNotMatch(s, ADVICE);
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
  assert.equal(recentText({ when: "09:10", name: "Muse Voice", patient: "R. Kumar", what: "Dr. A. Rao (synthetic) dictated 2 orders." }), "09:10 Muse Voice · R. Kumar · Dr. A. Rao dictated 2 orders.");
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

test("AI activity is a staff view: the patient sees a note, no data and no dock link or tab", () => {
  assert.equal(canSeeAi("doctor"), true);
  assert.equal(canSeeAi("nurse"), true);
  assert.equal(canSeeAi("patient"), false);
  assert.equal(STAFF_ONLY, "AI activity is a staff view. Switch to Doctor or Nurse.");
  assert.doesNotMatch(STAFF_ONLY, ADVICE);
  const page = fs.readFileSync(new URL("./AiDashboard.jsx", import.meta.url), "utf8");
  assert.match(page, /canSeeAi\(ward\.role\)/);
  assert.match(page, /STAFF_ONLY/);
  const order = ['aria-label="Pipelines"', "<ActivityList", "<AiFeed", "<ModelCards"].map((s) => page.indexOf(s));
  assert.ok(order[0] > -1 && order.every((at, i) => i === 0 || at > order[i - 1]), "pipeline filter, ActivityList, AiFeed, ModelCards");
  assert.ok(page.indexOf("<h2>What the AI did today</h2>") < page.indexOf("<h2>How it works</h2>"));
  const dock = fs.readFileSync(new URL("./DemoDock.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(dock, /to="\/ai"/);
  const shell = fs.readFileSync(new URL("./CareShell.jsx", import.meta.url), "utf8");
  assert.ok(shell.includes('["/ai", "AI activity"]'));
});

const m = (id, kind, at_ms, status = "matches") => ({ id, kind, at_ms, status });
const ward = [
  { id: "e1", name: "R. Kumar, 54 (synthetic)", view: { ai_moments: [m("a", "voice", 5), m("b", "record", 9), m("c", "rule", 1, "recorded")] } },
  { id: "e2", name: "S. Iyer, 61", view: { ai_moments: [m("d", "visual", 7), m("e", "photo_read", 3), m("f", "rule", 2, "flagged")] } },
  { id: "e3", name: "No view" },
];

test("activityRows is newest first, drops record rows and names the patient", () => {
  const rows = activityRows(ward);
  assert.deepEqual(rows.map((r) => r.moment.id), ["d", "a", "e", "f", "c"]);
  assert.deepEqual(rows[0], { episodeId: "e2", patient: "S. Iyer", moment: ward[1].view.ai_moments[0] });
  assert.equal(rows[1].patient, "R. Kumar");
});

test("storyCounts counts by kind and decided flags", () => {
  assert.deepEqual(storyCounts(activityRows(ward)), { transcribed: 1, photos: 1, videos: 1, flags: 2, decided: 1 });
});

test("storyLine words the day in one sentence", () => {
  assert.equal(storyLine({ transcribed: 3, photos: 4, videos: 2, flags: 3, decided: 3 }), "Today the AI transcribed 3 notes, read 4 photos, counted 2 videos and raised 3 flags; staff decided all 3.");
  assert.equal(storyLine({ transcribed: 1, photos: 0, videos: 1, flags: 1, decided: 1 }), "Today the AI transcribed 1 note, counted 1 video and raised 1 flag; staff decided it.");
  assert.equal(storyLine({ transcribed: 0, photos: 2, videos: 0, flags: 2, decided: 1 }), "Today the AI read 2 photos and raised 2 flags; staff decided 1 of 2.");
  assert.equal(storyLine({ transcribed: 2, photos: 0, videos: 0, flags: 0, decided: 0 }), "Today the AI transcribed 2 notes.");
  assert.equal(storyLine({ transcribed: 0, photos: 0, videos: 0, flags: 0, decided: 0 }), "");
});

test("pipeline buttons filter by the first word; the empty line names the patient", () => {
  assert.deepEqual(PIPELINES.map((p) => PIPELINE_KIND[p[0]]), ["voice", "photo_read", "visual"]);
  assert.equal(emptyLine("R. Kumar"), "Nothing yet today. Open R. Kumar to follow the demo.");
});

test("the pipelines are chips with arrows and fit 390 px", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.pipelines li \{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/);
  assert.match(css, /\.step-chip/);
  const page = fs.readFileSync(new URL("./AiDashboard.jsx", import.meta.url), "utf8");
  assert.match(page, /step-chip/);
});

test("pipeline buttons have a spaced name and a 44 px target; the two fallback strings give no advice", () => {
  const page = fs.readFileSync(new URL("./AiDashboard.jsx", import.meta.url), "utf8");
  assert.match(page, /aria-label=\{steps\.join\(", "\)\}/);
  assert.equal(PIPELINES[0].join(", "), "Voice, Draft orders, Nurse tasks");
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.pipelines button\.linklike \{[^}]*min-height:\s*44px/);
  const lead = page.match(/body=\{story \|\| "([^"]+)"\}/)[1];
  assert.equal(lead, "What the AI did on this ward, by patient and pipeline.");
  for (const s of [lead, "Nothing yet today."]) assert.doesNotMatch(s, ADVICE);
  assert.match(page, /"Nothing yet today\."/);
});

test("recentText shows the call's time on the dock clock", async () => {
  const { recentText } = await import("./ai.js");
  const H = 3600000;
  const row = { at_ms: 13 * H, when: "22:00", name: "Muse Voice", patient: "R. Kumar", what: "Logged BP" };
  assert.match(recentText(row, 13 * H), /^22:00 Muse Voice/);
  assert.match(recentText(row, 37 * H), /^Yesterday 22:00 Muse Voice/);
});
