import { useState } from "react";
import Fault from "./Fault";
import { correctionBody, correctorFor, fieldsFor } from "./correct.js";

const SCOPE = "/correct";

// Correct one recorded line (spec §9): Inspector → History, and the theatre drug row. Blank fields keep their value.
// The new line replaces the old one on the chart; the old one stays in the record. `by` is the person correcting:
// given by the panel, else the person in the role.
export default function Correct({ written, role, by, episodeId, act, busy, fault }) {
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  async function save(event) {
    event.preventDefault();
    const got = correctionBody(written, form, by || correctorFor(role));
    if (got.error) return setError(got.error);
    setError("");
    if (await act(SCOPE, got.body, SCOPE)) {
      setForm(null);
      setDone("Corrected. The earlier line stays in the record.");
    }
  }

  if (!form) {
    return (
      <>
        {" "}
        <button type="button" className="quiet" disabled={busy} onClick={() => { setForm({}); setDone(""); }}>Correct</button>
        {done && <span className="small muted" role="status"> {done}</span>}
      </>
    );
  }
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <form className="card" onSubmit={save} aria-label="Correct this line">
      <p className="small muted">Type only what was wrong. Blank fields keep the recorded value.</p>
      {fieldsFor(written.type).map(([key, label, kind, options]) => (
        <label key={key} className="field">
          {label}
          {kind === "choice" ? (
            <select value={form[key] ?? ""} onChange={set(key)}>
              <option value="">Keep as recorded</option>
              {options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input inputMode={kind === "text" ? "text" : kind === "int" ? "numeric" : "decimal"} value={form[key] ?? ""} onChange={set(key)} />
          )}
        </label>
      ))}
      {error && <p className="error small" role="alert">{error}</p>}
      <Fault fault={fault} episodeId={episodeId} only={[SCOPE]} />
      <div className="row">
        <button type="submit" disabled={busy}>Save correction</button>
        <button type="button" className="quiet" onClick={() => { setForm(null); setError(""); }}>Cancel</button>
      </div>
    </form>
  );
}
