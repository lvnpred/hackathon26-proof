import { STATE_LABEL } from "./derive";

// The patient's one state, with what is happening now and what comes next.
export default function StateHeader({ patient, view }) {
  const { now, next } = view.now_next || {};
  return (
    <header className="page-head state-head">
      <p className="label">Bed {patient.bed}</p>
      <h1>{patient.name}</h1>
      <p><span className="pill info state-badge">{STATE_LABEL[view.state] || view.state}</span></p>
      <dl className="now-next">
        <dt>Now</dt>
        <dd>{now || "Nothing recorded"}</dd>
        <dt>Next</dt>
        <dd>{next || "Nothing queued"}</dd>
      </dl>
    </header>
  );
}
