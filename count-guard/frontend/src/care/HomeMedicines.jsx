import { useState } from "react";
import { parseStrips } from "../journey";
import AiMoment from "./AiMoment.jsx";
import { DOCTOR } from "./DoctorActions";
import { stripMoments } from "./moments.js";
import PhotoInput from "./PhotoInput.jsx";
import Source from "./Source.jsx";
import { FROM_PHOTO, isPrepared } from "./source.js";
import ModelStep from "./ModelStep.jsx";
import { ExpandButton } from "./ModelExpand.jsx";
import { momentRecord, newMomentRecord } from "./expandModel.js";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { own, viewOutcome } from "./stepOutcome.js";

// One doctor action for the medicines a patient takes at home: a photo first, typing as the quiet way out (R11).
// Each medicine shows its match to the prescription. A photo that reads nothing says so in the fault line.
export default function HomeMedicines({ view, busy, upload, act }) {
  const [typing, setTyping] = useState(false);
  const [lines, setLines] = useState("");
  const { strips, nudges } = stripMoments(view);
  const episodeId = view.episode?.id;
  const step = useModelStep({ capability: "strips" });
  const readPhoto = (file) => step.run((o) => upload("/strips/photo", file, { by: DOCTOR }, undefined, own(o)), { what: "photo", outcome: viewOutcome(view, ["strips"]), record: newMomentRecord(view, ["strips"]) });

  return (
    <section className="card" aria-label="Photo of medicines from home" aria-busy={busyOf(step.step)}>
      <p className="label">Photo of medicines from home</p>
      <PhotoInput disabled={busy} onFiles={([file]) => readPhoto(file)} />
      <ModelStep busy={busy} step={step.step} onRetry={step.retry} expand={{ view, title: "Photo of medicines from home" }} />
      <button type="button" className="quiet" aria-expanded={typing} onClick={() => setTyping(!typing)}>Type instead</button>
      {typing && (
        <>
          <label className="field">
            One medicine per line: name then strength
            <textarea rows={3} value={lines} onChange={(e) => setLines(e.target.value)} />
          </label>
          <button type="button" disabled={busy || !lines.trim()} onClick={() => act("/strips", { strips: parseStrips(lines), by: DOCTOR })}>
            Check these medicines
          </button>
        </>
      )}
      {(view.strips || []).length > 0 && (
        <ul className="plain">
          {view.strips.map((s, i) => (
            <li key={s.match?.id || i}>
              {s.generic || s.name_as_read} {s.strength}: {s.match?.text}{" "}
              {s.source !== "typed" && <Source words={FROM_PHOTO} prepared={isPrepared(s)} />}
            </li>
          ))}
        </ul>
      )}
      {[...strips, ...nudges].map((moment) => <AiMoment key={moment.id} moment={moment} role="doctor" episodeId={episodeId} />)}
      {strips[0] && <p className="small"><ExpandButton record={momentRecord(strips[0])} view={view} title="Photo of medicines from home" label="Expand the photo read" /></p>}
    </section>
  );
}
