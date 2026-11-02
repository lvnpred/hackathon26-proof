import { useState } from "react";
import AiMoment from "./AiMoment.jsx";
import Source from "./Source.jsx";
import { isPrepared } from "./source.js";
import { momentFor } from "./moments.js";

// R21: the day and night nurses of the demo ward.
const FROM = "Nurse Meena (synthetic)";
const TO = "Nurse Kavya (synthetic)";

// The shift handover on the care chart: draft it, read it as one AI moment, then the next nurse accepts it.
export default function Handover({ view, busy, act }) {
  const [from, setFrom] = useState(FROM);
  const [to, setTo] = useState(TO);
  const [useModel, setUseModel] = useState(false); // the model takes 30-50 s, so it is opt-in
  const handover = view.handover;
  const moment = momentFor(view, handover?.id);
  const taker = to.trim();
  return (
    <section className="card" aria-label="Shift handover">
      <p className="label">Shift handover</p>
      <div className="row">
        <label className="field" style={{ flex: "1 1 160px" }}>
          From
          <input value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field" style={{ flex: "1 1 160px" }}>
          To
          <input value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <label className="small">
        <input type="checkbox" checked={useModel} onChange={(e) => setUseModel(e.target.checked)} /> Let the AI word it
      </label>
      <div className="row">
        <button type="button" disabled={busy || !from.trim() || !taker} onClick={() => act("/handover", { from_nurse: from.trim(), to_nurse: taker, use_model: useModel })}>
          Draft handover
        </button>
      </div>
      {moment && <AiMoment moment={moment} role="nurse" episodeId={view.episode?.id} />}
      {handover && (
        <div className="stack" aria-label="Handover text">
          <p className="small muted">{handover.from} to {handover.to} · {handover.since} to {handover.until}</p>
          {handover.text && (
            <>
              <p style={{ whiteSpace: "pre-line" }}>{handover.text}</p>
              <p className="small"><Source words="Worded by AI" prepared={isPrepared(handover)} /></p>
            </>
          )}
          <ol className="small">{(handover.lines || []).map((line, i) => <li key={i}>{line.text}</li>)}</ol>
          {handover.accepted_by && <p className="small"><span className="pill info">Accepted</span> by {handover.accepted_by}</p>}
        </div>
      )}
      {handover && !handover.accepted_by && (
        <button type="button" disabled={busy || !taker} onClick={() => act(`/handover/${handover.id}/accept`, { by: taker })}>
          Accept as {taker}
        </button>
      )}
    </section>
  );
}
