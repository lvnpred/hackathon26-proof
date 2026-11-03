import { useEffect, useState } from "react";
import { call } from "../journey";
import PhotoInput from "./PhotoInput.jsx";
import Provenance from "./Provenance.jsx";
import { adviceByModel } from "./provenance.js";
import Source from "./Source.jsx";
import { DRAFTED_FROM_CAMERA, FROM_CAMERA, FROM_REPLAY } from "./source.js";
import { pickedUpload } from "./video";
import ModelStep from "./ModelStep.jsx";
import { ExpandButton } from "./ModelExpand.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, outcomeOf, own } from "./stepOutcome.js";

// Each camera write returns the view with `camera` (camera_api._with_camera); its source words say how SAM did.
const seenBy = (v) => outcomeOf(v?.camera?.source ? { source: v.camera.source } : null) || UNKNOWN;
const replayedBy = (v) => outcomeOf(v?.camera?.replay) || UNKNOWN;
const explainedBy = (v) => outcomeOf(v?.camera?.closed) || UNKNOWN;

// Expand records (clarity §4.2): the camera's read (SAM), the replay, and the closing explanation (its own evidence).
const samCalls = (source) => (source ? [{ model: "sam", source }] : []);
const readRecord = (extra = {}) => (v) => (v?.camera?.source ? { type: "camera.ran", source: v.camera.source, calls: samCalls(v.camera.source), advice: v.camera.advice || [],
  adviceIds: (v.camera.advice || []).map((a) => a.id), ...extra } : null); // a person answers each finding (camera.ack)
const replayRecord = (v) => {
  const r = v?.camera?.replay;
  return r ? { type: "camera.replayed", source: r.source, calls: samCalls(r.source), finding: `${r.returned} of ${r.opened} swabs seen resting in the bucket.` } : null;
};
const closedRecord = (v) => (v?.camera?.closed ? { type: "camera.closed", ...v.camera.closed } : null);

export const ADVICE_ONLY = "Advice only. The count a person saves decides.";

// The swab camera on the count panel (spec §6.4, U10): what the rules found, in plain words, with the last frame of
// a missing swab as proof. A person acknowledges each finding, or resolves it with a reason. The recorded replay is
// labelled Prepared. Closing the camera case drafts an explanation and the count sheet. Nothing here saves or blocks
// the count. SAM's reads (clip, recorded clip, replay) show one step line; the closing explanation (Spark Open) another.
export default function CameraAdvice({ episodeId, version = 0, busy, act, upload, by, acts = [] }) {
  const [camera, setCamera] = useState(null);
  const [problem, setProblem] = useState("");
  const sam = useModelStep({ capability: "camera" });
  const closer = useModelStep({ capability: "reconciler" });
  const seen = (v) => { if (v?.camera) setCamera(v.camera); return v; };
  const clip = (file) => sam.run(async (o) => seen(await upload("/camera/clip", file, { by }, undefined, own(o))), { what: "video", outcome: seenBy, record: readRecord() });
  const demoClip = () => sam.run(async (o) => seen(await upload("/camera/clip", null, { scenario: "demo", by }, undefined, own(o))), { outcome: seenBy, record: readRecord({ scenario: "demo" }) });
  const replay = () => sam.run(async (o) => seen(await act("/camera/replay", { by }, undefined, own(o))), { outcome: replayedBy, record: replayRecord });
  const close = () => closer.run(async (o) => seen(await act("/camera/close", { by }, undefined, own(o))), { outcome: explainedBy, record: closedRecord });
  useEffect(() => {
    let live = true;
    call(`/journey/episodes/${episodeId}/camera`).then((got) => live && setCamera(got)).catch(() => live && setCamera(null));
    return () => { live = false; };
  }, [episodeId, version]);

  async function pick(files) {
    const { problem: bad, upload: file } = pickedUpload(files);
    setProblem(bad);
    if (file && !Array.isArray(file)) await clip(file);
    else if (file) setProblem("Send one video to the swab camera.");
  }

  if (!camera) return (
    <section className="card" aria-label="Swab camera advice">
      <p className="label">Swab camera</p>
      <p className="small muted">{ADVICE_ONLY}</p>
      <p className="empty small">No swab camera reading yet.</p>
    </section>
  );
  const expandView = { episode: { id: episodeId }, acts };
  const advice = camera.advice || [];
  return (
    <section className="card" aria-label="Swab camera advice" aria-busy={busyOf(sam.step) || busyOf(closer.step)}>
      <p className="label">Swab camera</p>
      <p className="small muted">{ADVICE_ONLY}</p>
      {!camera.case_id ? (
        <button type="button" disabled={busy} onClick={() => act("/camera/case", { by })}>Start the swab camera</button>
      ) : (
        <div className="row">
          <PhotoInput label="Add theatre video" accept="video/*" capture={false} disabled={busy} onFiles={pick} />
          <button type="button" className="quiet" disabled={busy} onClick={demoClip}>
            Play the recorded theatre clip
          </button>
          <button type="button" className="quiet" disabled={busy} onClick={replay}>
            Replay the recorded swab count
          </button>
        </div>
      )}
      <ModelStep busy={busy} step={sam.step} onRetry={sam.retry} expand={{ view: expandView, title: "Swab camera read" }} />
      {camera.replay && (
        <p className="small">
          <Source words={FROM_REPLAY} prepared={camera.replay.source === "prepared"} />{" "}
          {camera.replay.returned} of {camera.replay.opened} swabs seen resting in the bucket.
        </p>
      )}
      {problem && <p className="note" role="alert">{problem}</p>}
      {camera.source && <p className="small"><Source words={FROM_CAMERA} prepared={camera.source === "prepared"} /> <ExpandButton record={readRecord()({ camera })} view={expandView} title="Swab camera read" /></p>}
      {camera.source && advice.length === 0 && <p className="small">The camera found nothing to check.</p>}
      {advice.map((row) => <AdviceRow key={row.id} row={row} busy={busy} act={act} by={by} acts={acts} />)}
      {camera.case_id && (
        <div className="row">
          <button type="button" disabled={busy} onClick={close}>
            {camera.closed ? "Close the camera case again" : "Close the camera case"}
          </button>
        </div>
      )}
      <ModelStep busy={busy} step={closer.step} onRetry={closer.retry} expand={{ view: expandView, title: "Camera case explanation" }} />
      {camera.closed && (
        <div className="note" role="status">
          <p className="small"><Source words={DRAFTED_FROM_CAMERA} prepared={camera.closed.source === "prepared"} /> <ExpandButton record={closedRecord({ camera })} view={expandView} title="Camera case explanation" /></p>
          <p className="small">{camera.closed.text}</p>
          <a href={camera.closed.count_sheet_url} download="count-sheet.pdf">Download the count sheet (PDF)</a>
        </div>
      )}
    </section>
  );
}

function AdviceRow({ row, busy, act, by, acts }) {
  const [reason, setReason] = useState("");
  const why = reason.trim();
  return (
    <div className="alert-card" role={row.acked || row.resolved ? undefined : "alert"}>
      <p className="small">{row.text}</p>
      {row.frame_url && <img src={row.frame_url} alt="Last frame the camera saw it in" width={240} style={{ borderRadius: 6, maxWidth: "100%", height: "auto" }} />}
      {/* The camera proposed it; Acknowledge is Seen by, or Overridden by with a reason; Resolve with reason overrides it. */}
      <p className="small"><Provenance item={{ id: row.id, ai: adviceByModel(row) }} events={acts} /></p>
      {(row.resolved || row.acked)?.reason && <p className="small muted">{(row.resolved || row.acked).reason}</p>}
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
