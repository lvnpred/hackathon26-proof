// FastAPI's 422 list or a plain detail, as one readable line.
export function detailMessage(detail) {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = (item.loc || []).filter((part) => part !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  return detail?.message || detail;
}

// A reply's text -> its JSON body, or an Error carrying the readable detail and the status.
function parseReply(ok, status, statusText, text) {
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }
  if (!ok) {
    const error = new Error(detailMessage(body?.detail) || statusText);
    error.status = status;
    throw error;
  }
  return body;
}

export const noAnswer = (timeoutMs) => `no answer in ${timeoutMs / 1000} s`;

// Every journey POST returns the whole journey view of one episode.
// `signal` and `timeoutMs` are optional; a timeout fails with "no answer in N s".
export async function call(path, options, { signal, timeoutMs } = {}) {
  if (!signal && !timeoutMs) {
    const response = await fetch(path, options);
    return parseReply(response.ok, response.status, response.statusText, await response.text());
  }
  const ctl = new AbortController();
  let timedOut = false;
  const stop = () => ctl.abort();
  if (signal?.aborted) ctl.abort();
  signal?.addEventListener("abort", stop);
  const timer = timeoutMs ? setTimeout(() => { timedOut = true; ctl.abort(); }, timeoutMs) : null;
  try {
    const response = await fetch(path, { ...options, signal: ctl.signal });
    return parseReply(response.ok, response.status, response.statusText, await response.text());
  } catch (exc) {
    if (timedOut) throw new Error(noAnswer(timeoutMs));
    throw exc;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}

const base = (id) => `/journey/episodes/${id}`;

export function getJourney(id) {
  return call(base(id));
}

export function postJourney(id, path, body, opts = {}) {
  return call(
    `${base(id)}${path}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) },
    opts,
  );
}

function abortError() {
  const error = new Error("The call was stopped");
  error.name = "AbortError";
  return error;
}

// The file is added when given; each field is added unless it is null, undefined or "".
// Sent by XMLHttpRequest so the upload can report progress (0-100) through `onProgress`.
// `signal` aborts it; `timeoutMs` fails it with "no answer in N s". `XHR` lets tests pass a fake.
export function uploadJourney(id, path, file, fields = {}, { onProgress, signal, timeoutMs, XHR } = {}) {
  const form = new FormData();
  if (Array.isArray(file)) file.forEach((f) => form.append("files", f));
  else if (file) form.append("file", file);
  Object.entries(fields || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") form.append(key, value);
  });
  const Request = XHR || globalThis.XMLHttpRequest;
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const xhr = new Request();
    const stop = () => xhr.abort();
    const settle = (fn) => (value) => { signal?.removeEventListener("abort", stop); fn(value); };
    const ok = settle(resolve);
    const fail = settle(reject);
    xhr.open("POST", `${base(id)}${path}`);
    if (timeoutMs) xhr.timeout = timeoutMs;
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.upload.onload = () => onProgress(100); // the file is sent: the server is now working on it
    }
    xhr.onload = () => {
      try {
        ok(parseReply(xhr.status >= 200 && xhr.status < 300, xhr.status, xhr.statusText, xhr.responseText));
      } catch (exc) {
        fail(exc);
      }
    };
    xhr.onerror = () => fail(new Error("The upload did not reach the server"));
    xhr.ontimeout = () => fail(new Error(noAnswer(timeoutMs)));
    xhr.onabort = () => fail(abortError());
    signal?.addEventListener("abort", stop);
    xhr.send(form);
  });
}

// The ward list and the shared demo clock live on the server (spec §8).
export function getWard() {
  return call("/journey/ward");
}

export function postClock(ms) {
  return call("/journey/clock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ms }),
  });
}

export function getAudit(id) {
  return call(`${base(id)}/audit`);
}

export function parseStrips(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(.+?)\s+(\d+(?:\.\d+)?\s*(?:mg|ml|g|mcg))$/i);
      return match ? { name: match[1], strength: match[2] } : { name: line, strength: "" };
    });
}

// Blank stays null so optional numbers are left out, not sent as 0.
export function num(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// Sync asks Count Guard to pull from Doctor Dictation; the token never reaches the browser.
export function syncWard() {
  return call("/journey/sync", json({}));
}

export function newPatient({ name, ageSex, reason }) {
  return call("/journey/patients", json({ name: name.trim(), age_sex: ageSex.trim(), reason: reason.trim() }));
}
