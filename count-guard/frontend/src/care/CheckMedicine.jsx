import { useState } from "react";
import { useCareWard } from "./CareShell";
import Fault from "./Fault";
import PhotoInput from "./PhotoInput.jsx";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { own, viewOutcome } from "./stepOutcome.js";
import { momentRecord, newMomentRecord } from "./expandModel.js";
import { ExpandButton } from "./ModelExpand.jsx";
import { checkMatchLine } from "./checkMedicine.js";

const PHOTO_TYPES = "image/jpeg,image/png,image/webp";

// The patient's own check of one medicine, on My care: a photo first, typing as the quiet way out.
// Both write brownbag.med_found with by "patient" in every state, home included. Each row reads its
// match in the patient's own words (checkMedicine.js); the backend's staff wording is never shown.
// The typed path calls no model, so it has no step line (a step never claims a call that did not happen).
export default function CheckMedicine({ view, episodeId }) {
  const ward = useCareWard();
  const [typing, setTyping] = useState(false);
  const [name, setName] = useState("");
  const [strength, setStrength] = useState("");
  const step = useModelStep({ capability: "strips", lens: "patient" });
  const sendPhoto = (file) => step.run(
    (o) => ward.upload(episodeId, "/strips/photo", file, { by: "patient" }, undefined, own(o)),
    { what: "photo", outcome: viewOutcome(view, ["strips"]), record: newMomentRecord(view, ["strips"]) },
  );
  async function sendTyped() {
    const next = await ward.act(episodeId, "/strips", { strips: [{ name: name.trim(), strength: strength.trim() }], by: "patient" });
    if (next) {
      setName("");
      setStrength("");
    }
  }
  const latest = (view?.ai_moments || []).find((m) => m.capability === "strips") || null;
  const rows = [...(view?.strips || [])].reverse(); // the newest check first
  return (
    <section className="card" aria-label="Check a medicine" aria-busy={busyOf(step.step)}>
      <p className="label">Check a medicine</p>
      <p className="small muted">A photo of one strip, or its typed name. Each is matched to your prescription.</p>
      <Fault fault={ward.fault} episodeId={episodeId} only={["/strips/photo", "/strips"]} />
      <PhotoInput label="Add a photo" accept={PHOTO_TYPES} disabled={ward.busy} onFiles={([file]) => sendPhoto(file)} />
      <ModelStep busy={ward.busy} step={step.step} lens={step.lens} onRetry={step.retry} expand={{ view, title: "Check a medicine" }} />
      <button type="button" className="quiet" aria-expanded={typing} onClick={() => setTyping(!typing)}>Type instead</button>
      {typing && (
        <>
          <label className="field">
            <span className="small">Name</span>
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span className="small">Strength (optional)</span>
            <input value={strength} maxLength={40} onChange={(e) => setStrength(e.target.value)} />
          </label>
          <button type="button" disabled={ward.busy || !name.trim()} onClick={sendTyped}>Check this medicine</button>
        </>
      )}
      {latest && <p className="small">{latest.patient_finding || "Your last photo was read."} <ExpandButton record={momentRecord(latest)} view={view} lens="patient" title="Check a medicine" /></p>}
      {rows.length > 0 && (
        <ul className="plain">
          {rows.map((s, i) => (
            <li key={s.match?.id || i}>
              {s.generic || s.name_as_read} {s.strength}: {checkMatchLine(s.match?.kind)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
