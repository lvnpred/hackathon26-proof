import { useState } from "react";
import AiMoment from "./AiMoment.jsx";
import { draftChanged, itemsToRows } from "./drafts";
import OrderSentence from "./OrderSentence.jsx";
import Provenance from "./Provenance.jsx";
import { madeByModel } from "./provenance.js";
import { blankRow, KINDS, orderRowsToItems, PREFILL, unclearLines } from "./orders";

// Rows of orders; Sign orders posts the filled rows through onSign(items, draftId), which resolves to the new view or null.
// A dictated draft fills the rows once per draft id; draftId is sent only while the rows still came from that draft.
export default function OrderForm({ busy, onSign, draft, moment = null, episodeId, acts = [] }) {
  const [rows, setRows] = useState([]);
  const [draftId, setDraftId] = useState(null);
  const [all, setAll] = useState(false);
  if (draftChanged(draftId, draft)) {
    setDraftId(draft.id);
    setRows(itemsToRows(draft.items || []));
  }
  const set = (index, patch) => setRows((list) => list.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const { items, errors } = orderRowsToItems(rows);
  const invalid = Object.keys(errors).length > 0;
  // Rows that still came from the AI's draft sit in the dashed "Proposed by AI" frame until they are signed.
  const framed = (list) => (draftId && list.length ? <Provenance item={{ id: draftId, ai: madeByModel(moment) || madeByModel(draft) }} events={acts}>{list}</Provenance> : list);

  async function sign() {
    if (await onSign(items, draftId)) {
      setRows([]);
      setDraftId(null);
    }
  }

  return (
    <section className="card" aria-label="Orders">
      <p className="label">Orders</p>
      {draftId && (
        <>
          {moment && <AiMoment moment={moment} role="doctor" episodeId={episodeId} />}
          <p className="note small" role="status">Draft from dictation. Check each row, then sign.</p>
          {unclearLines(draft).map((line) => <p className="note small" key={line} data-unclear>{line}</p>)}
        </>
      )}
      <div className="row">
        <button type="button" onClick={() => setRows([...rows, PREFILL.dose()])}>Add dose</button>
        <button type="button" onClick={() => setRows([...rows, PREFILL.obs()])}>Add observation</button>
        <button type="button" onClick={() => setRows([...rows, PREFILL.procedure()])}>Add procedure</button>
        <button type="button" onClick={() => setRows([...rows, blankRow("other")])}>Add other</button>
      </div>
      {rows.length === 0 && <p className="empty small">No rows yet. Add a dose, observation or procedure.</p>}
      {rows.length > 0 && (
        <button type="button" aria-expanded={all} onClick={() => setAll(!all)}>Edit all fields</button>
      )}
      {framed(rows.map((row, index) => !all ? (
        <div className="stack" key={index}>
          <div className="row">
            <OrderSentence row={row} index={index} onChange={(next) => setRows((list) => list.map((r, i) => (i === index ? next : r)))} />
            <button type="button" onClick={() => setRows(rows.filter((_, i) => i !== index))}>Remove row</button>
          </div>
          {errors[index] && (
            <p className="error small" role="alert">{errors[index]} <button type="button" onClick={() => setAll(true)}>Open the full form</button></p>
          )}
        </div>
      ) : (
        <div className="stack" key={index}>
          <div className="row">
            <label className="field">Kind
              <select value={row.kind} onChange={(e) => set(index, { kind: e.target.value })}>
                {KINDS.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
              </select>
            </label>
            <label className="field" style={{ flex: "1 1 220px" }}>Text
              <input value={row.text} onChange={(e) => set(index, { text: e.target.value })} />
            </label>
            {row.kind === "dose" && (
              <>
                <label className="field">Medicine
                  <input value={row.name} onChange={(e) => set(index, { name: e.target.value })} />
                </label>
                <label className="field">Amount
                  <input value={row.amount} onChange={(e) => set(index, { amount: e.target.value })} />
                </label>
              </>
            )}
            <label className="field">Every h
              <input inputMode="decimal" value={row.every_h} onChange={(e) => set(index, { every_h: e.target.value })} />
            </label>
            <label className="field">Mode
              <select value={row.mode} onChange={(e) => set(index, { mode: e.target.value })}>
                <option value="tick">One tick</option>
                <option value="start_end">Begin and end</option>
              </select>
            </label>
            <label className="field">Proof
              <select value={row.proof} onChange={(e) => set(index, { proof: e.target.value })}>
                <option value="none">None</option>
                <option value="photo">Photo</option>
                <option value="video">Video</option>
              </select>
            </label>
            {row.kind === "obs" && (
              <>
                <label className="field">Systolic BP min
                  <input inputMode="numeric" value={row.sbp_min} onChange={(e) => set(index, { sbp_min: e.target.value })} />
                </label>
                <label className="field">Systolic BP max
                  <input inputMode="numeric" value={row.sbp_max} onChange={(e) => set(index, { sbp_max: e.target.value })} />
                </label>
              </>
            )}
            <button type="button" onClick={() => setRows(rows.filter((_, i) => i !== index))}>Remove row</button>
          </div>
          {errors[index] && <p className="error small" role="alert">{errors[index]}</p>}
        </div>
      )))}
      <button type="button" disabled={busy || invalid || items.length === 0} onClick={sign}>Sign orders</button>
    </section>
  );
}
