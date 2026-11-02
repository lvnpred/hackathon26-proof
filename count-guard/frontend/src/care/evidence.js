import { hhmm } from "./clock.js";
import { correctionLine } from "./capture.js";
import { displayName } from "./names.js";
import { TONE_COLOUR, stripLabel, stripMatch, stripTone } from "./brownbag.js";

export { correctionLine };

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
const FAILED = ["prepared (live call failed)", "failed", "unreadable", "rules (model reply not usable)", "unavailable"];

// A handmade fixture shows Sample in place of the mode (R6).
export function modeWord(source, handmade) {
  if (handmade) return "Sample";
  if (LIVE.includes(source)) return "live";
  if (source === "prepared") return "prepared";
  return FAILED.includes(source) ? "failed" : "";
}

// `model` names the card the chip sits under (T7-1); without it the chip names SAM, else the first call.
// `paired` (a photo read with regions) names both models when no card is asked for: SAM boxes, Spark reads.
// The accessible name of an evidence thumbnail: a model name only when a card asked for one.
export const thumbLabel = (chip) => (chip ? `Evidence ${chip}` : "Evidence photo");

export function chipText(calls, handmade, model, paired = false) {
  const list = calls || [];
  const c = (model && list.find((x) => x.model === model)) || list.find((x) => x.model === "sam") || list[0];
  if (!c) return "";
  const both = paired && !model && c.model === "sam" && list.some((x) => x.model === "spark");
  return `${both ? "SAM 3.1 + Spark 1.3" : MODEL_NAME[c.model]} · ${modeWord(c.source, handmade)}`;
}

const sameFrame = (f, at) => (f.t === null || f.t === undefined ? f.index === at : f.t === at);

export function boxesAt(frames, at, showIgnored) {
  const frame = (frames || []).find((f) => sameFrame(f, at));
  return (frame?.objects || []).filter((o) => showIgnored || o.kept);
}

export function countSeries(frames, concept) {
  return (frames || []).map((f) => ({
    t: f.t ?? f.index,
    n: new Set((f.objects || []).filter((o) => o.kept && o.label === concept).map((o) => o.id)).size,
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
  const ignored = new Set(objects.filter((o) => !o.kept).map((o) => `${o.label}\u0000${o.id}`)).size;
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
  return `Saved to the record: ${[when, cited.by ? displayName(cited.by) : ""].filter(Boolean).join(" · ")}`;
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
    chip: chipText(sidecar.calls, sidecar.handmade, undefined, Boolean(sidecar.regions)),
    images: sidecar.images || [],
    rows,
    regions: sidecar.regions || null,
    sentences,
    raw: sidecar.raw,
    cited: sidecar.cited_by || [],
  };
}

// The row the viewer opens on: the first short row with a best frame, else the first row with one (spec 2.2).
export function startImage(images, rows) {
  const list = rows || [];
  const row = list.find((r) => known(r.seen) && r.seen < r.planned && known(r.at_s)) || list.find((r) => known(r.at_s));
  if (!row) return 0;
  let best = 0;
  (images || []).forEach((im, i) => {
    if (known(im.t) && (!known((images[best] || {}).t) || Math.abs(im.t - row.at_s) < Math.abs(images[best].t - row.at_s))) best = i;
  });
  return best;
}

// One vocabulary: the tray item name, with the model's concept beside it when they differ.
export function itemName(row) {
  const names = (row.names || []).join(", ");
  if (!names) return row.concept;
  return names.toLowerCase() === String(row.concept).toLowerCase() ? names : `${names} (${row.concept})`;
}

// Move each label rect down until it no longer overlaps an earlier one. Rects are {x, y, w, h}.
export function nudgeLabels(rects) {
  const placed = [];
  for (const r of rects) {
    let y = r.y;
    for (let again = true, guard = 0; again && guard < 50; guard += 1) {
      again = false;
      for (const q of placed) {
        if (r.x < q.x + q.w && q.x < r.x + r.w && y < q.y + q.h && q.y < y + r.h) { y = q.y + q.h; again = true; }
      }
    }
    placed.push({ ...r, y });
  }
  return placed;
}

const EDGE = "#888";

// Everything the stage draws, as plain items: kept boxes solid in the concept colour, ignored ones dashed grey,
// and photo regions in the strip tone (with `rows`) or grey.
export function drawItems(boxes, regions, rows) {
  return [
    ...(boxes || []).map((o) => ({ bbox: o.bbox, colour: o.kept ? colourFor(o.label) : EDGE, dashed: !o.kept, ignored: !o.kept, box: o, text: boxLabel(o) })),
    ...(regions || []).map((r, i) => ({ r, i })).filter(({ r }) => r.bbox).map(({ r, i }) => (rows
      ? { bbox: r.bbox, colour: TONE_COLOUR[stripTone(stripMatch(rows[r.row]))], dashed: false, text: stripLabel(r, rows), region: i }
      : { bbox: r.bbox, colour: EDGE, dashed: false, text: regionLabel(r), region: i })),
  ];
}

// A crowded frame: any full pill wider than 1.5x its box. Each entry is {pill, box} in px.
export const isDense = (sizes) => sizes.some((s) => s.pill > 1.5 * s.box);

// "full" is the concept id score pill, "tag" the small id in the box corner. The inline picture always uses tags
// (the list beside it names the items); the expanded view gives full pills unless they would crowd, and always
// to the box picked in its panel and to ignored boxes.
export function labelKind(o, { expanded, dense, focus }) {
  if (!expanded) return "tag";
  if (focus && focus.id != null && isFocus(o, focus)) return "full";
  return !o.kept || !dense ? "full" : "tag";
}

// A photo region stays bright when no region is picked (or the pick is not a region) or it is the picked one.
export const isFocusRegion = (i, focus) => !focus || focus.region == null || focus.region === i;

// A box stays bright when nothing is picked, when its item is picked, or when it is the picked box.
export const isFocus = (o, focus) => !focus || (o.label === focus.concept && (focus.id == null || o.id === focus.id));

// The "What the AI saw" rows: items that came up short first, each with its colour and the number missing.
export function sawRows(rows) {
  const list = (rows || []).map((r) => ({
    concept: r.concept, name: itemName(r), colour: colourFor(r.concept), seen: r.seen, planned: r.planned,
    missing: known(r.seen) && r.seen < r.planned ? r.planned - r.seen : 0,
  }));
  return [...list.filter((r) => r.missing), ...list.filter((r) => !r.missing)];
}

export const sawCount = (r) => (known(r.seen) ? `${r.seen} of ${r.planned}` : "not checked");

// The expanded panel: kept boxes grouped by item, and the ignored ones apart.
export function boxGroups(boxes) {
  const kept = (boxes || []).filter((o) => o.kept);
  const concepts = [...new Set(kept.map((o) => o.label))].sort();
  return {
    groups: concepts.map((concept) => ({ concept, colour: colourFor(concept), boxes: kept.filter((o) => o.label === concept) })),
    ignored: (boxes || []).filter((o) => !o.kept),
  };
}

export const hasIgnored = (frames) => objectsOf(frames).some((o) => !o.kept);

// The scrubber names (as the frame buttons show them) of the images whose frame holds an ignored box.
export function ignoredFrameNames(frames, images) {
  return (images || [])
    .filter((im) => (boxesAt(frames, im.t ?? im.index, true)).some((o) => !o.kept))
    .map((im) => im.t ?? im.index + 1);
}
