import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import { STATE_LABEL } from "./derive";

// The demo patient (R. Kumar) sits in bed 4.
export const KUMAR_BED = "4";
export const findKumar = (patients) => patients.find((patient) => patient.bed === KUMAR_BED);

export function StateBadge({ patient }) {
  const state = patient.view.state;
  return <span className="pill info state-badge">{STATE_LABEL[state] || state}</span>;
}

export default function Patients() {
  const { patients } = useCareWard();
  return (
    <>
      <PageLead kicker="Ward" title="Patients" body="Open a chart to see the whole record." />
      <ul className="patient-list">
        {patients.map((patient) => (
          <li key={patient.id}>
            <Link to={`/chart/${patient.id}`}>
              <span className="num">Bed {patient.bed}</span>
              <span>{patient.name}</span>
              <StateBadge patient={patient} />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
