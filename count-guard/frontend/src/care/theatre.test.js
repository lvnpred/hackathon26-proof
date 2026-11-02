import test from "node:test";
import assert from "node:assert/strict";
import { theatreSteps, checklistState, swabFigures, packLine, canRecord, countReconciled, cameraRead, reasonNeeded } from "./theatre.js";
import { M } from "./clock.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const line = (type, when, plain = "") => ({ type, when, plain });
const IN_THEATRE = line("patient.state", "09:16", "moved to theatre");

test("nothing done yet: every step says so", () => {
  const steps = theatreSteps({ tray: { planned: [{}], latest: null }, timeline: [IN_THEATRE] });
  assert.deepEqual(steps.map((s) => s.title), ["Tray check", "Surgery began", "Swab count", "Surgery ended", "Back to ward"]);
  assert.deepEqual(steps.map((s) => s.done), [false, false, false, false, false]);
  assert.deepEqual(steps.map((s) => s.says), ["Not checked yet", "Not yet", "Not started", "Not yet", "Not yet"]);
});

test("progress reads from this theatre stay only", () => {
  const view = {
    tray: { planned: [{}], latest: { check: "tray", match: "mismatch" } },
    timeline: [
      line("surgery.began", "08:00"),
      line("count.closing", "08:10", "Closing count: old stay."),
      IN_THEATRE,
      line("surgery.began", "09:20"),
      line("count.pack_opened", "09:22", "Opened 15 swab."),
    ],
  };
  const steps = theatreSteps(view);
  assert.equal(steps[0].says, "Flagged: not everything planned was seen. The surgeon decides.");
  assert.equal(steps[0].done, true);
  assert.equal(steps[1].says, "Began 09:20");
  assert.equal(steps[2].says, "Pack opened; closing count not recorded yet");
  assert.equal(steps[2].done, false);
  assert.equal(steps[3].says, "Not yet");
});

test("closing count and end are shown when recorded", () => {
  const view = {
    tray: { planned: [{}], latest: { check: "tray", match: "ok" } },
    timeline: [
      IN_THEATRE,
      line("surgery.began", "09:20"),
      line("count.pack_opened", "09:22", "Opened 15 swab."),
      line("count.closing", "09:24", "Closing count: opened 15, back 15, unaccounted 0."),
      line("surgery.ended", "09:26"),
    ],
  };
  const steps = theatreSteps(view);
  assert.equal(steps[2].says, "Closing count: opened 15, back 15, unaccounted 0.");
  assert.equal(steps[3].says, "Ended 09:26");
  assert.ok(steps.slice(0, 4).every((s) => s.done));
  assert.equal(steps[4].done, false, "Back to ward is a move, not a recorded step");
  assert.ok(steps.every((s) => !ADVICE.test(s.says)));
});

