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

test("care.css styles the journey bar, the next card and the quiet row", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.journey li\.current/);
  assert.match(css, /\.journey li\.later, \.journey li\.skipped \{[^}]*color:\s*var\(--ink-muted\)/);
  assert.match(css, /\.next-text \{[^}]*font-size/);
  assert.match(css, /\.quiet-row/);
});

test("the dock folds to one line at phone width and the clock keeps its disabled style", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.demo-dock:not\(\.open\) \.dock-body \{[^}]*display:\s*none/);
  assert.match(css, /\.demo-dock \{[^}]*background/);
  assert.doesNotMatch(css, /\.demo-toggle/);
});

test("the research notice sits outside the folded dock body", () => {
  const jsx = fs.readFileSync(new URL("./DemoDock.jsx", import.meta.url), "utf8");
  const body = jsx.match(/<div className="dock-body">([\s\S]*?)\n      <\/div>/)[1];
  assert.doesNotMatch(body, /<Banner/);
  assert.match(jsx, /<Banner \/>/);
});

test("care.css styles the patient thread rows and the unread dot", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.thread-row/);
  assert.match(css, /\.dot \{/);
});

test("the evidence viewer stage is positioned and the thumb is 48 px", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.ev-stage \{[^}]*position:\s*relative/);
  assert.match(css, /\.ev-thumb \{[^}]*48px/);
});

test("the next card, the evidence viewer and the theatre checklist cannot grow wider than a 390 px screen", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  for (const rule of [/\n\.next-card \{[^}]*\}/, /\n\.evidence \{[^}]*\}/, /\n\.checklist \{[^}]*\}/, /\n\.checklist \.step \{[^}]*\}/]) {
    assert.match(css.match(rule)[0], /grid-template-columns:\s*minmax\(0, 1fr\)/);
  }
});

test("the brown-bag tone dots never share the Ask unread dot class, which stays 8 px", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\n\.dot \{[^}]*width:\s*8px[^}]*height:\s*8px/);
  assert.equal((css.match(/\n\.dot[ .{]/g) || []).length, 1);
  assert.match(css, /\.tone-dot \{[^}]*12px/);
  assert.match(css, /\.tone-dot\.green/);
  const jsx = fs.readFileSync(new URL("./MedicinesFromHome.jsx", import.meta.url), "utf8");
  assert.match(jsx, /tone-dot \$\{stripTone/);
  assert.doesNotMatch(jsx, /className=\{`dot /);
});
