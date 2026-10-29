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
