import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { health, track, uploadFile, uploadScenario } from "../api";
import { Models, Shell } from "../App";

// A null time is not the start of the clip: R1 and R2 come from the spoken
// count and have no camera time.
function clock(ms) {
  if (ms == null) return "No camera time (spoken count)";
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)} min ${total % 60} sec`;
}

export default function Live() {
  const { caseId } = useParams();
  const [snapshot, setSnapshot] = useState(() => {
    const stored = sessionStorage.getItem(`cg:${caseId}`);
    return stored ? JSON.parse(stored) : null;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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

  async function load(request) {
    setBusy(true);
    setError("");
    try {
      const next = await request();
      sessionStorage.setItem(`cg:${caseId}`, JSON.stringify(next));
      setSnapshot(next);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  if (!snapshot) {
    return (
      <Shell>
        <section className="sheet">
          <h2>2. Live</h2>
          <p>This session has no playback yet. Upload a recorded clip, or run the scripted demo on this case.</p>
          <div className="row">
            <button disabled={busy} onClick={() => load(() => uploadScenario(caseId, "demo"))}>
              Run the scripted demo on this case
            </button>
            <span className="clock">Scripted perception. SAM 3.1 is not called. The demo replaces the drawn zones with its own zones.</span>
          </div>
          <label style={{ marginTop: 12 }}>
            Upload a clip (.mp4) or a scenario file (.json)
            <input
              type="file"
              accept=".mp4,.json,video/mp4,application/json"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) load(() => uploadFile(caseId, file));
              }}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <p><Link to="/count">Back to the camera count.</Link></p>
        </section>
      </Shell>
    );
  }

  const evidenceFrame = selected?.last_frame_id;
  // The spoken lines around the alert: within 10 s of the last sighting, or the
  // transcript ids the rule cited when it has no time (R1, R2).
  const evidenceIds = (selected?.evidence || [])
    .filter((ref) => ref.startsWith("transcript:"))
    .map((ref) => ref.slice("transcript:".length));
  const evidenceLines = !selected
    ? []
    : (snapshot.transcript || []).filter((line) =>
        selected.last_media_ts_ms != null
          ? Math.abs(line.t0_ms - selected.last_media_ts_ms) <= 10000
          : evidenceIds.includes(line.id),
      );

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
            Rule {selected.rule_id}.{" "}
            {selected.last_media_ts_ms != null
              ? `Last seen ${clock(selected.last_media_ts_ms)} in ${selected.last_zone || "the recorded zone"}.`
              : `${clock(null)}.`}
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
          <div className="transcript">
            {evidenceLines.map((line) => (
              <p key={line.id}>
                <span className="clock">{clock(line.t0_ms)} </span>
                {line.text}
              </p>
            ))}
            {evidenceLines.length === 0 && <p>No spoken line near this alert.</p>}
          </div>
          <p className="clock">Evidence ids: {(selected.evidence || []).join(", ") || "none"}</p>
        </section>
      )}
    </Shell>
  );
}
