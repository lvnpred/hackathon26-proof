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

test("pills wrap and stay inside a 390 px screen", () => {
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  const pill = css.match(/\n\.pill \{[^}]*\}/)[0];
  assert.match(pill, /white-space:\s*normal/);
  assert.match(pill, /max-width:\s*100%/);
});

test("disabled mic keeps a visible muted circle; a disabled quiet button gets no border", () => {
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  assert.match(css, /\.mic:disabled, \.dictate-mic:disabled \{[^}]*background:\s*var\(--surface-sunk\)[^}]*border:\s*1px solid/);
  assert.match(css, /button\.quiet:disabled \{\s*border-color:\s*transparent/);
});

test("upload label looks disabled and an expanded action button is filled only while enabled", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.dictate-upload\.disabled \{[^}]*text-decoration:\s*none[^}]*cursor:\s*not-allowed/);
  assert.match(css, /\.action-bar button\[aria-expanded="true"\]:not\(:disabled\)/);
});
