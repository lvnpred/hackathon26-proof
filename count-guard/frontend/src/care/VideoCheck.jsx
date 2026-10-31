import { chipFor } from "./moments.js";
import { checkLabel, toUpload, videoProblem } from "./video";
import { useState } from "react";
import { Evidence } from "./Evidence.jsx";
import { seenCell } from "./evidence.js";

const DROP_LABEL = { tray: "Upload tray video or photos", swabs: "Upload a clip or photos of the returned swabs" };

// A tray, set-up or swab clip: pick it, and the result shows beside the planned list. A flag never blocks.
export default function VideoCheck({ title, kind, check, busy, onFile, hideUpload = false, step = "", episodeId, version = 0, moment = null }) {
  const [problem, setProblem] = useState("");
  async function pick(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    const bad = videoProblem(files);
    setProblem(bad);
    if (!bad) await onFile(toUpload(files));
  }
  return (
    <section className="card" aria-label={title}>
      <p className="label">{step && `${step} `}{title}</p>
      {!hideUpload && (
        <label className={kind === "setup" ? "field" : "field drop-zone"}>
          {DROP_LABEL[kind] || "Add video or photo check"}
          <input type="file" accept="video/*,image/*" multiple disabled={busy} onChange={pick} />
        </label>
      )}
      {problem && <p className="note" role="alert">{problem}</p>}
      {check && <CheckResult check={check} episodeId={episodeId} version={version} moment={moment} />}
    </section>
  );
}

function CheckResult({ check, episodeId, version, moment }) {
  const proved = Boolean(check.evidence_id && episodeId);
  return (
    <div>
      <p className="small">
        <span className={`pill ${check.match === "mismatch" ? "sun" : "info"}`}>{checkLabel(check)}</span>{" "}
        {moment && <><span className="chip">{chipFor(moment)}</span>{" "}</>}{check.why}
      </p>
      {proved && <Evidence episodeId={episodeId} evidenceId={check.evidence_id} check={check} version={version} />}
      {!proved && (check.rows || []).length > 0 && (
        <table className="small">
          <thead><tr><th>Item</th><th>Planned</th><th>Seen</th></tr></thead>
          <tbody>
            {check.rows.map((row) => (
              <tr key={row.concept}>
                <td>{(row.names || [row.concept]).join(", ")}</td>
                <td>{row.planned}</td>
                <td>{seenCell(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(check.unchecked || []).length > 0 && <p className="small muted">Not checked here: {check.unchecked.join(", ")}</p>}
      {!proved && (check.frames || []).length > 0 && (
        <div className="row">
          {check.frames.map((frame) => (
            <img key={frame.id} src={frame.url} alt={check.media === "photos" ? "Photo from the check" : "Frame from the clip"} width={96} style={{ borderRadius: 6 }} />
          ))}
        </div>
      )}
    </div>
  );
}

// What Send to theatre confirms: the instruments, the swab total, and where the list comes from.
export function TrayPreview({ plan }) {
  if (!plan) return null;
  return (
    <div>
      <p className="small">{plan.title}</p>
      <ul className="small">
        {(plan.instruments || []).map((item) => <li key={item.name}>{item.name} x {item.qty}</li>)}
      </ul>
      <p className="small">Swabs: {plan.swab_total}</p>
      {plan.note && <p className="small muted">{plan.note}</p>}
      {(plan.sources || []).length > 0 && (
        <p className="small muted">
          Sources: {plan.sources.map((s, i) => (
            <span key={s.id}>{i > 0 && ", "}<a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></span>
          ))}
        </p>
      )}
      <p className="small muted">Sending to theatre confirms this tray plan.</p>
    </div>
  );
}
