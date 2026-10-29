import test from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import { API_PORT, NO_KEY, OWNER_PORTS, WEB_PORT, assertOffline, busyPorts, childEnv, devArgs, portFree } from "./server.mjs";

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
