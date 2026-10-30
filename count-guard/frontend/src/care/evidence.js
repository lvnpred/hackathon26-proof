import { hhmm } from "./clock.js";
import { displayName } from "./names.js";

// Pure helpers for the evidence viewer. The "Why" text is built from numbers here, never from model text.
export const MODEL_NAME = { voice: "Muse Voice", spark: "Muse Spark 1.3", sam: "SAM 3.1", "spark-open": "Muse Spark Open" };

// Mid-tone colours that read on both light and dark surfaces.
export const PALETTE = ["#e6194b", "#3cb44b", "#f58231", "#4363d8", "#911eb4", "#0e9aa7", "#c9a100", "#d6409f"];

export function colourFor(concept) {
  let h = 5381;
  for (const ch of String(concept)) h = (Math.imul(h, 33) ^ ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

const LIVE = ["muse-voice-transcribe", "muse-spark-1.3", "sam-3.1"];
const FAILED = ["prepared (live call failed)", "failed", "unreadable", "rules (model reply not usable)"];

// A handmade fixture shows Sample in place of the mode (R6).
export function modeWord(source, handmade) {
  if (handmade) return "Sample";
  if (LIVE.includes(source)) return "live";
  if (source === "prepared") return "prepared";
  return FAILED.includes(source) ? "failed" : "";
}

export function chipText(calls, handmade) {
  const list = calls || [];
  const c = list.find((x) => x.model === "sam") || list[0];
  return c ? `${MODEL_NAME[c.model]} · ${modeWord(c.source, handmade)}` : "";
}

const sameFrame = (f, at) => (f.t === null || f.t === undefined ? f.index === at : f.t === at);

export function boxesAt(frames, at, showIgnored) {
  const frame = (frames || []).find((f) => sameFrame(f, at));
  return (frame?.objects || []).filter((o) => showIgnored || o.kept);
}

export function countSeries(frames, concept) {
  return (frames || []).map((f) => ({
    t: f.t ?? f.index,
    n: new Set(f.objects.filter((o) => o.kept && o.label === concept).map((o) => o.id)).size,
  }));
}

export const boxLabel = (o) => (o.score == null ? `${o.label} ${o.id}` : `${o.label} ${o.id} ${o.score.toFixed(2)}`);

export function seenCell(row) {
  if (row.seen === null || row.seen === undefined) return "not checked";
  return row.seen < row.planned ? `${row.seen} (missing)` : String(row.seen);
}

export const plural = (concept, n) => (n === 1 || concept.endsWith("s") ? concept : `${concept}s`);

const objectsOf = (frames) => (frames || []).flatMap((f) => f.objects || []);
const known = (v) => v !== null && v !== undefined;

export function explain(rows, frames, minScore, media) {
  const objects = objectsOf(frames);
  const ignored = objects.filter((o) => !o.kept).length;
  const seenAny = objects.some((o) => o.kept) || (rows || []).some((r) => known(r.seen) && r.seen > 0);
  const out = [];
  if (!seenAny) {
    out.push(`Nothing found above confidence ${minScore}.`);
  } else {
    const list = rows || [];
    const short = list.find((r) => known(r.seen) && r.seen < r.planned);
    if (short) {
      out.push(`Saw ${short.seen} of ${short.planned} ${plural(short.concept, short.planned)}.`);
      if (media === "video" && known(short.at_s)) out.push(`The best frame was ${short.at_s} s.`);
    } else {
      const seen = list.reduce((s, r) => s + (r.seen || 0), 0);
      const planned = list.reduce((s, r) => s + r.planned, 0);
      out.push(`Saw every planned item: ${seen} of ${planned}.`);
    }
  }
  if (ignored === 1) out.push(`1 detection under confidence ${minScore} was ignored.`);
  else if (ignored > 1) out.push(`${ignored} detections under confidence ${minScore} were ignored.`);
  return out;
}

const MONITOR = ["SBP", "DBP", "HR"];

export function regionLabel(r) {
  if (r.label === null || r.label === undefined) return "not read";
  const monitor = MONITOR.includes(r.label);
  if (!monitor) return r.label;
  return known(r.value) ? `${r.label} ${r.value}` : `${r.label} not read`;
}

export function explainRegions(regions) {
  const list = regions || [];
  const boxed = list.filter((r) => r.bbox);
  const values = list.filter((r) => known(r.value)).length;
  const unread = boxed.filter((r) => !known(r.value)).length;
  const unboxed = list.filter((r) => !r.bbox && known(r.value)).length;
  const out = [`Read ${values} values from ${boxed.length} regions.`];
  if (unread) out.push(unread === 1 ? "1 region had no value read." : `${unread} regions had no value read.`);
  if (unboxed) out.push(unboxed === 1 ? "1 value was read with no box." : `${unboxed} values were read with no box.`);
  return out;
}

export function capturedLine(cited) {
  const when = typeof cited.when === "number" ? hhmm(cited.when) : String(cited.when || "").slice(-5);
  return `Captured to record: ${cited.type} · ${when} · ${displayName(cited.by)}`;
}

const TITLE = { tray: "Tray check", setup: "Set-up check", swabs: "Swab camera count", monitor: "Monitor photo", strip: "Strip photo", medicines: "Medicines photo" };

// With no sidecar (an old event) only the count table can be shown.
export function evidenceView(sidecar, check) {
  if (!sidecar) return { fallback: true, rows: check?.rows || [] };
  const frames = sidecar.frames || [];
  const rows = check?.rows || (sidecar.expected || []).map((e) => ({
    ...e, seen: Math.max(0, ...countSeries(frames, e.concept).map((p) => p.n)),
  }));
  const sentences = sidecar.regions ? explainRegions(sidecar.regions) : explain(rows, frames, sidecar.min_score, sidecar.media);
  return {
    fallback: false,
    title: TITLE[sidecar.kind] || "Check",
    chip: chipText(sidecar.calls, sidecar.handmade),
    images: sidecar.images || [],
    rows,
    regions: sidecar.regions || null,
    sentences,
    raw: sidecar.raw,
    cited: sidecar.cited_by || [],
  };
}
