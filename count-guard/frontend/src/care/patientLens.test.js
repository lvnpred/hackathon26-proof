import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { agentMoments, myPatientsStrip, proposalsFor } from "./handling.js";
import { resolveMoment } from "./inspect.js";

const src = (name) => fs.readFileSync(new URL(`./${name}`, import.meta.url), "utf8");
const ops = {
  handling: [{ work_id: "w1", summary: "Reminded", at_ms: 0, level: "act", status: "done", reason: "r", inputs: [] }],
  proposals: [{ work_id: "p1", owner_role: "doctor", sentence: "Ready", draft: "d", cited: [], reason: "r", inputs: [] }],
  routes: { q1: "Dr. A. Rao" },
};

test("patient lens: helpers return no ops content", () => {
  assert.deepEqual(proposalsFor(ops, "patient"), []);
  assert.deepEqual(myPatientsStrip([{ id: "e", name: "A", view: { ops } }], "patient"), { rows: [], proposals: [] });
  // an agent moment never resolves for the patient lens, whatever id the URL names
  assert.equal(resolveMoment(agentMoments(ops, "e"), "w1", "patient"), null);
  assert.equal(resolveMoment(agentMoments(ops, "e"), "p1", "patient"), null);
});

test("patient lens: AiHandling renders nothing and ProposalCard stays out of patient screens", () => {
  assert.match(src("AiHandling.jsx"), /role === "patient"[^\n]*return null/);
  for (const f of ["Thread.jsx", "Today.jsx", "PatientToday.jsx"]) {
    if (!fs.existsSync(new URL(`./${f}`, import.meta.url))) continue;
    assert.doesNotMatch(src(f), /ProposalCard|AiHandling|handlingRows|proposalsFor/, f);
  }
  assert.match(src("Thread.jsx"), /routedLine/);
});

test("StatePanel gives the patient no strip", () => {
  assert.match(src("StatePanel.jsx"), /default:\s*\n\s*return <p className="note"/);
});

test("patient lens: no chip beside a photo match, none in AiMoment, names go through displayName", () => {
  assert.doesNotMatch(src("MyCare.jsx"), /modelChip\(|sourceWords\(/);
  assert.match(src("MyCare.jsx"), /Done by \{displayName\(d\.by\)\}/);
  assert.match(src("MyCare.jsx"), /Ordered by \$\{displayName\(order\.by\)\}/);
  assert.match(src("AiMoment.jsx"), /lens !== "patient" \? sourceWords\(moment\) : null/);
  assert.doesNotMatch(src("AiMoment.jsx"), /AiMark/);
  assert.match(src("Thread.jsx"), /displayName\(answer\.by\)/);
});
