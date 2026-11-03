import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createStepRunner, stepText } from "./modelStep.js";
import { hearWith, heardWords } from "./dictateFlow.js";
import { fakeClock } from "./fakeClock.test.js";

const staff = { lens: "staff" };
const read = (f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8");

test("Dictate: Recording 0:03, then Checking with Muse Voice… 1 s, then the heard text", async () => {
  const clock = fakeClock();
  const r = createStepRunner({ capability: "voice", clock });
  r.startRecording();
  clock.advance(3000);
  assert.equal(stepText(r.step, staff), "Recording 0:03 — tap the mic to finish");
  r.stopRecording();
  let opts;
  let reply;
  const file = { name: "said.webm" };
  let sent;
  const heard = hearWith(r, (f, o) => { sent = f; opts = o; return new Promise((res) => { reply = res; }); }, file);
  assert.equal(sent, file);
  assert.equal(stepText(r.step, staff), "Uploading recording… 0%");
  assert.equal(opts.timeoutMs, 120000);
  opts.onProgress(100);
  clock.advance(1000);
  assert.equal(stepText(r.step, staff), "Checking with Muse Voice… 1 s");
  reply({ text: "obs done, bp one eighteen over seventy six", heard_by: "muse-voice-transcribe" });
  assert.equal((await heard).text, "obs done, bp one eighteen over seventy six");
  assert.equal(stepText(r.step, staff), "Done · live (Muse Voice, 1.0 s)");
});

test("Dictate: a failed hearing shows Didn't work and Retry sends the same recording again", async () => {
  const r = createStepRunner({ capability: "voice", clock: fakeClock() });
  const file = { name: "said.webm" };
  const seen = [];
  const onHear = (f) => { seen.push(f); return seen.length === 1 ? Promise.reject(new Error("model unavailable")) : Promise.resolve({ text: "ok", heard_by: "prepared" }); };
  assert.equal(await hearWith(r, onHear, file), null);
  assert.equal(stepText(r.step, staff), "Didn't work: model unavailable");
  assert.equal((await r.retry()).text, "ok");
  assert.deepEqual(seen, [file, file]);
});

test("heardWords: edited heard text keeps the voice mark and says edited", () => {
  assert.equal(heardWords("From voice", "one eighteen", "one eighteen"), "From voice");
  assert.equal(heardWords("From voice", "one eighteen ", " one eighteen"), "From voice");
  assert.equal(heardWords("From voice", "one eighteen", "one twenty"), "From voice · edited");
  assert.equal(heardWords("Drafted from voice", "a", "b"), "Drafted from voice · edited");
});

test("Dictate.jsx: the hearing has its own step with Retry, and the mark stays until Send", () => {
  const src = read("Dictate.jsx");
  assert.match(src, /useModelStep\(\{ capability: "voice"/);
  assert.match(src, /startRecording\(\)/);
  assert.match(src, /stopRecording\(\)/);
  assert.match(src, /hearWith\(/);
  assert.match(src, /<ModelStep busy=\{busy\} step=\{hearing\.step\}[^>]*onRetry=/);
  assert.match(src, /heardWords\(/);
});
