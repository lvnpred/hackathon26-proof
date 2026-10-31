import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");

test("StatusPill maps each role to class s-{role}; only done has no icon", () => {
  const src = read("./StatusPill.jsx");
  assert.match(src, /status-pill s-\$\{role\}/);
  for (const role of ["fine", "wait", "check", "danger", "done"]) assert.match(src, new RegExp(`\\b${role}\\b`));
  assert.match(src, /fine: IconCheck/);
  assert.match(src, /wait: IconWait/);
  assert.match(src, /check: IconClock/);
  assert.match(src, /danger: IconWarn/);
  assert.match(src, /done: null/);
  assert.match(src, /aria-hidden="true"/);
});

test("AiMark is a span.ai-mark reading AI with a plain title", () => {
  const src = read("./AiMark.jsx");
  assert.match(src, /className="ai-mark"/);
  assert.match(src, /title="Done by the AI"/);
  assert.match(src, />AI</);
});

test("Fold sets aria-expanded and renders children only when open", () => {
  const src = read("./Fold.jsx");
  assert.match(src, /aria-expanded=\{open\}/);
  assert.match(src, /\{open && /);
  assert.match(src, /open \? "Hide" : "Show"/);
  assert.match(src, /button className="quiet"/);
});

test("icons.jsx exports the eight icons as hidden currentColor strokes", () => {
  const src = read("./icons.jsx");
  for (const name of ["IconCheck", "IconWait", "IconClock", "IconWarn", "IconCamera", "IconMic", "IconUndo", "IconWhy"]) {
    assert.match(src, new RegExp(`export function ${name}\\b`));
  }
  assert.match(src, /aria-hidden="true"/);
  assert.match(src, /stroke="currentColor"/);
});
