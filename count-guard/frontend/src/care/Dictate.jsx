import { useEffect, useId, useRef, useState } from "react";
import { isPrepared, sourceWords } from "./source.js";
import Source from "./Source.jsx";
import { audioName, micStatus, pickMime } from "./recorder";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { hearWith, heardWords } from "./dictateFlow.js";

const MIC = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <rect x="9" y="3" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

// One voice-first box: record with the mic, upload audio, or type. A recording is heard first and its text
// fills the box to check. bare: no card or region of its own (the caller supplies them).
// onHear(file, opts) -> { text, heard_by } | null, where opts is the voice step's { onProgress, signal, timeoutMs }.
// onSend({ text, heard }, opts) -> truthy when done. With `sendCapability` the send is a model step of its own
// (drafting with Spark): its line shows under the button and `sendOutcome(result)` says how the model did.
// `sendStep` (a useModelStep from the caller) runs the send instead; the caller then shows its line.
// Expand (clarity §4.2): the heard line opens what was recorded and heard; the send line opens `sendRecord(result)`.
// `view` (the chart view) gives the Expand its episode and the person acts.
// autoSend: a recording once heard is sent at once (one step: record, hear, send); typed text still waits for the button.
// Each step line sits in this box (spec §4.1): recording timer, upload, checking, done or Didn't work + Retry.
export default function Dictate({ label, field = "What was said", verb, capability = "task_voice", placeholder, busy, maxLength = 2000, bare = false, lens = "staff", autoSend = false, sendCapability, sendStep, sendOutcome, sendRecord, view, onHear, onSend }) {
  const boxId = useId();
  const [recording, setRecording] = useState(false);
  const [text, setText] = useState("");
  const [heard, setHeard] = useState(null);
  const [message, setMessage] = useState("");
  const recorder = useRef(null);
  const stream = useRef(null);
  const hearRef = useRef(onHear);
  hearRef.current = onHear;
  const mounted = useRef(true); // a step can finish after this box unmounted (the "Dictate again" fold remounts it)
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const hearing = useModelStep({ capability: "voice", lens });
  const ownSend = useModelStep({ capability: sendCapability, lens });
  const sending = sendStep || ownSend; // a caller's step (its line shown by the caller) outlives this box
  const working = [hearing.step, sending.step].some((s) => s.stage === "uploading" || s.stage === "checking");

  const release = () => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  };
  useEffect(() => () => {
    if (recorder.current?.state === "recording") recorder.current.onstop = null;
    release();
  }, []);

  function heardIt(result) {
    if (!mounted.current) return;
    if (!result) return;
    const said = { text: result.text, by: result.heard_by, audio_id: result.audio_id };
    setText(result.text);
    setHeard(said);
    if (autoSend && result.text?.trim()) sendSaid({ text: result.text.trim(), heard: said });
  }
  const hear = async (file) => heardIt(await hearWith(hearing, (f, opts) => hearRef.current(f, opts), file));

  async function start() {
    const hasMediaDevices = Boolean(navigator.mediaDevices?.getUserMedia);
    const hasRecorder = typeof window.MediaRecorder === "function";
    const mime = hasRecorder ? pickMime((type) => window.MediaRecorder.isTypeSupported(type)) : "";
    const unavailable = micStatus({ hasMediaDevices, hasRecorder, mime });
    if (!unavailable.ok) return setMessage(unavailable.message);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return setMessage(micStatus({ hasMediaDevices, hasRecorder, mime, denied: true }).message);
    }
    const chunks = [];
    const rec = new window.MediaRecorder(stream.current, { mimeType: mime });
    rec.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    rec.onstop = () => {
      release();
      setRecording(false);
      hearing.stopRecording();
      hear(new File(chunks, audioName(mime), { type: mime }));
    };
    recorder.current = rec;
    rec.start();
    setMessage("");
    setRecording(true);
    hearing.startRecording();
  }

  const finish = () => recorder.current?.stop();

  async function chooseFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await hear(file);
  }

  function sent(done) {
    if (!mounted.current) return;
    if (!done) return;
    setText("");
    setHeard(null);
    hearing.reset();
  }
  const send = () => sendSaid({ text: text.trim(), heard });
  async function sendSaid(said) {
    if (!sendCapability && !sendStep) return sent(await onSend(said));
    const outcome = { ...(sendOutcome ? { outcome: sendOutcome } : {}), ...(sendRecord ? { record: sendRecord } : {}) };
    return sent(await sending.run((opts) => onSend(said, opts), outcome));
  }

  const Wrap = bare ? "div" : "section";
  const wrapProps = bare ? { className: "stack" } : { className: "card", "aria-label": label };
  return (
    <Wrap {...wrapProps} aria-busy={working}>
      <p className="label">{label}</p>
      <div className="field">
        <label htmlFor={boxId}>{field}</label>
        <div className="dictate-box">
          <textarea id={boxId} rows={3} maxLength={maxLength} placeholder={placeholder} value={text} onChange={(e) => setText(e.target.value)} />
          <button
            type="button"
            className={`dictate-mic${recording ? " recording" : ""}`}
            aria-label={recording ? "Finish recording" : "Record"}
            disabled={(busy || working) && !recording}
            onClick={recording ? finish : start}
          >
            {MIC}
          </button>
        </div>
      </div>
      {message && <p className="note small" role="status">{message}</p>}
      <ModelStep busy={busy} step={hearing.step} lens={lens} onRetry={async () => heardIt(await hearing.retry())} expand={{ view, title: "Recording heard" }} />
      {/* The From voice mark stays while the heard text is edited, until it is sent (clarity §4.3). */}
      {heard && text.trim() && <p className="small"><Source words={heardWords(sourceWords({ kind: "voice", capability }), heard.text, text)} prepared={isPrepared({ heard_by: heard.by })} /></p>}
      <label className={`dictate-upload${busy || recording || working ? " disabled" : ""}`}>
        Upload audio
        <input className="visually-hidden" type="file" accept="audio/*" disabled={busy || recording || working} onChange={chooseFile} />
      </label>
      <button type="button" disabled={busy || recording || working || !text.trim()} onClick={send}>{verb}</button>
      {!sendStep && <ModelStep busy={busy} step={sending.step} lens={lens} onRetry={async () => sent(await sending.retry())} expand={{ view, title: label }} />}
    </Wrap>
  );
}
