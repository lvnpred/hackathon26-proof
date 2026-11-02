import { useState } from "react";

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
