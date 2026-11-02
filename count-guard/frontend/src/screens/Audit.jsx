import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageLead, Shell } from "../App";
import { loadEpisode } from "../episode";
import { getAudit } from "../journey";
import { AuditTable } from "../care/legacy/AuditTable";

export default function Audit() {
  const [audit, setAudit] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEpisode()
      .then((morning) => getAudit(morning.episode.id))
      .then(setAudit)
      .catch((exc) => setError(exc.message));
  }, []);

  const rows = audit?.rows || [];

  return (
    <Shell subtitle={audit ? `${audit.episode?.label || "This patient"} · audit trail` : undefined}>
      <PageLead
        kicker="Audit trail"
        title="Who wrote what, and when."
        body="Every line as written. Nothing is deleted."
      />
      {error && <p className="error" role="alert">{error}</p>}
      <section className="card">
        <div className="row between">
          <p className="label">{rows.length} lines</p>
          <Link to="/journey">Back to the journey</Link>
        </div>
        {audit && rows.length === 0 && <p className="empty">Nothing recorded for this patient yet.</p>}
        {rows.length > 0 && (
          <AuditTable rows={rows} />
        )}
      </section>
    </Shell>
  );
}
