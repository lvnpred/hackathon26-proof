import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageLead, Shell } from "../App";
import { loadEpisode } from "../episode";
import { getAudit } from "../journey";

// "28 Oct, 2:38 pm": when the line was written, beside the story clock.
function written(iso) {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return `written ${at.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${at.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase()}`;
}

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
          <div className="table-box">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th style={{ textAlign: "left" }}>Who</th>
                  <th style={{ textAlign: "left" }}>What</th>
                  <th>Tier</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const struck = Boolean(row.replaced_by);
                  return (
                    <tr key={row.id} className={struck ? "struck" : undefined}>
                      <td className="num" style={{ whiteSpace: "nowrap" }}>
                        {row.when}
                        {row.written_at && <div className="small muted">{written(row.written_at)}</div>}
                      </td>
                      <td style={{ textAlign: "left" }}>{row.who || "—"}</td>
                      <td style={{ textAlign: "left" }}>
                        {row.what}
                        {struck && <> <span className="tag">corrected</span></>}
                        {row.supersedes && <> <span className="tag info">correction</span></>}
                        <div className="small muted">{row.type}</div>
                      </td>
                      <td>{row.tier ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Shell>
  );
}
