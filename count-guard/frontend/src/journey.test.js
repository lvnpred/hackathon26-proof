import test from "node:test";
import assert from "node:assert/strict";
import { postJourney, uploadJourney } from "./journey.js";

// A fake XMLHttpRequest: the test drives the upload progress and the reply.
class FakeXHR {
  static last = null;
  constructor() {
    this.upload = {};
    this.headers = {};
    this.aborted = false;
    FakeXHR.last = this;
  }
  open(method, url) { this.method = method; this.url = url; }
  setRequestHeader(k, v) { this.headers[k] = v; }
  send(body) { this.body = body; }
  abort() { this.aborted = true; this.onabort?.(); }
  progress(loaded, total) { this.upload.onprogress?.({ lengthComputable: true, loaded, total }); }
  reply(status, text) { this.status = status; this.statusText = status === 200 ? "OK" : "Bad"; this.responseText = text; this.onload?.(); }
}

test("uploadJourney sends the form by XHR and reports progress 0 to 100", async () => {
  const seen = [];
  const done = uploadJourney(7, "/photo", null, { kind: "tray", empty: "" }, { XHR: FakeXHR, onProgress: (p) => seen.push(p) });
  const xhr = FakeXHR.last;
  assert.equal(xhr.method, "POST");
  assert.equal(xhr.url, "/journey/episodes/7/photo");
  assert.equal(xhr.body.get("kind"), "tray");
  assert.equal(xhr.body.has("empty"), false);
  xhr.progress(0, 200);
  xhr.progress(84, 200);
  xhr.progress(200, 200);
  xhr.reply(200, JSON.stringify({ id: 7 }));
  assert.deepEqual(await done, { id: 7 });
  assert.deepEqual(seen, [0, 42, 100]);
});

test("uploadJourney rejects with the server's detail on 4xx", async () => {
  const done = uploadJourney(7, "/photo", null, {}, { XHR: FakeXHR });
  FakeXHR.last.reply(422, JSON.stringify({ detail: [{ loc: ["body", "file"], msg: "field required" }] }));
  await assert.rejects(done, (e) => e.status === 422 && e.message === "file: field required");
  const plain = uploadJourney(7, "/photo", null, {}, { XHR: FakeXHR });
  FakeXHR.last.reply(400, "not json");
  await assert.rejects(plain, (e) => e.status === 400 && e.message === "not json");
});

test("uploadJourney aborts on the signal and on its timeout", async () => {
  const ctl = new AbortController();
  const done = uploadJourney(7, "/photo", null, {}, { XHR: FakeXHR, signal: ctl.signal });
  const xhr = FakeXHR.last;
  ctl.abort();
  assert.equal(xhr.aborted, true);
  await assert.rejects(done, (e) => e.name === "AbortError");

  const slow = uploadJourney(7, "/photo", null, {}, { XHR: FakeXHR, timeoutMs: 60000 });
  assert.equal(FakeXHR.last.timeout, 60000);
  FakeXHR.last.ontimeout();
  await assert.rejects(slow, (e) => e.message === "no answer in 60 s");
});

test("uploadJourney keeps its old four-argument call working", async () => {
  globalThis.XMLHttpRequest = FakeXHR;
  try {
    const done = uploadJourney(3, "/voice", null, { at_ms: 5 });
    assert.equal(FakeXHR.last.body.get("at_ms"), "5");
    FakeXHR.last.reply(200, "");
    assert.equal(await done, null);
  } finally {
    delete globalThis.XMLHttpRequest;
  }
});

test("postJourney passes a signal to fetch and keeps detailMessage errors", async () => {
  const real = globalThis.fetch;
  let init;
  globalThis.fetch = async (url, options) => {
    init = options;
    return { ok: false, status: 409, statusText: "Conflict", text: async () => JSON.stringify({ detail: { message: "Not yet" } }) };
  };
  try {
    const ctl = new AbortController();
    await assert.rejects(postJourney(1, "/go", { a: 1 }, { signal: ctl.signal, timeoutMs: 5000 }), (e) => e.status === 409 && e.message === "Not yet");
    assert.ok(init.signal, "fetch gets a signal");
    assert.equal(init.body, JSON.stringify({ a: 1 }));
    await assert.rejects(postJourney(1, "/go", { a: 1 }), (e) => e.message === "Not yet");
  } finally {
    globalThis.fetch = real;
  }
});

test("postJourney fails with no answer in N s when the timeout passes", async () => {
  const real = globalThis.fetch;
  globalThis.fetch = (url, options) => new Promise((_, reject) => {
    options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  try {
    await assert.rejects(postJourney(1, "/go", {}, { timeoutMs: 20 }), (e) => e.message === "no answer in 0.02 s");
  } finally {
    globalThis.fetch = real;
  }
});
