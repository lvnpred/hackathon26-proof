import { useState } from "react";
import Source from "./Source.jsx";
import { isPrepared } from "./source.js";
import { RESEARCH_BANNER, cardWords } from "./theatreLive.js";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, cardStep, outcomeOf } from "./stepOutcome.js";

// The context card (CG-24): numbers already in the record, side by side. Context, not an alarm, and no advice.
// It sits behind the research banner and the decision tier toggle; with the tier off the server has no card.
// onTier(on, opts) -> { card }. `due` (the panel's card_on_tier) says whether turning the tier on writes the card now
// and who words it. Only then is the toggle a step (ruling P10); otherwise it asks no model and shows no step line.
export default function ContextCard({ tier, card, due, busy, onTier }) {
  const spark = useModelStep({ capability: "card" });
  const rules = useModelStep({ capability: undefined });
  const steps = { card: spark, rules };
  const working = busyOf(spark.step) || busyOf(rules.step);
  const [problem, setProblem] = useState("");
  const toggle = (on) => {
    setProblem("");
    const writes = on ? cardStep(due) : null;
    if (writes) return steps[writes].run((o) => onTier(true, o), { outcome: (r) => outcomeOf(r?.card) || UNKNOWN });
    spark.reset();
    rules.reset();
    return onTier(on).catch((exc) => setProblem(exc.message)); // asks no model: a failure is a plain note
  };
  return (
    <section className="card" aria-label="Context card" aria-busy={working}>
      <label className="field inline">
        <input type="checkbox" checked={tier} disabled={busy || working} onChange={(event) => toggle(event.target.checked)} />
        Context card (research tier)
      </label>
      <ModelStep busy={busy} step={spark.step} onRetry={spark.retry} />
      <ModelStep busy={busy} step={rules.step} onRetry={rules.retry} />
      {problem && <p className="note small" role="alert">{problem}</p>}
      {tier && (
        <>
          <p className="note small" role="note">{RESEARCH_BANNER}</p>
          {card
            ? (
              <div role="status">
                <p>{card.text}</p>
                <p className="small"><Source words={cardWords(card)} prepared={isPrepared(card)} /></p>
              </div>
            )
            : <p className="small muted">No context card yet. It appears when the strip shows a blood pressure drop.</p>}
        </>
      )}
    </section>
  );
}