const base = { tray: { planned: [{}], latest: null }, timeline: [IN_THEATRE], count: { opened: null, returned: null, missing: null } };
test("first not-done step is current; later steps say why they wait", () => {
  const s = checklistState(theatreSteps(base));
  assert.deepEqual(s.map((x) => x.status), ["current", "later", "later", "later", "later"]);
  assert.deepEqual(s.map((x) => x.wait), ["", "Locked", "Locked", "Locked", "Locked"]);
});
test("an open count stays expanded", () => {
  const view = { ...base, tray: { planned: [{}], latest: { check: "tray", match: "ok", at_ms: 22 * M } },
    timeline: [IN_THEATRE, line("surgery.began", "09:24"), line("count.closing", "09:30", "Closing count: 14 of 15 back, 1 unaccounted.")],
    count: { opened: 15, returned: 14, missing: 1, opened_by: "Nurse Asha (synthetic)", opened_at_ms: 22 * M } };
  const s = checklistState(theatreSteps(view));
  assert.deepEqual(s.map((x) => x.status), ["done", "done", "open", "current", "later"]);
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

test("controls follow the backend rules, not the list order", () => {
  assert.equal(canRecord(base, "began"), true, "began without a tray check");
  assert.equal(canRecord(base, "tray"), true);
  assert.equal(canRecord(base, "count"), false, "the count is taken once surgery began");
  assert.equal(canRecord(base, "ended"), false, "ended waits for began");
  const began = { ...base, timeline: [IN_THEATRE, line("surgery.began", "09:24")] };
  assert.equal(canRecord(began, "began"), false);
  assert.equal(canRecord(began, "tray"), false, "tray upload is hidden once surgery began");
  assert.equal(canRecord(began, "count"), true, "the count opens once surgery began");
  assert.equal(canRecord(began, "ended"), false, "ended waits for a saved, reconciled count");
  const saved = { ...began, count: { opened: 15, returned: 15, missing: 0, closed_opened: 15, closed_by: "Nurse Asha (synthetic)", closed_after_began: true } };
  assert.equal(canRecord(saved, "ended"), true);
  assert.equal(canRecord(saved, "ward"), false, "ward waits for surgery ended");
  const checked = { ...base, tray: { planned: [{}], latest: { check: "tray", match: "mismatch", at_ms: 22 * M } } };
  assert.equal(canRecord(checked, "tray"), true, "re-upload after a flagged check");
  assert.equal(canRecord({ ...base, tray: { planned: null } }, "tray"), false);
  const over = { ...began, timeline: [...began.timeline, line("surgery.ended", "10:00")] };
  assert.equal(canRecord(over, "ended"), false);
  assert.equal(canRecord({ ...saved, timeline: over.timeline }, "ward"), true);
});

test("countReconciled mirrors the server rule", () => {
  const ASHA = "Nurse Asha (synthetic)";
  const v = (count) => ({ count: { closed_after_began: true, ...count } });
  assert.equal(countReconciled(v({})), false, "no closing");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 15, returned: 15 })), true, "adds up");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 15, returned: 14 })), false, "1 unaccounted, no reason");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 15, returned: 14, closed_detail: " " })), false, "blank reason");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 15, returned: 14, closed_detail: "Found under the drape" })), true);
  assert.equal(countReconciled(v({ closed_by: "AI (on behalf of Nurse Asha)", opened: 15, returned: 15 })), false, "an AI closing never counts");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 15, returned: 15, missing: 3 })), true, "recomputed, not the stored figure");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 20, closed_opened: 15, returned: 15 })), false, "an extra pack since the closing: the stay's sum, not the closing's figure");
  assert.equal(countReconciled(v({ closed_by: ASHA, opened: 15, returned: 15, closed_after_began: false })), false, "a closing before surgery began proves nothing");
});

test("the count panel keeps the nurse's own number and says what is worked out", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("./CountPanel.jsx", import.meta.url), "utf8");
  assert.match(src, /useState\(""\)/);
  assert.doesNotMatch(src, /value=\{[^}]*camera\.count/);
  assert.match(src, /Worked out, not typed/);
  assert.match(src, /Save count as \{displayName\(by\)\}/);
  const list = fs.readFileSync(new URL("./TheatreChecklist.jsx", import.meta.url), "utf8");
  assert.match(list, /Surgery ended unlocks when the count is saved\./);
});

test("after surgery began the pack is not replaced: Add pack records an extra pack", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("./CountPanel.jsx", import.meta.url), "utf8");
  assert.match(src, /const extra = packed && began;/);
  assert.match(src, /\{extra \? "Add pack" : "change"\}/);
  assert.match(src, /step: "opened", quantity: opened, extra: true/);
});

import { readFileSync } from "node:fs";
function require_src(f) { return readFileSync(new URL("./" + f, import.meta.url), "utf8"); }

test("the folded count line does not repeat the saved line", async () => {
  const fs = await import("node:fs");
  const view = {
    count: { missing: 0, read: { returned: 14 }, saved: { returned: 15 }, closed_by: "Nurse Asha (synthetic)" },
    timeline: [IN_THEATRE, line("surgery.began", "09:20"), line("count.pack_opened", "09:22", "Opened 15 swab."), line("count.closing", "09:25", "Closing count: opened 15, back 15, unaccounted 0.")],
  };
  assert.equal(theatreSteps(view)[2].correction, undefined);
  assert.doesNotMatch(fs.readFileSync(new URL("./TheatreChecklist.jsx", import.meta.url), "utf8"), /step\.correction/);
});

test("correcting a camera-linked closing still needs a reason when Back differs from the old camera read", () => {
  // camera read 14 of 15, saved 14 with a reason; the live camera is gone, the saved closing carries the read
  const count = { opened: 15, camera: null, read: { returned: 14 }, closed_via: "camera", returned: 14, closed_by: "Nurse Asha (synthetic)" };
  assert.equal(cameraRead(count), 14);
  assert.equal(reasonNeeded(count, 15), true);
  assert.equal(reasonNeeded(count, 14), true); // unaccounted 1
  assert.equal(reasonNeeded({ opened: 15, camera: { count: 15 } }, 15), false);
  assert.equal(reasonNeeded({ opened: 15 }, 15), false);
  assert.match(require_src("CountPanel.jsx"), /reasonNeeded\(count, back\)/);
});

