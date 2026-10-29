import { useEffect, useRef, useState } from "react";
import { audioName, micStatus, pickMime } from "./recorder";

// Record, choose an audio file, or type what was said. onSend({ file } | { text }) returns a promise.
export default function Dictate({ label, busy, onSend }) {
  const [recording, setRecording] = useState(false);
  const [typed, setTyped] = useState("");
  const [message, setMessage] = useState("");
  const recorder = useRef(null);
  const stream = useRef(null);

  const release = () => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  };
  useEffect(() => () => {
    if (recorder.current?.state === "recording") recorder.current.onstop = null;
    release();
  }, []);

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
      onSend({ file: new File(chunks, audioName(mime), { type: mime }) });
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
    if (file) await onSend({ file });
  }

  async function sendText() {
    if (await onSend({ text: typed.trim() })) setTyped("");
  }

  return (
    <section className="card" aria-label={label}>
      <p className="label">{label}</p>
      <div className="row">
        {recording
          ? <button type="button" className="primary" onClick={finish}>Finish recording</button>
          : <button type="button" disabled={busy} onClick={start}>Record</button>}
      </div>
      {message && <p className="note small" role="status">{message}</p>}
      <label className="field">
        Or choose an audio file
        <input type="file" accept="audio/*" disabled={busy || recording} onChange={chooseFile} />
      </label>
      <label className="field">
        Or type what was said
        <textarea rows={2} value={typed} onChange={(e) => setTyped(e.target.value)} />
      </label>
      <button type="button" disabled={busy || recording || !typed.trim()} onClick={sendText}>Use this text</button>
    </section>
  );
}
