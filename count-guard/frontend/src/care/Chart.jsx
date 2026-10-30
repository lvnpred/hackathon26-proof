import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAudit } from "../journey";
import { AuditTable } from "../screens/Audit";
import { useCareWard } from "./CareShell";
import { alertNow } from "./alerts";
import AlertBanner from "./AlertBanner";
import AskInbox from "./AskInbox";
import Fault from "./Fault";
import { INBOX_SCOPES, NUDGE_SCOPES } from "./faults";
import { trayOnNurseCard } from "./derive";
import { lensFor } from "./lens";
import OrderTasks from "./OrderTasks";
import Photos from "./Photos";
import StateHeader from "./StateHeader";
import StatePanel from "./StatePanel";
import Timeline, { LENSES } from "./Timeline";
import VideoChecks from "./VideoChecks";

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

  if (!ward.patients.length) return <p className="empty">{ward.loadError || "Loading the ward…"}</p>;
  if (!patient) {
    return <p className="empty">No patient with that id. <Link to="/patients">Back to patients</Link></p>;
  }

  const act = (path, body, scope) => ward.act(episodeId, path, body, scope);
  const upload = (path, file, fields, scope) => ward.upload(episodeId, path, file, fields, scope);
  const ask = (path, file, fields, scope) => ward.ask(episodeId, path, file, fields, scope);
  const replaced = new Set(rows.filter((row) => row.replaced_by).map((row) => row.id));
  const tasks = view.tasks || [];
  const orders = view.order_list || [];

  return (
    <>
      <StateHeader patient={patient} view={view} alert={alertNow(view)} />

      <AlertBanner view={view} role={ward.role} line={line} busy={ward.busy} act={act} />
      <Fault fault={ward.fault} episodeId={episodeId} only={NUDGE_SCOPES} />

      <AskInbox key={`ask-${episodeId}`} view={view} role={ward.role} busy={ward.busy} act={act} ask={ask} fault={ward.fault} episodeId={episodeId} />

      <StatePanel key={episodeId} state={view.state} role={ward.role} view={view} act={act} upload={upload} ask={ask} busy={ward.busy} nowMs={ward.nowMs} episodeId={episodeId} replaced={replaced} />
      <Fault fault={ward.fault} episodeId={episodeId} except={[...INBOX_SCOPES, ...NUDGE_SCOPES]} />

      <Photos view={view} />

      <VideoChecks view={view} hideTray={trayOnNurseCard(ward.role, view.state)} />

      <OrderTasks orders={orders} tasks={tasks} photos={view.photos} nowMs={ward.nowMs} state={view.state} />

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
