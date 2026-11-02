import { useState } from "react";
import { newPatient, syncWard } from "../journey";
import { newPatientError, syncSummary } from "./wardForm";

// Sync and New patient sit above the ward list, for staff only. The ward is read again right after either.
export default function WardActions({ role, onChanged = () => {} }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  if (role === "patient") return null;

  async function sync() {
    setBusy(true);
    setMessage("");
    try {
      const got = await syncWard();
      setMessage(got.error || syncSummary(got));
      onChanged();
    } catch (exc) {
      setMessage(exc.message);
    } finally {
      setBusy(false);
    }
  }

  async function add(event) {
    event.preventDefault();
    const problem = newPatientError(form);
    if (problem) return setError(problem);
    setBusy(true);
    setError("");
    try {
      await newPatient(form);
      setForm(null);
      setMessage("Patient added.");
      onChanged();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  return (
    <section className="ward-actions" aria-label="Ward actions">
      <button type="button" disabled={busy} onClick={sync}>Sync</button>
      <button type="button" disabled={busy} onClick={() => { setForm(form ? null : { name: "", ageSex: "", reason: "" }); setError(""); }}>New patient</button>
      {message && <p role="status" className="small">{message}</p>}
      {form && (
        <form onSubmit={add}>
          <label className="field">Name<input value={form.name} onChange={set("name")} maxLength={80} /></label>
          <label className="field">Age and sex<input value={form.ageSex} onChange={set("ageSex")} maxLength={20} placeholder="52 F" /></label>
          <label className="field">Reason<input value={form.reason} onChange={set("reason")} maxLength={300} /></label>
          {error && <p className="error small" role="alert">{error}</p>}
          <button type="submit" disabled={busy}>Add patient</button>
        </form>
      )}
    </section>
  );
}
