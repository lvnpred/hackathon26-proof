import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const dir = new URL(".", import.meta.url).pathname;
const read = (f) => fs.readFileSync(path.join(dir, f), "utf8");
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));

test("no care file imports from src/screens", () => {
  for (const file of walk(dir).filter((f) => /\.(jsx?|mjs)$/.test(f) && !f.endsWith(".test.js"))) {
    assert.doesNotMatch(fs.readFileSync(file, "utf8"), /from\s+["'][./]*\/screens\//, file);
  }
});

test("the moved journey v1 pieces live in care/legacy and the care screens use them", () => {
  for (const [file, names] of [["legacy/AuditTable.jsx", ["AuditTable"]], ["legacy/PatientCard.jsx", ["CheckIn", "MyCard", "NeedHelp"]],
    ["legacy/TodayPanel.jsx", ["Nudges", "Reminders", "Strips"]], ["legacy/Rx.jsx", ["RxImport", "RxTable"]]]) {
    for (const n of names) assert.match(read(file), new RegExp(`export function ${n}\\b`), `${file} ${n}`);
  }
  assert.match(read("History.jsx"), /from "\.\/legacy\/AuditTable"/);
  assert.match(read("Today.jsx"), /from "\.\/legacy\/PatientCard"/);
  assert.match(read("DoctorActions.jsx"), /from "\.\/legacy\/Rx"/);
});

test("the nurse chart has the dose and handover, the AI page has the audit lines", () => {
  assert.match(read("NurseActions.jsx"), /<DoseGiven /);
  assert.match(read("DoseGiven.jsx"), /act\("\/dose", \{ text: line, by \}\)/);
  assert.match(read("Handover.jsx"), /<Source words="Worded by AI" prepared=\{isPrepared\(handover\)\}/);
  assert.match(read("AiDashboard.jsx"), /<AiAudit /);
  assert.match(read("AiAudit.jsx"), /getAudit\(id\)/);
});
