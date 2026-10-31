import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { TABS, modelRows, readInspect, recordLine, resolveMoment, stepFrame, tabsFor } from "./inspect.js";

const src = (f) => fs.readFileSync(new URL(f, import.meta.url), "utf8");

test("readInspect rejects bad ids", () => {
  assert.deepEqual(readInspect(new URLSearchParams("inspect=dayplan:abc&focus=amlodipine")), { momentId: "dayplan:abc", episodeId: null, focus: "amlodipine" });
  assert.deepEqual(readInspect(new URLSearchParams("inspect=a&episode=ep-1")), { momentId: "a", episodeId: "ep-1", focus: null });
  for (const bad of ["inspect=%3Cscript%3E", `inspect=${"a".repeat(81)}`, "", "inspect="]) assert.equal(readInspect(new URLSearchParams(bad)), null);
  assert.equal(readInspect(new URLSearchParams("inspect=a&focus=%3Cb%3E")).focus, null);
});

test("a patient sees two tabs", () => {
  assert.deepEqual(tabsFor("patient"), ["input", "found"]);
  assert.deepEqual(tabsFor("staff"), ["input", "found", "record", "model"]);
  assert.equal(TABS.length, 4);
});

test("modelRows", () => {
  assert.deepEqual(modelRows([{ model: "sam", model_id: "sam-3.1", source: "prepared", ms: null }, { model: "spark", model_id: "m", source: "muse-spark-1.3", ms: 120 }], false),
    [{ name: "sam", id: "sam-3.1", mode: "prepared", ms: "—" }, { name: "spark", id: "m", mode: "muse-spark-1.3", ms: "120 ms" }]);
  assert.equal(modelRows([{ model: "sam", model_id: "x", source: "prepared", ms: 1 }], true)[0].mode, "Sample");
  assert.deepEqual(modelRows(null, false), []);
});

test("recordLine", () => {
  const w = { type: "tray.checked", when: "Day 0 09:20", by: "Nurse Asha (synthetic)", plain: "Tray checked, 14 of 15." };
  assert.equal(recordLine(w, "staff"), "tray.checked · 09:20 · Nurse Asha · Tray checked, 14 of 15.");
  assert.equal(recordLine(w, "patient"), "09:20 · Tray checked, 14 of 15.");
  assert.doesNotMatch(recordLine(w, "patient"), /\b[a-z]+\.[a-z_]+\b/);
});

test("stepFrame clamps", () => {
  assert.equal(stepFrame(0, -1, 5), 0);
  assert.equal(stepFrame(4, 1, 5), 4);
  assert.equal(stepFrame(2, 1, 5), 3);
});

test("a patient lens never resolves a staff-only moment", () => {
  const moments = [{ id: "a", patient_finding: null }, { id: "b", patient_finding: "x", written: [{ event_id: "w" }] }];
  assert.equal(resolveMoment(moments, "a", "patient"), null);
  assert.equal(resolveMoment(moments, "a", "staff").id, "a");
  assert.equal(resolveMoment(moments, "w", "patient").id, "b");
  assert.equal(resolveMoment(moments, "zzz", "staff"), null);
  assert.equal(resolveMoment(undefined, "a", "staff"), null);
});

test("Inspector renders inside .app without a portal or dialog role", () => {
  const s = src("./Inspector.jsx");
  assert.match(s, /aria-label="Inspector"/);
  assert.match(s, /Nothing to inspect with that id\./);
  assert.doesNotMatch(s, /createPortal/);
  assert.doesNotMatch(s, /role="dialog"/);
  assert.match(s, /replace: true/);
  assert.match(s, /export const KIND_VIEWS/);
  assert.match(src("./CareShell.jsx"), /from "\.\/Inspector\.jsx"/);
});
