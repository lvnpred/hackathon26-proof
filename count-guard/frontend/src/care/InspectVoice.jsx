import { diffLine, fieldDiffs, segments } from "./inspect.js";
import { isPrepared, sourceWords } from "./source.js";
import Source from "./Source.jsx";
import { orderSentence } from "./orders.js";

const NO_LINKS = "No word links for this draft.";
const wordsIn = (text) => String(text || "").split(/\s+/).filter(Boolean).length;
const lit = (focus, item, field) => focus && typeof focus === "object" && focus.item === item && focus.field === field;

// What was heard: the words, who heard them, and how many.
export function VoiceInput({ moment }) {
  const { transcript, heard_by: by } = moment.refs || {};
  const typed = !by || by === "typed";
  return (
    <div className="inspector-input">
      <p className="quote">{"“"}{transcript || ""}{"”"}</p>
      <p className="small">{typed ? <span className="source">Typed</span> : <Source words={sourceWords(moment)} prepared={isPrepared({ heard_by: by }) || isPrepared(moment)} />} <span className="muted">{wordsIn(transcript)} words</span></p>
    </div>
  );
}

function OrderLinks({ refs, focus, setFocus }) {
  const { spans, items } = refs;
  const pick = (item, field) => setFocus(lit(focus, item, field) ? null : { item, field });
  return (
    <>
      <p className="quote">
        {segments(spans.text, spans.marks).map((s, i) => (s.mark ? (
          <button key={i} type="button" className={`mark${lit(focus, s.mark.item, s.mark.field) ? " lit" : ""}`} aria-pressed={Boolean(lit(focus, s.mark.item, s.mark.field))} onClick={() => pick(s.mark.item, s.mark.field)}>{s.text}</button>
        ) : <span key={i}>{s.text}</span>))}
      </p>
      <ul>
        {(items || []).map((item, i) => (
          <li key={i} className="row">
            {orderSentence(item).map((chip) => (
              <button key={chip.field} type="button" className={`chip${lit(focus, i, chip.field) ? " lit" : ""}`} aria-pressed={Boolean(lit(focus, i, chip.field))} onClick={() => pick(i, chip.field)}>{chip.text}</button>
            ))}
          </li>
        ))}
      </ul>
    </>
  );
}

// Orders: words and chips light each other. Discharge: the sections. Task and answer: the transcript.
export function VoiceFound({ moment, focus, setFocus }) {
  const refs = moment.refs || {};
  if (moment.capability === "orders") {
    const diffs = refs.signed_items ? fieldDiffs(refs.items, refs.signed_items) : [];
    return (
      <div className="inspector-found">
        {refs.spans?.text ? <OrderLinks refs={refs} focus={focus} setFocus={setFocus} /> : (
          <>
            <p className="quote">{"“"}{refs.transcript || ""}{"”"}</p>
            <p className="muted small">{NO_LINKS}</p>
          </>
        )}
        {diffs.length > 0 && <ul>{diffs.map((d, i) => <li key={i} className="small">{diffLine(d)}</li>)}</ul>}
      </div>
    );
  }
  if (moment.capability === "discharge") {
    return (
      <div className="inspector-found">
        {(refs.sections || []).map((s) => <p key={s.heading}><strong>{s.heading}</strong> {s.text}</p>)}
      </div>
    );
  }
  return <div className="inspector-found"><p className="quote">{"“"}{refs.transcript || ""}{"”"}</p></div>;
}
