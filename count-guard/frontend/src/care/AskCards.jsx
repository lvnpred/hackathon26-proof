import { useEffect, useState } from "react";
import { PHOTO_CLOSED, photoAskOpen, questionProblem } from "./askText.js";
import Fault from "./Fault";

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

export function BotCard({ busy, act, fault, episodeId }) {
  const [text, setText] = useState("");
  async function send() {
    const next = await act("/ask/bot", { text: text.trim() });
    if (next) setText("");
  }
  return (
    <section className="card" aria-label="Ask your record">
      <QuestionForm
        title="Ask your record" button="Ask the record" busy={busy} text={text} setText={setText} onSend={send}
        hint="The record bot quotes lines from your own record."
      />
      <Fault fault={fault} episodeId={episodeId} only={["/ask/bot"]} />
    </section>
  );
}

export function DoctorCard({ busy, act, fill, fault, episodeId }) {
  const [text, setText] = useState("");
  // A question the bot could not find is copied here once per request.
  useEffect(() => { if (fill.id) setText(fill.text); }, [fill.id]);
  async function send() {
    const next = await act("/ask/doctor", { text: text.trim() });
    if (next) setText("");
  }
  return (
    <section className="card" aria-label="Ask Dr. Rao">
      <QuestionForm title="Ask Dr. Rao" button="Send to Dr. Rao" busy={busy} text={text} setText={setText} onSend={send} />
      <Fault fault={fault} episodeId={episodeId} only={["/ask/doctor"]} />
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

export function ReviewCard({ view, busy, upload, fault, episodeId }) {
  const [note, setNote] = useState("");
  return (
    <section className="card" aria-label="Healing photo">
      <p className="label">Healing photo</p>
      <Fault fault={fault} episodeId={episodeId} only={["/ask/review"]} />
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
    </section>
  );
}

export function MedicinesCard({ view, busy, upload, fault, episodeId }) {
  return (
    <section className="card" aria-label="Medicines photo">
      <p className="label">Medicines photo</p>
      <Fault fault={fault} episodeId={episodeId} only={["/ask/medicines"]} />
      {photoAskOpen(view.state)
        ? <PhotoInput title="Photograph your medicines" busy={busy} onFile={(file) => upload("/ask/medicines", file)} />
        : <p className="empty small">{PHOTO_CLOSED}</p>}
    </section>
  );
}
