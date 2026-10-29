// Headless run of the beat table with one screenshot per beat. Offline only; never touches 8100 or 5173.
// Options: --keep-data, --headed. CG_DEMO_UNTIL=<beat id> stops cleanly before that beat (exit 3, not a pass).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { BEATS, filmSeconds, missingMedia, roleSeconds } from "./beats.mjs";
import { findChrome } from "./chrome.mjs";
import { startServers } from "./server.mjs";
import { STEPS, helpers, waitGone, waitText } from "./steps.mjs";

const ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const SHOTS = path.join(ROOT, "demo-shots");
const ORIGIN = "http://127.0.0.1:";
const keepData = process.argv.includes("--keep-data");
const headed = process.argv.includes("--headed");
const until = process.env.CG_DEMO_UNTIL || "";
const two = (n) => String(n).padStart(2, "0");

const media = missingMedia(ROOT, fs.existsSync);
if (media) { console.error(media); process.exit(1); }
let chrome;
try { chrome = findChrome(); } catch (err) { console.error(err.message); process.exit(1); }
if (until && !BEATS.some((b) => b.id === until)) { console.error(`CG_DEMO_UNTIL names no beat: ${until}`); process.exit(1); }

fs.rmSync(SHOTS, { recursive: true, force: true });
fs.mkdirSync(SHOTS, { recursive: true });
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "cg-demo-"));

let servers = null;
let browser = null;
let code = 1;
const cleanup = async () => {
  await browser?.close().catch(() => {});
  await servers?.stop();
};
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => { cleanup().finally(() => process.exit(130)); });
}

try {
  servers = await startServers({ dataDir, logPath: path.join(SHOTS, "server.log") });
  browser = await chromium.launch({ executablePath: chrome, headless: !headed });
  const context = await browser.newContext({ viewport: { width: 1200, height: 1600 } });
  const page = await context.newPage();

  // Only our own origin counts (P5-R11): fonts and other third-party failures are not the app's.
  let problems = [];
  const ours = (url) => url.startsWith(ORIGIN);
  page.on("pageerror", (err) => problems.push(`page error: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error" && ours(msg.location().url || "")) problems.push(`console error: ${msg.text()}`);
  });
  page.on("response", (res) => {
    if (res.status() >= 400 && ours(res.url())) problems.push(`HTTP ${res.status()} ${res.request().method()} ${res.url()}`);
  });

  const H = helpers(page, ROOT);
  let stoppedEarly = false;
  for (const [i, beat] of BEATS.entries()) {
    if (beat.id === until) { stoppedEarly = true; break; }
    const nn = two(i + 1);
    problems = [];
    try {
      await STEPS[beat.id](H);
      for (const s of beat.expect) await waitText(page, s);
      if (beat.absent) await waitGone(page, beat.absent);
      await page.waitForTimeout(150);
      if (problems.length) throw new Error(problems.join("; "));
      await page.screenshot({ path: path.join(SHOTS, `${nn}-${beat.id}.png`), fullPage: true });
      console.log(`ok   ${nn} ${beat.id}`);
    } catch (err) {
      await page.screenshot({ path: path.join(SHOTS, `${nn}-${beat.id}-FAIL.png`), fullPage: true }).catch(() => {});
      const reason = String(err.message).split("\n")[0];
      console.error(`DEMO CHECK FAILED at beat ${nn} ${beat.id} (${beat.role}): ${reason}`);
      console.error((await H.text().catch(() => "")).slice(0, 600));
      throw Object.assign(new Error("beat failed"), { reported: true });
    }
  }
  if (stoppedEarly) {
    console.log(`DEMO CHECK STOPPED before ${until} (not a pass)`);
    code = 3;
  } else {
    const s = roleSeconds(BEATS);
    console.log(`DEMO CHECK PASSED: ${BEATS.length} beats; filmed doctor ${s.doctor} s, nurse ${s.nurse} s, patient ${s.patient} s, total ${filmSeconds(BEATS)} s`);
    code = 0;
  }
} catch (err) {
  if (!err.reported) console.error(`DEMO CHECK FAILED before the beats: ${err.message}`);
  code = 1;
} finally {
  await cleanup();
  if (!keepData) fs.rmSync(dataDir, { recursive: true, force: true });
}
process.exit(code);
