import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { health, track } from "../api";
import { Models, Shell } from "../App";

function clock(ms) {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  return `${Math.floor(total / 60)} min ${total % 60} sec`;
}

export default function Live() {
  const { caseId } = useParams();
  const stored = sessionStorage.getItem(`cg:${caseId}`);
  const snapshot = stored ? JSON.parse(stored) : null;
  const [status, setStatus] = useState(null);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState(null);
  const [path, setPath] = useState(null);

  useEffect(() => {
    health().then(setStatus).catch(() => setStatus(null));
  }, []);

  const keyframes = snapshot?.keyframes || [];
  const maxTs = keyframes.length ? keyframes[keyframes.length - 1].media_ts_ms : 0;
  const current = [...keyframes].reverse().find((frame) => frame.media_ts_ms <= playhead) || keyframes[0];
  const ledger = current?.ledger || snapshot?.ledger || [];
  const alerts = (current?.discrepancies || snapshot?.discrepancies || []).filter((row) => row.status === "open");
  const frame = (snapshot?.frames || []).find((item) => item.id === current?.frame_id) || null;
  const lines = (snapshot?.transcript || []).filter((line) => line.t0_ms <= playhead);

  useEffect(() => {
    if (!playing || !maxTs) return undefined;
    let frameId = 0;
    const started = performance.now();
    const from = playhead;
    const tick = (now) => {
      const next = Math.min(maxTs, from + ((now - started) / 18000) * maxTs);
      setPlayhead(next);
      if (next < maxTs) frameId = requestAnimationFrame(tick);
      else setPlaying(false);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [playing, maxTs]);

  async function openAlert(row) {
    setSelected(row);
    setPath(null);
    if (row.track_id) {
      try {
        setPath(await track(caseId, row.track_id));
      } catch {
        setPath(null);
      }
    }
  }

  if (!snapshot) {
    return (
      <Shell>
        <p>This session has no playback yet. <Link to="/count">Start from the camera count.</Link></p>
      </Shell>
    );
  }

  const evidenceFrame = selected?.last_frame_id;

  return (
    <Shell>
      <Models health={status} />
      <div className="row" style={{ marginBottom: 12 }}>
        <button onClick={() => { setPlayhead(0); setPlaying(true); }} disabled={playing}>Play case</button>
        <button className="secondary" onClick={() => { setPlaying(false); setPlayhead(maxTs); }}>Jump to closing count</button>
        <Link to={`/case/${caseId}/close`}>Close and report</Link>
        <span className="clock">{clock(playhead)} · {snapshot.perception === "scripted" ? "Scripted perception. SAM 3.1 not called." : snapshot.perception}</span>
      </div>
      <div className="layout">
        <section className="sheet">
          <h2>2. Live</h2>
          <div className="stage">
            {frame ? <img src={frame.url} alt="Tray frame with track boxes" /> : <div style={{ height: 280 }} />}
          </div>
          <div className="transcript">
            {lines.map((line) => (
              <p key={line.id}>
                <span className="clock">{clock(line.t0_ms)} </span>
                {/count|adding|added/i.test(line.text) ? <mark>{line.text}</mark> : line.text}
              </p>
            ))}
            {lines.length === 0 && <p>Waiting for the first spoken line.</p>}
          </div>
        </section>
        <section className="panel">
          <h2>Ledger</h2>
          <table>
            <thead>
              <tr>
                <th>Item</th><th>Opened</th><th>Tray</th><th>Field</th><th>Bucket</th><th>Unaccounted</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((row) => (
                <tr key={row.item_type}>
                  <td>{row.item_type}</td>
                  <td>{row.opened}</td>
                  <td>{row.tray}</td>
                  <td>{row.field}</td>
                  <td>{row.bucket}</td>
                  <td>{row.unaccounted}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2 style={{ marginTop: 16 }}>Alerts</h2>
          {alerts.length === 0 && <p>No open alerts at this moment.</p>}
          {alerts.map((row) => (
            <div className="alert" key={row.id} onClick={() => openAlert(row)} role="button" tabIndex={0}>
              <b>{row.kind}</b> · {row.item_type}
              <small>{row.detail}</small>
            </div>
          ))}
        </section>
      </div>
      {selected && (
        <section className="sheet" style={{ marginTop: 16 }}>
          <h2>3. Evidence</h2>
          <p>{selected.detail}</p>
          <p className="clock">
            Rule {selected.rule_id}. Last seen {clock(selected.last_media_ts_ms)} in {selected.last_zone || "the recorded zone"}.
          </p>
          {evidenceFrame && <img src={`/frames/${evidenceFrame}`} alt="Last frame for this alert" style={{ maxWidth: "100%" }} />}
          {path && (
            <ol>
              {path.path.map((point, index) => (
                <li key={`${point.media_ts_ms}-${index}`}>
                  {clock(point.media_ts_ms)} · {point.event_type} · {point.zone}
                </li>
              ))}
            </ol>
          )}
          <p className="clock">Evidence ids: {(selected.evidence || []).join(", ") || "none"}</p>
        </section>
      )}
    </Shell>
  );
}
