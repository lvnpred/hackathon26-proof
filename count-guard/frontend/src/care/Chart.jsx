import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAudit } from "../journey";
import { AuditTable } from "../screens/Audit";
import { useCareWard } from "./CareShell";
import { alertNow } from "./alerts";
import { label } from "./clock";
import AlertBanner from "./AlertBanner";
import AskInbox from "./AskInbox";
import { taskDue } from "./derive";
import { MATCH_LABEL, proofOf, sourceLabel } from "./drafts";
import { lensFor } from "./lens";
import Photos from "./Photos";
import StateHeader from "./StateHeader";
import StatePanel from "./StatePanel";
import Timeline, { LENSES } from "./Timeline";
import VideoChecks from "./VideoChecks";
import { taskVideoLabel } from "./video";

const LENS_CHIPS = [["nurse", "Nurse"], ["doctor", "Doctor"], ["patient", "Patient"], ["everyone", "Everyone (audit)"]];

export default function Chart() {
  const { episodeId } = useParams();
  const [params] = useSearchParams();
  const ward = useCareWard();
  const patient = ward.find(episodeId);
  const view = patient?.view;
  const line = params.get("line");
  const [picked, setPicked] = useState(null);
  const [rows, setRows] = useState([]);
  const [rowsError, setRowsError] = useState("");
  const lens = lensFor(ward.role, picked);
  const stamp = view?.timeline.length;

  // Audit rows feed the struck lines and the Everyone lens; refetch when the record grows.
  useEffect(() => {
    if (!patient) return undefined;
    let live = true;
    getAudit(episodeId)
      .then((audit) => { if (live) { setRows(audit.rows); setRowsError(""); } })
      .catch((exc) => { if (live) setRowsError(exc.message); });
    return () => { live = false; };
  }, [episodeId, Boolean(patient), stamp]);

  // A missing id leaves the chart at the top.
  useEffect(() => {
    if (!line || !view) return;
    const target = document.querySelector(`[data-line="${CSS.escape(line)}"]`);
    if (target) target.scrollIntoView({ block: "center" });
  }, [line, Boolean(view)]);

  if (!ward.patients.length) return <p className="empty">{ward.error || "Loading the ward…"}</p>;
  if (!patient) {
    return <p className="empty">No patient with that id. <Link to="/patients">Back to patients</Link></p>;
  }

  const act = (path, body) => ward.act(episodeId, path, body);
  const upload = (path, file, fields) => ward.upload(episodeId, path, file, fields);
  const ask = (path, file, fields) => ward.ask(episodeId, path, file, fields);
  const replaced = new Set(rows.filter((row) => row.replaced_by).map((row) => row.id));
  const tasks = view.tasks || [];
  const orders = view.order_list || [];

  return (
    <>
      <StateHeader patient={patient} view={view} alert={alertNow(view)} />

      <AlertBanner view={view} role={ward.role} line={line} busy={ward.busy} act={act} />

      <StatePanel key={episodeId} state={view.state} role={ward.role} view={view} act={act} upload={upload} ask={ask} busy={ward.busy} nowMs={ward.nowMs} episodeId={episodeId} replaced={replaced} />

      <Photos view={view} />

      <AskInbox key={`ask-${episodeId}`} view={view} role={ward.role} busy={ward.busy} act={act} ask={ask} />

      <VideoChecks view={view} />

      <section className="card">
        <p className="label">Orders and tasks</p>
        {orders.length === 0 && <p className="empty small">No orders or tasks yet.</p>}
        {orders.map((order) => (
          <div key={order.id} data-order={order.id}>
            <p className="small">
              Signed by {order.by} at {label(order.at_ms)} ·{" "}
              {order.acknowledged_by ? `Acknowledged by ${order.acknowledged_by}` : "Waiting for the nurse"}
            </p>
            <ul className="task-list">
              {(order.items || []).map((item, i) => <li key={i}><span>{item.text}</span></li>)}
            </ul>
            <ul className="task-list">
              {tasks.filter((task) => task.order_id === order.id).map((task) => {
                const due = taskDue(task, ward.nowMs);
                return (
                  <li key={task.id}>
                    <span>{task.title}</span> <span className={`pill ${due === "overdue" ? "sun" : due === "done" ? "ready" : "info"}`}>{due}</span>
                    {taskVideoLabel(task) && <span className="small muted"> · {taskVideoLabel(task)}</span>}
                    {(task.done || []).slice(-1).map((d) => {
                      const proof = proofOf(d, view.photos);
                      return (
                        <span className="small muted" key={d.at_ms}>
                          {" "}· Done by {d.by}, {proof.voice ? "by voice" : "by tap"}
                          {d.match && <> · <span className={`pill ${proof.flagged ? "sun" : "info"}`}>{MATCH_LABEL[d.match] || MATCH_LABEL.none}</span> <span className="muted">({sourceLabel(d.source || proof.photo?.check?.source)})</span></>}
                        </span>
                      );
                    })}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </section>

      <p className="label">History</p>
      <div className="row" role="group" aria-label="Lens">
        {LENS_CHIPS.map(([id, name]) => (
          <button key={id} type="button" className="pill" aria-pressed={lens === id} onClick={() => setPicked({ role: ward.role, lens: id })}>{name}</button>
        ))}
      </div>

      <section className="card">
        <p className="label">Timeline</p>
        {lens === "everyone" ? (
          rowsError ? <p className="error" role="alert">Could not load the audit lines: {rowsError}</p>
          : rows.length ? <AuditTable rows={rows} /> : <p className="empty small">Nothing recorded for this patient yet.</p>
        ) : (
          <Timeline
            lines={view.timeline}
            nudges={view.nudges}
            replaced={replaced}
            lens={lens in LENSES ? lens : "nurse"}
            role={ward.role}
            line={line}
          />
        )}
      </section>
    </>
  );
}
