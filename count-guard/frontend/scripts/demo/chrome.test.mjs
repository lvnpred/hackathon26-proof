import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { INSTALL_HINT, cacheRoot, findChrome, pickChrome } from "./chrome.mjs";

test("picks the newest headless shell", () => {
  const dirs = ["chromium-1243", "chromium_headless_shell-1200", "chromium_headless_shell-1243", "ffmpeg-1011"];
  assert.equal(
    pickChrome(dirs, "darwin", "arm64"),
    "chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell",
  );
  assert.equal(
    pickChrome(dirs, "darwin", "x64"),
    "chromium_headless_shell-1243/chrome-headless-shell-mac-x64/chrome-headless-shell",
  );
  assert.equal(
    pickChrome(dirs, "linux", "x64"),
    "chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell",
  );
});

test("compares revisions as numbers, not text", () => {
  assert.equal(
    pickChrome(["chromium_headless_shell-999", "chromium_headless_shell-1243"], "linux", "x64"),
    "chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell",
  );
  assert.match(pickChrome(["chromium-999", "chromium-1243"], "linux", "x64"), /^chromium-1243\//);
});

test("falls back to full chromium", () => {
  assert.equal(
    pickChrome(["chromium-1234", "chromium-1243", "ffmpeg-1011"], "darwin", "arm64"),
    "chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
  );
  assert.equal(pickChrome(["chromium-1243"], "linux", "x64"), "chromium-1243/chrome-linux64/chrome");
});

test("returns null on an empty cache or an unknown platform", () => {
  assert.equal(pickChrome([], "darwin", "arm64"), null);
  assert.equal(pickChrome(["ffmpeg-1011"], "linux", "x64"), null);
  assert.equal(pickChrome(["chromium-1243"], "win32", "x64"), null);
});

test("cacheRoot honours the env override, else the platform default", () => {
  assert.equal(cacheRoot({ PLAYWRIGHT_BROWSERS_PATH: "/x" }, "/h", "darwin"), "/x");
  assert.equal(cacheRoot({}, "/h", "darwin"), "/h/Library/Caches/ms-playwright");
  assert.equal(cacheRoot({}, "/h", "linux"), "/h/.cache/ms-playwright");
});

test("CG_CHROME wins when the file exists", () => {
  const dir = mkdtempSync(join(tmpdir(), "cg-chrome-"));
  const file = join(dir, "chrome");
  writeFileSync(file, "");
  assert.equal(findChrome({ CG_CHROME: file, PLAYWRIGHT_BROWSERS_PATH: dir }), file);
});

test("uses the cached browser when present", () => {
  const dir = mkdtempSync(join(tmpdir(), "cg-cache-"));
  const rel = pickChrome(["chromium_headless_shell-7"], process.platform, process.arch);
  if (!rel) return; // platform without a known layout
  mkdirSync(join(dir, rel, ".."), { recursive: true });
  writeFileSync(join(dir, rel), "");
  mkdirSync(join(dir, "chromium_headless_shell-7"), { recursive: true });
  assert.equal(findChrome({ PLAYWRIGHT_BROWSERS_PATH: dir }), join(dir, rel));
});

test("throws the install hint when nothing exists", () => {
  const dir = mkdtempSync(join(tmpdir(), "cg-empty-"));
  assert.throws(() => findChrome({ PLAYWRIGHT_BROWSERS_PATH: dir, CG_CHROME: join(dir, "nope") }), { message: INSTALL_HINT });
  assert.throws(() => findChrome({ PLAYWRIGHT_BROWSERS_PATH: join(dir, "missing") }), { message: INSTALL_HINT });
});
