// Pure helpers for the Inspector drawer.
import { correctionLine } from "./capture.js";
import { INSPECT_ID } from "./moments.js";
import { displayName } from "./names.js";

export const TABS = [["input", "Input"], ["found", "What the AI found"], ["record", "Record"], ["model", "Model"]];

export const tabsFor = (lens) => (lens === "patient" ? ["input", "found"] : TABS.map(([key]) => key));

// The ?inspect= parameter is untrusted: only a plain id passes.
export function readInspect(params) {
  const momentId = params.get("inspect");
  if (!momentId || !INSPECT_ID.test(momentId)) return null;
  const focus = params.get("focus");
  const episode = params.get("episode");
  return {
    momentId,
    episodeId: episode && INSPECT_ID.test(episode) ? episode : null,
    focus: focus && INSPECT_ID.test(focus) ? focus : null,
  };
}

export const modelRows = (calls, handmade) => (calls || []).map((c) => ({
  name: c.model,
  id: c.model_id,
  mode: handmade ? "Sample" : c.source,
  ms: c.ms == null ? "—" : `${c.ms} ms`,
}));

export const recordLine = (w, lens) => {
  const hhmm = String(w.when || "").slice(-5);
  return lens === "patient" ? `${hhmm} · ${w.plain}` : `${w.type} · ${hhmm} · ${displayName(w.by)} · ${w.plain}`;
};

export { correctionLine };

export const stepFrame = (i, delta, n) => Math.max(0, Math.min(n - 1, i + delta));

// A patient never resolves a staff-only moment, whatever the URL says.
export function resolveMoment(moments, id, lens) {
  const found = (moments || []).find((m) => m.id === id || m.photo_id === id || m.evidence_id === id
    || (m.written || []).some((w) => w.event_id === id));
  if (!found) return null;
  if (lens === "patient" && found.patient_finding == null) return null;
  return found;
}
