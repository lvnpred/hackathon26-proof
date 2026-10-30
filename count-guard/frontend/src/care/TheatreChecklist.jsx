import { useState } from "react";
import TheatrePanel from "./TheatrePanel";
import { canRecord, checklistState, theatreSteps } from "./theatre";
import VideoCheck from "./VideoCheck";

const NURSE = "Nurse Asha (synthetic)";
const DOCTOR = "Dr. A. Rao (synthetic)";

function Line({ step }) {
  const parts = [step.title, step.at, step.says].filter(Boolean);
  return <p className="step-line">✓ {parts.join(" · ")}</p>;
}

// The controls inside an expanded step. The doctor reads tray and count; the nurse does all four.
function Controls({ step, role, view, episodeId, busy, act, upload, replaced, onNote, by }) {
  const nurse = role === "nurse";
  if (step.key === "tray") {
    return nurse
      ? <VideoCheck title="Tray check" kind="tray" episodeId={episodeId} check={view.tray?.latest} busy={busy} onFile={(file) => upload("/video", file, { check: "tray", by })} />
      : <p className="small muted">The theatre nurse records the tray check.</p>;
  }
  if (step.key === "count") {
    return nurse
      ? <TheatrePanel episodeId={episodeId} view={view} busy={busy} act={act} replaced={replaced} onNote={onNote} />
      : <p className="small muted">The theatre nurse records the swab count.</p>;
  }
  const began = step.key === "began";
  return (
    <button type="button" disabled={busy} onClick={() => act("/surgery", { step: began ? "began" : "ended", by })}>
      {step.title}
    </button>
  );
}

// One vertical list of the four theatre steps: done ones fold to a line, the current one opens.
export default function TheatreChecklist({ role, view, episodeId, busy, act, upload, replaced }) {
  const [note, setNote] = useState("");
  const by = role === "nurse" ? NURSE : DOCTOR;
  const steps = checklistState(theatreSteps(view));
  const ended = steps[3].done;
  const move = (view.allowed || []).find((m) => m.to === "ward");
  const surgeonMoves = move?.role === "doctor";
  const flagged = view.tray?.latest?.match === "mismatch";
  return (
    <section className="card" aria-label="Theatre steps">
      <ol className="checklist">
        {steps.map((step) => (
          <li key={step.key} className={`step ${step.status}`}>
            {(step.status === "done" || step.status === "open") && <Line step={step} />}
            {!step.done && !canRecord(view, step.key) && <p className="step-line muted">{step.title} · {step.wait}</p>}
            {step.key === "tray" && step.done && flagged && !canRecord(view, "tray") && (
              <VideoCheck title="Tray check" kind="tray" episodeId={episodeId} check={view.tray.latest} busy={busy} hideUpload onFile={() => {}} />
            )}
            {canRecord(view, step.key) && (
              <Controls step={step} role={role} view={view} episodeId={episodeId} busy={busy} act={act} upload={upload} replaced={replaced} onNote={setNote} by={by} />
            )}
          </li>
        ))}
      </ol>
      {note && <p className="note" role="status">{note}</p>}
      {role === "nurse" && (surgeonMoves ? (
        <p className="note" role="status">The count is open: the surgeon records the reason before the patient leaves theatre.</p>
      ) : (
        <>
          {move && (move.needs || []).length > 0 && <p className="small muted">Needs: {move.needs.join(", ")}</p>}
          <div className="row">
            <button type="button" className="primary" disabled={busy || !ended} onClick={() => act("/state", { to: "ward", by, reason: "", checklist: {} })}>
              Back to ward
            </button>
            {!ended && <span className="small muted">after step 4</span>}
          </div>
        </>
      ))}
    </section>
  );
}
