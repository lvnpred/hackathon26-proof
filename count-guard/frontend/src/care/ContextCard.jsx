import Source from "./Source.jsx";
import { isPrepared } from "./source.js";
import { RESEARCH_BANNER, cardWords } from "./theatreLive.js";

// The context card (CG-24): numbers already in the record, side by side. Context, not an alarm, and no advice.
// It sits behind the research banner and the decision tier toggle; with the tier off the server has no card.
export default function ContextCard({ tier, card, busy, onTier }) {
  return (
    <section className="card" aria-label="Context card">
      <label className="field inline">
        <input type="checkbox" checked={tier} disabled={busy} onChange={(event) => onTier(event.target.checked)} />
        Context card (research tier)
      </label>
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
