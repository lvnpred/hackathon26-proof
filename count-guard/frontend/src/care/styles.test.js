import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

test("disabled buttons are outlined, never filled", () => {
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  assert.match(css, /button:disabled[^{]*\{[^}]*background:\s*transparent/);
  assert.match(css, /button\.primary:disabled/);
});

test("care.css styles clickable rows and the disabled clock buttons", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.row-link/);
  assert.match(css, /\.open-cue/);
  assert.match(css, /\.clock-bar button:disabled[^{]*\{[^}]*background:\s*transparent/);
});
