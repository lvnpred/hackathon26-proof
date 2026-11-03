import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createStepRunner, modeFrom, modelOf, stepSlot, stepText, timeoutFor } from "./modelStep.js";

const staff = { lens: "staff" };
const patient = { lens: "patient" };

test("stepText: every stage in the staff lens uses the exact step copy", () => {
  assert.equal(stepText({ stage: "idle" }, staff), "");
  assert.equal(stepText({ stage: "recording", seconds: 7 }, staff), "Recording 0:07 — tap the mic to finish");
  assert.equal(stepText({ stage: "recording", seconds: 75 }, staff), "Recording 1:15 — tap the mic to finish");
  assert.equal(stepText({ stage: "uploading", what: "photo", percent: 42 }, staff), "Uploading photo… 42%");
  assert.equal(stepText({ stage: "uploading", what: "recording" }, staff), "Uploading recording…");
  assert.equal(stepText({ stage: "checking", model: "SAM 3.1", seconds: 3 }, staff), "Checking with SAM 3.1… 3 s");
  assert.equal(stepText({ stage: "checking", model: "Muse Voice", seconds: 2 }, staff), "Checking with Muse Voice… 2 s");
  assert.equal(stepText({ stage: "done", mode: "live", model: "SAM 3.1", seconds: 2.1 }, staff), "Done · live (SAM 3.1, 2.1 s)");
  assert.equal(stepText({ stage: "done", mode: "prepared" }), "Done · Prepared (no live model)");
  assert.equal(stepText({ stage: "failed", reason: "model unavailable" }, staff), "Didn't work: model unavailable");
});

test("stepText: the patient lens never names a model", () => {
  assert.equal(stepText({ stage: "checking", model: "Spark 1.3", what: "photo", seconds: 3 }, patient), "Reading your photo… 3 s");
  assert.equal(stepText({ stage: "checking", model: "Muse Voice", what: "recording", seconds: 4 }, patient), "Listening to your recording… 4 s");
  assert.equal(stepText({ stage: "recording", seconds: 7 }, patient), "Recording 0:07 — tap the mic to finish");
  assert.equal(stepText({ stage: "uploading", what: "photo", percent: 5 }, patient), "Uploading photo… 5%");
  assert.equal(stepText({ stage: "done", mode: "prepared", model: "SAM 3.1" }, patient), "Done · Prepared (no live model)");
  assert.equal(stepText({ stage: "failed", reason: "no answer in 60 s" }, patient), "Didn't work: no answer in 60 s");
  for (const stage of ["recording", "uploading", "checking", "done", "failed"]) {
    for (const model of ["SAM 3.1", "Spark 1.3", "Spark Open", "Muse Voice"]) {
      const line = stepText({ stage, model, mode: "live", what: "photo", seconds: 2, percent: 10, reason: "x" }, patient);
      assert.ok(!line.includes(model), `${stage}/${model}: ${line}`);
    }
  }
});

test("modelOf maps each capability to its display name", () => {
  for (const c of ["tray", "setup", "swabs", "camera"]) assert.equal(modelOf(c), "SAM 3.1", c);
  for (const c of ["voice", "hear", "dictation", "audio"]) assert.equal(modelOf(c), "Muse Voice", c);
  for (const c of ["photo", "verdict", "strips", "medicines", "monitor", "review", "wording", "card", "handover", "discharge", "orders"]) {
    assert.equal(modelOf(c), "Spark 1.3", c);
  }
  assert.equal(modelOf("reconciler"), "Spark Open");
  assert.equal(modelOf("nothing"), null);
});

test("modeFrom reads prepared and unavailable results", () => {
  assert.equal(modeFrom({ source: "sam-3.1" }), "live");
  assert.equal(modeFrom({ source: "prepared" }), "prepared");
  assert.equal(modeFrom({ heard_by: "prepared" }), "prepared");
  assert.equal(modeFrom({ calls: [{ source: "prepared" }] }), "prepared");
  assert.equal(modeFrom({ source: "unavailable" }), "failed");
  assert.equal(modeFrom({ calls: [{ source: "unavailable" }] }), "failed");
  assert.equal(modeFrom(null), "failed");
  assert.equal(modeFrom({ id: 3, view: {} }), "live");
});

test("timeoutFor: 60 s for a photo, 120 s for video and audio", () => {
  assert.equal(timeoutFor("photo"), 60000);
  assert.equal(timeoutFor("recording"), 120000);
  assert.equal(timeoutFor("video"), 120000);
  assert.equal(timeoutFor(undefined), 60000);
});