test("a done tray step folds to its AI moment and offers Check the tray again", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("./TheatreChecklist.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /hideUpload/);
  assert.match(src, /Check the tray again/);
  assert.match(src, /<AiMoment moment=\{trayMoment\}/);
  assert.doesNotMatch(fs.readFileSync(new URL("./VideoCheck.jsx", import.meta.url), "utf8"), /hideUpload/);
  assert.doesNotMatch("Check the tray again", ADVICE);
});

test("when surgery begins an open change form closes and its field is cleared; Add pack starts empty", async () => {
  const { afterBegan } = await import("./theatre.js");
  assert.deepEqual(afterBegan({ changing: true, quantity: "20" }), { changing: false, quantity: "" });
  const src = require_src("CountPanel.jsx");
  assert.match(src, /useEffect\(\(\) => \{\s*if \(extra\) \{\s*const next = afterBegan\(\{ changing, quantity \}\);\s*setChanging\(next\.changing\);\s*setQuantity\(next\.quantity\);/);
  assert.match(src, /setChanging\(true\); if \(extra\) setQuantity\(""\);/);
});

test("theatre steps say Began and Ended on the dock clock from the line's ms, the server text only without ms", async () => {
  const { theatreSteps } = await import("./theatre.js");
  const H = 3600000;
  const view = (line) => ({ timeline: [line], tray: { planned: false } });
  const began = { type: "surgery.began", at_ms: 13 * H, when: "22:00" };
  // dock one day later: the server's own "now" would have said 22:00, the dock clock says Yesterday
  assert.match(theatreSteps(view(began), 13 * H + 24 * H)[1].says, /^Began Yesterday 22:00$/);
  assert.equal(theatreSteps(view(began), 13 * H)[1].says, "Began 22:00");
  assert.equal(theatreSteps(view({ type: "surgery.began", when: "Mon 2 Nov, 09:14" }), 5)[1].says, "Began Mon 2 Nov, 09:14");
});

test("theatre panels: simulated vitals, heard rows and packs read as plain staff words", async () => {
  const { vitalsLabel, drugLine, drugStatus, heardPackLine, cardWords, RESEARCH_BANNER } = await import("./theatreLive.js");
  const reading = { systolic: 86, diastolic: 50, hr: 76, source: "simulated" };
  assert.ok(vitalsLabel(reading).includes("Simulated"));
  assert.equal(vitalsLabel(reading), "BP 86/50 · HR 76 · Simulated");
  const row = { generic: "lignocaine", strength: "2%", amount: 5, unit: "ml", route: "local infiltration", grounded: true, given: null };
  assert.equal(drugLine(row), "lignocaine 2% 5 ml local infiltration");
  assert.equal(drugStatus(row), "Heard, not confirmed");
  assert.match(drugStatus({ ...row, grounded: false }), /Check the name/);
  assert.equal(drugStatus({ ...row, given: { by: "Dr. A. Rao (synthetic)", at_ms: 40 * M } }), "Given 09:40 · confirmed by Dr. A. Rao");
  assert.equal(heardPackLine({ text: "opening twenty swabs", n: 20, item_type: "swab", confirmed_by: null }),
    "Heard “opening twenty swabs” · 20 swabs · not counted until a person confirms");
  assert.equal(RESEARCH_BANNER, "Research demo — not for clinical use");
  assert.equal(cardWords({ wording: "template" }), "Template from the record");
  for (const s of [vitalsLabel(reading), drugStatus(row), heardPackLine({ text: "x", n: 1, item_type: "swab" }), cardWords({ wording: "llm" })]) {
    assert.doesNotMatch(s, ADVICE);
    assert.doesNotMatch(s, /_|\b[a-z]{3,}\.[a-z]{3,}\b/);
  }
});

test("the theatre chart carries the three panels; the card shows the research banner and its source", () => {
  const list = require_src("TheatreChecklist.jsx");
  assert.match(list, /<TheatrePanels /);
  const panels = require_src("TheatrePanels.jsx");
  for (const name of ["TheatreDrugs", "VitalsStrip", "ContextCard"]) assert.match(panels, new RegExp(`<${name} `));
  const card = require_src("ContextCard.jsx");
  assert.match(card, /RESEARCH_BANNER/);
  assert.match(card, /<Source words=\{cardWords\(card\)\} prepared=\{isPrepared\(card\)\} \/>/);
  assert.match(require_src("VitalsStrip.jsx"), /vitalsLabel\(/);
  assert.match(require_src("TheatreDrugs.jsx"), /confirm/);
});
