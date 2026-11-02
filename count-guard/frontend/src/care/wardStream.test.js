import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { followWard } from "./wardStream.js";
import { WARD_STREAM } from "./roster.js";

class FakeSource {
  static last = null;
  constructor(url) { this.url = url; this.listeners = {}; this.closed = false; FakeSource.last = this; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  close() { this.closed = true; }
}

const tick = (ms) => new Promise((r) => setTimeout(r, ms));

test("the ward follows the stream and refreshes once per burst of changes", async () => {
  let calls = 0;
  const stop = followWard(() => { calls += 1; }, { Source: FakeSource, delayMs: 10 });
  const source = FakeSource.last;
  assert.equal(source.url, WARD_STREAM);
  source.onmessage({ data: "{}" });
  source.onmessage({ data: "{}" });
  source.listeners.clock({ data: "{}" });
  await tick(30);
  assert.equal(calls, 1);
  source.onopen(); // a reconnect may have missed a change: read again
  await tick(30);
  assert.equal(calls, 2);
  stop();
  assert.equal(source.closed, true);
  source.onmessage({ data: "{}" });
  await tick(30);
  assert.equal(calls, 2); // nothing after stop
});

test("without EventSource the ward keeps to the 3 s refresh alone", () => {
  const stop = followWard(() => {}, { Source: undefined });
  assert.equal(typeof stop, "function");
  stop();
});

test("the dev proxy sends both streams to the API, not to the page", () => {
  const config = fs.readFileSync(new URL("../../vite.config.js", import.meta.url), "utf8");
  const list = JSON.parse(config.match(/const journeyApi = (\[[^\]]*\])/)[1]);
  for (const path of [WARD_STREAM, "/journey/episodes/e1/stream"]) {
    assert.ok(list.some((prefix) => path.startsWith(prefix)), path);
  }
});
