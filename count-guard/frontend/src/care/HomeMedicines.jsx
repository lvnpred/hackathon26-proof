import { useState } from "react";
import { parseStrips } from "../journey";
import AiMoment from "./AiMoment.jsx";
import { DOCTOR } from "./DoctorActions";
import { stripMoments } from "./moments.js";
import PhotoInput from "./PhotoInput.jsx";
import Source from "./Source.jsx";
import { FROM_PHOTO, isPrepared } from "./source.js";

// One doctor action for the medicines a patient takes at home: a photo first, typing as the quiet way out (R11).
// Each medicine shows its match to the prescription. A photo that reads nothing says so in the fault line.
export default function HomeMedicines({ view, busy, upload, act }) {
  const [typing, setTyping] = useState(false);
  const [lines, setLines] = useState("");
  const { strips, nudges } = stripMoments(view);
  const episodeId = view.episode?.id;

  return (
    <section className="card" aria-label="Photo of medicines from home">
      <p className="label">Photo of medicines from home</p>
      <PhotoInput disabled={busy} onFiles={([file]) => upload("/strips/photo", file, { by: DOCTOR })} />
      <button type="button" className="quiet" aria-expanded={typing} onClick={() => setTyping(!typing)}>Type instead</button>
      {typing && (
        <>
          <label className="field">
            One medicine per line: name then strength
            <textarea rows={3} value={lines} onChange={(e) => setLines(e.target.value)} />
          </label>
          <button type="button" disabled={busy || !lines.trim()} onClick={() => act("/strips", { strips: parseStrips(lines) })}>
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
    </section>
  );
}
