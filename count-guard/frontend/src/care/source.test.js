import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { PREPARED, isPrepared, sourceWords, sourceLine } from "./source.js";

test("sourceWords names how a reading was made", () => {
  assert.equal(sourceWords({ kind: "visual", capability: "tray" }), "Read by camera");
  assert.equal(sourceWords({ kind: "photo_read", capability: "monitor" }), "Read from photo");
  assert.equal(sourceWords({ kind: "photo_read", capability: "dose_strip" }), "Checked against the order");
  assert.equal(sourceWords({ kind: "voice", capability: "orders" }), "Drafted from voice");
  assert.equal(sourceWords({ kind: "voice", capability: "discharge" }), "Drafted from voice");
  assert.equal(sourceWords({ kind: "voice", capability: "task_voice" }), "From voice");
  assert.equal(sourceWords({ kind: "voice", capability: "answer_voice" }), "From voice");
});

test("rules-only and record moments have no source words", () => {
  for (const kind of ["rule", "record", "answer", "draft"]) assert.equal(sourceWords({ kind }), null);
  assert.equal(sourceWords(null), null);
});

test("source words are never a model name or the banned status word", () => {
  for (const m of [{ kind: "visual" }, { kind: "photo_read" }, { kind: "photo_read", capability: "dose_strip" }, { kind: "voice", capability: "orders" }, { kind: "voice", capability: "answer_voice" }]) {
    assert.doesNotMatch(sourceWords(m), /Muse|SAM|Spark|Recorded|prepared|live/);
  }
});

test("only the Inspector, the model cards and the AI page import modelChip", () => {
  const dir = new URL("./", import.meta.url);
  const allowed = new Set(["Inspector.jsx", "InspectAgent.jsx", "ModelCards.jsx", "AiDashboard.jsx"]);
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith(".jsx") || allowed.has(name)) continue;
    assert.doesNotMatch(fs.readFileSync(new URL(name, dir), "utf8"), /modelChip|chipFor|heardChip|draftChip/, name);
  }
});

test("a prepared result is labelled Prepared (spec §6.7)", () => {
  assert.equal(PREPARED, "Prepared");
  assert.equal(isPrepared({ source: "prepared" }), true);
  assert.equal(isPrepared({ heard_by: "prepared" }), true);
  assert.equal(isPrepared({ source: "", calls: [{ model: "sam", source: "prepared" }] }), true);
  for (const x of [{ source: "sam-3.1" }, { source: "unavailable" }, { heard_by: "typed" }, null, undefined]) assert.equal(isPrepared(x), false);
  assert.equal(sourceLine("Read by camera", true), "Read by camera · Prepared");
  assert.equal(sourceLine(null, true), "Prepared");
  assert.equal(sourceLine("From voice", false), "From voice");
  assert.equal(sourceLine(null, false), null);
});

test("every screen that shows source words also says when they are prepared", () => {
  const dir = new URL("./", import.meta.url);
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith(".jsx") || name === "Source.jsx") continue;
    const text = fs.readFileSync(new URL(name, dir), "utf8");
    for (const use of text.match(/<Source [^>]*\/>/g) || []) assert.match(use, /prepared=/, `${name}: ${use}`);
  }
});
