// Headless run of the beat table with one screenshot per beat, across two tabs: Doctor Dictation (8300) and
// Count Guard (5273). Offline only; never touches 8000, 8100 or 5173.
// Options: --keep-data, --headed. CG_DEMO_UNTIL=<beat id> stops cleanly before that beat (exit 3, not a pass).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { BEATS, filmSeconds, missingMedia, sceneSeconds } from "./beats.mjs";
import { findChrome } from "./chrome.mjs";
import { ALLOWED_SELECTOR, STEP_LINE, scanBeat } from "./scan.mjs";
import { API_PORT, startServers } from "./server.mjs";
import { STEPS, helpers, waitGone, waitText } from "./steps.mjs";

const ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const SHOTS = path.join(ROOT, "demo-shots");
const ORIGIN = "http://127.0.0.1:";
// Single-clinic DD answers 404 to its sign-in reads; that is how its page learns there is no sign-in.
const DD_EXPECTED_404 = /^http:\/\/127\.0\.0\.1:8300\/api\/v1\/(auth\/me|users)$/;
const keepData = process.argv.includes("--keep-data");
const headed = process.argv.includes("--headed");
const until = process.env.CG_DEMO_UNTIL || "";
const two = (n) => String(n).padStart(2, "0");

const media = missingMedia(ROOT, fs.existsSync);
if (media) { console.error(media); process.exit(1); }
let chrome;
try { chrome = findChrome(); } catch (err) { console.error(err.message); process.exit(1); }
if (until && !BEATS.some((b) => b.id === until)) { console.error(`CG_DEMO_UNTIL names no beat: ${until}`); process.exit(1); }

let dataDir = "";
let servers = null;
let browser = null;
let code = 1;
const cleanup = async () => {
  await browser?.close().catch(() => {});
  await servers?.stop();
};
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => { cleanup().finally(() => process.exit(130)); });
}

try {
  // The data dir is made first (the servers need it at spawn); startServers then checks the ports.
  // A refused run keeps the previous screenshots, and the finally removes the dir.
  fs.mkdirSync(SHOTS, { recursive: true });
  dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "cg-demo-"));
  servers = await startServers({ dataDir, logPath: path.join(SHOTS, "server.log"), onSpawn: (stop) => {
    servers = { stop };
    // Ports were free: only now drop the previous run's screenshots (the open server.log stays).
    for (const f of fs.readdirSync(SHOTS)) if (f.endsWith(".png")) fs.rmSync(path.join(SHOTS, f));
  } });
  // The fake microphone lets Doctor Dictation record; its stub speech result ignores the sound.
  browser = await chromium.launch({
    executablePath: chrome, headless: !headed,
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  });
  const context = await browser.newContext({ viewport: { width: 1200, height: 1600 } });
  await context.grantPermissions(["microphone"]);
  const dd = await context.newPage();
  const page = await context.newPage();

  // Only our own origins count (P5-R11): fonts and other third-party failures are not the apps'.
  let problems = [];
  const ours = (url) => url.startsWith(ORIGIN) && !DD_EXPECTED_404.test(url);
  for (const p of [page, dd]) {
    p.on("pageerror", (err) => problems.push(`page error: ${err.message}`));
    p.on("console", (msg) => {
      if (msg.type() === "error" && ours(msg.location().url || "")) problems.push(`console error: ${msg.text()}`);
    });
    p.on("response", (res) => {
      if (res.status() >= 400 && ours(res.url())) problems.push(`HTTP ${res.status()} ${res.request().method()} ${res.url()}`);
    });
  }

  const H = { ...helpers(page, ROOT), dd, cgApi: `${ORIGIN}${API_PORT}`, marks: {} };
  let stoppedEarly = false;
  for (const [i, beat] of BEATS.entries()) {
    if (beat.id === until) { stoppedEarly = true; break; }
    const nn = two(i + 1);
    const on = beat.app === "dd" ? dd : page;
    const root = beat.app === "dd" ? "body" : ".app";
    problems = [];
    try {
      await STEPS[beat.id](H);
      for (const s of beat.expect) await waitText(on, s, 10000, root);
      if (beat.absent) await waitGone(on, beat.absent, 3000, root);
      await on.waitForTimeout(150);
      if (problems.length) throw new Error(problems.join("; "));
      // The Demo dock is demo tooling, so the scan reads the app text without it. The Inspector Model tab may
      // name models, so its panel text is passed apart while that tab is open.
      const seen = await on.evaluate(([sel, allowedSel, stepLine]) => {
        const app = document.querySelector(sel);
        const dock = app?.querySelector("[aria-label=Demo]")?.innerText || "";
        const inspector = app?.querySelector("[aria-label=Inspector]");
        const tab = inspector?.querySelector("[role=tab][aria-selected=true]")?.innerText?.trim();
        const modelPanel = tab === "Model" ? inspector.querySelector("[role=tabpanel]")?.innerText || "" : "";
        const text = (app?.innerText || "").replace(dock, "");
        // Spec §4.1: a model step line and an open Expand view may name the model on a staff screen. They are hidden
        // for one synchronous read, so the model rules read the page by DOM position without them.
        const line = new RegExp(stepLine);
        const allowed = [...(app?.querySelectorAll(allowedSel) || [])].filter(
          (el) => el.matches('[data-expand="open"]') || line.test((el.innerText || "").replace(/\s+/g, " ").trim()),
        );
        const kept = allowed.map((el) => [el.style.getPropertyValue("display"), el.style.getPropertyPriority("display")]);
        allowed.forEach((el) => el.style.setProperty("display", "none", "important"));
        const modelText = (app?.innerText || "").replace(dock, "");
        allowed.forEach((el, i) => (kept[i][0] ? el.style.setProperty("display", ...kept[i]) : el.style.removeProperty("display")));
        return { text, modelPanel, modelText };
      }, [root, ALLOWED_SELECTOR, STEP_LINE.source]);
      const bad = scanBeat({ ...seen, role: beat.role, beat: beat.id });
      if (bad.length) throw new Error(`scan: ${bad.join("; ")}`);
      await on.screenshot({ path: path.join(SHOTS, `${nn}-${beat.id}.png`), fullPage: true });
      console.log(`ok   ${nn} ${beat.id}`);
    } catch (err) {
      await on.screenshot({ path: path.join(SHOTS, `${nn}-${beat.id}-FAIL.png`), fullPage: true }).catch(() => {});
      const reason = String(err.message).split("\n")[0];
      console.error(`DEMO CHECK FAILED at beat ${nn} ${beat.id} (${beat.app}, ${beat.role}): ${reason}`);
      console.error((await on.locator(root).innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 600));
      throw Object.assign(new Error("beat failed"), { reported: true });
    }
  }
  if (stoppedEarly) {
    console.log(`DEMO CHECK STOPPED before ${until} (not a pass)`);
    code = 3;
  } else {
    const s = sceneSeconds(BEATS);
    console.log(`DEMO CHECK PASSED: ${BEATS.length} beats; filmed DD ${s.dd} s, ward ${s.ward} s, theatre ${s.theatre} s, discharge ${s.discharge} s, total ${filmSeconds(BEATS)} s`);
    code = 0;
  }
} catch (err) {
  if (!err.reported) console.error(`DEMO CHECK FAILED before the beats: ${err.message}`);
  code = 1;
} finally {
  await cleanup();
  if (!keepData && dataDir) fs.rmSync(dataDir, { recursive: true, force: true });
}
process.exit(code);
