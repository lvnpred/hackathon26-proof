import { useState } from "react";
import { label } from "./clock";
import AiMoment from "./AiMoment.jsx";
import Dictate from "./Dictate";
import { DOCTOR } from "./DoctorActions";
import Fault from "./Fault";
import { INBOX_SCOPES } from "./faults";
import { botMoment } from "./moments.js";
import { answerHow, answerSourceLine, checkinLine, inboxGroups, inboxHeader, inboxItems, noteText, photoDay, questionText, sendVerb } from "./askText";

// The three fixed review decisions, as the server names them.
const DECISIONS = [["no_visit", "No visit needed"], ["come_in", "Come in to the clinic"], ["call", "The doctor will call you"]];
const THUMB = { objectFit: "cover", borderRadius: 6 };
const Waited = ({ item }) => (item.open ? <span className="pill">{item.waited}</span> : null);

function Answered({ answer, text }) {
  const source = answerSourceLine(answer);
  const how = answer.via === "voice" ? "by voice" : answer.via === "text" ? "typed" : "";
  return (
    <p className="small">
      {text} <span className="muted">{answer.by} · {label(answer.at_ms)}{how ? ` · ${how}` : ""}{source ? ` · ${source}` : ""}</span>
    </p>
  );
}

function QuestionCard({ q, item, role, name, busy, act, ask }) {
  const path = `/questions/${q.id}/answer`;
  const hear = (file) => ask("/ask/hear", file, { by: DOCTOR }, path);
  const send = ({ text, heard }) => act(path, { text, by: DOCTOR, ...answerHow(heard?.text, text, heard?.by) });
  return (
    <article className="card inbox-card" data-line={q.id}>
      <p className="small muted">{q.by} · {label(q.at_ms)} <Waited item={item} /></p>
      <p className="quote">{"\u201c"}{questionText(role, q)}{"\u201d"}</p>
      {q.answer && <Answered answer={q.answer} text={q.answer.text} />}
      {!q.answer && role === "doctor" && (
        <section aria-label={`Your answer to ${q.by} at ${label(q.at_ms)}`}>
          <Dictate bare label="Your answer" field="Your answer (check it before sending)" placeholder="Type or say your answer" verb={sendVerb(name)} maxLength={1000} busy={busy} onHear={hear} onSend={send} />
        </section>
      )}
    </article>
  );
}

// A question the record bot already answered, shown to staff with its answer as one AI moment.
function RecordBotItem({ q, moment, role, episodeId }) {
  return (
    <article className="card inbox-card" data-line={q.id}>
      <p className="label">Answered by record bot</p>
      <p className="small muted">{q.by} · {label(q.at_ms)}</p>
      <p className="quote">{"\u201c"}{questionText(role, q)}{"\u201d"}</p>
      {moment && <AiMoment moment={moment} role={role} episodeId={episodeId} />}
    </article>
  );
}

function ReviewCard({ r, item, role, busy, act, reference }) {
  const [note, setNote] = useState("");
  const [noting, setNoting] = useState(false);
  const decide = (decision) => act(`/reviews/${r.id}/answer`, { decision, note: note.trim(), by: DOCTOR });
  return (
    <article className="card inbox-card" data-line={r.id}>
      <p className="label">Healing photo</p>
      <p className="small muted">{r.by} · {label(r.at_ms)} <Waited item={item} /></p>
      {noteText(role, r) && <p className="quote">{"\u201c"}{noteText(role, r)}{"\u201d"}</p>}
      <div className="row">
        <figure>
          <img src={r.photo.url} alt="Healing photo to review" width={96} height={96} style={THUMB} />
          <figcaption className="small muted">{photoDay(r.at_ms)}</figcaption>
        </figure>
        {reference && (
          <figure>
            <img src={reference.url} alt={`Reference photo by ${reference.by}`} width={96} height={96} style={THUMB} />
            <figcaption className="small muted">After surgery</figcaption>
          </figure>
        )}
      </div>
      {r.answer && <Answered answer={{ ...r.answer, via: "", source: "" }} text={`${r.answer.label}${r.answer.note ? `: ${r.answer.note}` : ""}`} />}
      {!r.answer && role === "doctor" && (
        <>
          {noting ? (
            <label className="field">
              Note (optional)
              <input maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
          ) : (
            <button type="button" className="quiet" onClick={() => setNoting(true)}>+ add a note</button>
          )}
          <div className="row">
            {DECISIONS.map(([id, name]) => <button key={id} type="button" disabled={busy} onClick={() => decide(id)}>{name}</button>)}
          </div>
        </>
      )}
    </article>
  );
}

// The conversation with the patient: open cards first, then answered ones and check-ins in a fold. Only the doctor can answer.
export default function AskInbox({ view, role, name, nowMs, busy, act, ask, fault, episodeId }) {
  const items = inboxItems(view, role, nowMs);
  const checkins = view.ask?.checkins || [];
  if (!items.length && !checkins.length) return null;
  const questions = new Map((view.ask?.questions || []).map((q) => [q.id, q]));
  const reviews = new Map((view.ask?.reviews || []).map((r) => [r.id, r]));
  const references = (view.photos || []).filter((p) => p.purpose === "reference");
  const reference = references[references.length - 1];
  const { open, answered } = inboxGroups(items);
  const card = (item) => (item.kind === "bot"
    ? <RecordBotItem key={item.id} q={questions.get(item.id)} moment={botMoment(view, item.id)} role={role} episodeId={episodeId} />
    : item.kind === "question"
    ? <QuestionCard key={item.id} q={questions.get(item.id)} item={item} role={role} name={name} busy={busy} act={act} ask={ask} />
    : <ReviewCard key={item.id} r={reviews.get(item.id)} item={item} role={role} busy={busy} act={act} reference={reference} />);
  return (
    <section aria-label="Ask inbox">
      <p className="label">{inboxHeader(name, items)}</p>
      <Fault fault={fault} episodeId={episodeId} only={INBOX_SCOPES} />
      {open.map(card)}
      {(answered.length > 0 || checkins.length > 0) && (
        <details className="answered-fold" key={open.length ? "some" : "none"} open={open.length === 0}>
          <summary>Answered ({answered.length})</summary>
          {answered.map(card)}
          {checkins.map((c) => <p className="small" key={c.id} data-line={c.id}>{checkinLine(c)}</p>)}
        </details>
      )}
    </section>
  );
}
