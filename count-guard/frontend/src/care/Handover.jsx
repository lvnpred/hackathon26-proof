import { useState } from "react";
import AiMoment from "./AiMoment.jsx";
import Provenance from "./Provenance.jsx";
import { madeByModel } from "./provenance.js";
import Source from "./Source.jsx";
import { isPrepared } from "./source.js";
import { momentFor } from "./moments.js";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, outcomeOf, own } from "./stepOutcome.js";
import { ExpandButton } from "./ModelExpand.jsx";
import Opens from "./Opens.jsx";

// R21: the day and night nurses of the demo ward.
const FROM = "Nurse Meena (synthetic)";
const TO = "Nurse Kavya (synthetic)";

// The shift handover on the care chart: draft it, read it as one AI moment, then the next nurse accepts it.
// Outside an admitted state the card stays, its buttons disabled, and says when it opens (clarity §4.4).
export default function Handover({ view, busy: working, act, reason = "" }) {
  const busy = working || Boolean(reason);
  const [from, setFrom] = useState(FROM);
  const [to, setTo] = useState(TO);
  const [useModel, setUseModel] = useState(false); // the model takes 30-50 s, so it is opt-in
  const handover = view.handover;
  const moment = momentFor(view, handover?.id);
  const taker = to.trim();
  // The draft's evidence says whether Spark worded it, the template stood in, or no model was asked.
  const step = useModelStep({ capability: "handover" });
  const draft = () => step.run((o) => act("/handover", { from_nurse: from.trim(), to_nurse: taker, use_model: useModel }, undefined, own(o)),
    { outcome: (v) => outcomeOf(v?.handover) || UNKNOWN, record: (v) => (v?.handover ? { ...v.handover, eventId: v.handover.id } : null) });
  return (
    <section className="card" aria-label="Shift handover" aria-busy={busyOf(step.step)}>
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
        <button type="button" disabled={busy || !from.trim() || !taker} onClick={draft}>
          Draft handover
        </button>
      </div>
      <Opens reason={reason} />
      <ModelStep busy={busy} step={step.step} onRetry={step.retry} expand={{ view, title: "Shift handover" }} />
      {moment && <AiMoment moment={moment} role="nurse" episodeId={view.episode?.id} />}
      {handover && (
        <div className="stack" aria-label="Handover text">
          <Provenance item={{ id: handover.id, at_ms: moment?.at_ms, ai: handover.wording === "llm" || madeByModel(handover) }} events={view.acts}>
          <p className="small muted">{handover.from} to {handover.to} · {handover.since} to {handover.until}</p>
          {handover.text && (
            <>
              <p style={{ whiteSpace: "pre-line" }}>{handover.text}</p>
              <p className="small"><Source words="Worded by AI" prepared={isPrepared(handover)} /></p>
            </>
          )}
          <ol className="small">{(handover.lines || []).map((line, i) => <li key={i}>{line.text}</li>)}</ol>
          </Provenance>
          <p className="small"><ExpandButton record={{ eventId: handover.id }} view={view} title="Shift handover" /></p>
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
