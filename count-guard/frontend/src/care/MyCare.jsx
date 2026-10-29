import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import StateHeader from "./StateHeader";
import { findKumar } from "./Patients";
import Timeline from "./Timeline";

// The same record as Today, read-only: no forms, no actions.
export default function MyCare() {
  const ward = useCareWard();
  const patient = findKumar(ward.patients);
  if (!patient) return <p className="empty">{ward.error || "Loading your care…"}</p>;
  const { view } = patient;
  return (
    <>
      <PageLead kicker={patient.name} title="My care" body="Where you are and what has been recorded. You can read it here." />
      <StateHeader patient={patient} view={view} />
      <section className="card">
        <p className="label">Timeline</p>
        <Timeline lines={view.timeline} nudges={view.nudges} replaced={new Set()} lens="patient" role="patient" readOnly />
      </section>
    </>
  );
}
