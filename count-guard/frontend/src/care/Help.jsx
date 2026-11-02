import { Link } from "react-router-dom";
import { AUDIENCES, PATIENT_RULE, helpSections } from "./help.js";

// The care app's Help page: what each step does and who does it.
export default function Help() {
  return (
    <section aria-label="Help">
      <h1>Help</h1>
      <p className="note" role="note">{PATIENT_RULE}</p>
      <div className="grid-2">
        {helpSections().map((s) => (
          <article className="card" key={s.id}>
            <p className="label">{s.who} · {s.where}</p>
            <h2>{s.title}</h2>
            <p>{s.does}</p>
          </article>
        ))}
      </div>
      <section className="card" aria-label="Who starts where">
        <p className="label">Who starts where</p>
        <div className="rows">
          {AUDIENCES.map((a) => (
            <div className="list-row" key={a.who}>
              <span><b>{a.who}</b><small>{a.does}</small></span>
              <Link to={a.start}>Open</Link>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}
