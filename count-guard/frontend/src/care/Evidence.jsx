import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { call } from "../journey";
import { TONE_COLOUR, stripLabel, stripMatch, stripTone } from "./brownbag.js";
import { boxLabel, boxesAt, capturedLine, chipText, colourFor, correctionLine, countSeries, evidenceView, itemName, nudgeLabels, regionLabel, seenCell, startImage } from "./evidence.js";

const cache = new Map();

// The sidecar of one check (C5). Shows the cached copy at once and refetches when `version` (the number of
// timeline lines) changes, so a later "Captured to record" line appears. `error` is set for old events.
export function useEvidence(episodeId, evidenceId, skip = false, version = 0) {
  const key = `${episodeId}/${evidenceId}`;
  const [state, setState] = useState({ key, data: null, error: null });
  useEffect(() => {
    if (skip || !evidenceId || cache.get(key)?.version === version) return undefined;
    let live = true;
    call(`/journey/episodes/${episodeId}/evidence/${evidenceId}`)
      .then((data) => { cache.set(key, { data, version }); if (live) setState({ key, data, error: null }); })
      .catch((error) => { if (live) setState({ key, data: null, error }); });
    return () => { live = false; };
  }, [key, skip, episodeId, evidenceId, version]);
  if (skip) return { data: null, error: null };
  const data = cache.get(key)?.data || (state.key === key ? state.data : null);
  return { data, error: state.key === key && !data ? state.error : null };
}

const EDGE = "#888";

