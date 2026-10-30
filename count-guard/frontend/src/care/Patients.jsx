import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import LoadError from "./LoadError";
import { STATE_LABEL } from "./derive";

// The patient the Patient role is looking at; a saved bed the roster lacks falls back to the first patient.
export const findPatient = (patients, bed) => patients.find((patient) => patient.bed === bed) || patients[0];

export function StateBadge({ patient }) {
  const state = patient.view.state;
  return <span className="pill info state-badge">{STATE_LABEL[state] || state}</span>;
}

export default function Patients() {
  const { patients, loadError } = useCareWard();
  return (
    <>
      <PageLead kicker="Ward" title="Patients" body="Open a chart to see the whole record." />
      <LoadError patients={patients} error={loadError} />
      <ul className="patient-list">
        {patients.map((patient) => (
          <li key={patient.id}>
            <Link to={`/chart/${patient.id}`}>
              <span className="num">Bed {patient.bed}</span>
              <span>{patient.name}</span>
              <StateBadge patient={patient} />
              <span className="open-cue">Open →</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
