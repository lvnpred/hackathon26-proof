import { useState } from "react";
import { Pill } from "../App";

const DAY = "Nurse Meena (synthetic)";
const NIGHT = "Nurse Kavya (synthetic)";

// The shift handover: lines from the timeline, and Muse Spark Open's paragraph only if it passed the check.
export default function NurseHandover({ handover, busy, act }) {
  const [from, setFrom] = useState(DAY);
  const [to, setTo] = useState(NIGHT);
  const [useModel, setUseModel] = useState(true);
  const [taker, setTaker] = useState(NIGHT);

  return (
    <section className="card">
      <div className="row between">
        <p className="label">Shift handover</p>
        {handover && (
          <Pill tone={handover.wording === "template" ? "" : "ready"}>
            {handover.wording === "template" ? "from the timeline" : "worded by Muse Spark Open"}
          </Pill>
        )}
      </div>
      <div className="row">
        <label className="field" style={{ flex: "1 1 160px" }}>
          From
          <input value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "1 1 160px" }}>
          To
          <input value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
      </div>
      <label className="small">
        <input type="checkbox" checked={useModel} onChange={(event) => setUseModel(event.target.checked)} /> Ask Muse Spark
        Open to word it (kept only if it adds nothing)
      </label>
      <div className="row">
        <button
          className="primary"
          disabled={busy || !from.trim() || !to.trim()}
          onClick={() => act("/handover", { from_nurse: from.trim(), to_nurse: to.trim(), use_model: useModel })}
        >
          Draft handover
        </button>
      </div>
      {handover && (
        <div className="stack">
          <p className="small muted">
            {handover.from} to {handover.to} · {handover.since} to {handover.until}
            {handover.model_note ? ` · model wording not used: ${handover.model_note}` : ""}
          </p>
          {handover.text && <p><b>{handover.text}</b></p>}
          <ol className="small">
            {handover.lines.map((line, index) => <li key={index}>{line.text}</li>)}
          </ol>
          {handover.accepted_by ? (
            <p className="small"><span className="tag ready">accepted</span> by {handover.accepted_by}</p>
          ) : (
            <div className="row">
              <label className="field" style={{ flex: "1 1 160px" }}>
                Accepted by
                <input value={taker} onChange={(event) => setTaker(event.target.value)} />
              </label>
              <button disabled={busy || !taker.trim()} onClick={() => act(`/handover/${handover.id}/accept`, { by: taker.trim() })}>
                Accept handover
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
