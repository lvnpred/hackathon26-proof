import test from "node:test";
import assert from "node:assert/strict";
import { alertCount, alertsLabel, modelsText } from "./dock.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("modelsText and alertsLabel", () => {
  assert.equal(modelsText(false), "models: offline (prepared)");
  assert.equal(modelsText(true), "models: live");
  assert.equal(modelsText(null), "");
  assert.deepEqual([0, 1, 2].map(alertsLabel), ["", "1 alert", "2 alerts"]);
});

test("dock copy has no advice words", () => {
  for (const s of [modelsText(false), alertsLabel(2)]) assert.doesNotMatch(s, ADVICE);
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

test("the AI switch is staff only and posts the signed-in person, from one shared hook", async () => {
  const fs = await import("node:fs");
  const read = (f) => fs.readFileSync(new URL(f, import.meta.url), "utf8");
  const hook = read("./useOpsPaused.js");
  assert.match(hook, /canSeeAi\(role\)/);
  assert.match(hook, /by: SIGNED_IN\[role\]\.name/);
  assert.doesNotMatch(hook, /Demo dock/);
  assert.match(hook, /state\.paused \? "resume" : "pause"[\s\S]*\/journey\/ops\/\$\{verb\}/);
  const shell = read("./CareShell.jsx");
  assert.equal((shell.match(/useOpsPaused\(/g) || []).length, 1);
  assert.match(shell, /<DemoDock[^>]*ops=\{ops\}/);
  assert.match(shell, /<ProductHeader[\s\S]*ops=\{ops\}/);
  const dock = read("./DemoDock.jsx");
  assert.match(dock, /ops\.paused != null/);
  const header = read("./ProductHeader.jsx");
  assert.match(header, /staff && ops\.paused != null/);
  assert.match(header, /AI admin: \{ops\.paused \? "paused" : "on"\}/);
  assert.match(header, /ops\.paused \? "Resume" : "Pause"/);
  const { canSeeAi } = await import("./ai.js");
  assert.equal(canSeeAi("patient"), false);
});

test("the safety strip is first in the shell, in the product and not in the dock", async () => {
  const fs = await import("node:fs");
  const read = (f) => fs.readFileSync(new URL(f, import.meta.url), "utf8");
  assert.match(read("./ProductStrip.jsx"), /Research demo · Synthetic data · Not for clinical use/);
  const shell = read("./CareShell.jsx");
  assert.ok(shell.indexOf("<ProductStrip") > -1 && shell.indexOf("<ProductStrip") < shell.indexOf("<ProductHeader"));
  assert.ok(shell.indexOf("<ProductHeader") < shell.indexOf("<DemoDock"));
  const dock = read("./DemoDock.jsx");
  assert.doesNotMatch(dock, /Research demo|Banner|Synthetic data/);
  assert.doesNotMatch(shell, /care-foot/);
  for (const link of ['to="/guide">Guide<', 'to="/older">Older screens<']) assert.ok(dock.includes(link));
  assert.ok(dock.includes("Use the demo prescription"));
  assert.doesNotMatch(read("../screens/ClinicPanel.jsx"), /Use the demo prescription/);
});

test("the paused banner names who paused and when, for staff only", async () => {
  const fs = await import("node:fs");
  const header = fs.readFileSync(new URL("./ProductHeader.jsx", import.meta.url), "utf8");
  assert.match(header, /AI admin is paused for Ward 4\. Paused by \$\{by \|\| "a person"\}\$\{at\}\. New orders and tasks wait for a person\./);
  assert.match(header, /className="paused-banner" role="status"/);
  assert.match(header, /whenText\(atMs, nowMs\)/);
  const shell = fs.readFileSync(new URL("./CareShell.jsx", import.meta.url), "utf8");
  assert.match(shell, /ward\.role !== "patient" && <PausedBanner/);
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

test("a failed pause shows an alert, the button waits, and the feed follows the ward", async () => {
  const fs = await import("node:fs");
  const dock = fs.readFileSync(new URL("./DemoDock.jsx", import.meta.url), "utf8");
  const hook = fs.readFileSync(new URL("./useOpsPaused.js", import.meta.url), "utf8");
  assert.match(hook, /Could not \$\{verb\} the AI\./);
  assert.match(dock, /disabled=\{ops\.busy\}/);
  assert.match(fs.readFileSync(new URL("./ProductHeader.jsx", import.meta.url), "utf8"), /ops\.error && <span className="error small" role="alert">/);
  assert.doesNotMatch(hook, /catch\(\(\) => \{\}\)/);
  assert.doesNotMatch("Could not pause the AI. Could not resume the AI.", ADVICE);
  const feed = fs.readFileSync(new URL("./AiFeed.jsx", import.meta.url), "utf8");
  assert.match(feed, /\[load, ward\.patients\]/);
  assert.match(feed, /mine === seq\.current/);
});
