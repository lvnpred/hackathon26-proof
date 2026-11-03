import { useState } from "react";
import PhotoInput from "./PhotoInput.jsx";
import Provenance from "./Provenance.jsx";
import StatusPill from "./StatusPill.jsx";
import { checkFor, proofLabel, proofTone } from "./verdict.js";
import ModelStep from "./ModelStep.jsx";
import { ExpandButton } from "./ModelExpand.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, outcomeOf } from "./stepOutcome.js";

// The check.photo event behind a check row, for the Expand view (clarity §4.2); none before a photo.
const checkRecord = (check) => (check?.event_id ? { eventId: check.event_id, item: check.item, photo_id: check.photo_id } : null);

// One photo check (spec §6.6, U9): the verdict line, a photo button, and while the item is open an override
// with a typed reason. The verdict is the AI's (Proposed by AI) until a person overrides it; a newer photo is the AI's again. onPhoto is left out where the photo is taken elsewhere (a task's Confirm card).
// onPhoto(file, opts) gets the photo step's opts; the step line (upload, Spark checking, done or Didn't work) sits here.
export default function ProofItem({ check, label, busy, onPhoto, onOverride, acts = [], view }) {
  const [reason, setReason] = useState("");
  const expandView = view || { acts }; // the Expand view's person acts (an override answers the check's item)
  const step = useModelStep({ capability: "verdict" });
  const retake = check.state !== "none";
  const sendPhoto = (file) => step.run((o) => onPhoto(file, o), { what: "photo", outcome: (v) => outcomeOf(checkFor(v, check.item)) || UNKNOWN, record: (v) => checkRecord(checkFor(v, check.item)) });
  const record = checkRecord(check);
  async function override() {
    if (await onOverride(reason.trim())) setReason("");
  }
  return (
    <section className="proof-item" aria-label={`Photo check: ${label}`} aria-busy={busyOf(step.step)}>
      <p className="small">
        <StatusPill role={proofTone(check)} text={proofLabel(check)} />
        {check.photo_url && <> <a href={check.photo_url} target="_blank" rel="noreferrer">See photo</a></>}
        {record && <> <ExpandButton record={record} view={expandView} title={`Photo check: ${label}`} /></>}
      </p>
      {["accepted", "not_accepted", "overridden"].includes(check.state) && (
        <p className="small"><Provenance item={{ id: check.item, ai: ["accepted", "not_accepted"].includes(check.state) }} events={check.state === "overridden" ? acts : []} /></p>
      )}
      {onPhoto && <PhotoInput label={retake ? "Take the photo again" : "Take photo"} disabled={busy} onFiles={([file]) => sendPhoto(file)} />}
      {onPhoto && <ModelStep busy={busy} step={step.step} onRetry={step.retry} expand={{ view: expandView, title: `Photo check: ${label}` }} />}
      {check.open && (
        <div className="row">
          <label className="field">
            Reason to override
            <input type="text" value={reason} maxLength={300} disabled={busy} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button type="button" className="quiet" disabled={busy || !reason.trim()} onClick={override}>Override</button>
        </div>
      )}
    </section>
  );
}