// A fake clock: timers fire only when the test moves time on.
function fakeClock() {
  let now = 0;
  let next = 1;
  const timers = new Map();
  const clock = {
    now: () => now,
    setTimeout: (fn, ms) => { const id = next++; timers.set(id, { fn, at: now + ms }); return id; },
    clearTimeout: (id) => timers.delete(id),
    setInterval: (fn, ms) => { const id = next++; timers.set(id, { fn, at: now + ms, every: ms }); return id; },
    clearInterval: (id) => timers.delete(id),
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        const [id, t] = due;
        now = t.at;
        if (t.every) t.at += t.every; else timers.delete(id);
        t.fn();
      }
      now = end;
    },
  };
  return clock;
}

const flush = () => new Promise((r) => setImmediate(r));

function runner(extra = {}) {
  const clock = fakeClock();
  const seen = [];
  const r = createStepRunner({ capability: "tray", clock, onChange: (s) => seen.push(s), ...extra });
  return { r, clock, seen };
}

test("run passes onProgress, signal and timeoutMs; uploading turns into checking that ticks each second", async () => {
  const { r, clock } = runner();
  let opts;
  let finish;
  const done = r.run((o) => { opts = o; return new Promise((res) => { finish = res; }); }, { what: "photo" });
  assert.equal(typeof opts.onProgress, "function");
  assert.ok(opts.signal && opts.signal.aborted === false);
  assert.equal(opts.timeoutMs, 60000);
  assert.deepEqual([r.step.stage, r.step.percent], ["uploading", 0]);
  opts.onProgress(42);
  assert.equal(stepText(r.step, staff), "Uploading photo… 42%");
  opts.onProgress(100);
  assert.equal(r.step.stage, "checking");
  clock.advance(3000);
  assert.equal(stepText(r.step, staff), "Checking with SAM 3.1… 3 s");
  clock.advance(100);
  finish({ source: "sam-3.1" });
  assert.deepEqual(await done, { source: "sam-3.1" });
  assert.equal(stepText(r.step, staff), "Done · live (SAM 3.1, 3.1 s)");
});

test("run without `what` starts checking; a prepared result says so", async () => {
  const { r } = runner({ capability: "orders" });
  const done = r.run(() => Promise.resolve({ source: "prepared" }));
  assert.equal(r.step.stage, "checking");
  await done;
  assert.equal(stepText(r.step, staff), "Done · Prepared (no live model)");
});

test("a failed call shows the server's reason and retry repeats the same call", async () => {
  const { r } = runner();
  let calls = 0;
  const fn = () => (++calls === 1 ? Promise.reject(new Error("photo is too dark")) : Promise.resolve({ source: "sam-3.1" }));
  assert.equal(await r.run(fn, { what: "photo" }), null);
  assert.equal(stepText(r.step, staff), "Didn't work: photo is too dark");
  assert.deepEqual(await r.retry(), { source: "sam-3.1" });
  assert.equal(calls, 2);
  assert.equal(r.step.stage, "done");
});

test("an unavailable model is a failed step, and the result still comes back", async () => {
  const { r } = runner();
  const view = { source: "unavailable" };
  assert.equal(await r.run(() => Promise.resolve(view)), view);
  assert.equal(stepText(r.step, staff), "Didn't work: model unavailable");
});

test("modelStep times out: a call that never answers fails with no answer in 60 s", async () => {
  const { r, clock } = runner();
  let signal;
  const done = r.run((o) => { signal = o.signal; return new Promise(() => {}); }, { what: "photo" });
  clock.advance(60000);
  assert.equal(await done, null);
  assert.equal(r.step.stage, "failed");
  assert.equal(r.step.reason, "no answer in 60 s");
  assert.equal(signal.aborted, true);
});

test("abort on unmount: dispose aborts the call and no later change is reported", async () => {
  const { r, clock, seen } = runner();
  let signal;
  let finish;
  const done = r.run((o) => { signal = o.signal; return new Promise((res) => { finish = res; }); });
  r.dispose();
  assert.equal(signal.aborted, true);
  const count = seen.length;
  clock.advance(5000);
  finish({ source: "sam-3.1" });
  assert.equal(await done, null);
  await flush();
  assert.equal(seen.length, count);
});

