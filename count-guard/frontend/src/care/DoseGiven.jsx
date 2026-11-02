import { useState } from "react";

// A dose the nurse gave, typed or said as one line ("paracetamol 1 g"). The server reads the name and amount.
export default function DoseGiven({ by, busy, act }) {
  const [text, setText] = useState("");
  const [sent, setSent] = useState("");
  async function log() {
    const line = text.trim();
    if (await act("/dose", { text: line, by })) {
      setSent(`Logged: ${line}`);
      setText("");
    }
  }
  return (
    <section className="card" aria-label="Dose given">
      <p className="label">Dose given</p>
      <label className="field">
        What did you give
        <input value={text} onChange={(e) => { setText(e.target.value); setSent(""); }} placeholder="Paracetamol 1 g" />
      </label>
      <div className="row">
        <button type="button" disabled={busy || !text.trim()} onClick={log}>Log dose</button>
      </div>
      {sent && <p className="note small" role="status">{sent}</p>}
    </section>
  );
}
