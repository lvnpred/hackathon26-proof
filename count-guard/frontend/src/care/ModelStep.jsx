import { stepText } from "./modelStep.js";

export { useModelStep } from "./useModelStep.js";

// One line for one model step (spec §4.1), inside the card that started it. Idle shows nothing.
// Staff see the model name here (and in the Expand view); the patient lens never does.
// Demo-scan contract (scripts/demo/scan.mjs): model names may appear on a staff screen only (1) inside this
// `.model-step` while its text is a step line ("Checking with SAM 3.1… 3 s", "Done · live (SAM 3.1, 2.1 s)"),
// and (2) inside an Expand view's root element while it is open, marked `data-expand="open"` (Task 4's view sets
// `data-expand="closed"` or drops the attribute when folded). Anything else naming a model fails the demo check.
export default function ModelStep({ step, lens = "staff", onRetry, onExpand }) {
  const stage = step?.stage || "idle";
  if (stage === "idle") return null;
  const text = stepText(step, { lens });
  const moving = stage === "uploading" || stage === "checking";
  return (
    <div className={`model-step stage-${stage}`} role="status" aria-live="polite">
      {stage === "recording" && <span className="dot" aria-hidden="true" />}
      {stage === "done" && <span className="tick" aria-hidden="true">✓</span>}
      <span className="text">{text}</span>
      {stage === "failed" && onRetry && (
        <button type="button" className="quiet" onClick={onRetry}>
          Retry
        </button>
      )}
      {stage === "done" && onExpand && (
        <button type="button" className="quiet" onClick={onExpand}>
          Expand
        </button>
      )}
      {moving && (
        <span className={`bar${stage === "checking" ? " indeterminate" : ""}`} aria-hidden="true">
          <span style={stage === "uploading" ? { width: `${step.percent || 0}%` } : undefined} />
        </span>
      )}
    </div>
  );
}
