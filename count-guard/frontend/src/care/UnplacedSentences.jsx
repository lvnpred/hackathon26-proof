import { LEAVE_OUT, NOT_PLACED, SECTION_HEADINGS } from "./dischargeDraft.js";

// Dictated discharge sentences no section took (clarity §4.5). Each waits for a section or Leave out; the choice is
// kept by the caller beside the summary (onSettle(index, text, heading | LEAVE_OUT)), so it survives this list
// remounting. sentences: [{ index, text }]; a sentence said twice is two rows, two choices.
export default function UnplacedSentences({ sentences, busy, onSettle }) {
  if (!sentences.length) return null;
  return (
    <div className="stack" aria-label={NOT_PLACED}>
      <p className="label">{NOT_PLACED}</p>
      {sentences.map(({ index, text }) => (
        <label className="field small" key={`${index}:${text}`} data-unplaced>
          “{text}”
          <select value="" disabled={busy} onChange={(e) => onSettle(index, text, e.target.value)}>
            <option value="" disabled>Choose a section</option>
            {SECTION_HEADINGS.map((heading) => <option key={heading} value={heading}>{heading}</option>)}
            <option value={LEAVE_OUT}>{LEAVE_OUT}</option>
          </select>
        </label>
      ))}
    </div>
  );
}
