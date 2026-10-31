import { useState } from "react";
import TheatrePanel from "./TheatrePanel";
import { canRecord, checklistState, theatreSteps } from "./theatre";
import VideoCheck from "./VideoCheck";
import AiMoment from "./AiMoment.jsx";
import { momentFor } from "./moments.js";
import { toUpload, videoProblem } from "./video";

const NURSE = "Nurse Asha (synthetic)";
const DOCTOR = "Dr. A. Rao (synthetic)";

function Line({ step }) {
  const parts = [step.title, step.at, step.says, step.correction].filter(Boolean);
  return <p className="step-line">✓ {parts.join(" · ")}</p>;
}

// A compact way to film the tray again while the tray can still be recorded (R18).
function TrayAgain({ busy, onFile }) {
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
    <>
      <label className="field">
        Check the tray again
        <input type="file" accept="video/*,image/*" multiple disabled={busy} onChange={pick} />
      </label>
      {problem && <p className="note" role="alert">{problem}</p>}
    </>
  );
}

// The controls inside an expanded step. The doctor reads tray and count; the nurse does all four.
function Controls({ step, role, view, episodeId, busy, act, upload, replaced, onNote, by }) {
  const nurse = role === "nurse";
  if (step.key === "tray") {
    const onFile = (file) => upload("/video", file, { check: "tray", by });
    if (!nurse) return step.done ? null : <p className="small muted">The theatre nurse records the tray check.</p>;
    return step.done
      ? <TrayAgain busy={busy} onFile={onFile} />
      : <VideoCheck title="Tray check" kind="tray" episodeId={episodeId} version={view.timeline?.length} check={null} busy={busy} onFile={onFile} />;
  }
  if (step.key === "count") {
    return nurse
      ? <TheatrePanel episodeId={episodeId} view={view} busy={busy} act={act} upload={upload} replaced={replaced} onNote={onNote} />
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
  const trayMoment = momentFor(view, view.tray?.latest?.id);
  return (
    <section className="card" aria-label="Theatre steps">
      <ol className="checklist">
        {steps.map((step) => (
          <li key={step.key} className={`step ${step.status}`}>
            {(step.status === "done" || step.status === "open") && <Line step={step} />}
            {!step.done && !canRecord(view, step.key) && <p className="step-line muted">{step.title} · {step.wait}</p>}
            {step.key === "tray" && step.done && trayMoment && <AiMoment moment={trayMoment} role={role} episodeId={episodeId || view.episode?.id} />}
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
