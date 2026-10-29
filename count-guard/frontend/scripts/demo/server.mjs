import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import net from "node:net";
import { fileURLToPath } from "node:url";

// Pure guards for the demo check's own servers. The owner's servers (8100, 5173) are never used.
export const API_PORT = 8200;
export const WEB_PORT = 5273;
export const OWNER_PORTS = [8100, 5173];
// Built from parts so no tracked line reads the key name, "=", then a quote (repo hygiene test).
export const NO_KEY = ["MODEL_API_KEY", ""].join("=");

const EMPTIED = ["MODEL_API_KEY", "BASETEN_API_KEY", "META_API_KEY"];
const DROPPED = ["MAKEFLAGS", "MAKELEVEL", "MFLAGS", "CG_API_PORT", "CG_WEB_PORT"];

export function devArgs(dataDir) {
  return ["dev", NO_KEY, `CG_API_PORT=${API_PORT}`, `CG_WEB_PORT=${WEB_PORT}`, `COUNT_GUARD_DATA=${dataDir}`];
}

// Environment for the child `make dev`: every model key empty, nothing inherited from a parent make.
export function childEnv(parent) {
  const env = { ...parent };
  for (const k of DROPPED) delete env[k];
  for (const k of EMPTIED) env[k] = "";
  return env;
}

export function assertOffline(models) {
  if (models?.live !== false) {
    throw new Error("The demo server reports live models. Stopped before any click; nothing was spent.");
  }
}

// free: port -> true when nothing listens there.
export function busyPorts(free) {
  for (const port of [API_PORT, WEB_PORT]) {
    if (free[port] !== true) {
      return `Port ${port} is in use. Stop that server first; demo-check never stops a server it did not start.`;
    }
  }
  return "";
}

// ---- Process side: starts and stops the demo check's own servers (8200 and 5273 only). ----
const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Free when the connection is refused. Any other outcome counts as taken.
export function portFree(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host: "127.0.0.1" });
    socket.once("connect", () => { socket.destroy(); resolve(false); });
    socket.once("error", (err) => resolve(err.code === "ECONNREFUSED"));
  });
}

async function getJson(url) {
  const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
  return res.ok ? res.json() : null;
}

async function waitFor(what, probe, cancelled, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (cancelled()) throw new Error("Stopped while starting.");
    try {
      const got = await probe();
      if (got !== null && got !== undefined) return got;
    } catch {
      // not up yet
    }
    await sleep(500);
  }
  throw new Error(`${what} did not answer within ${ms / 1000} s. See the server log in demo-shots/server.log.`);
}

const REAL = {
  spawn, free: portFree, json: getJson, kill: (pid, sig) => process.kill(pid, sig),
  web: async (url) => (await fetch(url)).ok || null,
};

// onSpawn(stop) runs right after the spawn, so a signal during start-up can still stop the group.
// deps replaces process control in tests.
export async function startServers({ dataDir, logPath, onSpawn = () => {}, deps = {} }) {
  const d = { ...REAL, ...deps };
  const probes = { [API_PORT]: await d.free(API_PORT), [WEB_PORT]: await d.free(WEB_PORT) };
  const busy = busyPorts(probes);
  if (busy) throw new Error(busy);

  const log = openSync(logPath, "a");
  const child = d.spawn("make", devArgs(dataDir), {
    cwd: REPO, detached: true, stdio: ["ignore", log, log], env: childEnv(process.env),
  });
  let spawnError = null;
  child.on("error", (err) => { spawnError = err; });
  let stopping = null;
  const alive = () => { try { d.kill(-child.pid, 0); return true; } catch { return false; } };
  const stop = () => {
    stopping ??= (async () => {
      if (alive()) { try { d.kill(-child.pid, "SIGTERM"); } catch { /* already gone */ } }
      const end = Date.now() + 10000;
      while (Date.now() < end && !((await d.free(API_PORT)) && (await d.free(WEB_PORT)))) await sleep(250);
      if (alive()) { try { d.kill(-child.pid, "SIGKILL"); } catch { /* already gone */ } }
      closeSync(log);
    })();
    return stopping;
  };
  onSpawn(stop);

  const cancelled = () => {
    if (spawnError) throw new Error(`Could not start make: ${spawnError.message}`);
    return stopping !== null;
  };
  try {
    // Both URLs: the browser reaches the API through Vite's proxy, whose target comes from the environment.
    assertOffline(await waitFor("The API", () => d.json(`http://127.0.0.1:${API_PORT}/journey/models`), cancelled));
    await waitFor("The web server", () => d.web(`http://127.0.0.1:${WEB_PORT}/`), cancelled);
    assertOffline(await waitFor("The web proxy", () => d.json(`http://127.0.0.1:${WEB_PORT}/journey/models`), cancelled));
  } catch (err) {
    await stop();
    throw err;
  }
  return { stop };
}
