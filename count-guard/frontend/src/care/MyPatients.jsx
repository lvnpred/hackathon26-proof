import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import Fault from "./Fault";
import LoadError from "./LoadError";
import Patients from "./Patients";
import Queue from "./Queue";
import { STATUS } from "./faults";
import { patientGroups, statusWord } from "./patientGroups";
import { STATUS_CHOICES } from "./status";

function PatientList({ rows, kind }) {
  return (
    <ul className="patient-list">
      {rows.map((row) => (
        <li key={row.episodeId}>
          <Link to={`/chart/${row.episodeId}`} className={kind}>
            <span className="num">Bed {row.bed}</span>
            <span>{row.name}</span>
            {kind === "waiting" && <span>{row.reason}</span>}
            <span className="pill info state-badge">{row.state}</span>
            {kind === "waiting" ? <span className="pill sun">{row.waited}</span> : <span className="muted">{row.next}</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function MyPatients() {
  const ward = useCareWard();
  const { waiting, quiet } = patientGroups(ward.patients, ward.nowMs);
  return (
    <>
      <PageLead kicker="Ward" title="My patients" body="Who is waiting on you first." />
      <LoadError patients={ward.patients} error={ward.loadError} />
      <details className="status-menu">
        <summary className="pill info">{statusWord(ward.doctorStatus)} ▾</summary>
        <div className="row" role="group" aria-label="My status">
          {STATUS_CHOICES.map((choice) => (
            <button key={choice.id} type="button" disabled={ward.busy} onClick={() => ward.setDoctorStatus(choice)}>{choice.label}</button>
          ))}
        </div>
        <Fault fault={ward.fault} episodeId={null} only={[STATUS]} />
      </details>
      <h2>Waiting on you · {waiting.length}</h2>
      <PatientList rows={waiting} kind="waiting" />
      <h2>Nothing for you now · {quiet.length}</h2>
      <PatientList rows={quiet} kind="quiet" />
    </>
  );
}

// R14: the doctor's /queue and /patients are the same list; the nurse keeps both screens.
export const QueueRoute = () => (useCareWard().role === "doctor" ? <MyPatients /> : <Queue />);
export const PatientsRoute = () => (useCareWard().role === "doctor" ? <MyPatients /> : <Patients />);
