import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { call } from "../journey";
import { boxLabel, boxesAt, capturedLine, chipText, colourFor, countSeries, evidenceView, regionLabel, seenCell } from "./evidence.js";

const cache = new Map();

// The sidecar of one check (C5), fetched once. `null` while loading; `error` when there is none (old events).
export function useEvidence(episodeId, evidenceId, skip = false) {
  const key = `${episodeId}/${evidenceId}`;
  const [state, setState] = useState(() => ({ key, data: cache.get(key) || null, error: null }));
  useEffect(() => {
    if (skip || !evidenceId || cache.has(key)) return undefined;
    let live = true;
    call(`/journey/episodes/${episodeId}/evidence/${evidenceId}`)
      .then((data) => { cache.set(key, data); if (live) setState({ key, data, error: null }); })
      .catch((error) => { if (live) setState({ key, data: null, error }); });
    return () => { live = false; };
  }, [key, skip, episodeId, evidenceId]);
  if (skip) return { data: null, error: null };
  const data = cache.get(key) || (state.key === key ? state.data : null);
  return { data, error: state.key === key ? state.error : null };
}

const EDGE = "#888";

// Draw boxes (normalised [x, y, w, h]) over the image's displayed size. Kept: solid colour. Ignored: dashed grey.
function draw(canvas, img, boxes, regions, labels) {
  if (!canvas || !img) return;
  const w = img.clientWidth;
  const h = img.clientHeight;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext?.("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, w, h);
  ctx.font = "12px sans-serif";
  const stroke = (bbox, colour, dashed, text) => {
    const [x, y, bw, bh] = bbox;
    ctx.strokeStyle = colour;
    ctx.fillStyle = colour;
    ctx.lineWidth = 2;
    ctx.setLineDash(dashed ? [4, 3] : []);
    ctx.strokeRect(x * w, y * h, bw * w, bh * h);
    if (labels) ctx.fillText(text, x * w, Math.max(y * h - 3, 11));
  };
  boxes.forEach((o) => stroke(o.bbox, o.kept ? colourFor(o.label) : EDGE, !o.kept, boxLabel(o)));
  (regions || []).filter((r) => r.bbox).forEach((r) => stroke(r.bbox, EDGE, false, regionLabel(r)));
}

function Stage({ image, boxes, regions, labels = true, ...rest }) {
  const img = useRef(null);
  const canvas = useRef(null);
  const paint = () => draw(canvas.current, img.current, boxes, regions, labels);
  useEffect(() => {
    paint();
    window.addEventListener("resize", paint);
    return () => window.removeEventListener("resize", paint);
  });
  return (
    <div {...rest}>
      <img ref={img} src={image?.url} alt="Evidence frame" onLoad={paint} />
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
            <td>{(row.names || [row.concept]).join(", ")}</td>
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
export function Evidence({ episodeId, evidenceId, check, sample, linkLines = true }) {
  const fetched = useEvidence(episodeId, evidenceId, Boolean(sample));
  const data = sample || fetched.data;
  const [shown, setShown] = useState(0);
  const [ignored, setIgnored] = useState(false);
  const view = evidenceView(data, check);
  if (view.fallback) return <CountTable rows={view.rows} />;
  const image = view.images[shown] || view.images[0];
  const frames = data.frames;
  const boxes = image ? boxesAt(frames, image.t ?? image.index, ignored) : [];
  const keptTimes = view.images.map((i) => i.t ?? i.index);
  return (
    <section className="evidence" aria-label="Evidence">
      <p className="label">{view.title}{view.chip && ` · ${view.chip}`}</p>
      {image && <Stage className="ev-stage" image={image} boxes={boxes} regions={view.regions} />}
      {view.images.length > 1 && (
        <div className="row">
          {view.images.map((im, i) => {
            const name = im.t ?? im.index + 1;
            return (
              <button key={im.photo_id || i} type="button" className="ev-frame" aria-label={`Frame ${name}`} aria-pressed={i === shown} onClick={() => setShown(i)}>
                <img src={im.url} alt="" width={48} height={48} />
              </button>
            );
          })}
        </div>
      )}
      {frames && <label className="small"><input type="checkbox" checked={ignored} onChange={(e) => setIgnored(e.target.checked)} /> Show ignored</label>}
      {!view.regions && <CountTable rows={view.rows} />}
      {frames && view.rows.map((row) => {
        const series = countSeries(frames, row.concept);
        return series.length > 0 && (
          <p className="small" key={row.concept}>{row.concept}{" "}<Sparkline series={series} kept={keptTimes} planned={row.planned} concept={row.concept} /></p>
        );
      })}
      {view.regions && (
        <ul className="small">{view.regions.map((r, i) => <li key={i}>{regionLabel(r)}</li>)}</ul>
      )}
      <p className="small">Why: {view.sentences.join(" ")}</p>
      <details><summary>Raw output</summary><pre>{JSON.stringify(view.raw, null, 2)}</pre></details>
      {view.cited.map((c) => {
        const line = capturedLine(c);
        return (
          <p className="small muted" key={c.event_id}>
            {linkLines ? <Link to={`/chart/${episodeId}?line=${c.event_id}`}>{line}</Link> : line}
          </p>
        );
      })}
    </section>
  );
}

// A 48 px preview with the kept boxes; a click opens the full viewer below it.
export function EvidenceThumb({ episodeId, evidenceId, check, linkLines = true }) {
  const { data } = useEvidence(episodeId, evidenceId);
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const image = (data.images || [])[0];
  const chip = chipText(data.calls, data.handmade);
  return (
    <div>
      <button type="button" className="ev-thumb" title={chip} aria-expanded={open} aria-label={`Evidence ${chip}`.trim()} onClick={() => setOpen(!open)}>
        {image && <Stage className="ev-thumb-stage" image={image} boxes={boxesAt(data.frames, image.t ?? image.index, false)} regions={null} labels={false} />}
      </button>
      <span className="small muted">{chip}</span>
      {open && <Evidence episodeId={episodeId} evidenceId={evidenceId} check={check} linkLines={linkLines} />}
    </div>
  );
}
