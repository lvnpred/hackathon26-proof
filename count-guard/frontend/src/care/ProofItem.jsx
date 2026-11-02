import { useState } from "react";
import PhotoInput from "./PhotoInput.jsx";
import StatusPill from "./StatusPill.jsx";
import { proofLabel, proofTone } from "./verdict.js";

// One photo check (spec §6.6, U9): the verdict line, a photo button, and while the item is open an override
// with a typed reason. onPhoto is left out where the photo is taken elsewhere (a task's Confirm card).
export default function ProofItem({ check, label, busy, onPhoto, onOverride }) {
  const [reason, setReason] = useState("");
  const retake = check.state !== "none";
  async function override() {
    if (await onOverride(reason.trim())) setReason("");
  }
  return (
    <section className="proof-item" aria-label={`Photo check: ${label}`}>
      <p className="small">
        <StatusPill role={proofTone(check)} text={proofLabel(check)} />
        {check.photo_url && <> <a href={check.photo_url} target="_blank" rel="noreferrer">See photo</a></>}
      </p>
      {onPhoto && <PhotoInput label={retake ? "Take the photo again" : "Take photo"} disabled={busy} onFiles={([file]) => onPhoto(file)} />}
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
