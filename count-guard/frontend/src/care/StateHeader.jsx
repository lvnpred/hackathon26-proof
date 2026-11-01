import JourneyBar from "./JourneyBar";
import NextUp from "./NextUp.jsx";

// Who the patient is and where they are. `you` adds the patient's own next line (the patient pages);
// staff charts show the Now card in the action panel instead.
export default function StateHeader({ patient, view, nowMs, you = false }) {
  return (
    <header className="page-head state-head">
      <p className="label">Bed {patient.bed}</p>
      <h1>{patient.name}</h1>
      <JourneyBar state={view.state} visited={view.visited} />
      {you && <NextUp view={view} nowMs={nowMs} />}
    </header>
  );
}
