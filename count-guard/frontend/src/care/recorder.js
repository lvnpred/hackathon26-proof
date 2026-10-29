// Pure helpers for the voice recorder. The browser objects are passed in, so node can test them.
const MIMES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];

export const UNAVAILABLE = "Recording is not available in this browser. Choose an audio file or type what was said.";
export const DENIED = "The microphone could not be used. Choose an audio file or type what was said.";

export function pickMime(isSupported) {
  return MIMES.find((type) => isSupported(type)) || "";
}

export function audioName(mime) {
  if (mime.includes("mp4")) return "recording.m4a";
  if (mime.includes("ogg")) return "recording.ogg";
  return "recording.webm";
}

// denied: getUserMedia rejected. The typed box and the file input keep working either way.
export function micStatus({ hasMediaDevices, hasRecorder, mime, denied = false }) {
  if (!hasMediaDevices || !hasRecorder || !mime) return { ok: false, message: UNAVAILABLE };
  if (denied) return { ok: false, message: DENIED };
  return { ok: true, message: "" };
}
