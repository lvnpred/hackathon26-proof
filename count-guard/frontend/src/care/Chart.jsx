import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAudit } from "../journey";
import { AuditTable } from "../screens/Audit";
import { useCareWard } from "./CareShell";
import { taskDue } from "./derive";
import { lensFor } from "./lens";
import StateHeader from "./StateHeader";
import StatePanel from "./StatePanel";
import Timeline, { LENSES } from "./Timeline";

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
  const replaced = new Set(rows.filter((row) => row.replaced_by).map((row) => row.id));
  const tasks = view.tasks || [];

  return (
    <>
      <StateHeader patient={patient} view={view} />

      <StatePanel state={view.state} role={ward.role} view={view} act={act} busy={ward.busy} episodeId={episodeId} />

      <section className="card">
        <p className="label">Orders and tasks</p>
        {tasks.length === 0 && <p className="empty small">No orders or tasks yet.</p>}
        <ul className="task-list">
          {tasks.map((task) => {
            const due = taskDue(task, ward.nowMs);
            return (
              <li key={task.id}>
                <span>{task.title}</span> <span className={`pill ${due === "overdue" ? "sun" : due === "done" ? "ready" : "info"}`}>{due}</span>
              </li>
            );
          })}
        </ul>
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
            busy={ward.busy}
            act={act}
          />
        )}
      </section>
    </>
  );
}
