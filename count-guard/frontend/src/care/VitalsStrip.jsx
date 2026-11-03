import { hhmm } from "./clock.js";
import { vitalsLabel } from "./theatreLive.js";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, cardStep, outcomeOf } from "./stepOutcome.js";

const CARD_EXPAND = { title: "Context card" }; // the card carries its own evidence: the facts sent, the reply, the text

// The vitals strip (spec §6.4): a scenario file played one reading at a time, every reading labelled Simulated.
// onNext(opts) -> { view, card }. Only the reading the server marks `card_due` writes the context card, so only it runs
// as a step (ruling P10): "Checking with Spark 1.3…" when Spark words it, a step naming no model when the rules do.
// Every other reading runs plain, with no step line.
export default function VitalsStrip({ panel, busy, onNext }) {
  const readings = panel.readings || [];
  const spark = useModelStep({ capability: "card" });
  const rules = useModelStep({ capability: undefined });
  const steps = { card: spark, rules };
  const working = busyOf(spark.step) || busyOf(rules.step);
  async function next() {
    const due = cardStep(panel.card_due);
    if (!due) return onNext();
    return steps[due].run((o) => onNext(o), { outcome: (r) => outcomeOf(r?.card) || UNKNOWN, record: (r) => r?.card || null });
  }
  return (
    <section className="card" aria-label="Vitals strip" aria-busy={working}>
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
          <button type="button" disabled={busy || working} onClick={next}>
            Next reading ({readings.length + 1} of {panel.strip_total})
          </button>
        )}
      <ModelStep busy={busy} step={spark.step} onRetry={spark.retry} expand={CARD_EXPAND} />
      <ModelStep busy={busy} step={rules.step} onRetry={rules.retry} expand={CARD_EXPAND} />
    </section>
  );
}
