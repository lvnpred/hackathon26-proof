import { useState } from "react";
import DoctorOrders from "./DoctorOrders";

export function RxTable({ rx }) {
  if (!rx) return <p className="empty small">No prescription yet. Import one from Doctor Dictation.</p>;
  return (
    <div className="stack">
      <div className="table-box">
        <table>
          <thead>
            <tr><th>Medicine</th><th>Dose code</th><th>Timing</th><th>Duration</th></tr>
          </thead>
          <tbody>
            {rx.rows.map((row, index) => (
              <tr key={row.key || index}>
                <td>
                  <b>{[row.form, row.name, row.strength].filter(Boolean).join(" ")}</b>
                  {row.instructions && <div className="small muted">{row.instructions}</div>}
                </td>
                <td className="num">{row.dose || "—"}</td>
                <td>{row.timing || "—"}</td>
                <td>{row.duration || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(rx.diagnosis || []).length > 0 && <p className="small">Diagnosis: {rx.diagnosis.join(", ")}</p>}
      {rx.review && <p className="small">Review: {rx.review}</p>}
      <p className="small muted">
        By {rx.by || "unknown"} · source {rx.source}
        {rx.document_id ? ` · document ${rx.document_id}` : ""}
      </p>
    </div>
  );
}

// Prescription import: a Doctor Dictation document number. The demo prescription lives in the demo dock.
export function RxImport({ busy, act }) {
  const [documentId, setDocumentId] = useState("");
  const docNumber = Number(documentId);
  return (
    <div className="row">
      <label className="field" style={{ flex: "1 1 220px" }}>
        Doctor Dictation document number
        <input inputMode="numeric" value={documentId} onChange={(event) => setDocumentId(event.target.value)} placeholder="1" />
      </label>
      <button
        className="primary"
        disabled={busy || !Number.isInteger(docNumber) || docNumber < 1}
        onClick={() => act("/rx/import", { document_id: docNumber })}
      >
        Import from Doctor Dictation
      </button>
    </div>
  );
}

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
