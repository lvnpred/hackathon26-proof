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

// Every journey POST returns the whole journey view of one episode.
export async function call(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }
  if (!response.ok) {
    const error = new Error(detailMessage(body?.detail) || response.statusText);
    error.status = response.status;
    throw error;
  }
  return body;
}

const base = (id) => `/journey/episodes/${id}`;

export function getJourney(id) {
  return call(base(id));
}

export function postJourney(id, path, body) {
  return call(`${base(id)}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

// The file is added when given; each field is added unless it is null, undefined or "".
export function uploadJourney(id, path, file, fields = {}) {
  const form = new FormData();
  if (Array.isArray(file)) file.forEach((f) => form.append("files", f));
  else if (file) form.append("file", file);
  Object.entries(fields).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") form.append(key, value);
  });
  return call(`${base(id)}${path}`, { method: "POST", body: form });
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
