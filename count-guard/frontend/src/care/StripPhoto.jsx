import { useState } from "react";
import { parseStrips } from "../journey";
import AiMoment from "./AiMoment.jsx";
import { DOCTOR } from "./DoctorActions";
import { stripMoments } from "./moments.js";

// The clinic strip check: a photo of the strips first, typing as the quiet way out (R11). A photo that reads nothing says so in the fault line.
export default function StripPhoto({ view, busy, upload, act }) {
  const [typing, setTyping] = useState(false);
  const [lines, setLines] = useState("");
  const { strips, nudges } = stripMoments(view);
  const episodeId = view.episode?.id;

  async function pick(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await upload("/strips/photo", file, { by: DOCTOR });
  }

  return (
    <section className="card" aria-label="Photo of strips">
      <label className="field">
        Photo of strips
        <input type="file" accept="image/*" capture="environment" disabled={busy} onChange={pick} />
      </label>
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
