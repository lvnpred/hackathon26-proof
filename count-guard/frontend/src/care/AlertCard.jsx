import { useState } from "react";
import { alertParts, nudgeText } from "./alerts.js";
import { waitedText } from "./derive.js";
import { canInspect, momentFor } from "./moments.js";
import { useInspector } from "./Inspector.jsx";
import { SIGNED_IN } from "./people.js";
import StatusPill from "./StatusPill.jsx";
import { whenText } from "./when.js";

const NURSE = `${SIGNED_IN.nurse.name} (synthetic)`; // the tagged value goes to the server
const ASSIGNEE = { nurse: SIGNED_IN.nurse.name, doctor: SIGNED_IN.doctor.name, patient: "the patient" };

// Scrolls to the nurse's task list and puts the cursor in its first reading field.
function takeObservations() {
  const tasks = document.querySelector('[aria-label="Tasks"]');
  tasks?.scrollIntoView({ block: "start" });
  tasks?.querySelector("input")?.focus();
}

// One alert: the reading, the limit and who set it, a response field, and where the alert goes next.
export default function AlertCard({ view, role, nudge, safety, primary, busy, act, nowMs, episodeId }) {
  const [note, setNote] = useState("");
  const { openInspector } = useInspector();
  const { headline, limit, by } = alertParts(nudgeText(nudge, role));
  const moment = momentFor(view, nudge.id);
  const lens = role === "patient" ? "patient" : "staff";
  const age = nowMs != null && nudge.at_ms != null ? waitedText(nowMs - nudge.at_ms) : "";
  const sub = [limit && `Limit ${limit}, set by ${by}`, nudge.at_ms != null && whenText(nudge.at_ms, nowMs), age && `${age} ago`].filter(Boolean).join(" · ");
  const late = nudge.kind === "obs_overdue";
  return (
    <article className={`alert-card s-${safety ? "danger" : "check"}`} aria-label={`Alert: ${headline}`}>
      <div className="alert-card-head">
        <StatusPill role={safety ? "danger" : "check"} text={safety ? "Outside the limit" : "Late"} />
        <h3 className="t-heading">{headline}</h3>
      </div>
      {sub && <p className="t-caption">{sub}</p>}
      <label className="field">
        What did you do?
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Called the doctor, repeated the reading" />
      </label>
      <div className="alert-card-actions">
        <button type="button" className={primary ? "primary" : undefined} disabled={busy} onClick={() => act(`/nudges/${nudge.id}/seen`, { by: NURSE, note: note.trim() })}>
          Save response
        </button>
        {late && <button type="button" className="quiet" onClick={takeObservations}>Take observations now</button>}
        {moment && canInspect(moment, lens) && (
          <button type="button" className="quiet" onClick={() => openInspector(moment.id, { episodeId })}>Details</button>
        )}
      </div>
      <p className="t-caption">Assigned to {ASSIGNEE[nudge.to] || nudge.to}</p>
    </article>
  );
}
