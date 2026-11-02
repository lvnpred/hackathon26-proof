import { useEffect, useState } from "react";
import { call } from "../journey";
import { cameraRows, trackLine } from "./cameraEvidence.js";

// Staff only: the frames, tracked items and notes of the camera case linked to this theatre stay.
// Renders nothing until the stay has a camera case.
export default function CameraEvidence({ episodeId }) {
  const [data, setData] = useState(null);
  const [at, setAt] = useState(0);
  const [path, setPath] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    setData(null);
    setFailed(false);
    call(`/journey/episodes/${episodeId}/camera/evidence`).then((d) => { if (live) setData(d); }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [episodeId]);
  if (failed) return <p className="error small" role="alert">The camera frames did not load.</p>;
  if (!data?.case_id) return null;
  const frame = data.frames[Math.min(at, data.frames.length - 1)];
  const open = (id) => call(`/journey/episodes/${episodeId}/camera/evidence/tracks/${id}`).then((d) => setPath({ id, points: d.path })).catch(() => setPath(null));
  return (
    <div className="inspector-camera" aria-label="Camera frames and tracks">
      <p className="label">Camera frames</p>
      {frame ? (
        <>
          <img src={frame.url} alt="Camera frame" style={{ maxWidth: "100%" }} />
          <div className="row">
            <button type="button" className="quiet" disabled={at === 0} onClick={() => setAt(at - 1)}>Previous</button>
            <span className="small">Frame {at + 1} of {data.frames.length}</span>
            <button type="button" className="quiet" disabled={at >= data.frames.length - 1} onClick={() => setAt(at + 1)}>Next</button>
          </div>
        </>
      ) : <p className="muted">No frames are kept.</p>}
      <p className="label">Tracked items</p>
      <ul className="plain">
        {data.tracks.map((t) => (
          <li key={t.track_id}><button type="button" className="quiet" onClick={() => open(t.track_id)}>{trackLine(t)}</button></li>
        ))}
      </ul>
      {path && <p className="small" role="status">{path.id}: {path.points.length} moves seen.</p>}
      <p className="label">Camera notes</p>
      <ul className="plain">{cameraRows(data.events).map((r) => <li key={r.id}>{r.text}</li>)}</ul>
    </div>
  );
}
