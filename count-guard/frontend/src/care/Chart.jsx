import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAudit } from "../journey";
import { useCareWard } from "./CareShell";
import AlertBanner from "./AlertBanner";
import AskInbox from "./AskInbox";
import Fault from "./Fault";
import History from "./History";
import { INBOX_SCOPES, NUDGE_SCOPES } from "./faults";
import { trayOnNurseCard } from "./derive";
import OrderTasks from "./OrderTasks";
import Photos from "./Photos";
import StateHeader from "./StateHeader";
import StatePanel from "./StatePanel";
import { unseenCheckins } from "./thread.js";
import VideoChecks from "./VideoChecks";

const WARD_NURSE = "Nurse Meena (synthetic)"; // the ward nurse, as in NurseActions.jsx

export default function Chart() {
  const { episodeId } = useParams();
  const [params] = useSearchParams();
  const ward = useCareWard();
  const patient = ward.find(episodeId);
  const view = patient?.view;
  const line = params.get("line");
  const [rows, setRows] = useState([]);
  const [rowsError, setRowsError] = useState("");
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

  // The ward nurse opening a chart has seen its check-ins: one Seen per check-in, one after the other (R22).
  const checkinCount = view?.ask?.checkins?.length;
  useEffect(() => {
    if (ward.role !== "nurse" || !view) return;
    const ids = unseenCheckins(view, WARD_NURSE);
    (async () => {
      for (const id of ids) {
        if (!(await ward.markSeen(episodeId, id, WARD_NURSE))) break;
      }
    })();
  }, [episodeId, checkinCount, ward.role]);

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
      <StateHeader patient={patient} view={view} />

      <AlertBanner view={view} role={ward.role} line={line} busy={ward.busy} act={act} />
      <Fault fault={ward.fault} episodeId={episodeId} only={NUDGE_SCOPES} />

      <AskInbox key={`ask-${episodeId}`} view={view} role={ward.role} name={patient.name} nowMs={ward.nowMs} busy={ward.busy} act={act} ask={ask} fault={ward.fault} episodeId={episodeId} />

      <StatePanel key={episodeId} state={view.state} role={ward.role} view={view} act={act} upload={upload} ask={ask} busy={ward.busy} nowMs={ward.nowMs} episodeId={episodeId} replaced={replaced} />
      <Fault fault={ward.fault} episodeId={episodeId} except={[...INBOX_SCOPES, ...NUDGE_SCOPES]} />

      <Photos view={view} />

      <VideoChecks view={view} hideTray={trayOnNurseCard(ward.role, view.state)} />

      <OrderTasks orders={orders} tasks={tasks} photos={view.photos} nowMs={ward.nowMs} state={view.state} role={ward.role} />

      <History key={`history-${episodeId}`} view={view} role={ward.role} line={line} rows={rows} rowsError={rowsError} replaced={replaced} />
    </>
  );
}
