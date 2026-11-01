import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { call } from "../journey";
import { stripLabel } from "./brownbag.js";
import { boxesAt, capturedLine, chipText, thumbLabel, colourFor, correctionLine, countSeries, evidenceView, ignoredFrameNames, itemName, regionLabel, sawCount, sawRows, seenCell, startImage } from "./evidence.js";
import { EvidenceExpand } from "./EvidenceExpand.jsx";
import { Stage } from "./EvidenceStage.jsx";

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

// The inline viewer (R32): the picture with small id tags, "What the AI saw" beside it (tap an item to light up
// its boxes), a scrubber, a plain explanation and the raw output. Expand opens the full-screen view with readable
// labels and every box listed. linkLines false is the patient lens: no event codes, no raw output, no chart links.
export function Evidence({ episodeId, evidenceId, check, sample, linkLines = true, version = 0, model, rows }) {
  const fetched = useEvidence(episodeId, evidenceId, Boolean(sample), version);
  const data = sample || fetched.data;
  const [picked, setPicked] = useState(null);
  const [focus, setFocus] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const closeExpanded = useCallback(() => setExpanded(false), []);
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
  const boxes = image ? boxesAt(frames, image.t ?? image.index, false) : [];
  const saw = view.regions ? [] : sawRows(view.rows);
  const regionLines = view.regions && view.regions.map((r) => (rows ? stripLabel(r, rows) : regionLabel(r)));
  const ignoredNames = ignoredFrameNames(frames, view.images);
  const keptTimes = view.images.map((i) => i.t ?? i.index);
  const chip = model ? chipText(data.calls, data.handmade, model) : "";
  return (
    <section className="evidence" aria-label="Evidence">
      <p className="label">{view.title}{chip && ` · ${chip}`}</p>
      <div className="ev-main">
        {image && (
          <button type="button" className="ev-open" aria-label="Expand picture" onClick={() => setExpanded(true)}>
            <Stage className="ev-stage" image={image} boxes={boxes} regions={view.regions} rows={rows} focus={focus} />
          </button>
        )}
        <div className="ev-saw" aria-label="What the AI saw">
          <p className="label">What the AI saw</p>
          {saw.length > 0 && (
            <ul>
              {saw.map((r) => (
                <li key={r.concept}>
                  <button type="button" className="ev-saw-row" aria-pressed={focus?.concept === r.concept} onClick={() => setFocus(focus?.concept === r.concept ? null : { concept: r.concept })}>
                    <i className="ev-swatch" style={{ background: r.colour }} aria-hidden="true" />
                    <span>{r.name}</span>
                    <span className="muted">{sawCount(r)}</span>
                    {r.missing > 0 && <strong className="ev-missing">{r.missing} missing</strong>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {regionLines && <ul className="small">{regionLines.map((line, i) => <li key={i}>{line}</li>)}</ul>}
          <p className="small">Why: {view.sentences.join(" ")}</p>
          {ignoredNames.length > 0 && <p className="small muted">The AI ignored {ignoredNames.length === 1 ? "a box in frame" : "boxes in frames"} {ignoredNames.join(", ")}. Expand to see {ignoredNames.length === 1 ? "it" : "them"}.</p>}
          {image && <button type="button" className="ev-expand" onClick={() => setExpanded(true)}>⤢ Expand</button>}
        </div>
      </div>
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
      {frames && frames.length > 1 && (
        <div className="ev-sparks">
          {view.rows.map((row) => {
            const series = countSeries(frames, row.concept);
            return series.length > 0 && (
              <p className="small" key={row.concept}><span>{row.concept}</span><Sparkline series={series} kept={keptTimes} planned={row.planned} concept={row.concept} /></p>
            );
          })}
        </div>
      )}
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
      {expanded && (
        <EvidenceExpand title={view.title} images={view.images} start={shown} frames={frames} regions={view.regions} countRows={view.rows} rxRows={rows} regionLines={regionLines} onClose={closeExpanded} />
      )}
    </section>
  );
}

// A 48 px preview with the kept boxes; a click opens the full viewer below it.
export function EvidenceThumb({ episodeId, evidenceId, check, linkLines = true, version = 0, fallback = null, model }) {
  const { data } = useEvidence(episodeId, evidenceId, false, version);
  const [open, setOpen] = useState(false);
  if (!data) return fallback;
  const image = (data.images || [])[0];
  const chip = model ? chipText(data.calls, data.handmade, model) : "";
  return (
    <div>
      <button type="button" className="ev-thumb" title={chip || undefined} aria-expanded={open} aria-label={thumbLabel(chip)} onClick={() => setOpen(!open)}>
        {image && <Stage className="ev-thumb-stage" image={image} boxes={boxesAt(data.frames, image.t ?? image.index, false)} regions={null} labels={false} />}
      </button>
      {chip && <span className="small muted">{chip}</span>}
      {open && <Evidence episodeId={episodeId} evidenceId={evidenceId} check={check} linkLines={linkLines} version={version} model={model} />}
    </div>
  );
}
