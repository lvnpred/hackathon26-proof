// Pure helpers for the Inspector drawer.
import { correctionLine } from "./capture.js";
import { INSPECT_ID } from "./moments.js";
import { displayName } from "./names.js";
import { explainRegions, plural, regionLabel } from "./evidence.js";
import { stripLabel } from "./brownbag.js";
import { sentenceText } from "./orders.js";

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

// The "Why" sentences of a photo read. A monitor counts values; strips are read by label, never by value (numbers only).
export function whyRegions(reader, regions) {
  if (reader !== "strip" && reader !== "medicines") return explainRegions(regions);
  const list = regions || [];
  const boxed = list.length;
  const read = list.filter((r) => r.label !== null && r.label !== undefined).length;
  const out = [`Read ${read} ${plural("strip", read)} from ${boxed} ${plural("region", boxed)}.`];
  if (boxed > read) out.push(boxed - read === 1 ? "1 region had no strip read." : `${boxed - read} regions had no strip read.`);
  return out;
}

// Order field names -> the label on the form (Voice tab).
export const FIELD_LABEL = {
  name: "Medicine",
  amount: "Amount",
  every_h: "Every",
  proof: "Proof",
  text: "Order",
  "limits.sbp_min": "Systolic min",
  "limits.sbp_max": "Systolic max",
};

// The text cut into [{ text, mark }]; a mark out of range or overlapping an earlier one is dropped, so the pieces always rejoin to `text`.
export function segments(text, marks) {
  const source = String(text ?? "");
  const out = [];
  let at = 0;
  const sorted = [...(marks || [])].sort((a, b) => a.start - b.start);
  for (const mark of sorted) {
    if (!(mark.start >= at && mark.end > mark.start && mark.end <= source.length)) continue;
    if (mark.start > at) out.push({ text: source.slice(at, mark.start), mark: null });
    out.push({ text: source.slice(mark.start, mark.end), mark });
    at = mark.end;
  }
  if (at < source.length) out.push({ text: source.slice(at), mark: null });
  return out;
}

const NONE = "none";
const fieldValue = (item, field) => {
  const value = field.startsWith("limits.") ? item.limits?.[field.slice(7)] : field === "proof" ? (item.proof ?? NONE) : item[field];
  return value == null || value === "" ? NONE : String(value);
};
const DIFF_FIELDS = ["text", "name", "amount", "every_h", "proof", "limits.sbp_min", "limits.sbp_max"];

// R10: compare by index. A field that differs is one entry; a row in one list only is `added` or `removed`.
export function fieldDiffs(drafted, signed) {
  const a = drafted || [];
  const b = signed || [];
  const out = [];
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    if (i >= a.length) out.push({ item: i, field: "added", drafted: null, signed: sentenceText(b[i]) });
    else if (i >= b.length) out.push({ item: i, field: "removed", drafted: sentenceText(a[i]), signed: null });
    else {
      for (const field of DIFF_FIELDS) {
        const was = fieldValue(a[i], field);
        const now = fieldValue(b[i], field);
        if (was !== now) out.push({ item: i, field, drafted: was, signed: now });
      }
    }
  }
  return out;
}

export function diffLine(d) {
  if (d.field === "added") return `Added at signing: ${d.signed}`;
  if (d.field === "removed") return `Removed at signing: ${d.drafted}`;
  return `${FIELD_LABEL[d.field]}: ${d.drafted} → ${d.signed}`;
}
