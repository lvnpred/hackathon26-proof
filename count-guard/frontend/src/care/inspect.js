// Pure helpers for the Inspector drawer.
import { correctionLine } from "./capture.js";
import { INSPECT_ID } from "./moments.js";
import { displayName } from "./names.js";
import { regionLabel } from "./evidence.js";
import { stripLabel } from "./brownbag.js";

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

// The form field each photo value filled (R13 of the spec). Keys are the monitor labels.
export const REGION_FIELD = {
  monitor: { SBP: "Obs · systolic", DBP: "Obs · diastolic", HR: "Obs · pulse" },
  strip: "Dose · medicine",
  medicines: "Medicines from home",
};

// "SBP 88 → Obs · systolic"; an unread region names no field. `rows` lets a medicines region use its strip label.
export function regionFieldLine(region, reader, rows) {
  const known = region.value !== null && region.value !== undefined;
  if (reader === "monitor") {
    const field = REGION_FIELD.monitor[region.label];
    return known && field ? `${regionLabel(region)} \u2192 ${field}` : regionLabel(region);
  }
  if (region.label === null || region.label === undefined) return "not read";
  const field = REGION_FIELD[reader];
  const left = reader === "medicines" && rows ? stripLabel(region, rows) : regionLabel(region);
  return field ? `${left} \u2192 ${field}` : left;
}

// The episode a drawer shows: a patient only ever sees their own; staff follow the URL, then the chart route.
export const inspectEpisode = ({ lens, param, chartId, own }) => (lens === "patient" ? own || null : param || chartId || own || null);

// A ?focus= value is a region index when it is all digits.
export const focusRegion = (focus) => {
  if (focus && typeof focus === "object") return focus.region ?? null;
  return /^\d+$/.test(String(focus ?? "")) ? Number(focus) : null;
};
