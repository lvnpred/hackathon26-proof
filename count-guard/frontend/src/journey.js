import { useEffect, useState } from "react";
import { detailMessage } from "./api";
import { loadEpisode } from "./episode";

// The care journey sits on the same morning episode. Every POST returns the whole journey view.
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

export function getAudit(id) {
  return call(`${base(id)}/audit`);
}

export function loadJourney() {
  return loadEpisode().then((morning) => getJourney(morning.episode.id));
}

// One view per screen; act() posts, swaps in the returned view, and keeps the error readable.
export function useJourney() {
  const [view, setView] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadJourney().then(setView).catch((exc) => setError(exc.message));
  }, []);

  async function act(path, body) {
    if (!view) return null;
    setError("");
    setBusy(true);
    try {
      const next = await postJourney(view.episode.id, path, body);
      setView(next);
      return next;
    } catch (exc) {
      setError(exc.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { view, setView, error, setError, busy, setBusy, act };
}

export function subtitle(view) {
  return view ? `${view.episode.label} · care journey` : "Care journey · records only, no medical advice";
}

// "amlodipine 10 mg" -> { name, strength }, the same split the strips screen uses.
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
