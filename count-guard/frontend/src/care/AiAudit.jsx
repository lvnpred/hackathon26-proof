import { useEffect, useState } from "react";
import { getAudit } from "../journey";
import { AuditTable } from "./legacy/AuditTable";
import { shortName } from "./names.js";

// Every line as written for one patient, under the AI activity (staff only).
export default function AiAudit({ patients }) {
  const [picked, setPicked] = useState("");
  const id = picked || patients[0]?.id || "";
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!id) return undefined;
    let live = true;
    setRows(null);
    getAudit(id)
      .then((audit) => { if (live) { setRows(audit.rows); setError(""); } })
      .catch((exc) => { if (live) setError(exc.message); });
    return () => { live = false; };
  }, [id]);
  if (!id) return null;
  return (
    <section aria-label="Audit lines">
      <h3>Audit lines</h3>
      <label className="field">
        Patient
        <select value={id} onChange={(e) => setPicked(e.target.value)}>
          {patients.map((p) => <option key={p.id} value={p.id}>{shortName(p.name)}</option>)}
        </select>
      </label>
      {error && <p className="error" role="alert">Could not load the audit lines: {error}</p>}
      {rows && (rows.length ? <AuditTable rows={rows} /> : <p className="empty small">Nothing recorded for this patient yet.</p>)}
    </section>
  );
}
