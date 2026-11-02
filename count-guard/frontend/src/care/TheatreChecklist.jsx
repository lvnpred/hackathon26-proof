import { useState } from "react";
import CountPanel from "./CountPanel";
import { canRecord, checklistState, countReconciled, savedLine, theatreSteps } from "./theatre";
import VideoCheck from "./VideoCheck";
import StatusPill from "./StatusPill.jsx";
import AiMoment from "./AiMoment.jsx";
import { momentFor } from "./moments.js";
import { pickedUpload } from "./video";
import PhotoInput from "./PhotoInput.jsx";
import ProofItem from "./ProofItem.jsx";
import { checkFor } from "./verdict.js";

const NURSE = "Nurse Asha (synthetic)";
// Theatre-step photo proofs (spec §6.6). They keep only their own item open: never surgery ended, never a move.
const STEP_PROOF = { tray: ["theatre:swab_tray", "Swab tray before incision"], count: ["theatre:closing_tray", "Swab tray at closing"] };
const DOCTOR = "Dr. A. Rao (synthetic)";

function Line({ step }) {
  const parts = [step.title, step.at, step.says].filter(Boolean);
  return <p className="step-line">✓ {parts.join(" · ")}</p>;
}

// A compact way to film the tray again while the tray can still be recorded (R18).
function TrayAgain({ busy, onFile }) {
  const [problem, setProblem] = useState("");
  async function pick(files) {
    const { problem: bad, upload } = pickedUpload(files);
    setProblem(bad);
    if (upload) await onFile(upload);
  }
  return (
    <>
      <PhotoInput label="Check the tray again" accept="video/*,image/*" capture={false} multiple disabled={busy} onFiles={pick} />
      {problem && <p className="note" role="alert">{problem}</p>}
    </>
  );
}

// The controls inside an expanded step. The doctor reads tray and count; the nurse does all five.
function Controls({ step, role, view, episodeId, busy, act, upload, replaced, onNote, by, primary }) {
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
      ? <CountPanel episodeId={episodeId} view={view} busy={busy} act={act} upload={upload} replaced={replaced} onNote={onNote} primary={primary} />
      : <p className="small muted">The theatre nurse records the swab count.</p>;
  }
  if (step.key === "ward") return null; // the Back to ward button sits under the list
  const began = step.key === "began";
  return (
    <button type="button" disabled={busy} onClick={() => act("/surgery", { step: began ? "began" : "ended", by })}>
      {step.title}
    </button>
  );
}

// One vertical list of the five theatre steps: done ones fold to a line, the current one opens.
export default function TheatreChecklist({ role, view, episodeId, busy, act, upload, replaced, nowMs, primary = false }) {
  const [note, setNote] = useState("");
  const by = role === "nurse" ? NURSE : DOCTOR;
  const steps = checklistState(theatreSteps(view, nowMs));
  const ended = steps[3].done;
  const reconciled = countReconciled(view);
  const move = (view.allowed || []).find((m) => m.to === "ward");
  const surgeonMoves = move?.role === "doctor";
  const trayMoment = momentFor(view, view.tray?.latest?.id);
  return (
    <section className="card" aria-label="Theatre steps">
      <ol className="checklist">
        {steps.map((step) => (
          <li key={step.key} className={`step ${step.status}`}>
            {(step.status === "done" || step.status === "open") && <Line step={step} />}
            {step.key === "count" && step.done && !canRecord(view, "count") && (
              <p className="small" role="status">{countReconciled(view) && <StatusPill role="fine" text="Count complete" />} {savedLine(view.count)}</p>
            )}
            {!step.done && !canRecord(view, step.key) && !(step.key === "ended" && steps[1].done) && <p className="step-line muted">{step.title} · {step.wait || "Locked"}</p>}
            {step.key === "ended" && !step.done && steps[1].done && !reconciled && (
              <>
                <button type="button" disabled>Surgery ended</button>
                <p className="small muted">Surgery ended unlocks when the count is saved.</p>
              </>
            )}
            {step.key === "tray" && step.done && trayMoment && <AiMoment moment={trayMoment} role={role} episodeId={episodeId || view.episode?.id} />}
            {step.key === "ward" && role === "nurse" && (ended || surgeonMoves) && (surgeonMoves ? (
              <p className="note" role="status">The count is open: the surgeon records the reason before the patient leaves theatre.</p>
            ) : (
              <>
                {move && (move.needs || []).length > 0 && <p className="small muted">Needs: {move.needs.join(", ")}</p>}
                <button type="button" className={primary ? "primary" : undefined} disabled={busy} onClick={() => act("/state", { to: "ward", by, reason: "", checklist: {} })}>
                  Back to ward
                </button>
              </>
            ))}
            {canRecord(view, step.key) && step.key !== "ward" && (
              <Controls step={step} role={role} view={view} episodeId={episodeId} busy={busy} act={act} upload={upload} replaced={replaced} onNote={setNote} by={by} primary={primary} />
            )}
            {role === "nurse" && STEP_PROOF[step.key] && canRecord(view, step.key) && (
              <ProofItem check={checkFor(view, STEP_PROOF[step.key][0])} label={STEP_PROOF[step.key][1]} busy={busy}
                onPhoto={(file) => upload(`/checks/${STEP_PROOF[step.key][0]}/photo`, file, { by })}
                onOverride={(reason) => act(`/checks/${STEP_PROOF[step.key][0]}/override`, { reason, by })} />
            )}
          </li>
        ))}
      </ol>
      {note && <p className="note" role="status">{note}</p>}
    </section>
  );
}
