import test from "node:test";
import assert from "node:assert/strict";
import { opensOnKey, opensRow } from "./rows.js";

test("opensRow ignores clicks on the row's own controls", () => {
  assert.equal(opensRow({ closest: () => null }), true);
  assert.equal(opensRow({ closest: (s) => (s.includes("button") ? {} : null) }), false);
});

test("opensOnKey opens on Enter and Space from the row itself, and stops Space scrolling", () => {
  const row = {};
  let stopped = 0;
  const key = (k, target = row) => ({ key: k, target, currentTarget: row, preventDefault: () => { stopped += 1; } });
  assert.equal(opensOnKey(key("Enter")), true);
  assert.equal(opensOnKey(key(" ")), true);
  assert.equal(stopped, 2);
  assert.equal(opensOnKey(key(" ", {})), false);
  assert.equal(opensOnKey(key("a")), false);
  assert.equal(stopped, 2);
});
