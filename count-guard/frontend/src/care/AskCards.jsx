import { useEffect, useState } from "react";
import { PHOTO_CLOSED, photoAskOpen, questionProblem } from "./askText.js";
import Fault from "./Fault";
import PhotoInput from "./PhotoInput.jsx";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { own, viewOutcome } from "./stepOutcome.js";
import { momentRecord, newMomentRecord } from "./expandModel.js";
import { ExpandButton } from "./ModelExpand.jsx";

// The newest read of one capability stays on the card with its Expand (patient lens: plain words, no raw reply).
const latestOf = (view, cap) => (view?.ai_moments || []).find((m) => m.capability === cap) || null;
function LastRead({ view, cap, title }) {
  const m = latestOf(view, cap);
  if (!m) return null;
  return <p className="small">{m.patient_finding || "Your last photo was read."} <ExpandButton record={momentRecord(m)} view={view} lens="patient" title={title} /></p>;
}

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
      <button disabled={busy || questionProblem(text) !== ""} onClick={onSend}>{button}</button>
    </>
  );
}

// The record bot may ask Spark to word its answer: its step says "Looking in your record… s" (ruling P9).
export function BotCard({ view, busy, act, fault, episodeId }) {
  const [text, setText] = useState("");
  const step = useModelStep({ capability: "wording", lens: "patient" });
  async function send() {
    const next = await step.run((o) => act("/ask/bot", { text: text.trim() }, undefined, own(o)), { what: "question", upload: false, outcome: viewOutcome(view), record: newMomentRecord(view, ["record_bot"]) });
    if (next) setText("");
  }
  return (
    <section className="card" aria-label="Ask your record" aria-busy={busyOf(step.step)}>
      <QuestionForm
        title="Ask your record" button="Ask the record" busy={busy} text={text} setText={setText} onSend={send}
        hint="The record bot quotes lines from your own record."
      />
      <ModelStep busy={busy} step={step.step} lens={step.lens} onRetry={step.retry} expand={{ view, title: "Your record's answer" }} />
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

const PHOTO_TYPES = "image/jpeg,image/png,image/webp";

// The patient's photo cards: each shows its own step line in plain words ("Reading your photo… 3 s"), never a model name.
export function ReviewCard({ view, busy, upload, fault, episodeId }) {
  const [note, setNote] = useState("");
  const step = useModelStep({ capability: "review", lens: "patient" });
  async function send(file) {
    const next = await step.run((o) => upload("/ask/review", file, { note: note.trim() }, undefined, own(o)), { what: "photo", outcome: viewOutcome(view), record: newMomentRecord(view, ["healing_photo"]) });
    if (next) setNote("");
  }
  return (
    <section className="card" aria-label="Healing photo" aria-busy={busyOf(step.step)}>
      <p className="label">Healing photo</p>
      <Fault fault={fault} episodeId={episodeId} only={["/ask/review"]} />
      {photoAskOpen(view.state) ? (
        <>
          <label className="field">
            <span className="small">Note for the doctor (optional)</span>
            <input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
          </label>
          <PhotoInput label="Take photo" accept={PHOTO_TYPES} disabled={busy} onFiles={([file]) => send(file)} />
          <ModelStep busy={busy} step={step.step} lens={step.lens} onRetry={step.retry} expand={{ view, title: "Healing photo" }} />
        </>
      ) : <p className="empty small">{PHOTO_CLOSED}</p>}
      <LastRead view={view} cap="healing_photo" title="Healing photo" />
    </section>
  );
}

export function MedicinesCard({ view, busy, upload, fault, episodeId }) {
  const step = useModelStep({ capability: "medicines", lens: "patient" });
  const send = (file) => step.run((o) => upload("/ask/medicines", file, undefined, undefined, own(o)), { what: "photo", outcome: viewOutcome(view, ["medicines"]), record: newMomentRecord(view, ["medicines"]) });
  return (
    <section className="card" aria-label="Medicines photo" aria-busy={busyOf(step.step)}>
      <p className="label">Medicines photo</p>
      <Fault fault={fault} episodeId={episodeId} only={["/ask/medicines"]} />
      {photoAskOpen(view.state)
        ? <PhotoInput label="Take photo" accept={PHOTO_TYPES} disabled={busy} onFiles={([file]) => send(file)} />
        : <p className="empty small">{PHOTO_CLOSED}</p>}
      <ModelStep busy={busy} step={step.step} lens={step.lens} onRetry={step.retry} expand={{ view, title: "Medicines photo" }} />
      <LastRead view={view} cap="medicines" title="Medicines photo" />
    </section>
  );
}
