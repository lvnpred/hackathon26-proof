import { useState } from "react";
import Opens from "./Opens.jsx";

// A dose the nurse gave, typed or said as one line ("paracetamol 1 g"). The server reads the name and amount.
// Outside an admitted state the card stays, disabled, and says when it opens (clarity §4.4).
export default function DoseGiven({ by, busy: working, act, reason = "" }) {
  const busy = working || Boolean(reason);
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
        <input value={text} disabled={Boolean(reason)} onChange={(e) => { setText(e.target.value); setSent(""); }} placeholder="Paracetamol 1 g" />
      </label>
      <div className="row">
        <button type="button" disabled={busy || !text.trim()} onClick={log}>Log dose</button>
      </div>
      <Opens reason={reason} />
      {sent && <p className="note small" role="status">{sent}</p>}
    </section>
  );
}
