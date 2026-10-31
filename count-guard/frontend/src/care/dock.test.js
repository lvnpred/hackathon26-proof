import test from "node:test";
import assert from "node:assert/strict";
import { alertCount, alertsLabel, dockSummary, modelsText } from "./dock.js";
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

test("alertCount sums own and grouped pills, and is 0 for the patient", () => {
  const pills = { mine: [{}, {}], others: [{ pills: [{}] }, { pills: [{}, {}] }] };
  assert.equal(alertCount(pills, "nurse"), 5);
  assert.equal(alertCount(pills, "patient"), 0);
  assert.equal(alertCount({ mine: [], others: [] }, "doctor"), 0);
});

test("the patient's product bar shows no doctor chip (the greeting row keeps it)", async () => {
  const fs = await import("node:fs");
  const shell = fs.readFileSync(new URL("./CareShell.jsx", import.meta.url), "utf8");
  assert.match(shell, /ward\.role !== "patient" && <DoctorChip/);
  const today = fs.readFileSync(new URL("./Today.jsx", import.meta.url), "utf8");
  assert.match(today, /<DoctorChip/);
});

test("the AI chip and pause switch are staff only and posted by the dock role", async () => {
  const fs = await import("node:fs");
  const dock = fs.readFileSync(new URL("./DemoDock.jsx", import.meta.url), "utf8");
  assert.match(dock, /canSeeAi\(ward\.role\)/);
  assert.match(dock, /staff && paused != null/);
  assert.match(dock, /Demo dock \(\$\{ROLE_NAME\[role\]\}\)/);
  assert.match(dock, /\/journey\/ops\/\$\{paused \? "resume" : "pause"\}/);
  const { canSeeAi } = await import("./ai.js");
  assert.equal(canSeeAi("patient"), false);
});

test("the AI feed reads the ops feed, checks it and reloads after Undo", async () => {
  const fs = await import("node:fs");
  const feed = fs.readFileSync(new URL("./AiFeed.jsx", import.meta.url), "utf8");
  assert.match(feed, /\/journey\/ops\/feed\?ids=\$\{ids\}/);
  assert.match(feed, /isFeed\(out\)/);
  assert.match(feed, /aria-label="AI did this"/);
  assert.match(feed, /Nothing handled yet\./);
  assert.match(feed, /ward\.act\(r\.episodeId[\s\S]*await load\(\)/);
  assert.match(feed, /\{r\.undo &&/);
  const dash = fs.readFileSync(new URL("./AiDashboard.jsx", import.meta.url), "utf8");
  assert.ok(dash.indexOf("<ModelCards") < dash.indexOf("<AiFeed"));
});
