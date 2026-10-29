import { PageLead } from "../App";
import { StageBar } from "./Chart";
import { useCareWard } from "./CareShell";
import { stageOf } from "./clock";
import { findKumar } from "./Patients";
import Timeline from "./Timeline";

const ORDER = ["clinic", "theatre", "ward", "home"];

// Plain facts only: the theatre count is a staff record, so it is left off here.
function facts(view) {
  return {
    clinic: view.rx ? `${view.rx.rows.length} medicines` : "",
    theatre: "",
    ward: view.orders ? "orders set" : "",
    home: view.card ? "card signed" : "",
  };
}

// The same record as Today, read-only: no forms, no actions.
export default function MyCare() {
  const ward = useCareWard();
  const patient = findKumar(ward.patients);
  if (!patient) return <p className="empty">{ward.error || "Loading your care…"}</p>;
  const { view } = patient;
  return (
    <>
      <PageLead kicker={patient.name} title="My care" body="Where you are and what has been recorded. You can read it here." />
      <StageBar now={ORDER.indexOf(stageOf(ward.nowMs))} facts={facts(view)} />
      <section className="card">
        <p className="label">Timeline</p>
        <Timeline lines={view.timeline} nudges={view.nudges} replaced={new Set()} lens="patient" role="patient" readOnly />
      </section>
    </>
  );
}
