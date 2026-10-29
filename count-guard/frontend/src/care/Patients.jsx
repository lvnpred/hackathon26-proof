import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { STAGES, stageOf } from "./clock";
import { useCareWard } from "./CareShell";

const NAME = Object.fromEntries(STAGES.map((s) => [s.id, s.label]));

// The demo patient (R. Kumar) sits in bed 4.
export const KUMAR_BED = "4";
export const findKumar = (patients) => patients.find((patient) => patient.bed === KUMAR_BED);

// Kumar's story is built live on the demo clock; the others show the furthest stage their record reached.
export function stageFor(patient, nowMs) {
  if (patient.bed === KUMAR_BED) return NAME[stageOf(nowMs)];
  const { view } = patient;
  if (view.card) return NAME.home;
  if (view.orders || view.handover) return NAME.ward;
  if (view.rx) return NAME.theatre;
  return NAME.clinic;
}

export default function Patients() {
  const { patients, nowMs } = useCareWard();
  return (
    <>
      <PageLead kicker="Ward" title="Patients" body="Open a chart to see the whole record." />
      <ul className="patient-list">
        {patients.map((patient) => (
          <li key={patient.id}>
            <Link to={`/chart/${patient.id}`}>
              <span className="num">Bed {patient.bed}</span>
              <span>{patient.name}</span>
              <span className="pill">{stageFor(patient, nowMs)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
