import { label } from "./clock";
import { sourceLabel } from "./drafts";
import { checkLabel, patientCheckLine, shownChecks } from "./video";

// Every tray and set-up clip on the chart, oldest first, with the frames the check looked at.
export default function VideoChecks({ view, hideTray = false, patient = false }) {
  const checks = shownChecks(view?.video_checks || [], { hideTray, patient });
  if (checks.length === 0) return null;
  const titleOf = (id) => (view.tasks || []).find((t) => t.id === id)?.title || "task";
  return (
    <section className="card" aria-label={patient ? "Checks from a video" : "Video checks"}>
      <p className="label">{patient ? "Checks from a video" : "Video checks"}</p>
      {checks.map((c) => (
        <div key={c.id}>
          {patient ? (
            <p className="small">{patientCheckLine(c)}</p>
          ) : (
            <p className="small">
              {c.check === "tray" ? "Tray check" : `Set-up check · ${titleOf(c.task_id)}`}
              {c.by ? ` · ${c.by}` : ""}{c.at_ms !== undefined ? ` · ${label(c.at_ms)}` : ""}{" "}
              <span className={`pill ${c.match === "mismatch" ? "sun" : "info"}`}>{checkLabel(c)}</span>{" "}
              <span className="muted">({sourceLabel(c.source)})</span>
            </p>
          )}
          {!patient && c.why && <p className="small muted">{c.why}</p>}
          {(c.frames || []).length > 0 && (
            <div className="row">
              {c.frames.map((f) => <img key={f.id} src={f.url} alt="Frame from the clip" width={96} style={{ borderRadius: 6 }} />)}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