test("recording ticks m:ss; stop and reset go back to idle", () => {
  const { r, clock } = runner({ capability: "voice" });
  r.startRecording();
  clock.advance(7000);
  assert.equal(stepText(r.step, staff), "Recording 0:07 — tap the mic to finish");
  r.stopRecording();
  assert.equal(r.step.stage, "idle");
  r.startRecording();
  r.reset();
  assert.equal(r.step.stage, "idle");
});

test("ModelStep renders a polite status line with its stage class and Retry when failed", () => {
  const src = fs.readFileSync(new URL("./ModelStep.jsx", import.meta.url), "utf8");
  assert.match(src, /role="status"/);
  assert.match(src, /aria-live="polite"/);
  assert.match(src, /`model-step stage-\$\{/);
  assert.match(src, />\s*Retry\s*</);
  const hook = fs.readFileSync(new URL("./useModelStep.js", import.meta.url), "utf8");
  assert.match(hook, /createStepRunner/);
  assert.match(hook, /useEffect\(\(\) => slot\.current\.mount\(\), \[capability\]\)/, "the runner is mounted in the effect; its cleanup aborts");
  assert.match(hook, /stepSlot\(/);
});

test("care.css has the step styles, both keyframes and a reduced-motion off switch", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  for (const s of [".model-step", ".model-step .bar", "@keyframes cg-pulse", "@keyframes cg-indeterminate"]) assert.ok(css.includes(s), s);
  assert.match(css, /prefers-reduced-motion: reduce\)[^}]*\.model-step/);
});

test("ward's act, upload and ask pass opts to the journey client; ownFault hands the error to the step", () => {
  const src = fs.readFileSync(new URL("./ward.js", import.meta.url), "utf8");
  assert.match(src, /const act = \(id, path, body, scope = path, opts\)/);
  assert.match(src, /const upload = \(id, path, file, fields, scope = path, opts\)/);
  assert.match(src, /async function ask\(id, path, file, fields, scope = path, opts\)/);
  assert.match(src, /postJourney\(id, path, \{ \.\.\.body, at_ms: nowMs \}, clientOpts\(opts\)\)/);
  assert.match(src, /uploadJourney\(id, path, file, \{ \.\.\.fields, at_ms: nowMs \}, clientOpts\(opts\)\)/);
  assert.equal((src.match(/if \(opts\?\.ownFault\) throw exc;/g) || []).length, 2);
});

test("StrictMode: mount -> cleanup -> mount leaves a live runner that finishes its call", async () => {
  const clock = fakeClock();
  const seen = [];
  const slot = stepSlot(() => createStepRunner({ capability: "tray", clock, onChange: (s) => seen.push(s) }));
  const cleanup = slot.mount();
  cleanup();
  slot.mount();
  const r = slot.get();
  assert.equal(r.disposed, false);
  assert.deepEqual(await r.run(() => Promise.resolve({ source: "sam-3.1" })), { source: "sam-3.1" });
  assert.equal(r.step.stage, "done");
  assert.equal(seen.at(-1).stage, "done");
});

test("an AbortError that is not the timeout returns null quietly and goes back to idle", async () => {
  const { r } = runner();
  const abort = Object.assign(new Error("stopped"), { name: "AbortError" });
  assert.equal(await r.run(() => Promise.reject(abort)), null);
  assert.equal(r.step.stage, "idle");
});

test("startRecording drops a call in flight", async () => {
  const { r } = runner({ capability: "voice" });
  let signal;
  let finish;
  const done = r.run((o) => { signal = o.signal; return new Promise((res) => { finish = res; }); }, { what: "recording" });
  r.startRecording();
  assert.equal(signal.aborted, true);
  finish({ source: "muse-voice-transcribe" });
  assert.equal(await done, null);
  assert.equal(r.step.stage, "recording");
});

test("upload: false names its what but goes straight to checking", async () => {
  const { r } = runner({ capability: "photo" });
  let opts;
  const done = r.run((o) => { opts = o; return Promise.resolve({}); }, { what: "photo", upload: false });
  assert.equal(r.step.stage, "checking");
  assert.equal(stepText(r.step, patient), "Reading your photo… 0 s");
  assert.equal(opts.timeoutMs, 60000);
  await done;
});

test("ward drops an AbortError without a fault", () => {
  const src = fs.readFileSync(new URL("./ward.js", import.meta.url), "utf8");
  assert.equal((src.match(/if \(exc\?\.name === "AbortError"\) return null;/g) || []).length, 2);
});
