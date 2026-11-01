import { useState } from "react";
import { parseStrips } from "../journey";
import AiMoment from "./AiMoment.jsx";
import { DOCTOR } from "./DoctorActions";
import { stripMoments } from "./moments.js";
import PhotoInput from "./PhotoInput.jsx";

// The clinic strip check: a photo of the strips first, typing as the quiet way out (R11). A photo that reads nothing says so in the fault line.
export default function StripPhoto({ view, busy, upload, act }) {
  const [typing, setTyping] = useState(false);
  const [lines, setLines] = useState("");
  const { strips, nudges } = stripMoments(view);
  const episodeId = view.episode?.id;

  return (
    <section className="card" aria-label="Photo of strips">
      <p className="label">Photo of strips</p>
      <PhotoInput disabled={busy} onFiles={([file]) => upload("/strips/photo", file, { by: DOCTOR })} />
      <button type="button" className="quiet" aria-expanded={typing} onClick={() => setTyping(!typing)}>Type instead</button>
      {typing && (
        <>
          <label className="field">
            One strip per line: name then strength
            <textarea rows={3} value={lines} onChange={(e) => setLines(e.target.value)} />
          </label>
          <button type="button" disabled={busy || !lines.trim()} onClick={() => act("/strips", { strips: parseStrips(lines) })}>
            Check these strips
          </button>
        </>
      )}
      {[...strips, ...nudges].map((moment) => <AiMoment key={moment.id} moment={moment} role="doctor" episodeId={episodeId} />)}
    </section>
  );
}
