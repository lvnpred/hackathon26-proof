import { Fragment } from "react";
import { atText } from "./when.js";
import { displayName } from "./names.js";
import { MATCH_LABEL, proofOf } from "./drafts";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import StateHeader from "./StateHeader";
import { findPatient } from "./Patients";
import Timeline from "./Timeline";
import RecordEvidence from "./RecordEvidence.jsx";
import { orderLines, orderStatus, patientTaskStatus } from "./tasklist";
import { taskCheckLine } from "./video";

// The same record as Today, read-only: no forms, no actions.
export default function MyCare() {
  const ward = useCareWard();
  const patient = findPatient(ward.patients, ward.patientBed);
  if (!patient) return <p className="empty">{ward.loadError || "Loading your care…"}</p>;
  const { view } = patient;
  return (
    <Fragment key={patient.id}>
      <PageLead kicker={patient.name} title="My care" body="Where you are and what has been recorded. You can read it here." />
      <StateHeader patient={patient} view={view} you />
      <section className="card">
        <p className="label">Orders and tasks</p>
        {(view.order_list || []).length === 0 && <p className="empty small">No orders yet.</p>}
        {(view.order_list || []).map((order) => (
          <div key={order.id}>
            <p className="small">{[`Ordered by ${displayName(order.by)}`, orderStatus(order, view.state, true)].filter(Boolean).join(" · ")}</p>
            <ul className="task-list">
              {orderLines(order, view.tasks || []).map(({ key, text, task }) => {
                if (!task) return <li key={key}><span>{text}</span></li>;
                const status = patientTaskStatus(task, view.state, ward.nowMs);
                return (
                  <li key={key}>
                    <span>{task.title}</span>{status && <> <span className="pill info">{status}</span></>}
                    {task.video && <p className="small muted">{taskCheckLine(view, task)}</p>}
                    {(task.done || []).map((d, index) => {
                      const proof = proofOf(d, view.photos);
                      return (
                        <p className="small muted" key={`${task.id}:${index}`}>
                          Done by {displayName(d.by)} {atText(d.at_ms, ward.nowMs)}{proof.voice && ", by voice"}{proof.typed && ", typed"}
                          {proof.photo && <> · <a href={proof.photo.url} target="_blank" rel="noreferrer">Photo</a></>}
                          {d.match && <> · <span className={`pill ${proof.flagged ? "sun" : "info"}`}>{MATCH_LABEL[d.match] || MATCH_LABEL.none}</span></>}
                        </p>
                      );
                    })}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </section>
      <RecordEvidence view={view} role="patient" lens="patient" episodeId={patient.id} />
      <section className="card">
        <p className="label">Timeline</p>
        <Timeline lines={view.timeline} nudges={view.nudges} replaced={new Set()} lens="patient" role="patient" />
      </section>
    </Fragment>
  );
}
