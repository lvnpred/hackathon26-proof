import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAudit } from "../journey";
import { useCareWard } from "./CareShell";
import AlertBanner from "./AlertBanner";
import AskInbox from "./AskInbox";
import { DOCTOR } from "./DoctorActions";
import Fault from "./Fault";
import History from "./History";
import { INBOX_SCOPES, NUDGE_SCOPES } from "./faults";
import { OPS_SCOPE } from "./handling.js";
import MedicinesFromHome from "./MedicinesFromHome.jsx";
import RecordEvidence from "./RecordEvidence.jsx";
import StateHeader from "./StateHeader";
import StatePanel from "./StatePanel";
import { movedAlertId, pickNow } from "./now.js";
import { SIGNED_IN } from "./people.js";
import { unseenCheckins } from "./thread.js";

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

  // The ward nurse or the doctor opening a chart has seen its check-ins: one Seen per check-in, one after the other (R22, R15).
  const checkinCount = view?.ask?.checkins?.length;
  useEffect(() => {
    const reader = ward.role === "nurse" ? WARD_NURSE : ward.role === "doctor" ? DOCTOR : null;
    if (!reader || !view) return;
    const ids = unseenCheckins(view, reader);
    (async () => {
      for (const id of ids) {
        if (!(await ward.markSeen(episodeId, id, reader))) break;
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

  const pick = pickNow(view, { role: ward.role, name: SIGNED_IN[ward.role]?.name }, ward.nowMs);
  const act = (path, body, scope) => ward.act(episodeId, path, body, scope);
  const upload = (path, file, fields, scope) => ward.upload(episodeId, path, file, fields, scope);
  const ask = (path, file, fields, scope) => ward.ask(episodeId, path, file, fields, scope);
  const replaced = new Set(rows.filter((row) => row.replaced_by).map((row) => row.id));

  return (
    <>
      <StateHeader patient={patient} view={view} />

      <AlertBanner moved={movedAlertId(pick, ward.role)} view={view} role={ward.role} line={line} busy={ward.busy} act={act} nowMs={ward.nowMs} patientName={patient.name} />
      <Fault fault={ward.fault} episodeId={episodeId} only={NUDGE_SCOPES} />

      <AskInbox key={`ask-${episodeId}`} view={view} role={ward.role} name={patient.name} nowMs={ward.nowMs} busy={ward.busy} act={act} ask={ask} fault={ward.fault} episodeId={episodeId} />

      <StatePanel pick={pick} key={episodeId} state={view.state} role={ward.role} view={view} act={act} upload={upload} ask={ask} busy={ward.busy} nowMs={ward.nowMs} episodeId={episodeId} replaced={replaced} fault={ward.fault} />
      <Fault fault={ward.fault} episodeId={episodeId} except={[...INBOX_SCOPES, ...NUDGE_SCOPES, OPS_SCOPE]} />

      <MedicinesFromHome view={view} role={ward.role} nowMs={ward.nowMs} act={act} busy={ward.busy} />

      <RecordEvidence key={`record-${episodeId}`} view={view} role={ward.role} episodeId={episodeId} nowMs={ward.nowMs} />

      <History key={`history-${episodeId}`} view={view} role={ward.role} line={line} rows={rows} rowsError={rowsError} replaced={replaced} />
    </>
  );
}
