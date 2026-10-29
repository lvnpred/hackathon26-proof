import test from "node:test";
import assert from "node:assert/strict";
import { H, M } from "./clock.js";
import { STATUS_CHOICES, chipClass, statusBody, statusQuery } from "./status.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const choice = (id) => STATUS_CHOICES.find((c) => c.id === id);

test("busy for 30 min ends 30 min after now; auto has no end", () => {
  const body = statusBody(choice("busy30"), 2 * H, "b1", ["a", "b"]);
  assert.deepEqual(body, { board: "b1", ids: ["a", "b"], status: "busy", until_ms: 2 * H + 30 * M, at_ms: 2 * H });
  assert.equal(statusBody(choice("auto"), 2 * H, "b1", ["a"]).until_ms, null);
  assert.equal(statusBody(choice("auto"), 2 * H, "b1", ["a"]).status, "auto");
  assert.equal(statusBody(choice("free1h"), 0, "b1", ["a"]).until_ms, H);
});

test("statusQuery carries board, three ids and the clock, URL-encoded", () => {
  const q = statusQuery("board 1", ["a", "b", "c d"], 5 * M);
  assert.equal(q, "/journey/staff/doctor?board=board%201&ids=a%2Cb%2Cc%20d&at_ms=300000");
});

test("chipClass maps the three statuses", () => {
  assert.equal(chipClass("in_theatre"), "sun");
  assert.equal(chipClass("busy"), "sun");
  assert.equal(chipClass("available"), "ready");
  assert.equal(chipClass("unknown"), "info");
});

test("the four choices have the fixed labels and no advice words", () => {
  assert.deepEqual(STATUS_CHOICES.map((c) => c.label), [
    "Available for 1 h", "Busy for 30 min", "Busy for 1 h", "Back to automatic",
  ]);
  for (const c of STATUS_CHOICES) assert.doesNotMatch(c.label, ADVICE);
});
