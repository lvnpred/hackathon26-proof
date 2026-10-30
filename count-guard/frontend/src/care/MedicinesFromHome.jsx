import { label } from "./clock";
import { DOCTOR } from "./DoctorActions";
import { markLine, regionOfRow, stripLabel, stripMatch, stripTone, cropStyle } from "./brownbag.js";
import { medicineLine } from "./askText.js";

function Row({ photo, row, index, regions, rows, marks, doctor, busy, onMark }) {
  const mark = marks.find((m) => m.row === index);
  const region = regionOfRow(regions, index);
  return (
    <li className="from-home-row">
      <span className={`dot ${stripTone(stripMatch(row))}`} aria-hidden="true" />
      {region && <span className="crop" style={cropStyle(region.bbox, photo.url)} aria-hidden="true" />}
      <span className="small">
        <b>{stripLabel(region || { row: index }, rows)}</b><br />
        {medicineLine(row)}
        {mark && <><br /><span className="pill info">{markLine(mark)}</span></>}
      </span>
      {doctor && (
        <span className="row">
          <button disabled={busy} onClick={() => onMark(index, "noted")}>Noted</button>
          <button disabled={busy} onClick={() => onMark(index, "discuss")}>Discuss with patient</button>
        </span>
      )}
    </li>
  );
}

// The patient's medicines photo on a staff chart: each strip against the prescription, with the doctor's marks (R29).
export default function MedicinesFromHome({ view, role, act, busy }) {
  const reads = [...(view.ask?.medicines || [])].reverse();
  if (!reads.length) return null;
  return (
    <section className="card" aria-label="Medicines from home">
      <p className="label">Medicines from home</p>
      {reads.map((m) => (
        <div key={m.id}>
          <p className="small muted">Photo {label(m.at_ms)}</p>
          <ul className="task-list">
            {m.rows.map((row, i) => (
              <Row key={i} photo={m.photo} row={row} index={i} regions={m.regions} rows={m.rows} marks={m.marks || []}
                doctor={role === "doctor"} busy={busy} onMark={(index, mark) => act(`/medicines/${m.id}/mark`, { row: index, mark, by: DOCTOR })} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
