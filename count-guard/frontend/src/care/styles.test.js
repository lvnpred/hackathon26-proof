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

test("the demo dock is dusk and dashed, folds to a round button on a phone and keeps the disabled clock style", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.demo-dock \{[^}]*position: fixed[^}]*dashed[^}]*var\(--dusk\)/);
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.demo-dock:not\(\.open\) \.dock-body \{[^}]*display:\s*none/);
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.demo-dock \{[^}]*border-radius: 50%/);
  assert.match(css, /\.app \{ padding-bottom: calc\(var\(--dock-h/);
  assert.doesNotMatch(css, /\.demo-toggle/);
});

test("the safety strip is never hidden by a media query", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.product-strip \{/);
  assert.doesNotMatch(css, /\.product-strip[^{]*\{[^}]*display:\s*none/);
  for (const block of css.match(/@media[^{]*\{(?:[^{}]*\{[^}]*\})*[^{}]*\}/g) || []) {
    assert.doesNotMatch(block, /product-strip[^{]*\{[^}]*(display:\s*none|visibility:\s*hidden)/);
  }
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

test("care.css styles the AI moment, chips, tone pills and the Inspector drawer", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.ai-moment \{/);
  assert.match(css, /\.chip \{/);
  for (const tone of ["blue", "amber", "green", "grey"]) assert.match(css, new RegExp(`\\.pill\\.tone-${tone}`));
  assert.match(css, /\.inspector \{[^}]*width:\s*480px/);
  assert.match(css, /@media \(max-width: 600px\) \{\s*\.inspector \{[^}]*width:\s*100%/);
});

test("care.css styles the AI handling strip and the proposal card with 44 px targets", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.ai-handling/);
  assert.match(css, /\.proposal-card/);
  assert.match(css, /\.ai-handling button[^{]*\{[^}]*min-height:\s*44px/);
});

test("status tokens are defined in light and redefined in the dark block", () => {
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  const light = css.match(/:root \{[\s\S]*?\n\}/)[0];
  const dark = css.match(/prefers-color-scheme: dark\) \{[\s\S]*?\n  \}\n\}/)[0];
  for (const role of ["fine", "wait", "check", "danger", "done"]) {
    for (const suffix of ["", "-soft"]) {
      const re = new RegExp(`--status-${role}${suffix}:`);
      assert.match(light, re);
      assert.match(dark, re);
    }
  }
  assert.match(light, /--dusk:\s*#14120E/);
});

test("the status pill, AI mark and type scale are styled", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  const pill = css.match(/\.status-pill \{[^}]*\}/)[0];
  assert.match(pill, /min-height:\s*26px/);
  assert.match(pill, /white-space:\s*nowrap/);
  assert.match(css.match(/\.ai-mark \{[^}]*\}/)[0], /border:\s*1px solid var\(--line-control\)/);
  assert.match(css.match(/\.t-display \{[^}]*\}/)[0], /font-variant-numeric:\s*tabular-nums/);
  assert.match(css, /\.t-heading \{/);
  assert.match(css, /\.t-caption \{/);
  for (const role of ["fine", "wait", "check", "danger", "done"]) assert.match(css, new RegExp(`\\.status-pill\\.s-${role} \\{`));
});

test("dead stage-bar and dock link CSS is gone", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.doesNotMatch(css, /\.stage-bar|\.stage-btn|\.dock-body a/);
});
