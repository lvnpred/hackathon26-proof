// Finds a Chromium for the demo check. Never downloads one.
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const INSTALL_HINT =
  "No Chromium found for the demo check. Run: cd count-guard/frontend && npx playwright-core install chromium-headless-shell, or set CG_CHROME to a Chrome binary.";

const SHELL = /^chromium_headless_shell-(\d+)$/;
const FULL = /^chromium-(\d+)$/;

function newest(dirNames, pattern) {
  let best = null;
  for (const name of dirNames) {
    const m = pattern.exec(name);
    if (m && (best === null || Number(m[1]) > best.rev)) best = { name, rev: Number(m[1]) };
  }
  return best?.name ?? null;
}

function shellBinary(platform, arch) {
  if (platform === "darwin") return `chrome-headless-shell-mac-${arch === "arm64" ? "arm64" : "x64"}/chrome-headless-shell`;
  if (platform === "linux") return "chrome-headless-shell-linux64/chrome-headless-shell";
  return null;
}

function fullBinary(platform, arch) {
  if (platform === "darwin") {
    const dir = `chrome-mac-${arch === "arm64" ? "arm64" : "x64"}`;
    return `${dir}/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
  }
  if (platform === "linux") return "chrome-linux64/chrome";
  return null;
}

export function pickChrome(dirNames, platform, arch) {
  const shell = newest(dirNames, SHELL);
  if (shell && shellBinary(platform, arch)) return `${shell}/${shellBinary(platform, arch)}`;
  const full = newest(dirNames, FULL);
  if (full && fullBinary(platform, arch)) return `${full}/${fullBinary(platform, arch)}`;
  return null;
}

export function cacheRoot(env, home, platform) {
  if (env.PLAYWRIGHT_BROWSERS_PATH) return env.PLAYWRIGHT_BROWSERS_PATH;
  return platform === "darwin" ? join(home, "Library", "Caches", "ms-playwright") : join(home, ".cache", "ms-playwright");
}

export function findChrome(env = process.env) {
  if (env.CG_CHROME && existsSync(env.CG_CHROME)) return env.CG_CHROME;
  const root = cacheRoot(env, homedir(), process.platform);
  let names = [];
  try {
    names = readdirSync(root);
  } catch {
    // no cache folder: fall through to the hint
  }
  const rel = pickChrome(names, process.platform, process.arch);
  if (rel && existsSync(join(root, rel))) return join(root, rel);
  throw new Error(INSTALL_HINT);
}
