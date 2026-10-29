import { useEffect, useState } from "react";
import { label } from "./clock";
import {
  ASK_DOCTOR, NOT_FOUND, PHOTO_CLOSED, answerByLine, botQuestions, doctorQuestions, latestMedicines,
  latestReview, medicineLine, photoAskOpen, questionProblem,
} from "./ask.js";
import { sourceLabel } from "./drafts";

const WAITING = "Waiting for Dr. Rao";

function QuestionForm({ title, button, busy, text, setText, onSend, hint }) {
  const problem = text ? questionProblem(text) : "";
  return (
    <>
      <p className="label">{title}</p>
      {hint && <p className="small muted">{hint}</p>}
      <label className="field">
        <span className="small">Your question</span>
        <textarea rows={2} value={text} maxLength={400} onChange={(e) => setText(e.target.value)} />
      </label>
      {problem && <p className="note" role="alert">{problem}</p>}
      <button className="primary" disabled={busy || questionProblem(text) !== ""} onClick={onSend}>{button}</button>
    </>
  );
}

export function BotCard({ view, busy, act, onAskDoctor }) {
  const [text, setText] = useState("");
  async function send() {
    const next = await act("/ask/bot", { text: text.trim() });
    if (next) setText("");
  }
  return (
    <section className="card" aria-label="Ask the record">
      <QuestionForm
        title="Ask your record" button="Ask the record" busy={busy} text={text} setText={setText} onSend={send}
        hint="The record bot quotes lines from your own record."
      />
      {botQuestions(view).map((q) => (
        <div key={q.id} className="stack">
          <p className="small"><b>{q.text}</b></p>
          {q.answer && (
            <>
              <p>{q.answer.found ? q.answer.text : NOT_FOUND}</p>
              {q.answer.found && (
                <ul>{(q.answer.sources || []).map((line) => <li key={line.id}><q>{line.text}</q></li>)}</ul>
              )}
              <p className="small muted">{answerByLine(q.answer)}</p>
              {!q.answer.found && <button onClick={() => onAskDoctor(q.text)}>{ASK_DOCTOR}</button>}
            </>
          )}
        </div>
      ))}
    </section>
  );
}

export function DoctorCard({ view, busy, act, fill }) {
  const [text, setText] = useState("");
  // A question the bot could not find is copied here once per request.
  useEffect(() => { if (fill.id) setText(fill.text); }, [fill.id]);
  async function send() {
    const next = await act("/ask/doctor", { text: text.trim() });
    if (next) setText("");
  }
  return (
    <section className="card" aria-label="Ask the doctor">
      <QuestionForm title="Ask Dr. Rao" button="Send to Dr. Rao" busy={busy} text={text} setText={setText} onSend={send} />
      {doctorQuestions(view).map((q) => (
        <div key={q.id} className="stack">
          <p className="small"><b>{q.text}</b> <span className="muted">{label(q.at_ms)}</span></p>
          {q.answer ? (
            <>
              <p>{q.answer.text}</p>
              <p className="small muted">{answerByLine(q.answer)}</p>
            </>
          ) : <p className="small muted">{WAITING}</p>}
        </div>
      ))}
    </section>
  );
}

function PhotoInput({ title, busy, onFile, children }) {
  return (
    <label className="field">
      <span className="small">{title}</span>
      <input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy}
        onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) onFile(file); }} />
      {children}
    </label>
  );
}

export function ReviewCard({ view, busy, upload }) {
  const [note, setNote] = useState("");
  const review = latestReview(view);
  return (
    <section className="card" aria-label="Healing photo">
      <p className="label">Healing photo</p>
      {photoAskOpen(view.state) ? (
        <>
          <label className="field">
            <span className="small">Note for the doctor (optional)</span>
            <input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
          </label>
          <PhotoInput title="Send a healing photo" busy={busy} onFile={async (file) => {
            const next = await upload("/ask/review", file, { note: note.trim() });
            if (next) setNote("");
          }} />
        </>
      ) : <p className="empty small">{PHOTO_CLOSED}</p>}
      {review && (
        <div className="stack">
          <img src={review.photo.url} alt="Your healing photo" width={96} height={96} style={{ objectFit: "cover", borderRadius: 6 }} />
          {review.note && <p className="small">{review.note}</p>}
          {review.answer ? (
            <p>{review.answer.label}{review.answer.note && <> · {review.answer.note}</>} <span className="small muted">{review.answer.by}</span></p>
          ) : <p className="small muted">{WAITING}</p>}
        </div>
      )}
    </section>
  );
}

export function MedicinesCard({ view, busy, upload }) {
  const read = latestMedicines(view);
  return (
    <section className="card" aria-label="Medicine photo">
      <p className="label">Medicines photo</p>
      {photoAskOpen(view.state)
        ? <PhotoInput title="Photograph your medicines" busy={busy} onFile={(file) => upload("/ask/medicines", file)} />
        : <p className="empty small">{PHOTO_CLOSED}</p>}
      {read && (
        <div className="stack">
          <img src={read.photo.url} alt="Your medicines photo" width={96} height={96} style={{ objectFit: "cover", borderRadius: 6 }} />
          <ul className="task-list">
            {read.rows.map((row, i) => (
              <li key={i}><span className={row.flag ? "pill sun" : ""}>{medicineLine(row)}</span></li>
            ))}
          </ul>
          <p className="small">{read.why} <span className="muted">({sourceLabel(read.source)})</span></p>
        </div>
      )}
    </section>
  );
}
