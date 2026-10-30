import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { swabTotal } from "./video";

const NURSE = "Nurse Asha (synthetic)";

// The Theatre count: pack opened, closing count, a correction, and the door to the camera count.
export default function TheatrePanel({ episodeId, view, busy, act, replaced }) {
  const navigate = useNavigate();
  const [quantity, setQuantity] = useState(String(swabTotal(view) ?? "20"));
  const [returned, setReturned] = useState("");
  const [detail, setDetail] = useState("");
  const [by, setBy] = useState(NURSE);
  const [note, setNote] = useState("");

  const open = (view?.nudges || []).find((nudge) => nudge.kind === "count_open");
  const corrected = open && replaced?.has(open.fact_id);
  const ready = view && !busy && by.trim();
  const opened = Number(quantity);
  const back = Number(returned);

  async function post(body) {
    setNote("");
    return act("/count", { ...body, by: by.trim() });
  }

  async function close(supersedesId) {
    const body = { step: "closing", returned: back, detail: detail.trim() };
    if (supersedesId) body.supersedes_id = supersedesId;
    if (await post(body)) {
      setReturned("");
      setDetail("");
      setNote(supersedesId ? "Correction recorded." : "Closing count recorded.");
    }
  }

  function camera() {
    try {
      sessionStorage.setItem("cg-chart-episode", episodeId);
    } catch {
      // the camera screen then files to its default patient
    }
    navigate("/count");
  }

  const validBack = returned !== "" && Number.isInteger(back) && back >= 0;

  return (
    <section className="card">
      <p className="label">Swab count</p>
      <div className="row">
        <label className="field" style={{ flex: "1 1 120px" }}>
          Pack opened
          <input inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "1 1 160px" }}>
          By
          <input value={by} onChange={(event) => setBy(event.target.value)} />
        </label>
        <button
          disabled={!ready || !Number.isInteger(opened) || opened < 1}
          onClick={async () => (await post({ step: "opened", quantity: opened })) && setNote("Pack opened recorded.")}
        >
          Record pack opened
        </button>
      </div>
      <div className="row">
        <label className="field" style={{ flex: "1 1 120px" }}>
          Closing count (returned)
          <input inputMode="numeric" value={returned} onChange={(event) => setReturned(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "2 1 220px" }}>
          Detail
          <input value={detail} onChange={(event) => setDetail(event.target.value)} placeholder="Found under the drape" />
        </label>
        <button className="primary" disabled={!ready || !validBack} onClick={() => close(null)}>Record closing count</button>
        {open && !corrected && (
          <button disabled={!ready || !validBack} onClick={() => close(open.fact_id)}>Correct the count</button>
        )}
      </div>
      <div className="row">
        <button onClick={camera}>Count by camera</button>
        <span className="small muted">Opens the camera count. Its result is filed on this patient.</span>
      </div>
      {note && <p className="note" role="status">{note}</p>}
    </section>
  );
}
