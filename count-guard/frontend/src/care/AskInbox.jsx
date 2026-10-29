import { useState } from "react";
import { label } from "./clock";
import Dictate from "./Dictate";
import { DOCTOR } from "./DoctorActions";
import { sourceLabel } from "./drafts";

// The three fixed review decisions, as the server names them.
const DECISIONS = [["no_visit", "No visit needed"], ["come_in", "Come in to the clinic"], ["call", "The doctor will call you"]];
const THUMB = { objectFit: "cover", borderRadius: 6 };

function Answered({ answer, text }) {
  const how = answer.via === "voice" ? "by voice" : answer.via === "text" ? "typed" : "";
  return (
    <p className="small">
      {text} <span className="muted">{answer.by} · {label(answer.at_ms)}{how ? ` · ${how}` : ""}{answer.source ? ` · ${sourceLabel(answer.source)}` : ""}</span>
    </p>
  );
}

function QuestionItem({ q, role, busy, act, ask }) {
  const [text, setText] = useState("");
  const [how, setHow] = useState({ via: "text", heard_by: "" });
  async function hear({ file, text: typed }) {
    if (!file) {
      setText(typed);
      setHow({ via: "text", heard_by: "" });
      return true;
    }
    const heard = await ask("/ask/hear", file, { by: DOCTOR });
    if (!heard) return false;
    setText(heard.text);
    setHow({ via: "voice", heard_by: heard.heard_by });
    return true;
  }
  async function send() {
    const done = await act(`/questions/${q.id}/answer`, { text: text.trim(), by: DOCTOR, ...how });
    if (done) setText("");
  }
  return (
    <div data-line={q.id}>
      <p><b>{q.by}</b> asked at {label(q.at_ms)}: {q.text}</p>
      {q.answer && <Answered answer={q.answer} text={q.answer.text} />}
      {!q.answer && role === "doctor" && (
        <>
          <Dictate label="Answer by voice" busy={busy} onSend={hear} />
          <label className="field">
            Your answer (check it before sending)
            <textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <button type="button" className="primary" disabled={busy || !text.trim()} onClick={send}>Send answer</button>
        </>
      )}
    </div>
  );
}

function ReviewItem({ r, role, busy, act, references }) {
  const [note, setNote] = useState("");
  const decide = (decision) => act(`/reviews/${r.id}/answer`, { decision, note: note.trim(), by: DOCTOR });
  return (
    <div data-line={r.id}>
      <p className="small">Healing photo from <b>{r.by}</b> at {label(r.at_ms)}{r.note ? `: ${r.note}` : ""}</p>
      <div className="row">
        <figure>
          <img src={r.photo.url} alt="Healing photo to review" width={96} height={96} style={THUMB} />
          <figcaption className="small muted">Healing photo</figcaption>
        </figure>
        {references.map((p) => (
          <figure key={p.id}>
            <img src={p.url} alt={`Reference photo by ${p.by}`} width={96} height={96} style={THUMB} />
            <figcaption className="small muted">Reference</figcaption>
          </figure>
        ))}
      </div>
      {r.answer && <Answered answer={{ ...r.answer, via: "", source: "" }} text={`${r.answer.label}${r.answer.note ? `: ${r.answer.note}` : ""}`} />}
      {!r.answer && role === "doctor" && (
        <>
          <label className="field">
            Note (optional)
            <input maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="row">
            {DECISIONS.map(([id, name]) => <button key={id} type="button" disabled={busy} onClick={() => decide(id)}>{name}</button>)}
          </div>
        </>
      )}
    </div>
  );
}

// Questions to the doctor and healing photos on the chart. Only the doctor can answer; others see answered items.
export default function AskInbox({ view, role, busy, act, ask }) {
  const shown = (item) => role === "doctor" || item.answer;
  const questions = (view.ask?.questions || []).filter((q) => q.to === "doctor").filter(shown);
  const reviews = (view.ask?.reviews || []).filter(shown);
  if (!questions.length && !reviews.length) return null;
  const references = (view.photos || []).filter((p) => p.purpose === "reference");
  return (
    <section className="card" aria-label="Ask inbox">
      <p className="label">Questions and photos for the doctor</p>
      {questions.map((q) => <QuestionItem key={q.id} q={q} role={role} busy={busy} act={act} ask={ask} />)}
      {reviews.map((r) => <ReviewItem key={r.id} r={r} role={role} busy={busy} act={act} references={references} />)}
    </section>
  );
}
