import { useCallback, useState } from "react";
import { stepText } from "./modelStep.js";
import { ModelExpand } from "./ModelExpand.jsx";

export { useModelStep } from "./useModelStep.js";

// One line for one model step (spec §4.1), inside the card that started it. Idle shows nothing.
// Staff see the model name here (and in the Expand view); the patient lens never does.
// Demo-scan contract (scripts/demo/scan.mjs): model names may appear on a staff screen only (1) inside this
// `.model-step` while its text is a step line ("Checking with SAM 3.1… 3 s", "Done · live (SAM 3.1, 2.1 s)"),
// and (2) inside an Expand view's root element while it is open, marked `data-expand="open"` (Task 4's view sets
// `data-expand="closed"` or drops the attribute when folded). Anything else naming a model fails the demo check.
// `busy` (the ward's write in flight) holds Retry back so the same card cannot submit twice.
// Expand (clarity §4.2): `onExpand` opens the caller's own view; else `expand` ({ view, title }) opens ModelExpand on the
// done step's `record` (useModelStep's run(fn, { record })). The button is data-expand="closed"; the open view is "open".
export default function ModelStep({ step, lens = "staff", busy = false, onRetry, onExpand, expand }) {
  const [open, setOpen] = useState(false);
  const shut = useCallback(() => setOpen(false), []);
  const stage = step?.stage || "idle";
  if (stage === "idle") return null;
  const record = stage === "done" && step.record ? step.record : null;
  const opens = onExpand || (expand && record ? () => setOpen(true) : null);
  const text = stepText(step, { lens });
  const moving = stage === "uploading" || stage === "checking";
  return (
    <div className={`model-step stage-${stage}`} role="status" aria-live="polite">
      {stage === "recording" && <span className="dot" aria-hidden="true" />}
      {stage === "done" && <span className="tick" aria-hidden="true">✓</span>}
      <span className="text">{text}</span>
      {stage === "failed" && onRetry && (
        <button type="button" className="quiet" onClick={onRetry} disabled={busy}>
          Retry
        </button>
      )}
      {stage === "done" && opens && (
        <button type="button" className="quiet" data-expand="closed" aria-haspopup="dialog" onClick={opens}>
          Expand
        </button>
      )}
      {open && record && <ModelExpand record={record} view={expand?.view} lens={lens} title={expand?.title} onClose={shut} />}
      {moving && (
        <span className={`bar${stage === "checking" ? " indeterminate" : ""}`} aria-hidden="true">
          <span style={stage === "uploading" ? { width: `${step.percent || 0}%` } : undefined} />
        </span>
      )}
    </div>
  );
}
