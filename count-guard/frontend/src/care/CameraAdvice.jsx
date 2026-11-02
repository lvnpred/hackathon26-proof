import { useEffect, useState } from "react";
import { call } from "../journey";
import PhotoInput from "./PhotoInput.jsx";
import Source from "./Source.jsx";
import { displayName } from "./names";
import { DRAFTED_FROM_CAMERA, FROM_CAMERA, FROM_REPLAY } from "./source.js";
import { pickedUpload } from "./video";

export const ADVICE_ONLY = "Advice only. The count a person saves decides.";

// The swab camera on the count panel (spec §6.4, U10): what the rules found, in plain words, with the last frame of
// a missing swab as proof. A person acknowledges each finding, or resolves it with a reason. The recorded replay is
// labelled Prepared. Closing the camera case drafts an explanation and the count sheet. Nothing here saves or blocks
// the count.
export default function CameraAdvice({ episodeId, version = 0, busy, act, upload, by }) {
  const [camera, setCamera] = useState(null);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    let live = true;
    call(`/journey/episodes/${episodeId}/camera`).then((got) => live && setCamera(got)).catch(() => live && setCamera(null));
    return () => { live = false; };
  }, [episodeId, version]);

  async function pick(files) {
    const { problem: bad, upload: file } = pickedUpload(files);
    setProblem(bad);
    if (file && !Array.isArray(file)) await upload("/camera/clip", file, { by });
    else if (file) setProblem("Send one video to the swab camera.");
  }

  if (!camera) return null;
  const advice = camera.advice || [];
  return (
    <section className="card" aria-label="Swab camera advice">
      <p className="label">Swab camera</p>
      <p className="small muted">{ADVICE_ONLY}</p>
      {!camera.case_id ? (
        <button type="button" disabled={busy} onClick={() => act("/camera/case", { by })}>Start the swab camera</button>
      ) : (
        <div className="row">
          <PhotoInput label="Add theatre video" accept="video/*" capture={false} disabled={busy} onFiles={pick} />
          <button type="button" className="quiet" disabled={busy} onClick={() => upload("/camera/clip", null, { scenario: "demo", by })}>
            Play the recorded theatre clip
          </button>
          <button type="button" className="quiet" disabled={busy} onClick={() => act("/camera/replay", { by })}>
            Replay the recorded swab count
          </button>
        </div>
      )}
      {camera.replay && (
        <p className="small">
          <Source words={FROM_REPLAY} prepared={camera.replay.source === "prepared"} />{" "}
          {camera.replay.returned} of {camera.replay.opened} swabs seen resting in the bucket.
        </p>
      )}
      {problem && <p className="note" role="alert">{problem}</p>}
      {camera.source && <p className="small"><Source words={FROM_CAMERA} prepared={camera.source === "prepared"} /></p>}
      {camera.source && advice.length === 0 && <p className="small">The camera found nothing to check.</p>}
      {advice.map((row) => <AdviceRow key={row.id} row={row} busy={busy} act={act} by={by} />)}
      {camera.case_id && (
        <div className="row">
          <button type="button" disabled={busy} onClick={() => act("/camera/close", { by })}>
            {camera.closed ? "Close the camera case again" : "Close the camera case"}
          </button>
        </div>
      )}
      {camera.closed && (
        <div className="note" role="status">
          <p className="small"><Source words={DRAFTED_FROM_CAMERA} prepared={camera.closed.source === "prepared"} /></p>
          <p className="small">{camera.closed.text}</p>
          <a href={camera.closed.count_sheet_url} download="count-sheet.pdf">Download the count sheet (PDF)</a>
        </div>
      )}
    </section>
  );
}

function AdviceRow({ row, busy, act, by }) {
  const [reason, setReason] = useState("");
  const why = reason.trim();
  return (
    <div className="alert-card" role={row.acked || row.resolved ? undefined : "alert"}>
      <p className="small">{row.text}</p>
      {row.frame_url && <img src={row.frame_url} alt="Last frame the camera saw it in" width={240} style={{ borderRadius: 6, maxWidth: "100%", height: "auto" }} />}
      {row.resolved && (
        <p className="small muted">Resolved by {displayName(row.resolved.by)}. {row.resolved.reason}</p>
      )}
      {row.acked && (
        <p className="small muted">
          Seen by {displayName(row.acked.by)}{row.acked.reason ? `. ${row.acked.reason}` : ""}
        </p>
      )}
      {!row.resolved && (
        <div className="row">
          <label className="field" style={{ flex: "2 1 200px" }}>
            If you disagree, say why
            <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Counted by hand, all back" />
          </label>
          {!row.acked && (
            <button type="button" disabled={busy} onClick={async () => { if (await act(`/camera/advice/${row.id}/ack`, { by, reason: reason.trim() })) setReason(""); }}>
              Acknowledge
            </button>
          )}
          <button type="button" className="quiet" disabled={busy || !why} onClick={() => act(`/camera/advice/${row.id}/resolve`, { by, reason: why })}>
            Resolve with reason
          </button>
        </div>
      )}
    </div>
  );
}
