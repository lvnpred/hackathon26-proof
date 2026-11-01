import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import Fault from "./Fault";
import LoadError from "./LoadError";
import Patients from "./Patients";
import Queue from "./Queue";
import { STATUS } from "./faults";
import ProposalCard from "./ProposalCard.jsx";
import { OPS_SCOPE, myPatientsStrip, needsTitle, stripTitle } from "./handling.js";
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
            {kind !== "waiting" ? <span className="muted">{row.next}</span> : row.waited && <span className="pill sun">{row.waited}</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}

// Under the status menu: one live row per patient, then this doctor's proposals. Each acts on its own episode.
function AiStrip({ ward }) {
  const { rows, proposals } = myPatientsStrip(ward.patients, ward.role);
  if (!rows.length && !proposals.length) return null;
  return (
    <section className="ai-handling" aria-label="AI admin">
      <p className="label">{stripTitle(rows.length)}</p>
      <ul className="ai-handling-list">
        {rows.map((r) => (
          <li key={r.episodeId}><Link to={`/chart/${r.episodeId}`}>{r.name} · {r.text}</Link></li>
        ))}
      </ul>
      {proposals.length > 0 && <p className="label">{needsTitle(proposals.length)}</p>}
      {proposals.map(({ episodeId, name, p, view }) => (
        <div key={p.work_id}>
          <p className="small muted">{name}</p>
          <ProposalCard p={p} role={ward.role} view={view} busy={ward.busy} episodeId={episodeId} act={(path, body, scope) => ward.act(episodeId, path, body, scope)} />
        </div>
      ))}
      {proposals.map(({ episodeId }) => episodeId).filter((id, n, all) => all.indexOf(id) === n)
        .map((id) => <Fault key={id} fault={ward.fault} episodeId={id} only={[OPS_SCOPE]} />)}
    </section>
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
      <AiStrip ward={ward} />
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
