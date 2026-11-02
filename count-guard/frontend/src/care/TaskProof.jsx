import PhotoInput from "./PhotoInput.jsx";
import { useState } from "react";
import { EvidenceThumb } from "./Evidence.jsx";
import ObsForm from "./ObsForm";
import { prefillObs } from "./capture";
import { doneBody, MATCH_LABEL, newestPhoto } from "./drafts";
import { momentFor } from "./moments.js";
import { FROM_VOICE, isPrepared, sourceWords } from "./source.js";
import Source from "./Source.jsx";
import { obsValues } from "./tasklist";

const strings = (values) => Object.fromEntries(Object.entries(values || {}).map(([k, v]) => [k, String(v)]));

// Confirm one task: the words said, the values, a photo, then Confirm. Nothing is saved until Confirm.
// A photo that does not match is flagged and Confirm stays on (D9).
// session: { proposal: { candidates: [task], values }, via, transcript, source, heardBy }.
export default function TaskProof({ view, task, session, by, busy, act, upload, onClear }) {
  const [form, setForm] = useState(() => strings(session.proposal.values));
  const [photo, setPhoto] = useState(null);
  const [filled, setFilled] = useState(0); // bumps when a photo fills the form, so ObsForm shows it
  const [error, setError] = useState("");

  async function addPhoto([file]) {
    const stated = task.kind === "obs" ? obsValues(form).values || {} : {};
    const next = await upload("/photos", file, { purpose: "proof", task_id: task.id, by, sbp: stated.sbp, dbp: stated.dbp, hr: stated.hr });
    if (!next) return;
    const added = newestPhoto(next, task.id);
    setPhoto(added);
    if (task.kind === "obs") {
      setForm((current) => prefillObs(added?.check?.regions || [], current));
      setFilled(filled + 1);
    }
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

  const photoMoment = momentFor(view, photo?.check?.evidence_id);
  return (
    <section className="card" aria-label="Confirm task">
      <p className="label">Confirm task</p>
      <p className="small">{task.title}</p>
      {session.transcript && (
        <p className="small">
          “{session.transcript}” <Source words={session.via === "voice" ? FROM_VOICE : null} prepared={session.via === "voice" && isPrepared({ heard_by: session.heardBy })} />
        </p>
      )}
      {task.kind === "obs" && <ObsForm key={`${task.id}:${filled}`} busy={busy} initial={form} onChange={setForm} />}
      <PhotoInput disabled={busy} onFiles={addPhoto} />
      {photo && (
        <p className="small">
          <span className={`pill ${photo.check?.match === "mismatch" ? "sun" : "info"}`}>{MATCH_LABEL[photo.check?.match] || MATCH_LABEL.none}</span>{" "}
          <Source words={sourceWords(photoMoment)} prepared={isPrepared(photoMoment || photo.check)} />{" "}
          {photo.check?.why}
        </p>
      )}
      {photo?.check?.evidence_id && <EvidenceThumb episodeId={view.episode?.id} evidenceId={photo.check.evidence_id} version={view.timeline?.length} fallback={<img src={photo.url} alt="Proof photo" width={72} height={72} style={{ objectFit: "cover", borderRadius: 6 }} />} />}
      {error && <p className="error small" role="alert">{error}</p>}
      <div className="row">
        <button type="button" disabled={busy} onClick={confirm}>Confirm</button>
        <button type="button" disabled={busy} onClick={onClear}>Cancel</button>
      </div>
    </section>
  );
}
