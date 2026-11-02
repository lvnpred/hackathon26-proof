import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { API_PORT, NO_KEY, NO_KEYS, OWNER_PORTS, WEB_PORT, assertOffline, busyPorts, childEnv, devArgs, portFree, startServers } from "./server.mjs";
import { DD_ARGS, DD_PORT, STUB_FORM, assertDdOffline, ddEnv, refuseOwnerPorts } from "./dd.mjs";

test("devArgs uses 8200/5273 and the data dir, never the owner's ports", () => {
  const args = devArgs("/tmp/data");
  assert.deepEqual(args, ["dev", ...NO_KEYS, "CG_API_PORT=8200", "CG_WEB_PORT=5273", "COUNT_GUARD_DATA=/tmp/data"]);
  for (const a of args) for (const p of OWNER_PORTS) assert.ok(!a.includes(String(p)), a);
  assert.deepEqual([API_PORT, WEB_PORT], [8200, 5273]);
});

test("every model key is passed empty on the make command line", () => {
  assert.deepEqual(NO_KEY.split("="), ["MODEL_API_KEY", ""]);
  assert.deepEqual(NO_KEYS.map((k) => k.split("=")), [["MODEL_API_KEY", ""], ["BASETEN_API_KEY", ""], ["META_API_KEY", ""]]);
  assert.deepEqual(devArgs("/d").slice(1, 4), NO_KEYS);
});

test("assertOffline stops on live, missing or junk", () => {
  for (const bad of [{ live: true }, {}, null, "x", undefined, { live: "false" }]) {
    assert.throws(() => assertOffline(bad), { message: "The demo server reports live models. Stopped before any click; nothing was spent." });
  }
  assert.doesNotThrow(() => assertOffline({ live: false }));
});

test("busyPorts names the first busy port", () => {
  assert.equal(busyPorts({ 8200: true, 5273: true, 8300: true }), "");
  assert.match(busyPorts({ 8200: true, 5273: true, 8300: false }), /^Port 8300 is in use\./);
  assert.equal(
    busyPorts({ 8200: false, 5273: true, 8300: true }),
    "Port 8200 is in use. Stop that server first; demo-check never stops a server it did not start.",
  );
  assert.match(busyPorts({ 8200: true, 5273: false, 8300: true }), /^Port 5273 is in use\./);
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
  assert.equal(env.DD_BASE_URL, "http://127.0.0.1:8300");
  assert.equal(childEnv({}, "t0k").CG_SYNC_TOKEN, "t0k");
});

test("Doctor Dictation runs on 8300 with a temp DB, stub providers, no key, single clinic", () => {
  assert.equal(DD_PORT, 8300);
  assert.deepEqual(DD_ARGS.slice(-2), ["--port", "8300"]);
  const env = ddEnv({ PATH: "/bin", META_API_KEY: "live", OPENAI_API_KEY: "live", MULTI_CLINIC: "1", DATA_DIR: "/real", MAKEFLAGS: "-j" },
    { dbPath: "/tmp/x/app.db", apiPort: 8200, token: "t0k" });
  assert.equal(env.PATH, "/bin");
  for (const k of ["META_API_KEY", "OPENAI_API_KEY", "MODEL_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "ASSEMBLYAI_API_KEY"]) assert.equal(env[k], "", k);
  assert.equal(env.MULTI_CLINIC, "");
  assert.ok(!("DATA_DIR" in env) && !("MAKEFLAGS" in env));
  assert.equal(env.DB_PATH, "/tmp/x/app.db");
  assert.deepEqual([env.ALLOW_STUB_PROVIDERS, env.STT_ENGINE, env.STT_CHAIN, env.LLM_PROVIDER], ["1", "stub", "stub", "stub"]);
  assert.equal(ddEnv({ STT_ENGINE: "muse" }, { dbPath: "/d", apiPort: 8200, token: "" }).STT_ENGINE, "stub");
  assert.equal(env.COUNT_GUARD_URL, "http://127.0.0.1:8200");
  assert.equal(env.CG_SYNC_TOKEN, "t0k");
  const form = JSON.parse(env.STUB_LLM_JSON);
  assert.equal(form.patientName, "M. Fernandes (synthetic)");
  assert.equal(form.ageSex, "52 F");
  assert.ok(form.rx.length > 0 && form.rx.every((row) => row.status === "verified"));
  assert.deepEqual(form, STUB_FORM);
});

test("assertDdOffline stops unless DD reports the stub model and no key", () => {
  const ok = { llm_provider: "stub", stt_engine_requested: "stub", stt_engine_active: "stub", meta_configured: false, openai_configured: false };
  assert.doesNotThrow(() => assertDdOffline(ok));
  for (const bad of [null, {}, { ...ok, llm_provider: "openai" }, { ...ok, meta_configured: true }, { ...ok, stt_engine_requested: "muse" }, { ...ok, stt_engine_active: "muse-api" }]) {
    assert.throws(() => assertDdOffline(bad), /not on its stub providers/);
  }
});

test("the owner's ports are refused", () => {
  assert.deepEqual(OWNER_PORTS, [8000, 8100, 5173]);
  for (const p of [8000, 8100, 5173]) assert.throws(() => refuseOwnerPorts([8200, p]), new RegExp(`Port ${p} belongs`));
  assert.doesNotThrow(() => refuseOwnerPorts([8200, 5273, 8300]));
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
  let pid = 4241;
  const deps = {
    spawn: () => ({ pid: ++pid, on() {} }),
    free: async () => true,
    json: async () => null, // the API never answers: start-up would poll for 60 s
    kill: (target, sig) => {
      if (sig === 0) { if (!up) throw new Error("gone"); return; }
      sent.push([target, sig]);
      if (sent.length === 2) up = false;
    },
  };
  let stopFn = null;
  const dir = mkdtempSync(join(tmpdir(), "cg-test-"));
  const started = startServers({ dataDir: dir, logPath: join(dir, "log"), onSpawn: (stop) => { stopFn = stop; }, deps })
    .then(() => "started", (err) => err.message);
  while (!stopFn) await new Promise((r) => setTimeout(r, 10));
  await stopFn(); // what the SIGINT handler does
  assert.equal(await started, "Stopped while starting.");
  assert.deepEqual(sent, [[-4242, "SIGTERM"], [-4243, "SIGTERM"]]); // make dev, then Doctor Dictation
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
  await assert.rejects(startServers({ dataDir: dir, logPath: join(dir, "log"), deps }), /Could not start (make|Doctor Dictation): spawn make ENOENT/);
});
