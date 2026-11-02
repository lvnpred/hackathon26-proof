import { useState } from "react";
import { DOCTOR } from "./DoctorActions";
import { bedProblem } from "./header.js";

// The doctor moves the patient to another bed. The server refuses a bed someone else holds.
export default function BedChange({ bed, act, busy }) {
  const [open, setOpen] = useState(false);
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  if (!open) {
    return <button type="button" className="quiet" disabled={busy} onClick={() => { setNext(""); setError(""); setOpen(true); }}>Change bed</button>;
  }
  async function save() {
    const problem = bedProblem(next, bed);
    if (problem) return setError(problem);
    setError("");
    if (await act("/bed", { bed: next.trim(), by: DOCTOR }, "/bed")) setOpen(false);
  }
  return (
    <div className="row">
      <label className="field">
        New bed
        <input value={next} maxLength={8} onChange={(event) => setNext(event.target.value)} />
      </label>
      <button type="button" disabled={busy} onClick={save}>Move</button>
      <button type="button" className="quiet" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
      {error && <p className="error small" role="alert">{error}</p>}
    </div>
  );
}
