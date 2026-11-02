import { useState } from "react";
import DoctorOrders from "./DoctorOrders";
import { RxImport, RxTable } from "../care/legacy/Rx";

function CardSummary({ card }) {
  if (!card) return <p className="empty small">No card signed yet.</p>;
  return (
    <div className="stack">
      <p><b>{card.title}</b></p>
      <p className="small">Warning signs: {card.warning_signs.join("; ")}.</p>
      {card.wound_care && <p className="small">Wound care: {card.wound_care}</p>}
      {card.help_line && <p className="small">Help line: {card.help_line}</p>}
      {card.review && <p className="small">Review: {card.review}</p>}
      <p className="small muted">Signed by {card.by} · {(card.schedule || []).length} medicines on the schedule</p>
    </div>
  );
}

// The doctor's cards: prescription, ward limits, discharge card.
export default function ClinicPanel({ view, busy, act }) {
  const [template, setTemplate] = useState("hernia-repair");
  const [signer, setSigner] = useState("Dr. A. Rao (synthetic)");

  const templates = Object.entries(view?.templates || {});

  return (
    <>
      <section className="card">
        <p className="label">Prescription</p>
        <RxImport busy={busy || !view} act={act} />
        <RxTable rx={view?.rx} />
      </section>
      <DoctorOrders orders={view?.orders} busy={busy || !view} act={act} />
      <section className="card">
        <p className="label">Discharge card</p>
        <label className="field">
          Clinic template
          <select value={template} onChange={(event) => setTemplate(event.target.value)}>
            {templates.length === 0 && <option value="hernia-repair">hernia-repair</option>}
            {templates.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
          </select>
        </label>
        <label className="field">
          Signed by
          <input value={signer} onChange={(event) => setSigner(event.target.value)} />
        </label>
        <button
          className="primary"
          disabled={busy || !view || !signer.trim()}
          onClick={() => act("/discharge-card", { template, by: signer.trim() })}
        >
          Sign discharge card
        </button>
        <CardSummary card={view?.card} />
      </section>
    </>
  );
}
