import { useState } from "react";
import { OBS_FIELDS, obsValues } from "./tasklist";

// Observation inputs. With `onChange` and no `onSave`, the parent owns the button (TaskProof).
export default function ObsForm({ busy, onSave, onChange, initial = {} }) {
  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const edit = (next) => { setForm(next); onChange?.(next); };
  function save() {
    const out = obsValues(form);
    if (out.error) return setError(out.error);
    setError("");
    Promise.resolve(onSave(out.values)).then((next) => next && setForm({}));
  }
  return (
    <div className="row">
      {OBS_FIELDS.map(([key, label]) => (
        <label className="field" key={key} style={{ flex: "1 1 70px" }}>
          {label}
          <input inputMode="decimal" value={form[key] || ""} onChange={(event) => edit({ ...form, [key]: event.target.value })} />
        </label>
      ))}
      {onSave && <button type="button" className="primary" disabled={busy} onClick={save}>Mark done</button>}
      {error && <p className="error small" role="alert">{error}</p>}
    </div>
  );
}
