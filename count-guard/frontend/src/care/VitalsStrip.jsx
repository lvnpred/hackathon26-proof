import { hhmm } from "./clock.js";
import { vitalsLabel } from "./theatreLive.js";

// The vitals strip (spec §6.4): a scenario file played one reading at a time, every reading labelled Simulated.
export default function VitalsStrip({ panel, busy, act }) {
  const readings = panel.readings || [];
  return (
    <section className="card" aria-label="Vitals strip">
      <p className="label">Vitals strip · Simulated</p>
      {readings.length === 0 && <p className="small muted">No readings yet.</p>}
      {readings.length > 0 && (
        <ul className="plain-list">
          {readings.map((reading) => <li key={reading.id} className="small">{hhmm(reading.at_ms)} · {vitalsLabel(reading)}</li>)}
        </ul>
      )}
      {panel.strip_done
        ? <p className="small muted">End of the simulated strip.</p>
        : (
          <button type="button" disabled={busy} onClick={() => act("/theatre/vitals/step", {})}>
            Next reading ({readings.length + 1} of {panel.strip_total})
          </button>
        )}
    </section>
  );
}
