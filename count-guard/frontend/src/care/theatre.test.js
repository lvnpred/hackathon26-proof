import test from "node:test";
import assert from "node:assert/strict";
import { theatreSteps, checklistState, swabFigures, packLine } from "./theatre.js";
import { M } from "./clock.js";

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

const base = { tray: { planned: [{}], latest: null }, timeline: [IN_THEATRE], count: { opened: null, returned: null, missing: null } };
test("first not-done step is current; later steps say why they wait", () => {
  const s = checklistState(theatreSteps(base));
  assert.deepEqual(s.map((x) => x.status), ["current", "later", "later", "later"]);
  assert.deepEqual(s.map((x) => x.wait), ["", "after the tray check", "after surgery began", "after the count"]);
});
test("an open count stays expanded and does not block surgery ended", () => {
  const view = { ...base, tray: { planned: [{}], latest: { check: "tray", match: "ok", at_ms: 22 * M } },
    timeline: [IN_THEATRE, line("surgery.began", "Day 0 09:24"), line("count.closing", "Day 0 09:30", "Closing count: 14 of 15 back, 1 unaccounted.")],
    count: { opened: 15, returned: 14, missing: 1, opened_by: "Nurse Asha (synthetic)", opened_at_ms: 22 * M } };
  const s = checklistState(theatreSteps(view));
  assert.deepEqual(s.map((x) => x.status), ["done", "done", "open", "current"]);
  assert.equal(s[0].at, "09:22");
});
test("no tray planned reads done", () => {
  assert.deepEqual(theatreSteps({ ...base, tray: { planned: null } })[0], { key: "tray", title: "Tray check", done: true, says: "No tray planned", at: "", open: false });
});
test("swab figures and the pack line", () => {
  assert.deepEqual(swabFigures({ opened: 15, returned: 14, missing: 1 }), { opened: 15, back: 14, missing: 1, tone: "red" });
  assert.equal(swabFigures({ opened: 15, returned: 15, missing: 0 }).tone, "green");
  assert.deepEqual(swabFigures({ opened: null, returned: null, missing: null }), { opened: "–", back: "–", missing: "–", tone: "" });
  assert.equal(packLine({ opened: 15, opened_by: "Nurse Asha (synthetic)", opened_at_ms: 22 * M }), "Pack opened 09:22 by Nurse Asha");
  assert.equal(packLine({ opened: null }), "");
});
test("checklist copy has no advice words", () => {
  for (const s of ["after the tray check", "after surgery began", "after the count", "after step 4", "Upload tray video or photos", "No tray planned"]) assert.doesNotMatch(s, ADVICE);
});
