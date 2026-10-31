import { useState } from "react";
import { Evidence, useEvidence } from "./Evidence.jsx";
import { Stage } from "./EvidenceStage.jsx";
import { focusRegion, regionFieldLine, stepFrame, whyRegions } from "./inspect.js";
import { checkLabel } from "./video.js";

const NO_RAW = "No raw output is kept for this result.";

// The kept images of one result, one at a time. With no sidecar, the frames the check kept.
export function VisualInput({ moment, episodeId, view }) {
  const { data } = useEvidence(episodeId, moment.evidence_id, !moment.evidence_id);
  const [at, setAt] = useState(0);
  const kept = (view?.video_checks || []).find((c) => c.id === moment.id)?.frames || [];
  const images = data?.images?.length ? data.images : kept;
  if (!images.length) return <p className="muted">No picture is kept for this result.</p>;
  const i = stepFrame(at, 0, images.length);
  return (
    <div className="inspector-input">
      <img src={images[i].url} alt="Input frame" style={{ maxWidth: "100%" }} />
      <div className="row">
        <button type="button" className="quiet" disabled={i === 0} onClick={() => setAt(stepFrame(i, -1, images.length))}>Previous</button>
        <span className="small">Frame {i + 1} of {images.length}</span>
        <button type="button" className="quiet" disabled={i === images.length - 1} onClick={() => setAt(stepFrame(i, 1, images.length))}>Next</button>
      </div>
    </div>
  );
}

// The check line, then today's viewer: What the AI saw, tap to highlight, Expand.
export function VisualFound({ moment, episodeId, view, lens = "staff" }) {
  const check = moment.refs?.check;
  const staff = lens !== "patient";
  return (
    <div className="inspector-found">
      {staff && <p className="small"><span className={`pill ${check?.match === "mismatch" ? "sun" : "info"}`}>{checkLabel(check)}</span></p>}
      <Evidence episodeId={episodeId} evidenceId={moment.evidence_id} check={check} linkLines={staff} version={view?.timeline?.length} />
    </div>
  );
}

// A photo read: the picture with its regions, and one button per region naming the form field it filled.
export function PhotoFound({ moment, episodeId, focus, setFocus }) {
  const { data } = useEvidence(episodeId, moment.evidence_id, !moment.evidence_id);
  const { reader, rows } = moment.refs || {};
  const regions = moment.refs?.regions || data?.regions || [];
  const image = data?.images?.[0];
  const picked = focusRegion(focus);
  return (
    <div className="inspector-found">
      {image && <Stage className="ev-stage" image={image} boxes={[]} regions={regions} rows={rows || null} focus={picked == null ? null : { region: picked }} />}
      <ul>
        {regions.map((r, i) => (
          <li key={i}>
            <button type="button" className="ev-saw-row" aria-pressed={picked === i} onClick={() => setFocus(picked === i ? null : i)}>
              {regionFieldLine(r, reader, rows)}
            </button>
          </li>
        ))}
      </ul>
      <p className="small">Why: {whyRegions(reader, regions).join(" ")}</p>
    </div>
  );
}

// Staff only: what the model sent back, from the sidecar.
export function RawOutput({ moment, episodeId }) {
  const { data } = useEvidence(episodeId, moment.evidence_id, !moment.evidence_id);
  if (!moment.evidence_id || data?.raw == null) return <p className="muted">{NO_RAW}</p>;
  return <pre className="inspector-raw">{JSON.stringify(data.raw, null, 2)}</pre>;
}