// Draw boxes (normalised [x, y, w, h]) over the image's displayed size. Kept: solid colour. Ignored: dashed grey.
// A white outer stroke keeps a box visible on any picture; each label sits on a filled pill, nudged clear of the last.
function draw(canvas, img, boxes, regions, labels, rows) {
  if (!canvas || !img) return;
  const w = img.clientWidth;
  const h = img.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext?.("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const scale = Math.min(1, w / 640);
  const FONT = Math.max(10, Math.round(12 * scale));
  ctx.font = `${FONT}px sans-serif`;
  const items = [
    ...boxes.map((o) => ({ bbox: o.bbox, colour: o.kept ? colourFor(o.label) : EDGE, dashed: !o.kept, text: boxLabel(o) })),
    ...(regions || []).filter((r) => r.bbox).map((r) => (rows
      ? { bbox: r.bbox, colour: TONE_COLOUR[stripTone(stripMatch(rows[r.row]))], dashed: false, text: stripLabel(r, rows) }
      : { bbox: r.bbox, colour: EDGE, dashed: false, text: regionLabel(r) })),
  ];
  for (const it of items) {
    const [x, y, bw, bh] = it.bbox;
    ctx.setLineDash([]);
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 4;
    ctx.strokeRect(x * w, y * h, bw * w, bh * h);
    ctx.strokeStyle = it.colour;
    ctx.lineWidth = 2;
    ctx.setLineDash(it.dashed ? [4, 3] : []);
    ctx.strokeRect(x * w, y * h, bw * w, bh * h);
  }
  if (!labels) return;
  const PH = FONT + 4;
  const placed = nudgeLabels(items.map((it) => ({ x: Math.min(it.bbox[0] * w, w - 20), y: Math.max(it.bbox[1] * h - PH - 2, 0), w: ctx.measureText(it.text).width + 8, h: PH })));
  // Keep every pill inside the canvas on the right and at the bottom (T7-2).
  const pills = placed.map((p) => ({ ...p, x: Math.max(0, Math.min(p.x, w - p.w)), y: Math.max(0, Math.min(p.y, h - p.h)) }));
  ctx.setLineDash([]);
  items.forEach((it, i) => {
    const p = pills[i];
    ctx.fillStyle = it.colour;
    ctx.fillRect(p.x, p.y, p.w, p.h);
    ctx.fillStyle = "#fff";
    ctx.textBaseline = "middle";
    ctx.fillText(it.text, p.x + 4, p.y + PH / 2 + 0.5);
  });
}

function Stage({ image, boxes, regions, labels = true, rows, ...rest }) {
  const img = useRef(null);
  const canvas = useRef(null);
  const paint = useRef(null);
  paint.current = () => draw(canvas.current, img.current, boxes, regions, labels, rows);
  useEffect(() => {
    const again = () => paint.current();
    window.addEventListener("resize", again);
    return () => window.removeEventListener("resize", again);
  }, []);
  useEffect(() => paint.current());
  return (
    <div {...rest}>
      <img ref={img} src={image?.url} alt="Evidence frame" onLoad={() => paint.current()} />
      <canvas ref={canvas} aria-hidden="true" />
    </div>
  );
}

function Sparkline({ series, kept, planned, concept }) {
  const W = 160;
  const H = 32;
  const xs = series.map((p) => p.t);
  const lo = Math.min(...xs);
  const span = Math.max(Math.max(...xs) - lo, 1e-9);
  const top = Math.max(planned || 0, ...series.map((p) => p.n), 1);
  const x = (t) => 4 + ((t - lo) / span) * (W - 8);
  const y = (n) => H - 4 - (n / top) * (H - 8);
  const colour = colourFor(concept);
  return (
    <svg className="ev-spark" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${concept} count over the clip`}>
      <polyline fill="none" stroke={colour} strokeWidth="2" points={series.map((p) => `${x(p.t)},${y(p.n)}`).join(" ")} />
      {series.filter((p) => kept.includes(p.t)).map((p) => <circle key={p.t} cx={x(p.t)} cy={y(p.n)} r="3" fill={colour} />)}
    </svg>
  );
}

function CountTable({ rows }) {
  if (!rows.length) return null;
  return (
    <table className="small">
      <thead><tr><th>Item</th><th>Expected</th><th>Seen</th><th>Status</th></tr></thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.concept}>
            <td>{itemName(row)}</td>
            <td>{row.planned}</td>
            <td>{seenCell(row)}</td>
            <td>{row.seen === null || row.seen === undefined ? "" : row.seen >= row.planned ? "✓" : `missing ${row.planned - row.seen}`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// The inline viewer (R32): boxes on the frame, a scrubber, counts, a plain explanation and the raw output.
// linkLines false is the patient lens: no event codes, no raw output, no links to the staff chart.
export function Evidence({ episodeId, evidenceId, check, sample, linkLines = true, version = 0, model, rows }) {
  const fetched = useEvidence(episodeId, evidenceId, Boolean(sample), version);
  const data = sample || fetched.data;
  const [picked, setPicked] = useState(null);
  const [ignored, setIgnored] = useState(false);
  const view = evidenceView(data, check);
  if (view.fallback) {
    return (
      <>
        <CountTable rows={view.rows} />
        {(check?.frames || []).length > 0 && (
          <div className="row">
            {check.frames.map((f) => <img key={f.id} src={f.url} alt={check.media === "photos" ? "Photo from the check" : "Frame from the clip"} width={96} style={{ borderRadius: 6 }} />)}
          </div>
        )}
      </>
    );
  }
  const shown = picked ?? startImage(view.images, view.rows);
  const image = view.images[shown] || view.images[0];
  const frames = data.frames;
  const boxes = image ? boxesAt(frames, image.t ?? image.index, ignored) : [];
  const keptTimes = view.images.map((i) => i.t ?? i.index);
  return (
    <section className="evidence" aria-label="Evidence">
      <p className="label">{view.title}{(model ? chipText(data.calls, data.handmade, model) : view.chip) && ` · ${model ? chipText(data.calls, data.handmade, model) : view.chip}`}</p>
      {image && <Stage className="ev-stage" image={image} boxes={boxes} regions={view.regions} rows={rows} />}
      {view.images.length > 1 && (
        <div className="row">
          {view.images.map((im, i) => {
            const name = im.t ?? im.index + 1;
            return (
              <button key={im.photo_id || i} type="button" className="ev-frame" aria-label={`Frame ${name}`} aria-pressed={i === shown} onClick={() => setPicked(i)}>
                <img src={im.url} alt="" width={48} height={48} />
              </button>
            );
          })}
        </div>
      )}
      {frames && <label className="small"><input type="checkbox" checked={ignored} onChange={(e) => setIgnored(e.target.checked)} /> Show ignored</label>}
      {!view.regions && <CountTable rows={view.rows} />}
      {frames && (
        <div className="ev-sparks">
          {view.rows.map((row) => {
            const series = countSeries(frames, row.concept);
            return series.length > 0 && (
              <p className="small" key={row.concept}><span>{row.concept}</span><Sparkline series={series} kept={keptTimes} planned={row.planned} concept={row.concept} /></p>
            );
          })}
        </div>
      )}
      {view.regions && (
        <ul className="small">{view.regions.map((r, i) => <li key={i}>{rows ? stripLabel(r, rows) : regionLabel(r)}</li>)}</ul>
      )}
      <p className="small">Why: {view.sentences.join(" ")}</p>
      {linkLines && <details><summary>Raw output</summary><pre>{JSON.stringify(view.raw, null, 2)}</pre></details>}
      {linkLines && view.cited.map((c) => {
        const line = capturedLine(c);
        return (
          <p className="small muted" key={c.event_id}>
            <Link to={`/chart/${episodeId}?line=${c.event_id}`}>{line}</Link>
            {correctionLine(c.read, c.saved, c.by) && <><br />{correctionLine(c.read, c.saved, c.by)}</>}
          </p>
        );
      })}
    </section>
  );
}

// A 48 px preview with the kept boxes; a click opens the full viewer below it.
export function EvidenceThumb({ episodeId, evidenceId, check, linkLines = true, version = 0, fallback = null, model }) {
  const { data } = useEvidence(episodeId, evidenceId, false, version);
  const [open, setOpen] = useState(false);
  if (!data) return fallback;
  const image = (data.images || [])[0];
  const chip = chipText(data.calls, data.handmade, model);
  return (
    <div>
      <button type="button" className="ev-thumb" title={chip} aria-expanded={open} aria-label={`Evidence ${chip}`.trim()} onClick={() => setOpen(!open)}>
        {image && <Stage className="ev-thumb-stage" image={image} boxes={boxesAt(data.frames, image.t ?? image.index, false)} regions={null} labels={false} />}
      </button>
      <span className="small muted">{chip}</span>
      {open && <Evidence episodeId={episodeId} evidenceId={evidenceId} check={check} linkLines={linkLines} version={version} model={model} />}
    </div>
  );
}
