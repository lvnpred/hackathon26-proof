import { useState } from "react";
import { EvidenceThumb } from "./Evidence.jsx";
import ObsForm from "./ObsForm";
import { doneBody, MATCH_LABEL, newestPhoto, sourceLabel } from "./drafts";
import { obsValues } from "./tasklist";

const strings = (values) => Object.fromEntries(Object.entries(values || {}).map(([k, v]) => [k, String(v)]));

// Confirm one task: the words said, the values, a photo, then Confirm. Nothing is saved until Confirm.
// A photo that does not match is flagged and Confirm stays on (D9).
// session: { proposal: { candidates: [task], values }, via, transcript, source, heardBy }.
export default function TaskProof({ view, task, session, by, busy, act, upload, onClear }) {
  const [form, setForm] = useState(() => strings(session.proposal.values));
  const [photo, setPhoto] = useState(null);
  const [error, setError] = useState("");

  async function addPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const stated = task.kind === "obs" ? obsValues(form).values || {} : {};
    const next = await upload("/photos", file, { purpose: "proof", task_id: task.id, by, sbp: stated.sbp, dbp: stated.dbp, hr: stated.hr });
    if (next) setPhoto(newestPhoto(next, task.id));
  }

  async function confirm() {
    if (task.mode === "start_end" && task.status !== "running") {
      if (await act(`/tasks/${task.id}/begin`, { by })) onClear();
      return;
    }
    const out = doneBody({ task, via: session.via, transcript: session.transcript, form, photo, heardBy: session.heardBy });
    if (out.error) return setError(out.error);
    setError("");
    if (await act(`/tasks/${task.id}/done`, { by, ...out.body })) onClear();
  }

  return (
    <section className="card" aria-label="Confirm task">
      <p className="label">Confirm task</p>
      <p className="small">{task.title}</p>
      {session.transcript && (
        <p className="small">
          “{session.transcript}” <span className="muted">· {sourceLabel(session.source)}</span>
          {session.heardBy && session.via === "voice" && <span className="muted"> · Heard by: {sourceLabel(session.heardBy)}</span>}
        </p>
      )}
      {task.kind === "obs" && <ObsForm key={task.id} busy={busy} initial={form} onChange={setForm} />}
      <label className="field">
        Add photo
        <input type="file" accept="image/*" capture="environment" disabled={busy} onChange={addPhoto} />
      </label>
      {photo && (
        <p className="small">
          <span className={`pill ${photo.check?.match === "mismatch" ? "sun" : "info"}`}>{MATCH_LABEL[photo.check?.match] || MATCH_LABEL.none}</span>{" "}
          <span className="muted">({sourceLabel(photo.check?.source)})</span>{" "}
          {photo.check?.why}
        </p>
      )}
      {photo?.check?.evidence_id && <EvidenceThumb episodeId={view.episode?.id} evidenceId={photo.check.evidence_id} version={view.timeline?.length} fallback={<img src={photo.url} alt="Proof photo" width={72} height={72} style={{ objectFit: "cover", borderRadius: 6 }} />} />}
      {error && <p className="error small" role="alert">{error}</p>}
      <div className="row">
        <button type="button" className="primary" disabled={busy} onClick={confirm}>Confirm</button>
        <button type="button" disabled={busy} onClick={onClear}>Cancel</button>
      </div>
    </section>
  );
}
