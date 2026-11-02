import BedChange from "./BedChange.jsx";
import JourneyBar from "./JourneyBar";
import NextUp from "./NextUp.jsx";
import { headerFacts } from "./header.js";

// Who the patient is and where they are. `you` adds the patient's own next line (the patient pages);
// staff charts show the Now card in the action panel instead, and the facts Doctor Dictation sent.
// With `act`, the doctor can move the patient to another bed.
export default function StateHeader({ patient, view, nowMs, you = false, role, act, busy }) {
  const header = view.header;
  const facts = you ? [] : headerFacts(header);
  return (
    <header className="page-head state-head">
      <div className="row">
        <p className="label">Bed {patient.bed}</p>
        {!you && role === "doctor" && act && <BedChange bed={patient.bed} act={act} busy={busy} />}
      </div>
      <h1>{patient.name}</h1>
      {facts.length > 0 && (
        <dl className="row small muted state-facts">
          {facts.map((fact) => <div key={fact.label}><dt className="label">{fact.label}</dt><dd>{fact.value}</dd></div>)}
        </dl>
      )}
      {!you && header?.dd_pdf && <a className="small" href={header.dd_pdf} target="_blank" rel="noreferrer">Doctor Dictation PDF</a>}
      <JourneyBar state={view.state} visited={view.visited} />
      {you && <NextUp view={view} nowMs={nowMs} />}
    </header>
  );
}
