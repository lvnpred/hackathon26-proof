import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TITLES, health, track, uploadFile, uploadScenario } from "../api";
import { Models, Shell } from "../App";

// A null time is not the start of the clip: R1 and R2 come from the spoken
// count and have no camera time.
function clock(ms) {
  if (ms == null) return "No camera time (spoken count)";
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)} min ${total % 60} sec`;
}

function UploadField({ busy, onFile }) {
  return (
    <label className="field">
      Upload a clip (.mp4) or a scenario file (.json)
      <input
        type="file"
        accept=".mp4,.json,video/mp4,application/json"
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
    </label>
  );
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
  const scripted = snapshot?.perception === "scripted";

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
      <Shell subtitle="Camera count · no playback yet">
        <header className="page-head">
          <p className="label">Camera count</p>
          <h1>This session has no playback yet</h1>
          <p>Upload a recorded clip, or run the scripted demo on this case.</p>
        </header>
        {error && <p className="error" role="alert">{error}</p>}
        <section className="card">
          <div className="row">
            <button className="primary" disabled={busy} onClick={() => load(() => uploadScenario(caseId, "demo"))}>
              Run the scripted demo on this case
            </button>
          </div>
          <p className="muted small">Scripted perception. SAM 3.1 is not called. The demo replaces the drawn zones with its own zones.</p>
          <UploadField busy={busy} onFile={(file) => load(() => uploadFile(caseId, file))} />
          <Link to="/count">Back to the camera count</Link>
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
    <Shell
      subtitle={scripted ? "Camera count · scripted perception, SAM 3.1 not called" : `Camera count · ${snapshot.perception}`}
      status={alerts.length ? { tone: "record", label: `${alerts.length} open` } : { tone: "info", label: scripted ? "Scripted demo" : "Playback" }}
    >
      <div className="row between">
        <div className="row">
          <button className="primary" onClick={() => { setPlayhead(0); setPlaying(true); }} disabled={playing}>
            {playing ? "Playing" : "Play case"}
          </button>
          <button onClick={() => { setPlaying(false); setPlayhead(maxTs); }}>Jump to closing count</button>
          <span className="num small muted" style={{ fontWeight: 700 }}>{clock(playhead)}</span>
        </div>
        <Models health={status} />
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      <div className="split">
        <section className="main">
          {frame ? (
            <div className="stage">
              <img src={frame.url} alt="Tray frame with track boxes" />
            </div>
          ) : (
            <div className="stage-empty">
              <svg aria-hidden="true" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="muted">
                <path d="m22 8-6 4 6 4V8Z" />
                <rect x="2" y="6" width="14" height="12" rx="2" />
              </svg>
              <h2>{scripted ? "No camera frame at this moment" : "No frame at this moment"}</h2>
              <p className="muted small" style={{ maxWidth: "44ch" }}>
                {scripted
                  ? "The scripted demo replays the count without pictures. The ledger and alerts still follow the playhead."
                  : "Play the case to step through the recorded frames."}
              </p>
            </div>
          )}
          <div className="card">
            <p className="label">What was said</p>
            {lines.length === 0 && <p className="empty">Waiting for the first spoken line.</p>}
            <div className="timeline">
              {lines.map((line) => (
                <div key={line.id}>
                  <span className="when">{clock(line.t0_ms)}</span>
                  <span className="what">“{line.text}”</span>
                  {/count|adding|added/i.test(line.text) && <span className="tag sun">Count</span>}
                </div>
              ))}
            </div>
          </div>
        </section>

        <aside className="side" style={{ flexBasis: 400 }}>
          <div className="card">
            <p className="label">Ledger</p>
            <div className="table-box">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Item</th><th scope="col">Opened</th><th scope="col">Tray</th><th scope="col">Field</th><th scope="col">Bucket</th><th scope="col">Not back</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.map((row) => (
                    <tr key={row.item_type}>
                      <th scope="row" style={{ fontSize: 15, color: "var(--ink)", whiteSpace: "nowrap" }}>{row.item_type}</th>
                      <td>{row.opened}</td>
                      <td>{row.tray}</td>
                      <td>{row.field}</td>
                      <td>{row.bucket}</td>
                      <td className={row.unaccounted > 0 ? "miss" : ""}>{row.unaccounted}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="row between">
              <p className="label">Alerts</p>
              {alerts.length === 0 && <span className="pill ready">None open</span>}
            </div>
            {alerts.length === 0 && <p className="muted small">An alert names the rule, the item and where it was last seen. Open one to see the evidence.</p>}
            {alerts.map((row) => (
              <button
                key={row.id}
                className={`alert-row${selected?.id === row.id ? " picked" : ""}`}
                onClick={() => openAlert(row)}
                aria-expanded={selected?.id === row.id}
              >
                <span>
                  <b>{TITLES[row.kind] || row.kind}</b> · {row.item_type}
                  <small className="muted" style={{ display: "block" }}>{row.detail}</small>
                </span>
                <span className="tag record">{row.rule_id}</span>
              </button>
            ))}
            <Link className="button primary" to={`/case/${caseId}/close`}>Close and report</Link>
          </div>
        </aside>
      </div>

      {selected && (
        <section className="card">
          <div className="row between">
            <h2>Evidence · {TITLES[selected.kind] || selected.kind}</h2>
            <button className="quiet" onClick={() => setSelected(null)}>Hide evidence</button>
          </div>
          <p>{selected.detail}</p>
          <p className="muted small">
            Rule {selected.rule_id}.{" "}
            {selected.last_media_ts_ms != null
              ? `Last seen ${clock(selected.last_media_ts_ms)} in ${selected.last_zone || "the recorded zone"}.`
              : `${clock(null)}.`}
          </p>
          <div className="split">
            <div className="main">
              {evidenceFrame ? (
                <div className="stage"><img src={`/frames/${evidenceFrame}`} alt="Last frame for this alert" /></div>
              ) : (
                <p className="empty small">No frame for this alert.</p>
              )}
            </div>
            <div className="side">
              {path && (
                <div className="timeline">
                  {path.path.map((point, index) => (
                    <div key={`${point.media_ts_ms}-${index}`}>
                      <span className="when">{clock(point.media_ts_ms)}</span>
                      <span className="what">{point.event_type.replaceAll("_", " ")} · {point.zone}</span>
                    </div>
                  ))}
                </div>
              )}
              <p className="label">Said near this alert</p>
              {evidenceLines.map((line) => (
                <p key={line.id} className="small"><span className="muted num">{clock(line.t0_ms)}</span> “{line.text}”</p>
              ))}
              {evidenceLines.length === 0 && <p className="empty small">No spoken line near this alert.</p>}
              <p className="muted small">Evidence ids: {(selected.evidence || []).join(", ") || "none"}</p>
            </div>
          </div>
        </section>
      )}
    </Shell>
  );
}
