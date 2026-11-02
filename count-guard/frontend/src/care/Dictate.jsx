import { useEffect, useId, useRef, useState } from "react";
import { isPrepared, sourceWords } from "./source.js";
import Source from "./Source.jsx";
import { audioName, micStatus, pickMime } from "./recorder";

const MIC = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <rect x="9" y="3" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

// One voice-first box: record with the mic, upload audio, or type. A recording is heard first and its text
// fills the box to check. bare: no card or region of its own (the caller supplies them). onHear(file) -> { text, heard_by } | null. onSend({ text, heard }) -> truthy when done.
export default function Dictate({ label, field = "What was said", verb, capability = "task_voice", placeholder, busy, maxLength = 2000, bare = false, onHear, onSend }) {
  const boxId = useId();
  const [recording, setRecording] = useState(false);
  const [text, setText] = useState("");
  const [heard, setHeard] = useState(null);
  const [message, setMessage] = useState("");
  const recorder = useRef(null);
  const stream = useRef(null);
  const hearRef = useRef(onHear);
  hearRef.current = onHear;

  const release = () => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  };
  useEffect(() => () => {
    if (recorder.current?.state === "recording") recorder.current.onstop = null;
    release();
  }, []);

  async function hear(file) {
    const result = await hearRef.current(file);
    if (!result) return;
    setText(result.text);
    setHeard({ text: result.text, by: result.heard_by });
  }

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
      hear(new File(chunks, audioName(mime), { type: mime }));
    };
    recorder.current = rec;
    rec.start();
    setMessage("");
    setRecording(true);
  }

  const finish = () => recorder.current?.stop();

  async function chooseFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await hear(file);
  }

  async function send() {
    if (await onSend({ text: text.trim(), heard })) {
      setText("");
      setHeard(null);
    }
  }

  const Wrap = bare ? "div" : "section";
  const wrapProps = bare ? { className: "stack" } : { className: "card", "aria-label": label };
  return (
    <Wrap {...wrapProps}>
      <p className="label">{label}</p>
      <div className="field">
        <label htmlFor={boxId}>{field}</label>
        <div className="dictate-box">
          <textarea id={boxId} rows={3} maxLength={maxLength} placeholder={placeholder} value={text} onChange={(e) => setText(e.target.value)} />
          <button
            type="button"
            className={`dictate-mic${recording ? " recording" : ""}`}
            aria-label={recording ? "Finish recording" : "Record"}
            disabled={busy && !recording}
            onClick={recording ? finish : start}
          >
            {MIC}
          </button>
        </div>
      </div>
      {message && <p className="note small" role="status">{message}</p>}
      {heard && heard.text === text && <p className="small"><Source words={sourceWords({ kind: "voice", capability })} prepared={isPrepared({ heard_by: heard.by })} /></p>}
      <label className={`dictate-upload${busy || recording ? " disabled" : ""}`}>
        Upload audio
        <input className="visually-hidden" type="file" accept="audio/*" disabled={busy || recording} onChange={chooseFile} />
      </label>
      <button type="button" disabled={busy || recording || !text.trim()} onClick={send}>{verb}</button>
    </Wrap>
  );
}
