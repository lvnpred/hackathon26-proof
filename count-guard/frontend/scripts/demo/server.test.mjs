import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { API_PORT, NO_KEY, OWNER_PORTS, WEB_PORT, assertOffline, busyPorts, childEnv, devArgs, portFree, startServers } from "./server.mjs";

test("devArgs uses 8200/5273 and the data dir, never the owner's ports", () => {
  const args = devArgs("/tmp/data");
  assert.deepEqual(args, ["dev", NO_KEY, "CG_API_PORT=8200", "CG_WEB_PORT=5273", "COUNT_GUARD_DATA=/tmp/data"]);
  for (const a of args) for (const p of OWNER_PORTS) assert.ok(!a.includes(String(p)), a);
  assert.deepEqual([API_PORT, WEB_PORT], [8200, 5273]);
});

test("the key is passed empty", () => {
  assert.deepEqual(NO_KEY.split("="), ["MODEL_API_KEY", ""]);
});

test("assertOffline stops on live, missing or junk", () => {
  for (const bad of [{ live: true }, {}, null, "x", undefined, { live: "false" }]) {
    assert.throws(() => assertOffline(bad), { message: "The demo server reports live models. Stopped before any click; nothing was spent." });
  }
  assert.doesNotThrow(() => assertOffline({ live: false }));
});

test("busyPorts names the first busy port", () => {
  assert.equal(busyPorts({ 8200: true, 5273: true }), "");
  assert.equal(
    busyPorts({ 8200: false, 5273: true }),
    "Port 8200 is in use. Stop that server first; demo-check never stops a server it did not start.",
  );
  assert.match(busyPorts({ 8200: true, 5273: false }), /^Port 5273 is in use\./);
});

test("childEnv empties every model key and drops make's inherited flags", () => {
  const env = childEnv({
    PATH: "/bin",
    MODEL_API_KEY: "live-one",
    BASETEN_API_KEY: "live-two",
    META_API_KEY: "live-three",
    MAKEFLAGS: "-j",
    MAKELEVEL: "1",
    MFLAGS: "-j",
    CG_API_PORT: "8100",
  });
  assert.equal(env.PATH, "/bin");
  assert.equal(env.MODEL_API_KEY, "");
  assert.equal(env.BASETEN_API_KEY, "");
  assert.equal(env.META_API_KEY, "");
  for (const k of ["MAKEFLAGS", "MAKELEVEL", "MFLAGS"]) assert.ok(!(k in env), k);
  assert.ok(!("CG_API_PORT" in env), "the port comes from the command line only");
});

test("portFree is false while something listens and true once it stops", async () => {
  const server = net.createServer().listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  const { port } = server.address();
  assert.equal(await portFree(port), false);
  await new Promise((resolve) => server.close(resolve));
  assert.equal(await portFree(port), true);
});

test("a stop requested during start-up reaches the spawned group", async () => {
  const sent = [];
  let up = true;
  const fakeChild = { pid: 4242, on() {} };
  const deps = {
    spawn: () => fakeChild,
    free: async () => true,
    json: async () => null, // the API never answers: start-up would poll for 60 s
    kill: (pid, sig) => {
      if (sig === 0) { if (!up) throw new Error("gone"); return; }
      sent.push([pid, sig]);
      up = false;
    },
  };
  let stopFn = null;
  const dir = mkdtempSync(join(tmpdir(), "cg-test-"));
  const started = startServers({ dataDir: dir, logPath: join(dir, "log"), onSpawn: (stop) => { stopFn = stop; }, deps })
    .then(() => "started", (err) => err.message);
  while (!stopFn) await new Promise((r) => setTimeout(r, 10));
  await stopFn(); // what the SIGINT handler does
  assert.equal(await started, "Stopped while starting.");
  assert.deepEqual(sent, [[-4242, "SIGTERM"]]);
});

test("a spawn error rejects start-up and still stops", async () => {
  let fail;
  const deps = {
    spawn: () => ({ pid: 1, on: (ev, cb) => { if (ev === "error") fail = cb; } }),
    free: async () => true,
    json: async () => { fail?.(new Error("spawn make ENOENT")); return null; },
    kill: () => { throw new Error("gone"); },
  };
  const dir = mkdtempSync(join(tmpdir(), "cg-test-"));
  await assert.rejects(startServers({ dataDir: dir, logPath: join(dir, "log"), deps }), /Could not start make: spawn make ENOENT/);
});
