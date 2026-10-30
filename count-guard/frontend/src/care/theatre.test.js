import test from "node:test";
import assert from "node:assert/strict";
import { theatreSteps } from "./theatre.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const line = (type, when, plain = "") => ({ type, when, plain });
const IN_THEATRE = line("patient.state", "Day 0 09:16", "moved to theatre");

test("nothing done yet: every step says so", () => {
  const steps = theatreSteps({ tray: { planned: [{}], latest: null }, timeline: [IN_THEATRE] });
  assert.deepEqual(steps.map((s) => s.title), ["Tray check", "Surgery began", "Swab count", "Surgery ended"]);
  assert.deepEqual(steps.map((s) => s.done), [false, false, false, false]);
  assert.deepEqual(steps.map((s) => s.says), ["Not checked yet", "Not yet", "Not started", "Not yet"]);
});

test("progress reads from this theatre stay only", () => {
  const view = {
    tray: { planned: [{}], latest: { check: "tray", match: "mismatch" } },
    timeline: [
      line("surgery.began", "Day 0 08:00"),
      line("count.closing", "Day 0 08:10", "Closing count: old stay."),
      IN_THEATRE,
      line("surgery.began", "Day 0 09:20"),
      line("count.pack_opened", "Day 0 09:22", "Opened 15 swab."),
    ],
  };
  const steps = theatreSteps(view);
  assert.equal(steps[0].says, "Flagged: not everything planned was seen. The surgeon decides.");
  assert.equal(steps[0].done, true);
  assert.equal(steps[1].says, "Began Day 0 09:20");
  assert.equal(steps[2].says, "Pack opened; closing count not recorded yet");
  assert.equal(steps[2].done, false);
  assert.equal(steps[3].says, "Not yet");
});

test("closing count and end are shown when recorded", () => {
  const view = {
    tray: { planned: [{}], latest: { check: "tray", match: "ok" } },
    timeline: [
      IN_THEATRE,
      line("surgery.began", "Day 0 09:20"),
      line("count.pack_opened", "Day 0 09:22", "Opened 15 swab."),
      line("count.closing", "Day 0 09:24", "Closing count: opened 15, back 15, unaccounted 0."),
      line("surgery.ended", "Day 0 09:26"),
    ],
  };
  const steps = theatreSteps(view);
  assert.equal(steps[2].says, "Closing count: opened 15, back 15, unaccounted 0.");
  assert.equal(steps[3].says, "Ended Day 0 09:26");
  assert.ok(steps.every((s) => s.done));
  assert.ok(steps.every((s) => !ADVICE.test(s.says)));
});
