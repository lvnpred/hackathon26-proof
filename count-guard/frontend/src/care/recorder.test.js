import test from "node:test";
import assert from "node:assert/strict";
import { audioName, micStatus, pickMime } from "./recorder.js";
import { MATCH_LABEL, SOURCE_LABEL } from "./drafts.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const UNAVAILABLE = "Recording is not available in this browser. Choose an audio file or type what was said.";
const DENIED = "The microphone could not be used. Choose an audio file or type what was said.";

test("pickMime takes the first supported type, else empty", () => {
  assert.equal(pickMime(() => true), "audio/webm;codecs=opus");
  assert.equal(pickMime((t) => t === "audio/mp4"), "audio/mp4");
  assert.equal(pickMime(() => false), "");
});

test("audioName follows the mime", () => {
  assert.equal(audioName("audio/webm;codecs=opus"), "recording.webm");
  assert.equal(audioName("audio/mp4"), "recording.m4a");
  assert.equal(audioName("audio/ogg"), "recording.ogg");
});

test("micStatus reports unsupported and denied, plainly", () => {
  assert.deepEqual(micStatus({ hasMediaDevices: true, hasRecorder: true, mime: "audio/webm" }), { ok: true, message: "" });
  for (const bad of [{ hasMediaDevices: false }, { hasRecorder: false }, { mime: "" }]) {
    const status = micStatus({ hasMediaDevices: true, hasRecorder: true, mime: "audio/webm", ...bad });
    assert.deepEqual(status, { ok: false, message: UNAVAILABLE });
  }
  assert.deepEqual(micStatus({ hasMediaDevices: true, hasRecorder: true, mime: "audio/webm", denied: true }), { ok: false, message: DENIED });
});

test("no label or message reads as advice", () => {
  const texts = [UNAVAILABLE, DENIED, ...Object.values(MATCH_LABEL), ...Object.values(SOURCE_LABEL)];
  texts.forEach((t) => assert.equal(ADVICE.test(t), false, t));
});
