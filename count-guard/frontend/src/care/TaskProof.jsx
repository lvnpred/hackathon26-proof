import PhotoInput from "./PhotoInput.jsx";
import { useState } from "react";
import { EvidenceThumb } from "./Evidence.jsx";
import ObsForm from "./ObsForm";
import { prefillObs } from "./capture";
import { doneBody, MATCH_LABEL, newestPhoto } from "./drafts";
import { momentFor } from "./moments.js";
import { FROM_VOICE, isPrepared, sourceWords } from "./source.js";
import Provenance from "./Provenance.jsx";
import Source from "./Source.jsx";
import { obsValues } from "./tasklist";
import ProofItem from "./ProofItem.jsx";
import { checkFor } from "./verdict.js";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, outcomeOf, own } from "./stepOutcome.js";

const strings = (values) => Object.fromEntries(Object.entries(values || {}).map(([k, v]) => [k, String(v)]));

// Confirm one task: the words said, the values, a photo, then Confirm. Nothing is saved until Confirm.
// A strip or monitor read that does not match is flagged and Confirm stays on (D9). The photo's verdict is U9:
// Photo does not match or Not checked refuses Confirm until a new photo is accepted or the nurse overrides with a reason.
// session: { proposal: { candidates: [task], values }, via, transcript, source, heardBy, edited?, heardText? }.
// The heard values (the AI's proposal) go with Confirm, so a value the nurse changed reads "Changed by" (clarity §4.3).
export default function TaskProof({ view, task, session, by, busy, act, upload, onClear }) {
  const [form, setForm] = useState(() => strings(session.proposal.values));
  const [photo, setPhoto] = useState(null);
  const [filled, setFilled] = useState(0); // bumps when a photo fills the form, so ObsForm shows it
  const [error, setError] = useState("");
  // A monitor photo is read by Spark; a proof photo is checked by Spark. The step line sits in this card.
  const photoStep = useModelStep({ capability: task.kind === "obs" ? "monitor" : "photo" });

  async function addPhoto([file]) {
    const stated = task.kind === "obs" ? obsValues(form).values || {} : {};
    const fields = { purpose: "proof", task_id: task.id, by, sbp: stated.sbp, dbp: stated.dbp, hr: stated.hr };
    took(await photoStep.run((o) => upload("/photos", file, fields, undefined, own(o)),
      { what: "photo", outcome: (v) => outcomeOf(newestPhoto(v, task.id)?.check) || UNKNOWN }));
  }

  function took(next) {
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
    const out = doneBody({ task, via: session.via, transcript: session.transcript, form, photo, heardBy: session.heardBy,
      proposed: session.proposal.values, edited: session.edited, heardText: session.heardText });
    if (out.error) return setError(out.error);
    setError("");
    if (await act(`/tasks/${task.id}/done`, { by, ...out.body })) onClear();
  }

  const photoMoment = momentFor(view, photo?.check?.evidence_id);
  return (
    <section className="card" aria-label="Confirm task" aria-busy={busyOf(photoStep.step)}>
      <p className="label">Confirm task</p>
      <p className="small">{task.title}</p>
      {session.transcript && (
        <p className="small">
          “{session.transcript}” <Source words={session.via === "voice" ? FROM_VOICE : null} prepared={session.via === "voice" && isPrepared({ heard_by: session.heardBy })} />
          {/* Heard values stay the AI's proposal until Confirm saves them (then the row reads Accepted by …). */}
          {session.via === "voice" && <> <Provenance item={{ id: task.id, ai: session.ai === true }} events={[]} /></>}
        </p>
      )}
      {task.kind === "obs" && <ObsForm key={`${task.id}:${filled}`} busy={busy} initial={form} onChange={setForm} />}
      <PhotoInput disabled={busy} onFiles={addPhoto} />
      <ModelStep busy={busy} step={photoStep.step} onRetry={async () => took(await photoStep.retry())} />
      {photo && (
        <p className="small">
          <span className={`pill ${photo.check?.match === "mismatch" ? "sun" : "info"}`}>{MATCH_LABEL[photo.check?.match] || MATCH_LABEL.none}</span>{" "}
          <Source words={sourceWords(photoMoment)} prepared={isPrepared(photoMoment || photo.check)} />{" "}
          {photo.check?.why}
        </p>
      )}
      {photo && (
        <ProofItem check={checkFor(view, `task:${task.id}`)} label={task.title} busy={busy} acts={view.acts}
          onOverride={(reason) => act(`/checks/task:${task.id}/override`, { reason, by })} />
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
